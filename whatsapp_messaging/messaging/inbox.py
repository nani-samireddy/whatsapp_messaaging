"""Authenticated inbox operations. Assignment is workflow, not visibility."""
import re
from datetime import timedelta

import frappe
from whatsapp_messaging.messaging.naming import set_record_values
from frappe.utils import get_datetime
from whatsapp_messaging.send_security import require_send_role
from .common import account, changed, check_version, conversation, digest, insert, lock, page_size, parsed, public_message, require_supervisor, supervisor, utcnow, window_open


def ensure_peer(identity, sender, display_name=None):
    identity = str(identity).strip()
    if not re.fullmatch(r'[A-Za-z0-9_:+.-]{1,200}', identity):
        frappe.throw('Unsupported recipient identity')
    scope = sender.portfolio_id or sender.waba_id or sender.name
    key = digest(scope, identity)
    name = frappe.db.get_value('WhatsApp Peer', {'identity_key': key}, 'name')
    if name:
        return frappe.get_doc('WhatsApp Peer', name)
    # Serialize first-time identities across accounts in the same portfolio.
    frappe.db.savepoint('peer_insert')
    try:
        peer = insert('WhatsApp Peer', identity_key=key, provider_identity=identity,
            portfolio_id=scope, phone_number=identity if identity.isdigit() else None,
            display_name=(display_name or identity)[:140])
        insert('WhatsApp Identity Alias', identity_key=digest(scope, 'provider', identity),
            peer=peer.name, portfolio_id=scope, identity_kind='provider', identity_value=identity, provenance='Provider or explicit recipient entry')
        return peer
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        frappe.db.rollback(save_point='peer_insert')
        return frappe.get_doc('WhatsApp Peer', frappe.db.sql('SELECT name FROM `tabWhatsApp Peer` WHERE identity_key=%s FOR UPDATE',key)[0][0])


def ensure_conversation(sender, peer):
    key = digest(sender.name, peer.name)
    name = frappe.db.get_value('WhatsApp Conversation', {'identity_key': key}, 'name')
    if name:
        return frappe.get_doc('WhatsApp Conversation', name)
    frappe.db.savepoint('conversation_insert')
    try:
        return insert('WhatsApp Conversation', identity_key=key,
            account=sender.name, peer=peer.name, recipient=peer.provider_identity,
            workflow_status='Open', last_sequence=0, last_activity_at=utcnow(), version=0)
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        frappe.db.rollback(save_point='conversation_insert')
        return frappe.get_doc('WhatsApp Conversation', frappe.db.sql('SELECT name FROM `tabWhatsApp Conversation` WHERE identity_key=%s FOR UPDATE',key)[0][0])


@frappe.whitelist(methods=['POST'])
def new_conversation(account_name, recipient):
    sender = account(account_name)
    number = re.sub(r'[\s()+-]', '', str(recipient))
    if not re.fullmatch(r'[1-9][0-9]{6,14}', number):
        frappe.throw('Enter a full international phone number including country code')
    return {'name': ensure_conversation(sender, ensure_peer(number, sender)).name}


