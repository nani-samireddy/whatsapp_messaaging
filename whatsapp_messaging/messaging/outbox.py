"""One immutable send intent per logical request; uncertain sends are never retried."""
import json
import hashlib
from datetime import timedelta

import frappe
from whatsapp_messaging.messaging.naming import set_record_values
import requests
from frappe.utils import get_datetime
from whatsapp_messaging.send_security import require_outbound_enabled, require_send_role
from whatsapp_messaging.utils.config import get_cloud_api_url, get_headers
from .common import account, as_user, changed, conversation, digest, insert, lock, parsed, require_supervisor, utcnow, window_open
from . import catalogue, media

ELIGIBLE_STATES=('Ready','Retry wait')


def create_intent(conversation_name,request_id,body='',template=None,parameters=None,file_id=None,reply_to=None,source_doctype=None,source_name=None,rule=None,run=None,origin_key=None,deleted_source=False,interactive=None,conversation_flow=None,flow_version=None,flow_session=None,flow_generation=None):
    require_send_role()
    if not request_id or len(str(request_id))>200:frappe.throw('A stable request identifier is required')
    doc=conversation(conversation_name,locked=True)
    input_hash=digest(doc.name,str(body or ''),template,parsed(parameters,[]),file_id,reply_to,source_doctype,source_name)
    if conversation_flow:
        input_hash=digest(input_hash,interactive,conversation_flow,flow_version,flow_session,flow_generation)
    elif interactive:
        frappe.throw('Interactive menus must belong to a published conversation flow.')
    request_key=digest('origin',origin_key) if origin_key else digest(frappe.session.user,request_id)
    existing=frappe.db.get_value('WhatsApp Outbox',{'request_key':request_key},['name','input_hash','message','state','conversation'],as_dict=True)
    if existing:
        if existing.conversation!=doc.name or existing.input_hash!=input_hash:frappe.throw('This request identifier was already used with different content')
        return {'outbox':existing.name,'message':existing.message,'state':existing.state}
    require_outbound_enabled()
    sender=account(doc.account,enabled=True)
    peer=frappe.get_doc('WhatsApp Peer',doc.peer)
    if peer.suppressed:frappe.throw('This recipient is suppressed')
    if source_doctype and source_name:
        frappe.get_doc(source_doctype,source_name).check_permission('read')
    body=str(body or '')
    if len(body)>4096:frappe.throw('Message text exceeds 4096 characters')
    payload={'messaging_product':'whatsapp','recipient_type':'individual','to':peer.provider_identity}
    template_hash=None;rendered=body
    if template:
        if not peer.consent_recorded:frappe.throw('Record recipient consent before initiating a template message')
        template_data,template_hash,approved=catalogue.template_payload(template,sender,parameters)
        payload.update(type='template',template=template_data)
        rendered=catalogue.rendered_text(approved,parsed(parameters,[]))
        if file_id:frappe.throw('Approved templates cannot be combined with a separate attachment')
    else:
        if not window_open(doc):frappe.throw('The reply window is closed. Choose an approved template.')
        if not body.strip() and not file_id:frappe.throw('Enter a message or choose an attachment')
        payload.update(type='text',text={'body':body})
    if interactive:
        if template or file_id or not conversation_flow:frappe.throw('A menu cannot be combined with a template or attachment.')
        payload.pop('text',None);payload.update(type='interactive',interactive=interactive)
    if reply_to:
        if not frappe.db.exists('WhatsApp Message',{'conversation':doc.name,'provider_message_id':reply_to}):frappe.throw('Reply context must belong to this conversation')
        payload['context']={'message_id':reply_to}
    file_digest=None
    if file_id:
        if len(body)>1024:frappe.throw('Attachment caption, including header and footer, exceeds 1024 characters')
        file,content=media.authorized_file(file_id)
        file_digest=hashlib.sha256(content).hexdigest()
        payload['type']='image' if media.inspect(content).startswith('image/') else 'document'
        payload.pop('text',None)
        payload[payload['type']]={'caption':body}
    request_key=digest('origin',origin_key) if origin_key else digest(frappe.session.user,request_id)
    payload_hash=digest(payload,file_digest,template_hash,source_doctype,source_name)
    from .campaigns import version as rule_version
    existing=frappe.db.get_value('WhatsApp Outbox',{'request_key':request_key},['name','payload_hash','message','state','conversation'],as_dict=True)
    if existing:
        conversation(existing.conversation)
        if existing.payload_hash!=payload_hash:frappe.throw('This request identifier was already used with different content')
        return {'outbox':existing.name,'message':existing.message,'state':existing.state}
    sequence=int(doc.last_sequence or 0)+1
    frappe.db.savepoint('intent_insert')
    try:
        message=insert('WhatsApp Message',conversation=doc.name,account=doc.account,peer=doc.peer,direction='Outbound',message_type=payload['type'],message=rendered,status='Queued',sequence=sequence,sequence_key=digest(doc.name,sequence),received_at=utcnow(),agent=frappe.session.user,reply_to=reply_to,approved_template=template,source_doctype=source_doctype,source_name=source_name)
        if file_id:
            attachment=media.attach(message,file_id)
            if attachment.content_hash!=file_digest:frappe.throw('Attachment changed during submission')
        if source_doctype and source_name and not deleted_source:
            from .inbox import link_record
            link_record(doc.name,source_doctype,source_name)
        intent=insert('WhatsApp Outbox',request_key=request_key,payload_hash=payload_hash,message=message.name,conversation=doc.name,account=doc.account,payload_json=json.dumps(payload),requester=frappe.session.user,origin_key=origin_key,source_doctype=source_doctype,source_name=source_name,rule=rule,run=run,next_attempt_at=utcnow(),template_hash=template_hash,input_hash=input_hash,rule_version=rule_version(rule) if rule else None,deleted_source=int(deleted_source),state='Ready',attempt_count=0)
        if conversation_flow:
            set_record_values(intent.doctype,intent.name,dict(conversation_flow=conversation_flow,flow_version=flow_version,flow_session=flow_session,flow_generation=flow_generation))
    except (frappe.DuplicateEntryError,frappe.UniqueValidationError):
        frappe.db.rollback(save_point='intent_insert')
        existing=frappe.db.get_value('WhatsApp Outbox',{'request_key':request_key},['name','payload_hash','message','state','conversation'],as_dict=True)
        if not existing or existing.payload_hash!=payload_hash:raise
        conversation(existing.conversation)
        return {'outbox':existing.name,'message':existing.message,'state':existing.state}
    except Exception:
        frappe.db.rollback(save_point='intent_insert')
        raise
    changed(doc,last_sequence=sequence,last_message=rendered[:240],last_activity_at=utcnow())
    frappe.enqueue('whatsapp_messaging.messaging.outbox.dispatch',name=intent.name,enqueue_after_commit=True)
    return {'outbox':intent.name,'message':message.name,'state':intent.state}


