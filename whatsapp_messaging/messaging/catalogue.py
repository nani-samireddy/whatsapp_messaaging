import json
import re

import frappe
from whatsapp_messaging.messaging.naming import set_record_values
import requests
from whatsapp_messaging.send_security import require_outbound_enabled, require_send_role
from whatsapp_messaging.utils.config import get_headers
from .common import account, digest, insert, parsed, require_supervisor, service_write, utcnow
from . import template_framing as framing


def normalize(item):
    components=item.get('components',[])
    body=next((c.get('text','') for c in components if c.get('type')=='BODY'),'')
    parameters=re.findall(r'{{\s*([^{}]+)\s*}}',body)
    numeric=sorted(set(parameters),key=lambda x:int(x) if x.isdigit() else -1)
    supported=bool(body) and framing.supported(components) and numeric==[str(i) for i in range(1,len(numeric)+1)] and item.get('parameter_format','POSITIONAL')=='POSITIONAL'
    return {'body':body,'parameters_json':json.dumps(numeric),'components_json':json.dumps(components),'supported':int(supported),'schema_hash':digest(components,item.get('status'),item.get('language'))}


@frappe.whitelist()
def list_templates(account_name):
    sender=account(account_name)
    return frappe.get_list('WhatsApp Approved Template',filters={'waba_id':sender.waba_id or '', 'approval_status':'APPROVED','supported':1},fields=['name','template_name','language','body','components_json','parameters_json','schema_hash'],order_by='template_name asc',limit_page_length=200)


@frappe.whitelist(methods=['POST'])
def sync(account_name):
    require_supervisor();require_outbound_enabled()
    sender=account(account_name,enabled=True)
    if not re.fullmatch(r'[0-9]+',sender.waba_id or ''):frappe.throw('Configure the WABA identifier first')
    version=frappe.db.get_single_value('WhatsApp Settings','whatsapp_api_version')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+',version or ''):frappe.throw('Invalid API version')
    url=f'https://graph.facebook.com/{version}/{sender.waba_id}/message_templates'
    after=None;seen=set();count=0;started=utcnow()
    # Pagination cursors are opaque parameters. Provider next URLs are never followed.
    while True:
        params={'limit':100,'fields':'id,name,language,status,category,components,parameter_format,rejected_reason'}
        if after:params['after']=after
        response=requests.get(url,headers=get_headers(sender.name),params=params,timeout=(5,20),allow_redirects=False)
        if response.status_code >= 300:
            from .template_editor import action_error
            frappe.throw(action_error(response,sender))
        data=response.json()
        for item in data.get('data',[]):
            key=digest(sender.waba_id,item['name'],item['language'])
            upsert(sender.waba_id,item,sync_started=started)
            seen.add(key);count+=1
        paging=data.get('paging',{});after=paging.get('cursors',{}).get('after') if paging.get('next') else None
        if not after:break
        if count>10000:frappe.throw('Template catalogue exceeds the supported sync size')
    # Templates missing from a complete snapshot become unavailable.
    for row in frappe.get_all('WhatsApp Approved Template',filters={'waba_id':sender.waba_id},fields=['name','catalogue_key','reviewed_at']):
        if row.reviewed_at and frappe.utils.get_datetime(row.reviewed_at)>started:continue
        if row.catalogue_key not in seen:
            set_record_values('WhatsApp Approved Template',row.name,'approval_status','UNAVAILABLE')
            from .template_editor import refresh_related
            refresh_related(row.name)
    return {'synced':count}