@frappe.whitelist()
def list_conversations(account_name=None, status=None, assignment=None, search=None, cursor=None, limit=40):
    require_send_role()
    filters = {'account': ['is', 'set'], 'peer': ['is', 'set']}
    if account_name:
        account(account_name)
        filters['account'] = account_name
    if status:
        if status not in ('Open', 'Pending', 'Resolved'): frappe.throw('Invalid status')
        filters['workflow_status'] = status
    if assignment == 'Mine': filters['assigned_to'] = frappe.session.user
    if assignment == 'Unassigned': filters['assigned_to'] = ['is', 'not set']
    # Personal unread filtering is applied in SQL using this user's read cursor.
    conditions = []
    params = {'user': frappe.session.user}
    if assignment == 'Unread':
        conditions.append("EXISTS (SELECT 1 FROM `tabWhatsApp Message` m WHERE m.conversation=c.name AND m.direction='Inbound' AND m.sequence>COALESCE((SELECT r.last_read_sequence FROM `tabWhatsApp Conversation Read` r WHERE r.conversation=c.name AND r.user=%(user)s),0))")
    # First use permission-filtered names, then join the bounded personal projections.
    if search:
        text = '%' + str(search)[:100] + '%'
        peers = frappe.get_list('WhatsApp Peer', or_filters={'display_name':['like',text], 'provider_identity':['like',text]}, pluck='name', limit_page_length=200)
        if not peers: return {'items':[], 'next_cursor':None}
        filters['peer'] = ['in', peers]
    if cursor:
        value = parsed(cursor)
        params.update(cursor_time=value['time'], cursor_name=value['name'])
        conditions.append('(COALESCE(c.last_activity_at,c.creation)<%(cursor_time)s OR (COALESCE(c.last_activity_at,c.creation)=%(cursor_time)s AND c.name<%(cursor_name)s))')
    # Frappe's permission-filtered query is the authority for names and accounts.
    from frappe.model.db_query import DatabaseQuery
    query = DatabaseQuery('WhatsApp Conversation').execute(filters=filters, fields=['name'], run=False)
    params['limit'] = page_size(limit) + 1
    where = (' AND ' + ' AND '.join(conditions)) if conditions else ''
    rows = frappe.db.sql(f"""SELECT c.name,c.account,c.peer,c.recipient,c.workflow_status,c.assigned_to,
        c.last_message,c.last_sequence,c.version,COALESCE(c.last_activity_at,c.creation) AS activity_at,
        p.display_name,
        (SELECT COUNT(*) FROM `tabWhatsApp Message` m WHERE m.conversation=c.name AND m.direction='Inbound'
         AND m.sequence>COALESCE(r.last_read_sequence,0)) AS unread
        FROM `tabWhatsApp Conversation` c LEFT JOIN `tabWhatsApp Peer` p ON p.name=c.peer
        LEFT JOIN `tabWhatsApp Conversation Read` r ON r.conversation=c.name AND r.user=%(user)s
        WHERE c.name IN (SELECT permitted.name FROM ({query}) permitted){where}
        ORDER BY COALESCE(c.last_activity_at,c.creation) DESC,c.name DESC LIMIT %(limit)s""", params, as_dict=True)
    size=page_size(limit)
    more=len(rows)>size
    rows=rows[:size]
    return {'items':rows,'next_cursor':{'time':str(rows[-1].activity_at),'name':rows[-1].name} if rows and more else None}


@frappe.whitelist()
def get_conversation(name, before=None, after=None, limit=40):
    doc=conversation(name)
    peer=frappe.get_doc('WhatsApp Peer',doc.peer)
    filters={'conversation':name}
    if before: filters['sequence']=['<',int(before)]
    if after: filters['sequence']=['>',int(after)]
    messages=frappe.get_list('WhatsApp Message',filters=filters,fields=['*'],order_by='sequence asc' if after else 'sequence desc',limit_page_length=page_size(limit))
    if not after: messages.reverse()
    result=[]
    for row in messages:
        item=public_message(row)
        item['attachments']=frappe.get_list('WhatsApp Attachment',filters={'message':row.name},fields=['name','file_name','mime_type','size','state','error_reason'])
        result.append(item)
    links=[]
    for row in frappe.get_all('WhatsApp Record Link',filters={'conversation':name},fields=['reference_doctype','reference_name']):
        if frappe.has_permission(row.reference_doctype,'read',row.reference_name): links.append(row)
    sessions=frappe.get_list('WhatsApp Flow Session',filters={'conversation':name},fields=['name','flow','state','current_step','answers_json','pause_reason'],limit_page_length=1)
    return {'conversation':{key:doc.get(key) for key in ('name','account','recipient','workflow_status','assigned_to','version','last_sequence','window_expires_at')},'peer':{key:peer.get(key) for key in ('name','display_name','suppressed','consent_recorded','consent_source')},'window_open':window_open(doc),'messages':result,'links':links,'activity':frappe.get_list('WhatsApp Conversation Activity',filters={'conversation':name},fields=['actor','action','details','creation'],order_by='creation desc',limit_page_length=20),'flow_session':sessions[0] if sessions else None}


