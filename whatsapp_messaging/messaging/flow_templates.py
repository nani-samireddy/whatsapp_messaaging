"""Saved text templates and explicit, contact-scoped record lookup in flows."""
import re

import frappe

from whatsapp_messaging.template_security import PLACEHOLDER
from . import template_editor, template_framing
from .common import account, digest, parsed, require_send_role


def snapshot(name, account_name, publishing=False):
    try:
        return _snapshot(name, account_name, publishing)
    except ValueError as error:
        frappe.throw(str(error))


def _snapshot(name, account_name, publishing=False):
    doc = frappe.get_doc('WhatsApp Message Template', name)
    doc.check_permission('read')
    if doc.media:
        frappe.throw('Flow template steps currently support text templates. Choose a template without an image or PDF.')
    sender = account(account_name)
    mode = doc.delivery_mode or template_editor.LOCAL
    approved = None
    if mode == template_editor.META:
        body, paths, _ = template_editor.compile_content(doc)
        if publishing:
            template_editor.ensure_sendable(doc)
        linked = template_editor.linked_template(doc)
        original_sender = account(doc.phone_number_id)
        if original_sender.waba_id != sender.waba_id:
            frappe.throw('Choose a template registered for the same WhatsApp business account as this flow.')
        approved = linked.name if linked else None
        approval_hash = linked.schema_hash if linked else None
    else:
        body = doc.message_preview or ''
        paths = list(dict.fromkeys(m.group(1).strip() for m in PLACEHOLDER.finditer(body)))
        if any(path not in template_editor.allowed_paths(doc) for path in paths):
            frappe.throw('A template field is no longer approved or readable. Review the template’s shared fields.')
        body = PLACEHOLDER.sub(lambda m:'{{' + str(paths.index(m.group(1).strip())+1) + '}}', body)
        approval_hash = None
    if not body.strip() or len(paths) > 50 or '{{' in re.sub(r'\{\{\d+\}\}', '', body):
        frappe.throw('Choose a saved text template with valid fields and a non-empty message.')
    header, footer = template_framing.validate(doc.meta_header, doc.meta_footer)
    spec = dict(record=doc.name, source_doctype=doc.template_doctype, mode=mode, body=body, paths=paths, header=header, footer=footer,
                approved_template=approved, approval_hash=approval_hash)
    spec['fingerprint'] = digest(spec)
    return spec


@frappe.whitelist()
def options(name, account_name):
    require_send_role()
    spec = snapshot(name, account_name)
    doc = frappe.get_doc('WhatsApp Message Template', name)
    fields = []
    for path in spec['paths']:
        key = path.rsplit('.', 1)[-1]
        label = key.replace('_', ' ').capitalize()
        if path.startswith('template_doctype.'):
            field = frappe.get_meta(doc.template_doctype).get_field(key)
            if field: label = field.label or label
        fields.append(dict(path=path, label=label))
    meta = frappe.get_meta(doc.template_doctype)
    if meta.issingle or meta.istable or meta.is_virtual or not frappe.has_permission(doc.template_doctype, 'read'):
        lookup = dict(phones=[], fields=[], reason='Record lookup needs a readable record DocType. Use Flow values for this template.')
    else:
        lookup = lookup_fields(doc.template_doctype)
    return dict(source_doctype=doc.template_doctype,lookup=lookup,fields=fields, preview=template_framing.compose(spec['body'], spec['header'], spec['footer']),
                mode=spec['mode'], status=template_editor.review_values(doc)['meta_status'])


def validate_current(spec, account_name):
    current = snapshot(spec['record'], account_name, publishing=True)
    if current['fingerprint'] != spec['fingerprint']:
        frappe.throw('A linked template changed. Review the flow and publish it again before sending.')
    return current


