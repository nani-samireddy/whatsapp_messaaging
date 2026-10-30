"""Generic record-to-private-PDF rules using the canonical WhatsApp outbox."""
import re
from contextlib import contextmanager

import frappe
from frappe.utils import get_datetime

from .common import account, as_user, digest, parsed, require_supervisor, utcnow
from .field_policy import eligible
from .template_framing import document_header

RULE = 'WhatsApp Document Rule'
DELIVERY = 'WhatsApp Document Delivery'
EVENTS = {'Record created':'after_insert', 'Field changes to a value':'on_update', 'Document submitted':'on_submit'}
TEXT_TRIGGER_TYPES = {'Text', 'Small Text', 'Long Text'}
TRIGGER_TYPES = {'Select', 'Check', 'Data', 'Int'} | TEXT_TRIGGER_TYPES
INTERNAL_SOURCES = {'File','Version','Error Log','Scheduled Job Log','DocType','DocField','DocPerm',
    'Custom Field','User','Role','Role Profile','Scheduled Job Type','DocShare','Session Default'}


@contextmanager
def service():
    previous = frappe.flags.get('whatsapp_document_service')
    frappe.flags.whatsapp_document_service = True
    try:
        yield
    finally:
        frappe.flags.whatsapp_document_service = previous


def update(name, **values):
    with service():
        frappe.db.set_value(DELIVERY, name, values)


def source_meta(rule):
    meta = frappe.get_meta(rule.source_doctype)
    if meta.istable or meta.issingle or meta.is_virtual or rule.source_doctype.startswith('WhatsApp') or rule.source_doctype in INTERNAL_SOURCES:
        frappe.throw('Choose a normal business record type, not a child, settings or messaging record.')
    if not frappe.has_permission(rule.source_doctype, 'read'):
        frappe.throw('You cannot read this record type.', frappe.PermissionError)
    return meta


def approved_field(meta, name, types=None):
    field = meta.get_field(name or '')
    if not field or field.hidden or field.print_hide or (types and field.fieldtype not in types):
        frappe.throw('Choose an available field from the field picker.')
    if field.fieldname not in meta.get_permitted_fieldnames(permission_type='read'):
        frappe.throw('The selected field is not readable.', frappe.PermissionError)
    return field


def recipient_meta(rule, meta=None):
    meta = meta or source_meta(rule)
    if rule.recipient_mode == 'A linked record':
        link = approved_field(meta, rule.recipient_link_field, {'Link'})
        if not frappe.has_permission(link.options, 'read'):
            frappe.throw('You cannot read the linked recipient type.', frappe.PermissionError)
        meta = frappe.get_meta(link.options)
    return meta


def validate_rule(rule):
    require_supervisor()
    meta = source_meta(rule)
    if rule.event_type not in EVENTS:
        frappe.throw('Choose a supported trigger.')
    if rule.event_type == 'Document submitted' and not meta.is_submittable:
        frappe.throw('This record type does not use submission. Choose a field-change or creation trigger.')
    if rule.event_type == 'Field changes to a value':
        field = approved_field(meta, rule.trigger_field, TRIGGER_TYPES)
        if field.fieldtype in TEXT_TRIGGER_TYPES:
            if rule.text_match_operator not in ('Equals', 'Contains'):
                frappe.throw('Choose Equals or Contains for text matching.')
            if not str(rule.trigger_text or '').strip():
                frappe.throw('Enter comparison text that is not empty or only spaces.')
        elif not str(rule.trigger_values or '').strip():
            frappe.throw('Enter at least one value that triggers delivery.')
    if rule.document_mode == 'Generate PDF':
        fmt = frappe.get_doc('Print Format', rule.print_format) if rule.print_format else None
        if not fmt or fmt.doc_type != rule.source_doctype or fmt.disabled:
            frappe.throw('Choose an enabled print format for this record type.')
    elif rule.document_mode == 'Private attachment':
        approved_field(meta, rule.file_field, {'Attach'})
    else:
        frappe.throw('Choose a document source.')
    phone = approved_field(recipient_meta(rule, meta), rule.phone_field)
    from whatsapp_messaging.template_security import is_recipient_phone_field
    if not is_recipient_phone_field(phone):
        frappe.throw('Choose a Phone field for the recipient.')
    for row in rule.get('conditions') or []:
        field = approved_field(meta, row.fieldname_value)
        if not eligible(field) or row.expected_value is None or not str(row.expected_value).strip():
            frappe.throw('Choose a non-sensitive field and an expected value for each condition.')
    if rule.enabled:
        rule.run_as = frappe.session.user
        validate_template(rule)
    elif rule.has_value_changed('run_as'):
        old = rule.get_doc_before_save()
        rule.run_as = old.run_as if old else None
    seen = set()
    for row in rule.parameters or []:
        if row.position < 1 or row.position in seen:
            frappe.throw('Message variables need unique positions starting at 1.')
        seen.add(row.position)
        if row.value_source == 'Fixed text':
            if not (row.fixed_value or '').strip():
                frappe.throw('Enter a value for each fixed message variable.')
        elif row.value_source in ('Record', 'Recipient'):
            field = approved_field(meta if row.value_source == 'Record' else recipient_meta(rule, meta), row.fieldname_value)
            if not eligible(field):
                frappe.throw('Choose a non-sensitive message field.')
        else:
            frappe.throw('Choose where each message variable comes from.')
    if seen and sorted(seen) != list(range(1, len(seen)+1)):
        frappe.throw('Message variable positions must be sequential.')


