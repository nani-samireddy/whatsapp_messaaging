"""Select Meta catalogue entries and create inactive, reusable local content."""
import json

import frappe

from . import catalogue, template_editor as editor, template_framing as framing
from .common import account, digest, parsed, require_supervisor


def existing_templates(sender):
    # A second Sender in the same WABA must not duplicate the same content.
    senders = frappe.get_all('WhatsApp Phone Number ID', filters={'waba_id':sender.waba_id}, pluck='name')
    return frappe.get_all(editor.DOCT, filters={
        'phone_number_id': ['in', senders], 'delivery_mode': editor.META},
        fields=['name', 'approved_template', 'meta_template_name', 'meta_language'],
        order_by='creation asc', limit_page_length=0)


def existing(sender, linked, templates=None):
    return next((row.name for row in (existing_templates(sender) if templates is None else templates)
        if row.approved_template == linked.name or (
            row.meta_template_name == linked.template_name and row.meta_language == linked.language)), None)


def unavailable_reason(linked):
    if linked.approval_status in ('UNAVAILABLE', 'DELETED', 'PENDING_DELETION', 'ARCHIVED'):
        return 'This template is no longer available from Meta.'
    if not linked.supported or linked.category not in ('UTILITY', 'MARKETING'):
        return 'Unsupported format. Use a text body with numbered variables and an optional fixed text header or PDF document header. Video/image headers, header variables, buttons and named variables are not supported.'
    return ''


@frappe.whitelist()
def options(account_name):
    require_supervisor()
    sender = account(account_name, enabled=True)
    rows = []
    templates = existing_templates(sender)
    for linked in frappe.get_list('WhatsApp Approved Template', filters={'waba_id':sender.waba_id},
            fields=['name', 'template_name', 'language', 'approval_status', 'category', 'supported',
                'body', 'components_json', 'parameters_json'], order_by='template_name asc, language asc', limit_page_length=0):
        local_name = existing(sender, linked, templates)
        readable_name = local_name if local_name and frappe.has_permission(editor.DOCT, 'read', doc=local_name) else None
        reason = 'Already imported. Existing content will be preserved.' if local_name else unavailable_reason(linked)
        header, footer = framing.texts(parsed(linked.components_json, []))
        rows.append(dict(name=linked.name, template_name=linked.template_name, language=linked.language,
            status=linked.approval_status, category=linked.category, body=linked.body, header=header, footer=footer,
            variable_count=len(parsed(linked.parameters_json, [])), existing=readable_name,
            can_import=not bool(reason), reason=reason))
    return rows


@frappe.whitelist(methods=['POST'])
def sync_options(account_name):
    result = catalogue.sync(account_name)
    return dict(**result, templates=options(account_name))


@frappe.whitelist(methods=['POST'])
def import_selected(account_name, source_doctype, catalogue_names):
    require_supervisor()
    sender = account(account_name, enabled=True)
    if not frappe.has_permission(editor.DOCT, 'create'):
        frappe.throw('You cannot create message templates.', frappe.PermissionError)
    if not isinstance(source_doctype, str) or not frappe.db.exists('DocType', source_doctype):
        frappe.throw('Choose a Source DocType for the imported templates.')
    from whatsapp_messaging.utils import _check_metadata_permission
    _check_metadata_permission(source_doctype)
    try:
        names = json.loads(catalogue_names) if isinstance(catalogue_names, str) else catalogue_names
    except (TypeError, ValueError):
        frappe.throw('Choose templates from the import list.')
    if not isinstance(names, list) or not names or len(names) > 100 or any(not isinstance(n, str) or not n for n in names):
        frappe.throw('Select between 1 and 100 templates to import.')
    # Stable lock order makes concurrent imports idempotent across Senders.
    linked_docs = []
    for name in sorted(set(names)):
        linked = frappe.get_doc('WhatsApp Approved Template', name, for_update=True)
        linked.check_permission('read')
        if linked.waba_id != sender.waba_id:
            frappe.throw('Choose templates belonging to this Sender’s WABA.')
        if not existing(sender, linked) and unavailable_reason(linked):
            frappe.throw(unavailable_reason(linked))
        linked_docs.append(linked)
    result = dict(imported=[], existing=[])
    for linked in linked_docs:
        local_name = existing(sender, linked)
        if local_name:
            result['existing'].append(local_name if frappe.has_permission(editor.DOCT, 'read', doc=local_name) else None)
            continue
        title = f'Meta - {linked.template_name.replace("_", " ").title()[:95]} - {linked.language}'
        if frappe.db.exists(editor.DOCT, title):
            title += ' - ' + digest(sender.waba_id, linked.name)[:8]
        if frappe.db.exists(editor.DOCT, title):
            title += ' - ' + frappe.generate_hash(length=6)
        header, footer = framing.texts(parsed(linked.components_json, []))
        doc = frappe.get_doc(dict(doctype=editor.DOCT, template_name=title,
            phone_number_id=sender.name, template_doctype=source_doctype, delivery_mode=editor.META,
            approved_template=linked.name, meta_template_name=linked.template_name, meta_language=linked.language,
            meta_category=linked.category, message_preview=linked.body, meta_header=header, meta_footer=footer,
            disable=1, automation_active=0,
            meta_examples=[dict(position=i, source_path='', sample_value='')
                for i in range(1, len(parsed(linked.parameters_json, [])) + 1)])).insert()
        result['imported'].append(dict(name=doc.name, variables=len(doc.meta_examples)))
    return result