@frappe.whitelist(methods=['POST'])
def send(conversation_name,request_id,body='',template=None,parameters=None,file_id=None,reply_to=None):
    doc=conversation(conversation_name,locked=True)
    from .flows import pause_session
    pause_session(doc,'A team member sent a reply')
    return create_intent(conversation_name,request_id,body,template,parameters,file_id,reply_to)


def set_outcome(intent,state,reason=None,code=None):
    set_record_values('WhatsApp Outbox',intent.name,{'state':state,'lease_until':None,'lease_owner':None,'error_reason':reason,'error_code':code})
    message_status={'Ready':'Queued','Retry wait':'Queued','Claimed':'Queued'}.get(state,state)
    set_record_values('WhatsApp Message',intent.message,'status',message_status)
    from .common import notify
    notify(intent.conversation)


def validate_dispatch(intent):
    require_outbound_enabled()
    require_send_role()
    sender=account(intent.account,enabled=True)
    doc=conversation(intent.conversation)
    peer=frappe.get_doc('WhatsApp Peer',doc.peer)
    if peer.suppressed:frappe.throw('Recipient is suppressed')
    if intent.get('conversation_flow'):
        from .flows import validate_dispatch as validate_flow_dispatch
        validate_flow_dispatch(intent,doc)
    if intent.deleted_source:
        if not frappe.has_permission(intent.source_doctype,'read'):frappe.throw('Source type is no longer readable',frappe.PermissionError)
    elif intent.source_doctype and intent.source_name:
        frappe.get_doc(intent.source_doctype,intent.source_name).check_permission('read')
    if intent.rule:
        from .campaigns import load
        rule=load(intent.rule)
        if rule.disable or str(rule.modified)!=intent.rule_version:frappe.throw('The originating rule was disabled or changed')
        from .field_policy import validate_static_access
        validate_static_access(rule.message_preview)
        if rule.get('delivery_mode') == 'Meta-approved template':
            from .template_editor import ensure_sendable
            paths = ensure_sendable(rule)
            # Imported Meta wording uses numbered tokens; its real field paths
            # live in the mapping rows and must also be rechecked at dispatch.
            validate_static_access(' '.join('{{' + path + '}}' for path in paths))
        if intent.run:
            run=frappe.get_doc('WhatsApp Automation Run',intent.run)
            if run.state in ('Paused','Cancelled','Skipped'):frappe.throw('The originating run is paused or cancelled')
            if run.kind in ('Schedule','Event') and (not rule.automation_active or not frappe.db.get_single_value('WhatsApp Settings','enable_automation',cache=False)):frappe.throw('The originating automation is inactive')
        if intent.source_doctype and intent.source_name and not intent.deleted_source:
            from whatsapp_messaging.utils import doc_matches_filters
            source=frappe.get_doc(intent.source_doctype,intent.source_name)
            if not doc_matches_filters(source,rule.query_filters):frappe.throw('The source no longer matches this rule')
            if rule.template_event=='Date Reminder':
                from .automation import validate_date_reminder,reminder_matches,origin_key
                validate_date_reminder(rule)
                if not intent.run or not reminder_matches(rule,source) or origin_key(rule,source,frappe.get_doc('WhatsApp Automation Run',intent.run),peer.provider_identity)!=intent.origin_key:
                    frappe.throw('The reminder date changed or is no longer due')
    payload=parsed(intent.payload_json,{})
    if payload.get('to')!=peer.provider_identity:frappe.throw('Recipient identity changed')
    if payload.get('type')=='template':
        message=frappe.get_doc('WhatsApp Message',intent.message)
        template=frappe.get_doc('WhatsApp Approved Template',message.approved_template)
        template.check_permission('read')
        if not peer.consent_recorded or template.waba_id!=sender.waba_id or template.approval_status!='APPROVED' or not template.supported or template.schema_hash!=intent.template_hash:
            frappe.throw('The approved template or recipient eligibility changed')
    elif not window_open(doc):frappe.throw('The reply window has expired')
    return sender,doc,payload


