"""Published conversation menus, durable inbound turns and explicit staff takeover."""
import hmac
import json
import math
from datetime import timedelta

import frappe
from frappe.utils import get_datetime, getdate, nowdate
from . import flow_engine as engine
from .common import account, as_user, changed, conversation, digest, insert, lock, parsed, require_supervisor, require_send_role, utcnow, window_open
from .naming import set_record_values as update

PROTECTED = ('status', 'is_active', 'published_account', 'published_at', 'run_as', 'published_version', 'published_definition')


def definition(doc, publishing=False):
    value = doc.as_dict() if hasattr(doc, 'as_dict') else doc
    from .flow_templates import snapshot,compile_lookup
    specs = {}
    for row in value.get('steps', []):
        if row.get('step_type') == 'Template' and row.get('message_template'):
            spec=snapshot(row['message_template'],value.get('account'),publishing)
            spec['lookup']=compile_lookup(row,spec)
            specs[row['step_key']]=spec
    try: return engine.compile_definition(value, publishing, template_specs=specs)
    except ValueError as error: frappe.throw(str(error))


def validate_flow(doc):
    require_supervisor()
    account(doc.account)
    previous = doc.get_doc_before_save()
    for field in PROTECTED:
        old = previous.get(field) if previous else ('Draft' if field == 'status' else 0 if field == 'is_active' else None)
        if (doc.get(field) or None) != (old or None):
            frappe.throw('Use Publish or Pause to change the published flow.', frappe.PermissionError)
    definition(doc)
    if doc.get('layout_json'):
        try:
            layout=parsed(doc.layout_json)
            positions=layout['positions']
            if layout.get('version') != 1 or not isinstance(positions,dict) or len(positions)>200: raise ValueError()
            keys={step.step_key for step in doc.steps}
            cleaned={}
            for key, point in positions.items():
                if not isinstance(point,dict) or any(isinstance(point.get(axis),bool) or not isinstance(point.get(axis),(int,float)) or not math.isfinite(point[axis]) or not 0<=point[axis]<=100000 for axis in ('x','y')): raise ValueError()
                if key in keys:cleaned[key]={'x':round(point['x']), 'y':round(point['y'])}
            doc.layout_json=json.dumps({'version':1,'positions':cleaned})
        except (ValueError,KeyError,TypeError):frappe.throw('The saved canvas positions are invalid. Use Auto arrange to reset the map.')


@frappe.whitelist(methods=['POST'])
def publish(name):
    require_supervisor()
    draft = frappe.get_doc('WhatsApp Conversation Flow', name); draft.check_permission('write')
    sender = lock('WhatsApp Phone Number ID', draft.account); account(sender.name, enabled=True)
    doc = lock('WhatsApp Conversation Flow', name)
    if doc.account != sender.name: frappe.throw('The business number changed. Reload the flow and publish again.')
    other = frappe.db.sql('SELECT name FROM `tabWhatsApp Conversation Flow` WHERE published_account=%s AND is_active=1 AND name!=%s FOR UPDATE', (sender.name, name))
    if other:
        frappe.throw('Pause the other active flow for this business number before publishing this one.')
    compiled = definition(doc, publishing=True)
    update(doc.doctype, name, dict(status='Published', is_active=1, published_account=sender.name, published_at=utcnow(),
        run_as=frappe.session.user, published_version=digest(compiled), published_definition=json.dumps(compiled)))
    return {'published': True}


@frappe.whitelist(methods=['POST'])
def pause(name):
    require_supervisor(); doc = lock('WhatsApp Conversation Flow', name); doc.check_permission('write')
    update(doc.doctype, name, {'is_active': 0, 'status': 'Paused'})
    return {'paused': True}


@frappe.whitelist(methods=['POST'])
def preview(name, state=None, text='', choice=None, lookup_result='matched'):
    require_send_role(); doc = frappe.get_doc('WhatsApp Conversation Flow', name); doc.check_permission('read')
    if len(str(state or '')) > 25000 or len(str(text or '')) > 4096: frappe.throw('The preview input is too long.')
    compiled = definition(doc)
    try:
        state = parsed(state) if state else None
        if state and (not isinstance(state, dict) or not isinstance(state.get('answers'), dict) or not isinstance(state.get('history'), list)):
            raise ValueError('Restart the preview to clear invalid progress.')
        if lookup_result not in ('matched','no_match','multiple_match'):raise ValueError('Choose a preview lookup result.')
        def training_lookup(step, *_):
            return dict(outcome=lookup_result,values=['Sample '+path.rsplit('.',1)[-1].replace('_',' ') for path in step['template']['paths']])
        new_state, outputs = engine.advance(compiled, state, text=text, choice=choice or None, contact_name='Training visitor', contact_phone='919000000001', template_resolver=training_lookup, today=getdate(nowdate()))
    except ValueError as error: frappe.throw(str(error))
    except (KeyError, TypeError): frappe.throw('Restart the preview to clear invalid progress.')
    return {'state': new_state, 'messages': outputs}