@frappe.whitelist(methods=['POST'])
def mark_read(name, sequence):
    doc=conversation(name,locked=True)
    # The client may acknowledge only an existing inbound message it could display.
    sequence=int(sequence)
    if sequence<0 or sequence>int(doc.last_sequence or 0): frappe.throw('Invalid read cursor')
    key=digest(name,frappe.session.user)
    previous=frappe.db.get_value('WhatsApp Conversation Read',{'read_key':key},['name','last_read_sequence'],as_dict=True)
    value=max(sequence,int(previous.last_read_sequence or 0) if previous else 0)
    if previous: set_record_values('WhatsApp Conversation Read',previous.name,{'last_read_sequence':value,'read_at':utcnow()})
    else: insert('WhatsApp Conversation Read',read_key=key,conversation=name,user=frappe.session.user,last_read_sequence=value,read_at=utcnow())
    return {'sequence':value}


@frappe.whitelist(methods=['POST'])
def assign(name, version, user=None):
    doc=conversation(name,locked=True);check_version(doc,version)
    user=user or None
    if not supervisor():
        if (user and user!=frappe.session.user) or (doc.assigned_to and doc.assigned_to!=frappe.session.user):
            frappe.throw('Only supervisors can reassign another agent’s conversation',frappe.PermissionError)
    if user and (not frappe.db.get_value('User',user,'enabled') or not set(frappe.get_roles(user)).intersection(('Whatsapp Editor','Whatsapp Admin','System Manager'))):
        frappe.throw('Choose an enabled WhatsApp agent')
    changed(doc,assigned_to=user)
    if user:
        from .flows import pause_session
        pause_session(doc,'Conversation assigned to a team member')
    insert('WhatsApp Conversation Activity',conversation=name,actor=frappe.session.user,action='Assignment',details=user or 'Unassigned')
    return {'version':int(doc.version or 0)+1}


@frappe.whitelist(methods=['POST'])
def set_status(name, version, status):
    doc=conversation(name,locked=True);check_version(doc,version)
    if not supervisor() and doc.assigned_to!=frappe.session.user: frappe.throw('Claim this conversation before changing its status',frappe.PermissionError)
    if status not in ('Open','Pending','Resolved'):frappe.throw('Invalid conversation status')
    changed(doc,workflow_status=status)
    insert('WhatsApp Conversation Activity',conversation=name,actor=frappe.session.user,action='Status',details=status)
    return {'version':int(doc.version or 0)+1}


@frappe.whitelist(methods=['POST'])
def link_record(name, doctype, docname):
    conversation(name)
    target=frappe.get_doc(doctype,docname);target.check_permission('read')
    key=digest(name,doctype,docname)
    if not frappe.db.exists('WhatsApp Record Link',{'link_key':key}):
        insert('WhatsApp Record Link',link_key=key,conversation=name,reference_doctype=doctype,reference_name=docname)
        insert('WhatsApp Conversation Activity',conversation=name,actor=frappe.session.user,action='Link',details='Business record linked')
    return {'linked':True}


@frappe.whitelist(methods=['POST'])
def set_eligibility(peer, suppressed=0, consent_recorded=0, consent_source=None):
    require_supervisor()
    doc=lock('WhatsApp Peer',peer)
    if int(consent_recorded) and not str(consent_source or '').strip():frappe.throw('Record the source of consent')
    set_record_values(doc.doctype,doc.name,{'suppressed':int(bool(int(suppressed))),'consent_recorded':int(bool(int(consent_recorded))),'consent_source':str(consent_source or '')[:140],'consent_at':utcnow() if int(consent_recorded) else None})
    for name in frappe.get_all('WhatsApp Conversation',filters={'peer':peer},pluck='name'):
        insert('WhatsApp Conversation Activity',conversation=name,actor=frappe.session.user,action='Eligibility',details='Recipient eligibility updated')
    return {'updated':True}