def validate_template(rule):
    sender = account(rule.sender, enabled=True)
    template = frappe.get_doc('WhatsApp Approved Template', rule.approved_template)
    template.check_permission('read')
    if template.waba_id != sender.waba_id or template.approval_status != 'APPROVED' or not template.supported:
        frappe.throw('Choose a WhatsApp-approved template for this sender.')
    if not document_header(parsed(template.components_json, [])):
        frappe.throw('Choose a template with a DOCUMENT header so each record can supply its own PDF.')
    if len(rule.parameters or []) != len(parsed(template.parameters_json, [])):
        frappe.throw('Map every body variable in the approved message template.')
    return sender, template


def trigger_matches(rule, source):
    if any(str(source.get(row.fieldname_value)) != str(row.expected_value).strip() for row in rule.get('conditions') or []):
        return False
    if rule.event_type != 'Field changes to a value':
        return True
    value = source.get(rule.trigger_field)
    if value is None:
        return False
    field = source.meta.get_field(rule.trigger_field)
    if field and field.fieldtype in TEXT_TRIGGER_TYPES:
        text = rule.trigger_text or ''
        if not text.strip():
            return False
        if rule.text_match_operator == 'Contains':
            return text in str(value)
        return rule.text_match_operator == 'Equals' and str(value) == text
    values = {v.strip() for v in (rule.trigger_values or '').splitlines() if v.strip()}
    return str(value) in values


def on_event(source, event):
    if frappe.flags.in_install or frappe.flags.in_migrate or source.doctype.startswith('WhatsApp') or source.doctype in INTERNAL_SOURCES or not frappe.db.has_table(RULE):
        return
    for name in frappe.get_all(RULE, filters={'source_doctype':source.doctype, 'enabled':1}, pluck='name'):
        rule = frappe.get_doc(RULE, name)
        if EVENTS.get(rule.event_type) != event or not trigger_matches(rule, source):
            continue
        old = source.get_doc_before_save()
        if rule.event_type == 'Field changes to a value' and old and old.get(rule.trigger_field) == source.get(rule.trigger_field):
            continue
        if rule.event_type == 'Field changes to a value' and old and trigger_matches(rule, old):
            continue
        key = digest(rule.name, source.doctype, source.name, str(source.modified), event)
        if frappe.db.exists(DELIVERY, {'delivery_key':key}):
            continue
        # Persist intent in the same source transaction; rollbacks cannot send.
        with service():
            delivery = frappe.get_doc(dict(doctype=DELIVERY, rule=rule.name, source_doctype=source.doctype,
                source_name=source.name, source_modified=source.modified, rule_modified=rule.modified,
                delivery_key=key, record_title=f'{rule.rule_name}: {source.name}',
                state='Awaiting release' if rule.require_release else 'Pending')).insert(ignore_permissions=True)
        if not rule.require_release:
            enqueue(delivery.name)


def enqueue(name):
    frappe.enqueue('whatsapp_messaging.messaging.document_delivery.process', name=name, enqueue_after_commit=True)