def active_flow(account_name):
    names = frappe.get_all('WhatsApp Conversation Flow', filters={'published_account': account_name, 'is_active': 1}, pluck='name', limit_page_length=2)
    return frappe.get_doc('WhatsApp Conversation Flow', names[0]) if len(names) == 1 else None


def enqueue_inbound(message):
    if not frappe.db.has_table('WhatsApp Conversation Flow'): return
    if not active_flow(message.account) and not frappe.db.exists('WhatsApp Flow Session', {'conversation': message.conversation}): return
    enabled = all(frappe.db.get_single_value('WhatsApp Settings', flag, cache=False) for flag in ('enable_inbound', 'enable_automation', 'enable_outbound_messages'))
    event = insert('WhatsApp Flow Event', event_key=digest('flow-inbound', message.name), message=message.name, conversation=message.conversation,
        state='Pending' if enabled else 'Skipped', reason=None if enabled else 'Automatic replies were switched off when this message arrived.')
    if enabled: frappe.enqueue('whatsapp_messaging.messaging.flows.process_event', name=event.name, enqueue_after_commit=True)


def choice_token(session, step, key):
    return 'wa-flow:' + digest(session.name, session.flow_version, int(session.generation or 0), step, key)[:48]


def finish_event(event, state, reason=None, session=None):
    update(event.doctype, event.name, dict(state=state, reason=reason, processed_at=utcnow(), session=session.name if session else None,
        answers_json=session.answers_json if session else None))


def pause_session(doc, reason='Staff took over', actor=None):
    session_name = frappe.db.get_value('WhatsApp Flow Session', {'conversation': doc.name}, 'name')
    if not session_name: return
    session = frappe.get_doc('WhatsApp Flow Session', session_name)
    if session.state == 'Paused': return
    update(session.doctype, session.name, {'state': 'Paused', 'pause_reason': reason, 'generation': int(session.generation or 0) + 1})
    insert('WhatsApp Conversation Activity', conversation=doc.name, actor=actor or frappe.session.user, action='Flow paused', details=reason)


@frappe.whitelist(methods=['POST'])
def control(conversation_name, action):
    doc = conversation(conversation_name, locked=True)
    if action == 'Pause': pause_session(doc)
    elif action == 'Resume':
        from .common import supervisor
        if doc.assigned_to and doc.assigned_to != frappe.session.user and not supervisor():
            frappe.throw('Only the assigned team member or an administrator can release this conversation.', frappe.PermissionError)
        session_name = frappe.db.get_value('WhatsApp Flow Session', {'conversation': doc.name}, 'name')
        if not session_name: frappe.throw('No flow has started in this conversation.')
        session = frappe.get_doc('WhatsApp Flow Session', session_name)
        flow = active_flow(doc.account)
        if not flow: frappe.throw('Publish and enable a flow for this business number first.')
        with as_user(flow.run_as):
            flow.check_permission('write'); account(doc.account, enabled=True)
        update(session.doctype, session.name, dict(flow=flow.name, flow_version=flow.published_version, state='Completed',
            state_json=json.dumps(engine.fresh_state(parsed(flow.published_definition))), generation=int(session.generation or 0)+1,
            pause_reason='Waiting for the contact to type a start word, such as menu.', expires_at=utcnow()+timedelta(hours=24)))
        changed(doc, assigned_to=None)
        insert('WhatsApp Conversation Activity', conversation=doc.name, actor=frappe.session.user, action='Flow resumed', details='Waiting for a new menu request; no message sent')
    else: frappe.throw('Choose Pause or Resume.')
    from .common import notify
    notify(doc.name)
    return {'updated': True}