def dispatch(name):
    """Worker entry; short claim transaction, then bounded network I/O."""
    if not frappe.db.get_single_value('WhatsApp Settings','enable_outbound_messages',cache=False):return
    base=frappe.db.get_value('WhatsApp Outbox',name,['account','requester','run'],as_dict=True)
    if not base:return
    if not frappe.db.get_value('User',base.requester,'enabled') or not set(frappe.get_roles(base.requester)).intersection(('Whatsapp Editor','Whatsapp Admin','System Manager')):
        intent=lock('WhatsApp Outbox',name)
        if intent.state in ELIGIBLE_STATES:set_outcome(intent,'Held','Execution user no longer has messaging access')
        frappe.db.commit();return
    with as_user(base.requester):
        sender=lock('WhatsApp Phone Number ID',base.account)
        origin_run=lock('WhatsApp Automation Run',base.run) if base.run else None
        if origin_run and origin_run.schedule:lock('WhatsApp Schedule',origin_run.schedule)
        if origin_run and origin_run.kind in ('Schedule','Event') and not frappe.db.get_single_value('WhatsApp Settings','enable_automation',cache=False):return
        intent=lock('WhatsApp Outbox',name)
        now=utcnow()
        if intent.state not in ELIGIBLE_STATES or (intent.next_attempt_at and get_datetime(intent.next_attempt_at)>now):return
        if sender.dispatch_lease_until and get_datetime(sender.dispatch_lease_until)>now:return
        doc=conversation(intent.conversation,locked=True)
        # Conservative default pacing: at most one request/account/second and one/peer/six seconds.
        if sender.last_dispatch_at and get_datetime(sender.last_dispatch_at)+timedelta(seconds=1)>now:return
        if doc.last_outbound_at and get_datetime(doc.last_outbound_at)+timedelta(seconds=6)>now:return
        if intent.run and frappe.db.get_value('WhatsApp Automation Run',intent.run,'state')=='Paused':return
        if intent.run:
            schedule=frappe.db.get_value('WhatsApp Automation Run',intent.run,'schedule')
            if schedule and frappe.db.get_value('WhatsApp Schedule',schedule,'state')=='Paused':return
        try:sender,doc,payload=validate_dispatch(intent)
        except (frappe.ValidationError,frappe.PermissionError,frappe.DoesNotExistError):
            set_outcome(intent,'Held','Send eligibility changed; review the source, account and recipient')
            frappe.db.commit();return
        count=int(intent.attempt_count or 0)+1
        lease=frappe.generate_hash(length=20)
        set_record_values('WhatsApp Outbox',name,{'state':'Claimed','lease_owner':lease,'lease_until':now+timedelta(seconds=120),'attempt_count':count,'network_started':0})
        set_record_values(sender.doctype,sender.name,{'dispatch_lease_until':now+timedelta(seconds=120),'last_dispatch_at':now})
        attempt=insert('WhatsApp Send Attempt',attempt_key=digest(name,count),outbox=name,attempt_number=count,started_at=now,payload_hash=intent.payload_hash,outcome='Claimed')
        frappe.db.commit()
        network_started=False
        try:
            attachments=frappe.get_all('WhatsApp Attachment',filters={'message':intent.message},pluck='name')
            for attachment_name in attachments:
                attachment=frappe.get_doc('WhatsApp Attachment',attachment_name)
                if attachment.state!='Ready':frappe.throw('Attachment is unavailable')
                provider_media_id=media.upload(attachment,sender)
                payload[payload['type']]['id']=provider_media_id
                if payload['type']=='document':payload['document']['filename']=attachment.file_name
            # Recheck the gate and window after media upload, immediately before sending.
            validate_dispatch(intent)
            url=get_cloud_api_url(sender.name)
            headers=get_headers(sender.name)
            payload['biz_opaque_callback_data']=name
            set_record_values('WhatsApp Outbox',name,'network_started',1)
            set_record_values('WhatsApp Conversation',doc.name,'last_outbound_at',utcnow())
            frappe.db.commit();network_started=True
            response=requests.post(url,json=payload,headers=headers,timeout=(5,30))
            data=response.json()
            if response.status_code>=500:
                state='Unknown';code=str(response.status_code)
            elif response.status_code==429 and count<3:
                state='Retry wait';code=str(data.get('error',{}).get('code','429'))
                set_record_values('WhatsApp Outbox',name,'next_attempt_at',utcnow()+timedelta(seconds=60*(2**(count-1))))
            elif not response.ok:
                state='Failed';code=str(data.get('error',{}).get('code',response.status_code))
            elif data.get('messages') and data['messages'][0].get('id'):
                provider_id=str(data['messages'][0]['id'])[:200]
                state='Held' if data['messages'][0].get('message_status')=='held_for_quality_assessment' else 'Accepted';code=None
                set_record_values('WhatsApp Message',intent.message,{'provider_message_id':provider_id,'provider_key':digest(sender.name,provider_id)})
                set_record_values('WhatsApp Outbox',name,'accepted_at',utcnow())
                set_record_values(attempt.doctype,attempt.name,'provider_message_id',provider_id)
            else:state='Unknown';code='unrecognized_response'
            set_outcome(intent,state,'Provider request requires review' if state in ('Failed','Unknown','Held') else None,code)
            set_record_values(attempt.doctype,attempt.name,{'outcome':state,'finished_at':utcnow(),'http_status':response.status_code,'error_code':code})
            from .webhooks import reconcile_statuses
            reconcile_statuses(intent.message)
        except Exception:
            # Never copy exception strings, HTTP bodies or credentials into operator logs.
            frappe.db.rollback()
            state='Unknown' if network_started else 'Held'
            set_outcome(intent,state,'Provider response uncertain; do not retry automatically' if network_started else 'Attachment or send eligibility requires review')
            set_record_values(attempt.doctype,attempt.name,{'outcome':state,'finished_at':utcnow()})
        finally:
            set_record_values(sender.doctype,sender.name,'dispatch_lease_until',None)
            frappe.db.commit()


