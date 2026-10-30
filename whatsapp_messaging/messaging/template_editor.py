"""Reusable content and explicit Meta review actions, separate from campaigns."""
import json
import re
from datetime import timedelta

import frappe
import requests
from frappe.utils import get_datetime

from whatsapp_messaging.send_security import require_outbound_enabled, require_send_role
from whatsapp_messaging.template_security import PLACEHOLDER, SAFE_TEMPLATE_FIELDS
from whatsapp_messaging.utils.config import get_headers
from .common import account, digest, parsed, require_supervisor, utcnow
from . import template_framing as framing

META = 'Meta-approved template'
LOCAL = 'Local message'
DOCT = 'WhatsApp Message Template'
INTERNAL = ('meta_submission_state', 'meta_submission_key', 'meta_submission_hash', 'meta_submission_at',
    'meta_action_error', 'legacy_message_text')
STATUS_LABELS = {'APPROVED':'Approved', 'PENDING':'In review', 'REJECTED':'Rejected',
    'PAUSED':'Paused', 'DISABLED':'Disabled', 'UNAVAILABLE':'Unavailable', 'ARCHIVED':'Archived',
    'PENDING_DELETION':'Pending deletion', 'DELETED':'Deleted'}
REVIEW_URL = 'https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review'
FIXES = {
    'INVALID_FORMAT':'Check variable braces, keep variables sequential, separate them with descriptive text, and do not start or end the message with a variable. Provide a fictional review example for every variable.',
    'INCORRECT_CATEGORY':'Choose the category that matches the message. Use Utility for a specific transaction or requested update; use Marketing for promotional content. Then submit the corrected version.',
    'TAG_CONTENT_MISMATCH':'Review the category and remove unrelated promotional wording from a Utility message, or choose Marketing when appropriate. Then resubmit.',
    'ABUSIVE_CONTENT':'Review the wording against WhatsApp policies. Remove abusive, threatening or prohibited content before resubmitting.',
    'PROMOTIONAL':'Review the message purpose and category against WhatsApp policies. Correct the content and category before resubmitting.',
    'SCAM':'Remove misleading claims and clearly identify the business and purpose. Review WhatsApp policies before resubmitting.',
    'DUPLICATE':'Import the existing template instead of submitting duplicate wording. If this is a different message, revise its actual content before submitting.',
}


def clean_detail(value, sender=None, limit=2000):
    """Bound plain provider explanations; never retain credentials or HTML."""
    value = str(value or '')
    if sender:
        token = sender.get_password('access_token', raise_exception=False)
        if token:
            value = value.replace(token, '[redacted]')
    value = re.sub(r'Bearer\s+\S+|EAA[A-Za-z0-9_-]{20,}', '[redacted]', value, flags=re.I)
    return frappe.utils.strip_html(value)[:limit]


def allowed_paths(doc):
    from .field_policy import editor_fields
    result = {'self.' + field for field in SAFE_TEMPLATE_FIELDS}
    for group in editor_fields(doc.template_doctype):
        result.update(group['section'] + '.' + field['value'] for field in group['fields'])
    return result


def variable_paths(doc):
    tokens = [m.group(1).strip() for m in PLACEHOLDER.finditer(doc.message_preview or '')]
    if tokens and all(token.isdigit() for token in tokens):
        positions = sorted({int(token) for token in tokens})
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError('Numbered variables must start at 1 and be sequential.')
        rows = {int(row.position or row.idx):row for row in (doc.meta_examples or [])}
        return [rows[i].source_path if i in rows else '' for i in positions], True
    if any(token.isdigit() for token in tokens):
        raise ValueError('Use either inserted fields or numbered variables, not both in the same message.')
    return list(dict.fromkeys(tokens)), False


def sync_variables(doc):
    try:
        paths, numbered = variable_paths(doc)
    except ValueError:
        return  # Drafts can be incomplete; Submit and Send validate strictly.
    previous = list(doc.meta_examples or [])
    rows = []
    for i, path in enumerate(paths, 1):
        old = next((r for r in previous if (int(r.position or r.idx) == i if numbered else r.source_path == path)), None)
        values = dict(position=i, source_path=path, sample_value=old.sample_value if old else '')
        if old and not old.is_new():
            values['name'] = old.name
        rows.append(values)
    doc.set('meta_examples', rows)