def dispatch_spec(intent, flow):
    """Recheck published template versions and any record used by this queued message."""
    payload = parsed(intent.payload_json, {})
    compiled = parsed(flow.published_definition, {})
    for step in compiled.get('steps', {}).values():
        spec = step.get('template')
        if not spec: continue
        # A flow version pins every referenced template, including local content.
        validate_current(spec, intent.account)
    if intent.get('flow_step'):
        step=compiled.get('steps',{}).get(intent.flow_step)
        if not step or not step.get('template'):frappe.throw('The queued template step is no longer available.')
        if step.get('lookup'):
            session=frappe.get_doc('WhatsApp Flow Session',intent.flow_session)
            peer=frappe.get_doc('WhatsApp Peer',frappe.db.get_value('WhatsApp Conversation',intent.conversation,'peer'))
            result=resolve_lookup(step,parsed(session.answers_json,{}),peer.display_name or 'Contact',peer.provider_identity)
            if result['outcome']!='matched' or (result.get('source_doctype'),result.get('source_name'))!=(intent.source_doctype,intent.source_name):frappe.throw('The matching record changed. Review this conversation before sending.')
            values=result['values'];spec=step['template']
            if spec['mode']==template_editor.META:
                sent=[p.get('text') for component in payload.get('template',{}).get('components',[]) if component.get('type')=='body' for p in component.get('parameters',[])]
                if sent!=values:frappe.throw('The appointment details changed before sending. Review and try again.')
            else:
                body=re.sub(r'\{\{(\d+)\}\}',lambda m:values[int(m[1])-1],spec['body'])
                if payload.get('text',{}).get('body')!=template_framing.compose(body,spec['header'],spec['footer']):frappe.throw('The record details changed before sending. Review and try again.')


def lookup_fields(doctype):
    from whatsapp_messaging.template_security import FIELD_NAME, is_recipient_phone_field
    from .field_policy import eligible
    meta = frappe.get_meta(doctype)
    if meta.issingle or meta.istable or meta.is_virtual or not frappe.has_permission(doctype, 'read'):
        frappe.throw('Choose a readable record DocType for record lookup.', frappe.PermissionError)
    permitted = set(meta.get_permitted_fieldnames(permission_type='read'))
    direct = [f for f in meta.fields if eligible(f) and f.fieldname in permitted and FIELD_NAME.fullmatch(f.fieldname)]
    phones = [dict(value=f.fieldname,label=f.label or f.fieldname) for f in direct if is_recipient_phone_field(f)]
    for link in direct:
        if link.fieldtype != 'Link' or not link.options or not frappe.has_permission(link.options,'read'): continue
        linked = frappe.get_meta(link.options)
        if linked.issingle or linked.istable or linked.is_virtual: continue
        allowed = set(linked.get_permitted_fieldnames(permission_type='read'))
        phones.extend(dict(value=link.fieldname+'.'+f.fieldname,label=(link.label or link.fieldname)+' → '+(f.label or f.fieldname))
            for f in linked.fields if eligible(f) and f.fieldname in allowed and is_recipient_phone_field(f))
    return dict(phones=phones, fields=[dict(value='name',label='Record ID')]+[dict(value=f.fieldname,label=f.label or f.fieldname) for f in direct])