def process_turn(event, doc, message):
    # All operations are serialized by the conversation lock, including staff actions.
    if not all(frappe.db.get_single_value('WhatsApp Settings', flag, cache=False) for flag in ('enable_inbound', 'enable_automation', 'enable_outbound_messages')):
        return finish_event(event, 'Skipped', 'Automatic replies are switched off.')
    flow = active_flow(doc.account)
    if not flow: return finish_event(event, 'Skipped', 'No active flow for this business number.')
    if flow.published_at and get_datetime(message.received_at) < get_datetime(flow.published_at):
        return finish_event(event, 'Skipped', 'This message arrived before the current flow was published.')
    session_name = frappe.db.get_value('WhatsApp Flow Session', {'conversation': doc.name}, 'name')
    session = frappe.get_doc('WhatsApp Flow Session', session_name) if session_name else None
    if session and int(message.sequence) <= int(session.last_sequence or 0):
        return finish_event(event, 'Skipped', 'This message was already handled.', session)
    if session and session.last_provider_at and get_datetime(message.provider_at) < get_datetime(session.last_provider_at):
        return finish_event(event, 'Skipped', 'Older message arrived after a newer response.', session)
    peer = frappe.get_doc('WhatsApp Peer', doc.peer)
    if peer.suppressed or not window_open(doc) or doc.assigned_to:
        return finish_event(event, 'Skipped', 'Sending is blocked, the reply window is closed or staff are handling this conversation.', session)
    if session and session.state in ('Paused', 'Waiting for staff'):
        return finish_event(event, 'Skipped', 'Reception is handling this conversation.', session)
    if message.message_type not in ('text', 'interactive', 'button'):
        return finish_event(event, 'Skipped', 'This flow responds to text and menu selections.', session)
    compiled = parsed(flow.published_definition)
    text = message.message or ''
    requested = text.strip().casefold() in set(compiled['keywords']) | {'menu'}
    is_new = not session or session.flow_version != flow.published_version or not session.expires_at or get_datetime(session.expires_at) <= utcnow()
    if session and is_new and not requested:
        pause_session(doc, 'The flow changed or the session expired. Reception can resume it.')
        return finish_event(event, 'Skipped', 'Session needs a new start word or staff review.', session)
    if not session and (message.interactive_reply_id or (compiled['trigger_mode'] == 'Keyword only' and not requested)):
        return finish_event(event, 'Skipped', 'Waiting for a start word.')
    if session and session.state == 'Completed' and not requested:
        return finish_event(event, 'Skipped', 'Flow finished; waiting for a new start word.', session)
    with as_user(flow.run_as):
        flow.check_permission('write'); account(doc.account, enabled=True)
        if not session:
            session = insert('WhatsApp Flow Session', conversation=doc.name, flow=flow.name, flow_version=flow.published_version,
                state='Active', state_json=json.dumps(engine.fresh_state(compiled)), generation=0, last_sequence=0)
        state = engine.fresh_state(compiled) if is_new or requested else parsed(session.state_json)
        choice = None
        if message.interactive_reply_id:
            if is_new or state.get('status') != 'Active': return finish_event(event, 'Skipped', 'This menu is no longer active.', session)
            step = compiled['steps'][state['step']]
            for option in step['choices']:
                if hmac.compare_digest(str(message.interactive_reply_id), choice_token(session, state['step'], option['key'])):
                    choice = option['key']; break
            if choice is None: return finish_event(event, 'Skipped', 'An old or unrelated menu option was selected.', session)
            text = ''
        # Repeated invalid replies hand off after three turns. Bound all other automation too.
        recent = frappe.db.count('WhatsApp Flow Event', {'conversation': doc.name, 'state': 'Processed', 'processed_at': ['>=', utcnow()-timedelta(hours=1)]})
        if recent >= 60:
            pause_session(doc, 'Automatic reply limit reached. Reception can review this conversation.')
            return finish_event(event, 'Skipped', 'Hourly automatic reply limit reached.', session)
        initial = not session_name or is_new or requested
        input_text = text if not initial or text.strip().casefold() in ('reception', 'human', 'staff') else ''
        from .flow_templates import resolve_lookup
        new_state, outputs = engine.advance(compiled, state, text=input_text, choice=choice,
            contact_name=peer.display_name or 'Contact', contact_phone=peer.provider_identity, template_resolver=resolve_lookup, today=getdate(nowdate()))
        session.generation = int(session.generation or 0)+1
        session.flow_version = flow.published_version; session.flow = flow.name
        update(session.doctype, session.name, dict(flow=flow.name, flow_version=flow.published_version, state=new_state['status'], current_step=new_state['step'],
            state_json=json.dumps(new_state), answers_json=json.dumps(new_state['answers']), generation=session.generation,
            last_sequence=message.sequence, last_provider_at=message.provider_at, expires_at=utcnow()+timedelta(hours=24), pause_reason=None))
        from .outbox import create_intent
        last = None
        for index, output in enumerate(outputs):
            menu = engine.interactive(output, lambda key: choice_token(session, output['step'], key)) if output['kind'] == 'Menu' else None
            # Store numbered labels in the Inbox too, so staff see the choices the contact received.
            body = output['text'] + (('\n\n' + '\n'.join(str(i)+'. '+c['label'] for i,c in enumerate(output['choices'],1))) if menu else '')
            extra = {key:output[key] for key in ('source_doctype','source_name') if output.get(key)}
            if output['kind'] == 'Template':
                spec = compiled['steps'][output['step']]['template']
                from .flow_templates import validate_current
                validate_current(spec, doc.account)
                if spec['mode'] == 'Meta-approved template':
                    extra.update(template=spec['approved_template'], parameters=output['parameters'])
            last = create_intent(doc.name, digest('flow-turn', event.name, index), body=body, interactive=menu,
                conversation_flow=flow.name, flow_version=flow.published_version, flow_session=session.name, flow_generation=session.generation, **extra)
            if output['kind']=='Template': update('WhatsApp Outbox',last['outbox'],'flow_step',output['step'])
        if last: update(session.doctype, session.name, 'last_outbox', last['outbox'])
        session.reload()
        if new_state['status'] == 'Waiting for staff':
            insert('WhatsApp Conversation Activity', conversation=doc.name, actor=flow.run_as, action='Reception requested', details='Flow handed the conversation to staff. Review collected answers in Flow details.')
            changed(frappe.get_doc(doc.doctype, doc.name), workflow_status='Open')
        finish_event(event, 'Processed', session=session)