def compile_content(doc, *, check_permissions=True, examples=False):
    if examples and doc.approved_template:
        linked = linked_template(doc)
        if linked and framing.document_header(parsed(linked.components_json, [])):
            raise ValueError('Manage document-header wording in WhatsApp Manager, then sync the Sender. Use Document Delivery Rules to map each record and PDF.')
    body = doc.message_preview or ''
    if not body.strip():
        raise ValueError('Write the message before submitting it to Meta.')
    if doc.media:
        raise ValueError('Meta submission supports a text body with optional text header and footer. Remove Media to use this mode.')
    paths, numbered = variable_paths(doc)
    if any(not path for path in paths):
        raise ValueError('Choose a Source Field for every numbered variable in Variables & Review Examples.')
    if check_permissions:
        permitted = allowed_paths(doc)
        if any(path not in permitted for path in paths):
            raise ValueError('A message variable is not approved or readable. Choose an available field from Insert field.')
    if not numbered:
        body = PLACEHOLDER.sub(lambda m:'{{' + str(paths.index(m.group(1).strip()) + 1) + '}}', body)
    else:
        body = PLACEHOLDER.sub(lambda m:'{{' + str(int(m.group(1).strip())) + '}}', body)
    if '{{' in re.sub(r'\{\{\d+\}\}', '', body) or '}}' in re.sub(r'\{\{\d+\}\}', '', body):
        raise ValueError('The message has mismatched variable braces. Use Insert field to add variables.')
    if len(body) > 1024:
        raise ValueError('Meta template body text must be at most 1,024 characters.')
    header, footer = framing.validate(doc.get('meta_header'), doc.meta_footer)
    component = {'type':'BODY', 'text':body}
    if examples:
        if re.match(r'^\s*\{\{\d+\}\}', body) or re.search(r'\{\{\d+\}\}\s*$', body):
            raise ValueError('Add descriptive text before the first variable and after the last variable.')
        if re.search(r'\{\{\d+\}\}\s*\{\{\d+\}\}', body):
            raise ValueError('Separate adjacent variables with descriptive text.')
        rows = {int(row.position or row.idx):row for row in (doc.meta_examples or [])}
        values = [rows[i].sample_value if i in rows else '' for i in range(1, len(paths) + 1)]
        if any(not str(value or '').strip() or len(value) > 1024 for value in values):
            raise ValueError('Enter a fictional Review Example for every variable, up to 1,024 characters each.')
        if values:
            component['example'] = {'body_text':[values]}
    components = ([{'type':'HEADER', 'format':'TEXT', 'text':header}] if header else []) + [component]
    if footer:
        components.append({'type':'FOOTER', 'text':footer})
    return body, paths, components


def linked_template(doc):
    if doc.approved_template and frappe.db.exists('WhatsApp Approved Template', doc.approved_template):
        return frappe.get_doc('WhatsApp Approved Template', doc.approved_template)


def matches(doc, linked):
    if not linked or not linked.supported:
        return False
    try:
        body, _, components = compile_content(doc, check_permissions=False)
    except ValueError:
        return False
    header, footer = framing.texts(parsed(linked.components_json, []))
    return (body == (linked.body or '') and (doc.meta_footer or '') == footer and (doc.get('meta_header') or '') == header
        and doc.meta_template_name == linked.template_name and doc.meta_language == linked.language
        and frappe.db.get_value('WhatsApp Phone Number ID', doc.phone_number_id, 'waba_id') == linked.waba_id)