def resolve_recipient(rule, source):
    recipient = source
    if rule.recipient_mode == 'A linked record':
        field = approved_field(source.meta, rule.recipient_link_field, {'Link'})
        if not source.get(field.fieldname):
            frappe.throw('The linked recipient is missing.')
        recipient = frappe.get_doc(field.options, source.get(field.fieldname))
    recipient.check_permission('read')
    approved_field(recipient.meta, rule.phone_field)
    number = re.sub(r'[\s()+-]', '', str(recipient.get(rule.phone_field) or ''))
    if not re.fullmatch(r'[1-9][0-9]{6,14}', number):
        frappe.throw('The recipient needs a full international phone number including country code.')
    return recipient, number


def parameter_values(rule, source, recipient):
    values = []
    for row in sorted(rule.parameters, key=lambda row: row.position):
        if row.value_source == 'Fixed text':
            value = row.fixed_value
        else:
            doc = source if row.value_source == 'Record' else recipient
            field = approved_field(doc.meta, row.fieldname_value)
            if not eligible(field):
                frappe.throw('The selected message field is no longer available.')
            value = doc.get_formatted(field.fieldname)
        if value is None or not str(value).strip():
            frappe.throw('A message variable has no value on this record.')
        values.append(str(value))
    return values


def load_delivery(name):
    frappe.db.sql('select name from `tabWhatsApp Document Delivery` where name=%s for update', name)
    delivery = frappe.get_doc(DELIVERY, name)
    rule = frappe.get_doc(RULE, delivery.rule)
    rule.check_permission('read')
    source_meta(rule)
    source = frappe.get_doc(delivery.source_doctype, delivery.source_name)
    source.check_permission('read')
    if not rule.enabled or get_datetime(rule.modified) != get_datetime(delivery.rule_modified):
        frappe.throw('The document rule was paused or changed. Review this delivery before sending.')
    if get_datetime(source.modified) != get_datetime(delivery.source_modified) or not trigger_matches(rule, source) or source.docstatus == 2:
        frappe.throw('The source record changed or was cancelled. Release the current version instead.')
    return delivery, rule, source


def process(name):
    base = frappe.db.get_value(DELIVERY, name, ['state','rule'], as_dict=True)
    if not base or base.state != 'Pending':
        return
    execution_user = frappe.db.get_value(RULE, base.rule, 'run_as')
    try:
        with as_user(execution_user):
            delivery, rule, source = load_delivery(name)
            if delivery.state != 'Pending' or delivery.outbox:
                return
            if rule.require_release and not delivery.released_by:
                frappe.throw('Staff release is required.')
            sender, template = validate_template(rule)
            recipient, number = resolve_recipient(rule, source)
            from .inbox import ensure_peer, ensure_conversation
            peer = ensure_peer(number, sender)
            if peer.suppressed or not peer.consent_recorded:
                frappe.throw('Recipient permission is missing or messages to this recipient are blocked.')
            from whatsapp_messaging.send_security import require_outbound_enabled
            require_outbound_enabled()
            if not frappe.db.get_single_value('WhatsApp Settings', 'enable_automation', cache=False):
                frappe.throw('WhatsApp automation is paused.')
            values = parameter_values(rule, source, recipient)
            frappe.db.savepoint('document_preparation')
            try:
                file = prepare_file(rule, source)
                conversation = ensure_conversation(sender, peer)
                from .outbox import create_intent
                result = create_intent(conversation.name, delivery.name, template=template.name, parameters=values,
                    file_id=file.name, source_doctype=source.doctype, source_name=source.name,
                    origin_key='document:'+delivery.delivery_key)
                update(name, state='Queued', recipient=number, file=file.name,
                    outbox=result['outbox'], message=result['message'], last_error=None)
            except Exception:
                frappe.db.rollback(save_point='document_preparation')
                raise
    except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as exc:
        update(name, state='Held', last_error=frappe.utils.strip_html(str(exc))[:500])
    except Exception:
        update(name, state='Failed', last_error='Unable to prepare the document. Check the print format/PDF renderer and retry after correcting it.')