def process_event(name):
    base = frappe.db.get_value('WhatsApp Flow Event', name, ['conversation', 'state'], as_dict=True)
    if not base or base.state != 'Pending': return
    doc = lock('WhatsApp Conversation', base.conversation)
    # Drain in receive order, even if jobs reach different workers out of order.
    rows = frappe.db.sql('SELECT e.name,e.message FROM `tabWhatsApp Flow Event` e JOIN `tabWhatsApp Message` m ON m.name=e.message WHERE e.conversation=%s AND e.state="Pending" ORDER BY m.sequence LIMIT 20', doc.name, as_dict=True)
    for row in rows:
        event = frappe.get_doc('WhatsApp Flow Event', row.name)
        frappe.db.savepoint('flow_turn')
        try: process_turn(event, frappe.get_doc(doc.doctype, doc.name), frappe.get_doc('WhatsApp Message', row.message))
        except Exception:
            frappe.db.rollback(save_point='flow_turn')
            finish_event(event, 'Failed', 'Automatic reply could not be prepared. Ask an administrator to review the flow and its publishing user.')
    frappe.db.commit()


def validate_dispatch(intent, doc):
    if not intent.get('conversation_flow'): return
    if not frappe.db.get_single_value('WhatsApp Settings', 'enable_automation', cache=False): frappe.throw('Automatic replies are switched off.')
    flow = frappe.get_doc('WhatsApp Conversation Flow', intent.conversation_flow); flow.check_permission('write')
    session = frappe.get_doc('WhatsApp Flow Session', intent.flow_session)
    if (not flow.is_active or flow.published_account != doc.account or flow.published_version != intent.flow_version or
            session.conversation != doc.name or session.flow != flow.name or int(session.generation or 0) != int(intent.flow_generation or 0) or
            session.state == 'Paused' or doc.assigned_to):
        frappe.throw('This automatic reply is no longer current, or reception has taken over.')
    from .flow_templates import dispatch_spec
    dispatch_spec(intent, flow)


def sweep():
    for name in frappe.get_all('WhatsApp Flow Event', filters={'state': 'Pending'}, pluck='name', order_by='creation', limit_page_length=50):
        frappe.enqueue('whatsapp_messaging.messaging.flows.process_event', name=name)


@frappe.whitelist(methods=['POST'])
def hospital_draft(account_name):
    require_supervisor(); account(account_name)
    from .flow_starter import hospital
    doc = frappe.get_doc(hospital(account_name)).insert()
    return {'name': doc.name}


@frappe.whitelist()
def template_options(name, account_name):
    from .flow_templates import options
    return options(name, account_name)