def review_values(doc):
    values = dict(meta_provider_id=None, meta_rejection_reason=None, meta_rejection_detail=None,
        meta_recommendation=None, meta_fix_guidance=None, meta_checked_on=None, meta_status='Draft')
    linked = linked_template(doc)
    if doc.delivery_mode != META:
        values['meta_status'] = 'Not requested'
        return values
    if linked:
        values.update(meta_provider_id=linked.provider_template_id, meta_checked_on=linked.synced_at,
            meta_rejection_reason=linked.rejection_reason, meta_rejection_detail=linked.rejection_detail,
            meta_recommendation=linked.recommendation)
        status = STATUS_LABELS.get(linked.approval_status, linked.approval_status or 'Not available')
        if not linked.supported:
            status = 'Unsupported content'
        elif not matches(doc, linked):
            status = 'Changes not submitted'
        values['meta_status'] = status
        if linked.approval_status == 'REJECTED':
            values['meta_fix_guidance'] = FIXES.get(linked.rejection_reason,
                'Meta has not provided a specific fix. Review the reason in WhatsApp Manager or Business Support Home, correct the message, then resubmit. Approval is decided by Meta.')
            if not linked.rejection_detail and not linked.rejection_reason:
                values['meta_rejection_detail'] = 'Meta reported rejection without a detailed reason. Open WhatsApp Manager or Business Support Home for more information.'
    if doc.meta_submission_state in ('Submitting', 'Unknown'):
        values['meta_status'] = 'Submitting' if doc.meta_submission_state == 'Submitting' else 'Check submission outcome'
    return values


def prepare(doc):
    previous = doc.get_doc_before_save()
    for field in INTERNAL:
        doc.set(field, previous.get(field) if previous else None)
    if not doc.delivery_mode:
        doc.delivery_mode = META if doc.approved_template else LOCAL
    if doc.delivery_mode == LOCAL and previous and previous.delivery_mode == META:
        doc.approved_template = None
    if doc.delivery_mode == META:
        sync_variables(doc)
    doc.update(review_values(doc))


def ensure_sendable(doc):
    linked = linked_template(doc)
    if not linked or linked.approval_status != 'APPROVED' or not matches(doc, linked):
        frappe.throw('This message is not approved for the current content and sender. Check Meta Approval on the template form.')
    try:
        _, paths, _ = compile_content(doc)
    except ValueError as exc:
        frappe.throw(str(exc))
    return paths


def get_editor(name, *, lock=False, supervisor=False):
    require_supervisor() if supervisor else require_send_role()
    doc = frappe.get_doc(DOCT, name, for_update=lock)
    doc.check_permission('write')
    return doc


def api_url(sender, resource=None):
    if not re.fullmatch(r'[0-9]+', sender.waba_id or ''):
        frappe.throw('Enter the Sender’s WABA ID before submitting or syncing templates.')
    version = frappe.db.get_single_value('WhatsApp Settings', 'whatsapp_api_version')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+', version or ''):
        frappe.throw('Configure a valid WhatsApp API version.')
    if resource and not re.fullmatch(r'[0-9]+', str(resource)):
        frappe.throw('Invalid Meta template identifier.')
    return f'https://graph.facebook.com/{version}/' + (str(resource) if resource else sender.waba_id + '/message_templates')


def action_error(response, sender):
    try:
        error = response.json().get('error', {})
    except (ValueError, AttributeError):
        error = {}
    code = str(error.get('code', ''))
    if code == '190':
        return 'The Sender access token is invalid or expired. Update it, then retry.'
    if code in ('10', '200'):
        return 'The Sender token needs whatsapp_business_management access to this WABA. Correct its permissions, then retry.'
    detail = error.get('error_user_msg') or error.get('message') or 'Meta did not provide a detailed error.'
    return clean_detail(f'Meta could not accept the request (HTTP {response.status_code}, code {code}). {detail}', sender)


