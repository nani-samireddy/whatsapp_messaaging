"""Signed durable ingress; no site-wide CSRF exemption or unauthenticated data APIs."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import frappe
from whatsapp_messaging.messaging.naming import set_record_values
from frappe.utils import get_datetime
from werkzeug.wrappers import Response
from .common import changed, digest, insert, lock, parsed, utcnow
from .inbox import ensure_conversation, ensure_peer

MAX_BODY=3*1024*1024


def valid_signature(raw,signature,secret):
    return bool(secret and signature and hmac.compare_digest('sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest(),signature))


@frappe.whitelist(allow_guest=True,methods=['GET','POST'])
def receive(**kwargs):
    if not frappe.db.get_single_value('WhatsApp Settings','enable_inbound',cache=False):return Response('Webhook disabled',status=503)
    settings=frappe.get_doc('WhatsApp Settings')
    if frappe.request.method=='GET':
        args=frappe.request.args
        token=settings.get_password('verify_token',raise_exception=False)
        if args.get('hub.mode')!='subscribe' or not token or not hmac.compare_digest(token,args.get('hub.verify_token','')):return Response('Invalid verification',status=403)
        return Response(args.get('hub.challenge',''),mimetype='text/plain')
    if (frappe.request.content_length or 0)>MAX_BODY:return Response('Payload too large',status=413)
    raw=frappe.request.get_data()
    if len(raw)>MAX_BODY:return Response('Payload too large',status=413)
    if not valid_signature(raw,frappe.request.headers.get('X-Hub-Signature-256'),settings.get_password('app_secret',raise_exception=False)):return Response('Invalid signature',status=403)
    try:
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get('object')!='whatsapp_business_account' or not isinstance(data.get('entry'),list):raise ValueError()
    except (ValueError,TypeError):return Response('Invalid payload',status=400)
    key=digest(settings.meta_app_id or 'default',hashlib.sha256(raw).hexdigest())
    if frappe.db.exists('WhatsApp Webhook Event',{'event_key':key}):return Response('OK')
    frappe.db.savepoint('receipt_insert')
    try:receipt=insert('WhatsApp Webhook Event',event_key=key,payload_json=raw.decode(),received_at=utcnow(),state='Pending',next_attempt_at=utcnow(),attempt_count=0)
    except (frappe.DuplicateEntryError,frappe.UniqueValidationError):
        frappe.db.rollback(save_point='receipt_insert');return Response('OK')
    frappe.enqueue('whatsapp_messaging.messaging.webhooks.process_event',name=receipt.name,enqueue_after_commit=True)
    return Response('OK')


def provider_time(value):
    result=datetime.fromtimestamp(int(value),timezone.utc).replace(tzinfo=None)
    if result>utcnow()+timedelta(minutes=5):raise ValueError('Future provider timestamp')
    return result


def inbound(sender,item,display_name=None):
    provider_id=str(item['id'])[:200]
    key=digest(sender.name,provider_id)
    if frappe.db.exists('WhatsApp Message',{'provider_key':key}):return
    occurred=provider_time(item['timestamp'])
    peer=ensure_peer(item['from'],sender,display_name)
    doc=lock('WhatsApp Conversation',ensure_conversation(sender,peer).name)
    if frappe.db.exists('WhatsApp Message',{'provider_key':key}):return
    kind=item.get('type','unknown')
    body=item.get('text',{}).get('body','') if kind=='text' else item.get(kind,{}).get('caption','')
    if kind not in ('text','image','document'):body='Unsupported incoming message ('+str(kind)[:40]+')'
    seq=int(doc.last_sequence or 0)+1
    message=insert('WhatsApp Message',conversation=doc.name,account=sender.name,peer=peer.name,direction='Inbound',message_type=kind,message=str(body)[:65535],status='Received',provider_message_id=provider_id,provider_key=key,sequence=seq,sequence_key=digest(doc.name,seq),provider_at=occurred,received_at=utcnow(),reply_to=item.get('context',{}).get('id'))
    if kind in ('image','document'):
        attachment_data=item.get(kind,{})
        mime=attachment_data.get('mime_type','')
        supported=mime in ('image/jpeg','image/png','application/pdf')
        attachment=insert('WhatsApp Attachment',message=message.name,account=sender.name,provider_media_id=str(attachment_data.get('id',''))[:200],provider_hash=attachment_data.get('sha256'),mime_type=mime,file_name=str(attachment_data.get('filename') or 'Attachment')[:140],state='Pending' if supported else 'Blocked',error_reason=None if supported else 'Unsupported attachment type')
        if supported:frappe.enqueue('whatsapp_messaging.messaging.media.download_inbound',name=attachment.name,enqueue_after_commit=True)
    latest=max(get_datetime(doc.last_inbound_at),occurred) if doc.last_inbound_at else occurred
    activity=max(get_datetime(doc.last_activity_at),occurred) if doc.last_activity_at else occurred
    changed(doc,last_sequence=seq,last_message=str(body)[:240],last_activity_at=activity,last_inbound_at=latest,window_expires_at=latest+timedelta(hours=24),workflow_status='Open')


def status_event(sender,item):
    occurred=provider_time(item['timestamp'])
    provider_id=str(item['id'])[:200];status=str(item['status'])[:80]
    error=item.get('errors') or []
    key=digest(sender.name,provider_id,status,str(occurred),error)
    if frappe.db.exists('WhatsApp Status Event',{'event_key':key}):return
    event=insert('WhatsApp Status Event',event_key=key,account=sender.name,provider_message_id=provider_id,provider_status=status,provider_at=occurred,error_code=str(error[0].get('code',''))[:100] if error else None,correlation_key=str(item.get('biz_opaque_callback_data') or '')[:140])
    apply_status(event)


def apply_status(event):
    name=frappe.db.get_value('WhatsApp Message',{'provider_key':digest(event.account,event.provider_message_id)},'name')
    if not name and event.correlation_key:
        intent=frappe.db.get_value('WhatsApp Outbox',{'name':event.correlation_key,'account':event.account,'network_started':1},['name','message'],as_dict=True)
        if intent:
            name=intent.message
            old=frappe.db.get_value('WhatsApp Message',name,'provider_message_id')
            if old and old!=event.provider_message_id:return
            set_record_values('WhatsApp Message',name,{'provider_message_id':event.provider_message_id,'provider_key':digest(event.account,event.provider_message_id)})
    if not name:return
    message=frappe.get_doc('WhatsApp Message',name)
    if message.direction!='Outbound':return
    lock('WhatsApp Conversation',message.conversation)
    message.reload()
    set_record_values(event.doctype,event.name,'message',name)
    ranks={'Queued':0,'Unknown':0,'Held':0,'Failed':0,'Accepted':0,'Sent':1,'Delivered':2,'Read':3}
    target={'sent':'Sent','delivered':'Delivered','read':'Read','failed':'Failed'}.get(event.provider_status)
    if target=='Sent' and message.status=='Failed' and message.status_at and get_datetime(event.provider_at)<=get_datetime(message.status_at):return
    if target and ((target=='Failed' and message.status not in ('Delivered','Read') and (not message.status_at or get_datetime(event.provider_at)>=get_datetime(message.status_at))) or (target!='Failed' and ranks.get(target,0)>ranks.get(message.status,0))):
        set_record_values(message.doctype,name,{'status':target,'status_at':event.provider_at})
    message.reload()
    for row in frappe.get_all('WhatsApp Outbox',filters={'message':name},fields=['name','state']):
        if target in ('Sent','Delivered','Read'):
            set_record_values('WhatsApp Outbox',row.name,{'state':'Accepted','error_reason':None,'lease_until':None})
        elif target=='Failed' and message.status=='Failed':
            set_record_values('WhatsApp Outbox',row.name,{'state':'Failed','error_code':event.error_code,'error_reason':'Provider reported delivery failure','lease_until':None})
    from .common import notify
    notify(message.conversation)


def reconcile_statuses(message_name):
    message=frappe.get_doc('WhatsApp Message',message_name)
    if not message.provider_message_id:return
    for name in frappe.get_all('WhatsApp Status Event',filters={'account':message.account,'provider_message_id':message.provider_message_id},pluck='name',order_by='provider_at asc'):
        apply_status(frappe.get_doc('WhatsApp Status Event',name))


def process_event(name):
    receipt=lock('WhatsApp Webhook Event',name)
    if receipt.state in ('Processed','Quarantined'):return
    attempts=int(receipt.attempt_count or 0)+1
    if not frappe.db.get_single_value('WhatsApp Settings','enable_inbound',cache=False):return
    frappe.db.savepoint('process_receipt')
    try:
        quarantined=False
        for entry in parsed(receipt.payload_json,{})['entry']:
            for change in entry.get('changes',[]):
                value=change.get('value',{})
                if change.get('field')=='message_template_status_update':
                    from .catalogue import review_update
                    if not review_update(str(entry.get('id','')),value,entry.get('time')):quarantined=True
                    continue
                if change.get('field')!='messages':continue
                external=str(value.get('metadata',{}).get('phone_number_id',''))
                names=frappe.get_all('WhatsApp Phone Number ID',filters={'phone_number_id':external,'waba_id':str(entry.get('id','')),'enabled':1},pluck='name')
                if len(names)!=1:quarantined=True;continue
                sender=frappe.get_doc('WhatsApp Phone Number ID',names[0])
                contacts={c.get('wa_id'):c.get('profile',{}).get('name') for c in value.get('contacts',[])}
                for item in value.get('messages',[]):inbound(sender,item,contacts.get(item.get('from')))
                for item in value.get('statuses',[]):status_event(sender,item)
        set_record_values(receipt.doctype,name,{'state':'Quarantined' if quarantined else 'Processed','processed_at':utcnow(),'attempt_count':attempts,'error_reason':'Unconfigured or ambiguous sender account' if quarantined else None})
    except Exception:
        frappe.db.rollback(save_point='process_receipt')
        set_record_values(receipt.doctype,name,{'state':'Failed' if attempts<5 else 'Quarantined','attempt_count':attempts,'next_attempt_at':utcnow()+timedelta(seconds=60*2**min(attempts,6)),'error_reason':'Event processing requires review'})
    frappe.db.commit()


@frappe.whitelist(methods=['POST'])
def replay(name):
    from .common import require_supervisor
    require_supervisor()
    receipt=lock('WhatsApp Webhook Event',name)
    if receipt.state not in ('Failed','Quarantined'):frappe.throw('This event does not require replay')
    set_record_values(receipt.doctype,name,{'state':'Pending','attempt_count':0,'next_attempt_at':utcnow()})
    frappe.enqueue('whatsapp_messaging.messaging.webhooks.process_event',name=name,enqueue_after_commit=True)
    return {'queued':True}


def sweep():
    if not frappe.db.get_single_value('WhatsApp Settings','enable_inbound',cache=False):return
    for name in frappe.get_all('WhatsApp Webhook Event',filters={'state':['in',['Pending','Failed']],'next_attempt_at':['<=',utcnow()]},pluck='name',limit_page_length=50):
        frappe.enqueue('whatsapp_messaging.messaging.webhooks.process_event',name=name,enqueue_after_commit=True)
    for name in frappe.get_all('WhatsApp Attachment',filters={'state':'Pending'},pluck='name',limit_page_length=20):
        frappe.enqueue('whatsapp_messaging.messaging.media.download_inbound',name=name,enqueue_after_commit=True)
