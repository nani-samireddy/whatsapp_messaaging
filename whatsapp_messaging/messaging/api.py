"""Permission-aware workspace summaries and operational projections."""
import frappe
from whatsapp_messaging.send_security import require_send_role
from .common import account, digest, page_size, parsed, require_supervisor, supervisor, utcnow


def count(doctype,filters=None):
    if not frappe.has_permission(doctype,'read'):return 0
    rows=frappe.get_list(doctype,filters=filters or {},fields=[{'COUNT':'name','as':'total'}],order_by=None)
    return int(rows[0].total or 0) if rows else 0


@frappe.whitelist()
def bootstrap():
    require_send_role()
    accounts=frappe.get_list('WhatsApp Phone Number ID',fields=['name','label','display_phone'],order_by='label asc',limit_page_length=200)
    return {'accounts':accounts,'user':frappe.session.user,'supervisor':supervisor(),'manager':'System Manager' in frappe.get_roles(),'outbound_enabled':bool(frappe.db.get_single_value('WhatsApp Settings','enable_outbound_messages',cache=False)),'automation_enabled':bool(frappe.db.get_single_value('WhatsApp Settings','enable_automation',cache=False)),'inbound_enabled':bool(frappe.db.get_single_value('WhatsApp Settings','enable_inbound',cache=False)),'timezone':frappe.utils.get_system_timezone()}


@frappe.whitelist()
def overview(section='messaging'):
    info=bootstrap();cards=[]
    def card(label,doctype,filters=None,route=None,options=None):
        cards.append({'label':label,'value':count(doctype,filters),'route':route or ['List',doctype],'route_options':options if options is not None else filters or {}})
    if section=='messaging':
        card('Open conversations','WhatsApp Conversation',{'account':['is','set'],'workflow_status':'Open'},['whatsapp-inbox'],{'status':'Open'})
        card('Unassigned','WhatsApp Conversation',{'account':['is','set'],'assigned_to':['is','not set']},['whatsapp-inbox'],{'assignment':'Unassigned'})
        # Read state is per user; use permission-filtered conversation SQL as the boundary.
        from frappe.model.db_query import DatabaseQuery
        query=DatabaseQuery('WhatsApp Conversation').execute(fields=['name'],filters={'account':['is','set']},run=False)
        rows=frappe.db.sql(f"SELECT COUNT(DISTINCT m.conversation) FROM `tabWhatsApp Message` m LEFT JOIN `tabWhatsApp Conversation Read` r ON r.conversation=m.conversation AND r.user=%s WHERE m.direction='Inbound' AND m.sequence>COALESCE(r.last_read_sequence,0) AND m.conversation IN ({query.replace('%','%%')})",frappe.session.user)
        cards.append({'label':'My unread','value':int(rows[0][0]),'route':['whatsapp-inbox'],'route_options':{'assignment':'Unread'}})
        card('Failed outgoing','WhatsApp Message',{'direction':'Outbound','status':'Failed'})
    elif section=='automation':
        card('Templates','WhatsApp Message Template')
        card('Conversation Flows','WhatsApp Conversation Flow')
        if frappe.db.has_table('WhatsApp Campaign'):card('Campaigns','WhatsApp Campaign')
        card('Active schedules','WhatsApp Schedule',{'state':'Active'})
        card('Failed runs','WhatsApp Automation Run',{'state':'Failed'})
        if supervisor():card('Active campaigns','WhatsApp Automation Run',{'kind':'Campaign','state':['in',['Ready','Expanding','Paused']]},['whatsapp-automations'],{'kind':'Campaign'})
    elif section=='administration':
        require_supervisor()
        card('Configured senders','WhatsApp Phone Number ID')
        card('Unknown outcomes','WhatsApp Outbox',{'state':'Unknown'})
        card('Failed webhook events','WhatsApp Webhook Event',{'state':['in',['Failed','Quarantined']]})
        card('Held sends','WhatsApp Outbox',{'state':'Held'})
    else:frappe.throw('Unknown workspace section')
    return {**info,'cards':cards}


@frappe.whitelist()
def agents():
    require_send_role()
    users=set(frappe.get_all('Has Role',filters={'role':['in',['Whatsapp Admin','Whatsapp Editor','System Manager']],'parenttype':'User'},pluck='parent'))
    return frappe.get_all('User',filters={'name':['in',list(users)],'enabled':1,'user_type':'System User'},fields=['name','full_name'],order_by='full_name asc',limit_page_length=200)


@frappe.whitelist()
def runs(kind=None,state=None,rule=None,limit=40,start=0):
    require_send_role()
    filters={}
    if kind:
        if kind=='Campaign':require_supervisor()
        filters['kind']=kind
    if state:filters['state']=state
    if rule:
        from .campaigns import load
        load(rule)
        filters['rule']=rule
    rows=frappe.get_list('WhatsApp Automation Run',filters=filters,fields=['name','rule','kind','state','run_as','due_at','records_selected','records_processed','messages_created','records_excluded','last_error','creation'],order_by='creation desc',limit_start=max(0,int(start)),limit_page_length=page_size(limit))
    for row in rows:
        row['delivery']={status:count('WhatsApp Outbox',{'run':row.name,'state':status}) for status in ('Ready','Claimed','Accepted','Held','Retry wait','Failed','Unknown','Cancelled')}
    return rows


@frappe.whitelist()
def run_detail(name):
    require_send_role()
    run=frappe.get_doc('WhatsApp Automation Run',name);run.check_permission('read')
    if run.kind=='Campaign':require_supervisor()
    return {'name':run.name,'state':run.state,'intents':frappe.get_list('WhatsApp Outbox',filters={'run':name},fields=['name','message','conversation','state','error_code','error_reason','attempt_count'],limit_page_length=100)}


def run_query(user=None):
    user=user or frappe.session.user
    if {'System Manager','Whatsapp Admin'}.intersection(frappe.get_roles(user)):return ''
    return "`tabWhatsApp Automation Run`.kind!='Campaign' AND `tabWhatsApp Automation Run`.run_as="+frappe.db.escape(user)


def run_permission(doc,ptype,user=None):
    user=user or frappe.session.user
    if {'System Manager','Whatsapp Admin'}.intersection(frappe.get_roles(user)):return ptype in ('read','select')
    return bool(doc.kind!='Campaign' and doc.run_as==user and 'Whatsapp Editor' in frappe.get_roles(user)) if ptype in ('read','select') else False


def read_query(user=None):
    return '`tabWhatsApp Conversation Read`.user='+frappe.db.escape(user or frappe.session.user)


def read_permission(doc,ptype,user=None):
    return doc.user==(user or frappe.session.user) if ptype in ('read','select') else False


@frappe.whitelist()
def record_conversations(doctype,docname):
    require_send_role()
    frappe.get_doc(doctype,docname).check_permission('read')
    names=frappe.get_all('WhatsApp Record Link',filters={'reference_doctype':doctype,'reference_name':docname},pluck='conversation')
    if not names:return []
    return frappe.get_list('WhatsApp Conversation',filters={'name':['in',names]},fields=['name','account','recipient'],limit_page_length=100)


def has_app_permission():
    return frappe.session.user!='Guest' and bool({'System Manager','Whatsapp Admin','Whatsapp Editor'}.intersection(frappe.get_roles()))