@frappe.whitelist(methods=['POST'])
def submit(name):
    """Explicit user action only. Saving a local draft never invokes Meta."""
    doc = get_editor(name, lock=True, supervisor=True)
    if doc.delivery_mode != META:
        frappe.throw('Choose Meta-approved template mode first.')
    if doc.meta_submission_state in ('Submitting', 'Unknown'):
        frappe.throw('Check Meta Status before submitting again; the previous request may already have reached Meta.')
    require_outbound_enabled()
    sender = account(doc.phone_number_id, enabled=True)
    try:
        body, paths, components = compile_content(doc, examples=True)
    except ValueError as exc:
        frappe.throw(str(exc))
    if not re.fullmatch(r'[a-z0-9_]{1,512}', doc.meta_template_name or ''):
        frappe.throw('Meta Template Name must contain only lowercase letters, numbers and underscores, up to 512 characters.')
    if not re.fullmatch(r'[a-z]{2,3}(?:_[A-Z]{2})?', doc.meta_language or ''):
        frappe.throw('Enter a Meta language code, such as en_US or te.')
    if doc.meta_category not in ('UTILITY', 'MARKETING'):
        frappe.throw('Choose Utility or Marketing for a text-body template.')
    linked = linked_template(doc)
    same = linked and linked.waba_id == sender.waba_id and linked.template_name == doc.meta_template_name and linked.language == doc.meta_language
    if same and (not linked.supported or linked.approval_status not in ('APPROVED','REJECTED','PAUSED')):
        frappe.throw('This Meta template cannot be edited in its current status or format. Check its status first.')
    if same and linked.approval_status == 'APPROVED' and linked.category != doc.meta_category:
        frappe.throw('Meta does not allow changing an approved template’s category. Use a new Meta Template Name for a different category.')
    url = api_url(sender, linked.provider_template_id if same else None)
    payload = {'components':components}
    if not same:
        payload.update(name=doc.meta_template_name, language=doc.meta_language, category=doc.meta_category, parameter_format='POSITIONAL')
    elif linked.approval_status != 'APPROVED':
        payload['category'] = doc.meta_category
    key = frappe.generate_hash(length=20)
    fingerprint = digest(sender.waba_id, doc.meta_template_name, doc.meta_language, payload)
    frappe.db.set_value(DOCT, name, dict(meta_submission_state='Submitting', meta_submission_key=key,
        meta_submission_hash=fingerprint, meta_submission_at=utcnow(), meta_action_error=None), update_modified=False)
    frappe.db.commit()  # Persist uncertainty before a request can reach Meta.
    request_started = False
    try:
        require_outbound_enabled()
        sender = account(sender.name, enabled=True)
        request_started = True
        response = requests.post(url, headers=get_headers(sender.name), json=payload, timeout=(5,30), allow_redirects=False)
        if response.status_code >= 300:
            return finish_action(name, key, 'Failed', action_error(response, sender))
        result = response.json()
        provider_id = linked.provider_template_id if same else str(result.get('id') or '')
        if not re.fullmatch(r'[0-9]+', provider_id) or (same and result.get('success') is not True and not result.get('id')):
            raise ValueError('Uncertain provider result')
        from .catalogue import upsert
        item = dict(id=provider_id, name=doc.meta_template_name, language=doc.meta_language,
            category=result.get('category') or doc.meta_category, status=result.get('status') or 'PENDING',
            components=components, parameter_format='POSITIONAL')
        catalogue_name = upsert(sender.waba_id, item)
        current = get_editor(name, lock=True, supervisor=True)
        if (current.delivery_mode == META and current.phone_number_id == doc.phone_number_id
                and current.meta_template_name == doc.meta_template_name and current.meta_language == doc.meta_language):
            frappe.db.set_value(DOCT, name, 'approved_template', catalogue_name)
        return finish_action(name, key, 'Idle', None)
    except (frappe.PermissionError, frappe.ValidationError):
        frappe.db.rollback()
        return finish_action(name, key, 'Unknown' if request_started else 'Failed',
            'The Sender, permissions or Outbound Requests changed. Check Meta Status and the account settings before retrying.')
    except Exception:
        frappe.db.rollback()
        return finish_action(name, key, 'Unknown', 'The submission outcome is uncertain. Choose Check Meta Status before trying again; Meta may have received the request.')


def finish_action(name, key, state, error):
    doc = frappe.get_doc(DOCT, name, for_update=True)
    if doc.meta_submission_key == key:
        frappe.db.set_value(DOCT, name, dict(meta_submission_state=state, meta_action_error=error), update_modified=False)
        doc.reload()
        frappe.db.set_value(DOCT, name, review_values(doc), update_modified=False)
        frappe.db.commit()
    return {'status':state, 'message':error}