def upsert(waba_id,item,sync_started=None):
    from frappe.utils import get_datetime
    from .template_editor import clean_detail,refresh_related
    key=digest(waba_id,item['name'],item['language'])
    name=frappe.db.get_value('WhatsApp Approved Template',{'catalogue_key':key},'name')
    previous=frappe.get_doc('WhatsApp Approved Template',name) if name else None
    if previous and sync_started and previous.reviewed_at and get_datetime(previous.reviewed_at)>sync_started:
        return previous.name
    values=dict(waba_id=waba_id,provider_template_id=str(item['id']),template_name=item['name'],language=item['language'],
        approval_status=item['status'],category=item.get('category'),synced_at=utcnow(),**normalize(item))
    reason=clean_detail(item.get('rejected_reason') or '') or None
    values['rejection_reason']=reason if item['status']=='REJECTED' else None
    if item['status']!='REJECTED' or not previous or previous.rejection_reason!=reason:
        values.update(rejection_detail=None,recommendation=None)
    if name:set_record_values('WhatsApp Approved Template',name,values)
    else:name=insert('WhatsApp Approved Template',catalogue_key=key,**values).name
    refresh_related(name)
    return name


def review_update(waba_id,value,timestamp):
    """Called only after the existing signed, durable webhook ingress."""
    from frappe.utils import get_datetime
    from .template_editor import clean_detail,refresh_related
    from .webhooks import provider_time
    if not frappe.db.exists('WhatsApp Phone Number ID',{'waba_id':waba_id,'enabled':1}):
        return False
    occurred=provider_time(timestamp)
    provider_id=str(value.get('message_template_id') or '')
    if not re.fullmatch(r'[0-9]+',provider_id):raise ValueError('Invalid template ID')
    name=frappe.db.get_value('WhatsApp Approved Template',{'waba_id':waba_id,'provider_template_id':provider_id},'name')
    if not name:
        if not value.get('message_template_name') or not value.get('message_template_language'):raise ValueError('Incomplete template review')
        name=upsert(waba_id,dict(id=provider_id,name=value['message_template_name'],language=value['message_template_language'].replace('-','_'),
            status=value.get('event','UNAVAILABLE'),category=value.get('message_template_category'),components=[]))
    doc=frappe.get_doc('WhatsApp Approved Template',name,for_update=True)
    if doc.reviewed_at and get_datetime(doc.reviewed_at)>=occurred:return True
    event=value.get('event')
    if event=='UNARCHIVED':event='UNAVAILABLE' # Refresh status before claiming approval.
    if event not in ('APPROVED','REJECTED','PENDING','PAUSED','DISABLED','ARCHIVED','DELETED','PENDING_DELETION','UNAVAILABLE'):
        return True
    detail=value.get('rejection_info') or {}
    values=dict(approval_status=event,reviewed_at=occurred,synced_at=utcnow(),
        rejection_reason=clean_detail(value.get('reason')) if event=='REJECTED' else None,
        rejection_detail=clean_detail(detail.get('reason')) if event=='REJECTED' else None,
        recommendation=clean_detail(detail.get('recommendation')) if event=='REJECTED' else None,
        schema_hash=digest(parsed(doc.components_json,[]),event,doc.language))
    if value.get('message_template_category'):values['category']=value['message_template_category']
    set_record_values(doc.doctype,name,values)
    refresh_related(name)
    return True


def template_payload(name,sender,values):
    doc=frappe.get_doc('WhatsApp Approved Template',name);doc.check_permission('read')
    if doc.waba_id!=sender.waba_id or doc.approval_status!='APPROVED' or not doc.supported:frappe.throw('This template is unavailable or unsupported')
    values=parsed(values,[])
    if not isinstance(values,list) or len(values)!=len(parsed(doc.parameters_json,[])):frappe.throw('Provide every template parameter')
    values=[str(v) for v in values]
    if any(not v.strip() or len(v)>1024 for v in values):frappe.throw('Invalid template parameter')
    payload={'name':doc.template_name,'language':{'code':doc.language}}
    if values:payload['components']=[{'type':'body','parameters':[{'type':'text','text':v} for v in values]}]
    return payload,doc.schema_hash,doc


def rendered_text(doc, values):
    values = [str(value) for value in values]
    body = re.sub(r'{{\s*(\d+)\s*}}',
        lambda match: values[int(match[1])-1] if 0 < int(match[1]) <= len(values) else match[0], doc.body or '')
    return framing.compose(body, *framing.texts(parsed(doc.components_json, [])))