def prepare_file(rule, source):
    from .media import authorized_file, inspect
    if rule.document_mode == 'Private attachment':
        field = approved_field(source.meta, rule.file_field, {'Attach'})
        url = source.get(field.fieldname)
        if not url or not url.startswith('/private/files/'):
            frappe.throw('Choose a released private PDF attachment on the source record.')
        name = frappe.db.get_value('File', {'file_url':url, 'attached_to_doctype':source.doctype, 'attached_to_name':source.name}, 'name')
        if not name:
            frappe.throw('The attachment must belong to this source record.')
        file, content = authorized_file(name)
        if inspect(content) != 'application/pdf':
            frappe.throw('Only PDF documents can use this document template.')
        return file
    fmt = frappe.get_doc('Print Format', rule.print_format)
    fmt.check_permission('read')
    if fmt.doc_type != source.doctype or fmt.disabled:
        frappe.throw('The selected print format is no longer available for this record.')
    pdf = frappe.get_print(source.doctype, source.name, print_format=fmt.name, as_pdf=True)
    if inspect(pdf) != 'application/pdf':
        frappe.throw('The renderer did not produce a PDF.')
    label = source.name
    if re.fullmatch(r'[a-z0-9]{10,40}', label) or re.fullmatch(r'[0-9a-f-]{36}', label, re.I):
        label = source.get(source.meta.title_field) if source.meta.title_field else None
        label = label or (fmt.name + '-' + frappe.utils.today())
    filename = re.sub(r'[^A-Za-z0-9_.-]', '-', label)[:120] + '.pdf'
    return frappe.get_doc(dict(doctype='File', file_name=filename, content=pdf, is_private=1,
        attached_to_doctype=source.doctype, attached_to_name=source.name)).insert(ignore_permissions=True)


def validate_dispatch(intent):
    if not frappe.db.has_table(DELIVERY):
        return
    name = frappe.db.get_value(DELIVERY, {'outbox':intent.name}, 'name')
    if not name:
        return
    delivery, rule, source = load_delivery(name)
    if rule.require_release and not delivery.released_by:
        frappe.throw('Staff release was withdrawn.')
    if not frappe.db.get_single_value('WhatsApp Settings', 'enable_automation', cache=False):
        frappe.throw('Document automation is paused.')
    recipient, number = resolve_recipient(rule, source)
    if number != delivery.recipient:
        frappe.throw('The recipient phone changed after the document was prepared.')
    if rule.document_mode == 'Private attachment':
        file = frappe.get_doc('File', delivery.file)
        if source.get(rule.file_field) != file.file_url:
            frappe.throw('The source attachment changed.')


@frappe.whitelist(methods=['POST'])
def release(name):
    require_supervisor()
    delivery, rule, source = load_delivery(name)
    delivery.check_permission('write')
    source.check_permission('write')
    if delivery.state != 'Awaiting release':
        frappe.throw('This delivery is not awaiting release.')
    update(name, state='Pending', released_by=frappe.session.user, released_on=utcnow(), last_error=None)
    enqueue(name)


@frappe.whitelist(methods=['POST'])
def retry(name):
    require_supervisor()
    delivery, rule, source = load_delivery(name)
    delivery.check_permission('write')
    if delivery.outbox or delivery.state not in ('Held','Failed'):
        frappe.throw('Only document preparation can be retried here. Review queued message delivery separately.')
    if rule.require_release and not delivery.released_by:
        frappe.throw('Staff release is required.')
    update(name, state='Pending', last_error=None)
    enqueue(name)


@frappe.whitelist(methods=['POST'])
def prepare_current(rule_name, source_name):
    """Explicit staff action for the current version; never replays an uncertain send."""
    require_supervisor()
    rule = frappe.get_doc(RULE, rule_name)
    rule.check_permission('read')
    if not rule.enabled:
        frappe.throw('Enable and validate the rule before preparing a document.')
    source = frappe.get_doc(rule.source_doctype, source_name)
    source.check_permission('write')
    if source.docstatus == 2 or not trigger_matches(rule, source):
        frappe.throw('The current record does not meet this rule.')
    existing = frappe.db.get_value(DELIVERY, {'rule':rule.name, 'source_name':source.name,
        'source_modified':source.modified, 'rule_modified':rule.modified}, 'name')
    if existing:
        return {'name':existing, 'existing':True}
    with service():
        doc = frappe.get_doc(dict(doctype=DELIVERY, rule=rule.name, source_doctype=source.doctype,
            source_name=source.name, source_modified=source.modified, rule_modified=rule.modified,
            delivery_key=digest('current',rule.name,str(rule.modified),source.name,str(source.modified)),
            record_title=f'{rule.rule_name}: {source.name}',state='Awaiting release' if rule.require_release else 'Pending')).insert(ignore_permissions=True)
    if not rule.require_release:
        enqueue(doc.name)
    return {'name':doc.name, 'existing':False}