@frappe.whitelist(methods=['POST'])
def cancel(name,reason):
    require_send_role()
    intent=lock('WhatsApp Outbox',name);conversation(intent.conversation)
    if intent.requester!=frappe.session.user:
        require_supervisor()
    if intent.state not in ('Ready','Retry wait','Held') or intent.network_started:frappe.throw('This send can no longer be cancelled')
    if not str(reason or '').strip():frappe.throw('Provide a cancellation reason')
    set_outcome(intent,'Cancelled')
    set_record_values(intent.doctype,name,'cancel_reason',str(reason)[:140])
    insert('WhatsApp Conversation Activity',conversation=intent.conversation,actor=frappe.session.user,action='Cancel',details='Undispatched message cancelled')
    return {'state':'Cancelled'}


@frappe.whitelist(methods=['POST'])
def retry(name):
    require_send_role();require_outbound_enabled()
    intent=lock('WhatsApp Outbox',name);conversation(intent.conversation)
    if intent.requester!=frappe.session.user:require_supervisor()
    # A known provider rejection is safe; Held may be accepted and is not safe to retry.
    if intent.state!='Failed' or frappe.db.get_value('WhatsApp Message',intent.message,'provider_message_id'):frappe.throw('Only a confirmed unaccepted request can be retried; compose a new message for delivery failures')
    with as_user(intent.requester):validate_dispatch(intent)
    set_outcome(intent,'Ready')
    set_record_values(intent.doctype,name,{'network_started':0,'next_attempt_at':utcnow()})
    insert('WhatsApp Conversation Activity',conversation=intent.conversation,actor=frappe.session.user,action='Retry',details='Confirmed failed request queued again')
    frappe.enqueue('whatsapp_messaging.messaging.outbox.dispatch',name=name,enqueue_after_commit=True)
    return {'state':'Ready'}


def sweep(conversation_flows_only=False):
    now=utcnow()
    scope={'conversation_flow':['is','set']} if conversation_flows_only else {}
    for name in frappe.get_all('WhatsApp Outbox',filters={**scope,'state':'Claimed','lease_until':['<',now]},pluck='name',limit_page_length=100):
        intent=lock('WhatsApp Outbox',name)
        if intent.state=='Claimed' and intent.lease_until and get_datetime(intent.lease_until)<now:
            set_outcome(intent,'Unknown' if intent.network_started else 'Ready','Worker lease expired')
    for name in frappe.get_all('WhatsApp Outbox',filters={**scope,'state':['in',ELIGIBLE_STATES],'next_attempt_at':['<=',now]},pluck='name',limit_page_length=20,order_by='next_attempt_at asc'):
        frappe.enqueue('whatsapp_messaging.messaging.outbox.dispatch',name=name,enqueue_after_commit=True)