@frappe.whitelist(methods=['POST'])
def refresh_status(name):
    doc = get_editor(name, supervisor=True)
    from .catalogue import sync
    sync(doc.phone_number_id)
    current = get_editor(name, lock=True, supervisor=True)
    if any(current.get(field) != doc.get(field) for field in ('delivery_mode','phone_number_id','meta_template_name','meta_language')):
        frappe.throw('The template identity changed during the status check. Save and check its status again.')
    doc = current
    sender = account(doc.phone_number_id)
    found = frappe.db.get_value('WhatsApp Approved Template', dict(waba_id=sender.waba_id,
        template_name=doc.meta_template_name, language=doc.meta_language), 'name')
    values = {'meta_checked_on':utcnow()}
    if found:
        values.update(approved_template=found, meta_submission_state='Idle', meta_action_error=None)
    elif doc.meta_submission_state in ('Submitting','Unknown'):
        # A complete sync plus a cooling-off period permits a deliberate retry.
        # It never retries automatically; creation uses the same unique Meta name.
        if doc.meta_submission_at and get_datetime(doc.meta_submission_at) < utcnow() - timedelta(minutes=10):
            values.update(meta_submission_state='Failed', meta_action_error='Meta returned no matching template after the waiting period. Check WhatsApp Manager, then choose Submit to Meta if it is still absent. No request has been resent.')
        else:
            values.update(meta_action_error='Meta has not returned a matching template yet. Check WhatsApp Manager and check status again after 10 minutes before retrying an uncertain submission.')
    frappe.db.set_value(DOCT, name, values, update_modified=bool(found and doc.approved_template != found))
    doc.reload()
    frappe.db.set_value(DOCT, name, review_values(doc), update_modified=False)
    return {'found':bool(found)}


@frappe.whitelist()
def import_options(account_name):
    sender = account(account_name)
    return frappe.get_list('WhatsApp Approved Template', filters={'waba_id':sender.waba_id},
        fields=['name','template_name','language','approval_status'], order_by='template_name asc', limit_page_length=500)


@frappe.whitelist()
def import_content(name, catalogue_name):
    doc = get_editor(name)
    linked = frappe.get_doc('WhatsApp Approved Template', catalogue_name)
    linked.check_permission('read')
    sender = account(doc.phone_number_id)
    if linked.waba_id != sender.waba_id:
        frappe.throw('Choose a Meta template belonging to this Sender’s WABA.')
    if not linked.supported:
        frappe.throw('This editor supports a text body with optional fixed text header and footer. Media headers, header variables and buttons are not supported.')
    header, footer = framing.texts(parsed(linked.components_json, []))
    mappings = parsed(doc.parameter_fields, [])
    return dict(delivery_mode=META, approved_template=linked.name, message_preview=linked.body,
        meta_template_name=linked.template_name, meta_language=linked.language, meta_category=linked.category,
        meta_header=header, meta_footer=footer, meta_examples=[dict(position=i,source_path=('template_doctype.' + mappings[i-1]) if len(mappings)>=i else '',sample_value='')
            for i in range(1,len(parsed(linked.parameters_json,[]))+1)])


def refresh_related(catalogue_name):
    for name in frappe.get_all(DOCT, filters={'approved_template':catalogue_name}, pluck='name'):
        doc = frappe.get_doc(DOCT, name)
        frappe.db.set_value(DOCT, name, review_values(doc), update_modified=False)


def backfill():
    """Preserve rule names, execution users, timestamps and the old unused text."""
    for name in frappe.get_all(DOCT, pluck='name'):
        doc = frappe.get_doc(DOCT, name)
        if doc.delivery_mode and not (doc.approved_template and not doc.meta_template_name):
            if doc.delivery_mode == LOCAL:
                frappe.db.set_value(DOCT, name, review_values(doc), update_modified=False)
            continue
        values = {'delivery_mode':LOCAL}
        linked = linked_template(doc)
        if linked:
            mappings = parsed(doc.parameter_fields, [])
            body = linked.body or ''
            if linked.supported:
                for i, field in enumerate(mappings, 1):
                    body = re.sub(r'\{\{\s*' + str(i) + r'\s*\}\}', '{{template_doctype.' + field + '}}', body)
            values.update(delivery_mode=META, meta_template_name=linked.template_name, meta_language=linked.language,
                meta_category=linked.category, legacy_message_text=doc.message_preview, message_preview=body,
                meta_header=framing.texts(parsed(linked.components_json,[]))[0],
                meta_footer=next((c.get('text','') for c in parsed(linked.components_json,[]) if c.get('type')=='FOOTER'), ''))
        doc.update(values)
        values.update(review_values(doc))
        frappe.db.set_value(DOCT, name, values, update_modified=False)