@frappe.whitelist()
def field_options(source_doctype, recipient_link_field=None, sender=None):
    require_supervisor()
    if not frappe.has_permission(source_doctype, 'read'):
        frappe.throw('You cannot read this record type.', frappe.PermissionError)
    meta = frappe.get_meta(source_doctype)
    def fields(meta):
        permitted = set(meta.get_permitted_fieldnames(permission_type='read'))
        return [dict(value=f.fieldname,label=f.label or f.fieldname,type=f.fieldtype,options=f.options) for f in meta.fields
            if not f.hidden and f.fieldname in permitted and not re.search(r'password|secret|token|api_key', f.fieldname, re.I)]
    linked = []
    if recipient_link_field:
        field = approved_field(meta, recipient_link_field, {'Link'})
        if frappe.has_permission(field.options, 'read'):
            linked = fields(frappe.get_meta(field.options))
    templates = []
    if sender:
        from .catalogue import list_templates
        templates = [t for t in list_templates(sender) if document_header(parsed(t.components_json, []))]
    return dict(fields=fields(meta),recipient_fields=linked,print_formats=frappe.get_list('Print Format',
        filters={'doc_type':source_doctype,'disabled':0},fields=['name']),templates=templates)


@frappe.whitelist(methods=['GET'])
def trigger_value_options(source_doctype, trigger_field, search=''):
    """Suggest existing Data values using the caller's normal list permissions."""
    require_supervisor()
    meta = source_meta(frappe._dict(source_doctype=source_doctype))
    field = approved_field(meta, trigger_field, {'Data'})
    if not eligible(field):
        frappe.throw('Choose an available, non-sensitive Data field.')
    filters = [[field.fieldname, 'is', 'set']]
    if search:
        filters.append([field.fieldname, 'like', '%' + str(search)[:140] + '%'])
    rows = frappe.get_list(source_doctype, fields=[field.fieldname], filters=filters,
        distinct=True, order_by=field.fieldname + ' asc', limit_page_length=20)
    return [row[field.fieldname] for row in rows if str(row.get(field.fieldname) or '').strip()]


@frappe.whitelist(methods=['POST'])
def preview(rule_name, source_name):
    require_supervisor()
    rule = frappe.get_doc(RULE, rule_name)
    rule.check_permission('read')
    source = frappe.get_doc(rule.source_doctype, source_name)
    source.check_permission('read')
    recipient, number = resolve_recipient(rule, source)
    values = parameter_values(rule, source, recipient)
    template = frappe.get_doc('WhatsApp Approved Template', rule.approved_template) if rule.approved_template else None
    from .catalogue import rendered_text
    return dict(recipient=number,source_name=source.name,trigger_matches=trigger_matches(rule,source),
        message=rendered_text(template,values) if template else 'Choose an approved document template to preview the message.',
        document=rule.print_format if rule.document_mode=='Generate PDF' else source.get(rule.file_field),
        release_required=bool(rule.require_release),sent=False)


def recover():
    if not frappe.db.has_table(DELIVERY):
        return
    for name in frappe.get_all(DELIVERY,filters={'state':'Pending'},pluck='name',limit_page_length=20,order_by='creation asc'):
        enqueue(name)
    if frappe.db.get_single_value('WhatsApp Settings','enable_automation',cache=False):
        for row in frappe.get_all('WhatsApp Outbox',filters={'state':['in',['Ready','Retry wait']],
                'origin_key':['like','document:%'],'next_attempt_at':['<=',utcnow()]},fields=['name'],limit_page_length=20,order_by='next_attempt_at asc'):
            if frappe.db.exists(DELIVERY,{'outbox':row.name}):
                frappe.enqueue('whatsapp_messaging.messaging.outbox.dispatch',name=row.name,enqueue_after_commit=True)
    for row in frappe.get_all(DELIVERY, filters={'state':'Queued'}, fields=['name','message','delivery_status'], limit_page_length=200, order_by='modified desc'):
        status = frappe.db.get_value('WhatsApp Message', row.message, 'status')
        if status and status != row.delivery_status:
            update(row.name, delivery_status=status)