def compile_lookup(row, spec):
    if row.get('template_data_source') != 'Record lookup': return None
    doc = frappe.get_doc('WhatsApp Message Template', spec['record']); fields = lookup_fields(doc.template_doctype)
    phone = row.get('record_phone_field')
    if phone not in {f['value'] for f in fields['phones']}:
        frappe.throw('Choose a readable phone field to match the WhatsApp contact, including a linked Patient phone field when needed.')
    try: filters = parsed(row.get('record_filters'), [])
    except ValueError: frappe.throw('The record filters are invalid. Open the template step and set them again.')
    if not isinstance(filters,list) or len(filters)>10: frappe.throw('Use at most 10 record filters.')
    allowed = {f['value'] for f in fields['fields']}
    cleaned=[]
    from .flow_engine import TOKEN
    for condition in filters:
        if (not isinstance(condition,dict) or condition.get('field') not in allowed or condition.get('operator') not in ('=','!=','>','<','>=','<=')
            or not isinstance(condition.get('value'),str) or not condition['value'].strip() or len(condition['value'])>1024
            or '{{' in TOKEN.sub('',condition['value']) or '}}' in TOKEN.sub('',condition['value'])):
            frappe.throw('Choose valid filter fields, comparison operators and values from answers, the contact phone number or fixed text.')
        cleaned.append({key:condition[key] for key in ('field','operator','value')})
    selection = row.get('record_selection') or 'Exactly one record'
    if selection not in ('Exactly one record', 'Most recently created'):
        frappe.throw('Choose a valid matching record rule.')
    return dict(doctype=doc.template_doctype,phone_field=phone,filters=cleaned,selection=selection,
                no_match=row.get('no_match_step'),multiple_match=row.get('multiple_match_step'))


def resolve_lookup(step, answers, contact_name, contact_phone):
    """Phone identity is always the actual WhatsApp contact, never another entered number."""
    from .flow_engine import render
    from whatsapp_messaging.controller import parse_message
    lookup=step['lookup'];spec=step['template'];available=lookup_fields(lookup['doctype'])
    if lookup['phone_field'] not in {f['value'] for f in available['phones']} or any(c['field'] not in {f['value'] for f in available['fields']} for c in lookup['filters']):frappe.throw('Lookup fields are no longer readable.',frappe.PermissionError)
    phone=re.sub(r'\D','',str(contact_phone or ''))
    if not re.fullmatch(r'[0-9]{7,15}',phone): return {'outcome':'no_match'}
    parts=lookup['phone_field'].split('.')
    filters=[]
    if len(parts)==2:
        link=frappe.get_meta(lookup['doctype']).get_field(parts[0])
        matches=frappe.get_list(link.options,filters={parts[1]:['in',[phone,'+'+phone]]},fields=['name'],limit_page_length=2)
        if len(matches)!=1:return {'outcome':'multiple_match' if matches else 'no_match'}
        linked=frappe.get_doc(link.options,matches[0].name);linked.check_permission('read')
        if not linked.has_permlevel_access_to(parts[1],permission_type='read'):frappe.throw('The phone field is not readable.',frappe.PermissionError)
        filters.append([parts[0],'=',linked.name])
    else:filters.append([parts[0],'in',[phone,'+'+phone]])
    for c in lookup['filters']:
        from .flow_engine import TOKEN
        if any(token.startswith('answers.') and not str(answers.get(token[8:]) or '').strip() for token in TOKEN.findall(c['value'])):
            frappe.throw('Collect the required answer before looking up a record.')
        filters.append([c['field'],c['operator'],render(c['value'],answers,contact_name,contact_phone)])
    latest = lookup.get('selection') == 'Most recently created'
    matches=frappe.get_list(lookup['doctype'],filters=filters,fields=['name'],
        order_by='creation desc, name desc' if latest else 'name asc',limit_page_length=1 if latest else 2)
    if len(matches)!=1:return {'outcome':'multiple_match' if matches else 'no_match'}
    source=frappe.get_doc(lookup['doctype'],matches[0].name);source.check_permission('read')
    doc=frappe.get_doc('WhatsApp Message Template',spec['record']);doc.check_permission('read')
    if doc.template_doctype!=lookup['doctype']:
        frappe.throw('The template source changed. Review and publish the flow again.')
    values=[]
    for path in spec['paths']:
        clone=frappe._dict(template_doctype=doc.template_doctype,template_name=doc.template_name,
            template_button_label=doc.template_button_label,message_preview='{{'+path+'}}')
        values.append(parse_message(clone,source))
    return dict(outcome='matched',values=values,source_doctype=source.doctype,source_name=source.name)
