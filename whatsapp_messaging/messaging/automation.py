"""Durable schedules and paged campaigns, executed as the activating user."""
import json
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

import frappe
from whatsapp_messaging.messaging.naming import set_record_values
from croniter import croniter
from frappe.utils import get_datetime, get_system_timezone
from whatsapp_messaging.send_security import require_outbound_enabled, require_send_role
from .common import account, as_user, digest, insert, lock, parsed, require_supervisor, utcnow
from .inbox import ensure_conversation, ensure_peer
from .outbox import create_intent

BATCH=25
MAX_CAMPAIGN=10000


def enabled():
    return bool(frappe.db.get_single_value('WhatsApp Settings','enable_automation',cache=False) and frappe.db.get_single_value('WhatsApp Settings','enable_outbound_messages',cache=False))


def local_to_utc(value,tz):
    from dateutil.tz import datetime_exists, datetime_ambiguous, gettz
    date=get_datetime(value)
    if date.tzinfo is None:
        zone=gettz(tz)
        if not datetime_exists(date,zone) or datetime_ambiguous(date,zone):frappe.throw('Choose an unambiguous local schedule time')
        date=date.replace(tzinfo=ZoneInfo(tz))
    return date.astimezone(timezone.utc).replace(tzinfo=None)


def next_due(expression,previous,tz):
    base=get_datetime(previous).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
    return croniter(expression,base).get_next(type(base)).astimezone(timezone.utc).replace(tzinfo=None)


def get_rule(name):
    require_send_role()
    from .campaigns import load
    rule=load(name)
    if rule.disable:frappe.throw('This rule is disabled')
    account(rule.phone_number_id)
    if not frappe.has_permission(rule.template_doctype,'read'):frappe.throw('You cannot read this source type',frappe.PermissionError)
    if rule.template_event=='Date Reminder':validate_date_reminder(rule)
    return rule


def validate_date_reminder(rule):
    from .reminders import date_window, daily_cron
    meta=frappe.get_meta(rule.template_doctype)
    field=meta.get_field(rule.reminder_date_field)
    if not field or field.fieldtype!='Date' or field.hidden or field.fieldname not in meta.get_permitted_fieldnames(permission_type='read'):
        frappe.throw('Choose a readable Date field for this reminder.',frappe.PermissionError)
    try:
        date_window(utcnow(),rule.reminder_timezone,rule.reminder_days_before)
        daily_cron(rule.reminder_time)
    except (ValueError,TypeError,KeyError):
        frappe.throw('Choose a valid reminder timezone, time and a window of 0 to 30 days.')


def source_filters(rule):
    value=parsed(rule.query_filters,{})
    filters=value.get('filters',[]) if isinstance(value,dict) else value
    if rule.template_event!='Date Reminder':return filters
    from .reminders import date_window
    start,end=date_window(utcnow(),rule.reminder_timezone,rule.reminder_days_before)
    if isinstance(filters,dict):
        filters=[[key,*(condition if isinstance(condition,(list,tuple)) else ['=',condition])] for key,condition in filters.items()]
    return [*(filters or []),[rule.template_doctype,rule.reminder_date_field,'between',[str(start),str(end)]]]


def reminder_matches(rule,source):
    from .reminders import matches
    return rule.template_event!='Date Reminder' or matches(source.get(rule.reminder_date_field),utcnow(),rule.reminder_timezone,rule.reminder_days_before)


def origin_key(rule,source,run,recipient):
    values=[run.run_key,source.doctype,source.name,recipient]
    if rule.template_event=='Date Reminder':values.append(str(source.get(rule.reminder_date_field) or ''))
    return digest(*values)


def source_snapshot(rule):
    records=[];start=0
    while True:
        page=frappe.get_list(rule.template_doctype,filters=source_filters(rule),fields=['name','modified'],order_by='name asc',limit_start=start,limit_page_length=200)
        records.extend({'name':r.name,'modified':str(r.modified)} for r in page)
        if len(records)>MAX_CAMPAIGN:frappe.throw('Select at most 10,000 source records per run')
        if len(page)<200:break
        start+=200
    return records


def render(rule,source):
    from whatsapp_messaging.controller import parse_message,get_template_recipients
    from whatsapp_messaging.template_security import FIELD_NAME,parse_allowed_fields
    source.check_permission('read')
    from whatsapp_messaging.utils import doc_matches_filters
    if not doc_matches_filters(source,rule.query_filters):frappe.throw('Source no longer matches the rule')
    if not reminder_matches(rule,source):frappe.throw('The reminder date is outside this campaign window')
    recipients=get_template_recipients(rule,source)
    if not recipients:frappe.throw('No valid recipients on this record')
    if len(recipients)>100:frappe.throw('At most 100 recipients are supported per record')
    values=[]
    if rule.get('delivery_mode') == 'Meta-approved template':
        from .template_editor import ensure_sendable
        paths = ensure_sendable(rule)
        for path in paths:
            clone=frappe._dict(template_doctype=rule.template_doctype,template_name=rule.get('template_name'),
                template_button_label=rule.template_button_label,message_preview='{{'+path+'}}')
            values.append(parse_message(clone,source))
        body=''
    elif rule.approved_template:
        fields=parsed(rule.parameter_fields,[])
        if not isinstance(fields,list):frappe.throw('Parameter fields must be an ordered JSON list')
        from .field_policy import get_allowed_source_fields
        allowed=get_allowed_source_fields(rule.template_doctype)
        for name in fields:
            if not isinstance(name,str) or not FIELD_NAME.fullmatch(name) or name not in allowed:frappe.throw('Template parameter field has not been approved')
            clone=frappe._dict(template_doctype=rule.template_doctype,template_name=rule.get('template_name'),
                template_button_label=rule.template_button_label,message_preview='{{template_doctype.'+name+'}}')
            values.append(parse_message(clone,source))
        body=''
    else:
        from .template_framing import compose
        body=compose(parse_message(rule,source),rule.get('meta_header'),rule.get('meta_footer'))
    from .template_content import resolve
    file_id=resolve(rule.media,rule.approved_template)['file_id']
    return recipients,body,values,file_id


def emit(rule,source,run,deleted=False):
    recipients,body,values,file_id=render(rule,source)
    sender=account(rule.phone_number_id,enabled=True)
    count=0
    for recipient in sorted(set(recipients)):
        peer=ensure_peer(recipient,sender)
        doc=ensure_conversation(sender,peer)
        origin=origin_key(rule,source,run,recipient)
        create_intent(doc.name,origin,body=body,template=rule.approved_template,parameters=values,file_id=file_id,
            source_doctype=source.doctype,source_name=source.name,rule=rule.name,run=run.name,origin_key=origin,deleted_source=deleted)
        count+=1
    return count


@frappe.whitelist(methods=['POST'])
def preview_campaign(rule_name):
    require_supervisor()
    rule=get_rule(rule_name)
    if not rule.is_single or rule.template_event not in ('Custom','None','',None):frappe.throw('Choose an enabled manual bulk template')
    snapshot=source_snapshot(rule)
    # Preview freezes source identity/version and rule version; it never dispatches.
    run=insert('WhatsApp Automation Run',run_key=digest('preview',frappe.generate_hash(length=20)),rule=rule.name,kind='Campaign',state='Preview',run_as=frappe.session.user,records_selected=len(snapshot),snapshot_json=json.dumps({'rule_modified':str(rule.modified),'records':snapshot}))
    return {'run':run.name,**preview_rows(run,rule)}


def preview_rows(run,rule,start=0):
    snapshot=parsed(run.snapshot_json,{})
    items=[]
    for row in snapshot.get('records',[])[start:start+BATCH]:
        try:
            source=frappe.get_doc(rule.template_doctype,row['name']);source.check_permission('read')
            recipients,body,values,file_id=render(rule,source)
            if rule.approved_template:
                from .catalogue import rendered_text
                approved=frappe.get_doc('WhatsApp Approved Template',rule.approved_template)
                approved.check_permission('read')
                body=rendered_text(approved,values)
            items.append({'source':source.name,'recipients':len(recipients),'body':body,'parameters':values,'attachment':bool(file_id)})
        except (frappe.PermissionError,frappe.DoesNotExistError):items.append({'excluded':True,'reason':'Source is no longer readable'})
        except Exception:items.append({'source':row['name'],'excluded':True,'reason':'Template or recipient configuration requires review'})
    return {'records':run.records_selected,'items':items,'next_start':start+BATCH if start+BATCH<len(snapshot.get('records',[])) else None,'duplicates':'One message per business record and recipient'}


@frappe.whitelist()
def preview_page(name,start=0):
    require_supervisor()
    run=frappe.get_doc('WhatsApp Automation Run',name);run.check_permission('read')
    if run.kind!='Campaign':frappe.throw('Not a campaign')
    if run.run_as!=frappe.session.user:frappe.throw('Preview this campaign as its execution user',frappe.PermissionError)
    return preview_rows(run,get_rule(run.rule),max(0,int(start)))


@frappe.whitelist(methods=['POST'])
def start_campaign(name):
    require_supervisor();require_outbound_enabled()
    run=lock('WhatsApp Automation Run',name)
    if run.kind!='Campaign' or run.run_as!=frappe.session.user:frappe.throw('Only the preview owner can start this campaign',frappe.PermissionError)
    if run.state!='Preview':return {'run':name,'state':run.state}
    rule=get_rule(run.rule)
    if str(rule.modified)!=parsed(run.snapshot_json,{})['rule_modified']:frappe.throw('The rule changed; preview it again')
    set_record_values(run.doctype,name,'state','Ready')
    frappe.enqueue('whatsapp_messaging.messaging.automation.expand_run',name=name,enqueue_after_commit=True)
    return {'run':name,'state':'Ready'}


@frappe.whitelist(methods=['POST'])
def control_run(name,action):
    require_send_role()
    run=lock('WhatsApp Automation Run',name);run.check_permission('read')
    if run.kind=='Campaign':require_supervisor()
    if run.run_as!=frappe.session.user:require_supervisor()
    if action not in ('Pause','Resume','Cancel'):frappe.throw('Invalid action')
    if run.state in ('Cancelled','Failed','Skipped'):frappe.throw('This run is terminal')
    if action=='Resume':
        require_outbound_enabled()
        if run.state!='Paused':frappe.throw('Only a paused run can be resumed')
        state='Ready' if int(run.records_processed or 0)<int(run.records_selected or 0) else 'Completed'
    else:state='Paused' if action=='Pause' else 'Cancelled'
    set_record_values(run.doctype,name,'state',state)
    if state=='Cancelled':
        from .outbox import set_outcome
        for intent_name in frappe.get_all('WhatsApp Outbox',filters={'run':name,'state':['in',['Ready','Retry wait']]},pluck='name'):
            intent=lock('WhatsApp Outbox',intent_name)
            if intent.state in ('Ready','Retry wait'):set_outcome(intent,'Cancelled','Originating run cancelled')
    if action=='Resume':frappe.enqueue('whatsapp_messaging.messaging.automation.expand_run',name=name,enqueue_after_commit=True)
    return {'state':state}


@frappe.whitelist(methods=['POST'])
def save_schedule(rule_name,when=None,cron_expression=None,timezone_name=None):
    rule=get_rule(rule_name)
    rule.check_permission('write')
    zone=timezone_name or get_system_timezone()
    try:ZoneInfo(zone)
    except Exception:frappe.throw('Unknown timezone')
    if cron_expression and not croniter.is_valid(cron_expression):frappe.throw('Invalid cron expression')
    due=local_to_utc(when,zone) if when else next_due(cron_expression,utcnow(),zone) if cron_expression else None
    if not due:frappe.throw('Choose a date/time or recurrence')
    if due<utcnow():frappe.throw('Choose a future schedule time')
    key=digest('rule_schedule',rule.name)
    name=frappe.db.get_value('WhatsApp Schedule',{'schedule_key':key},'name')
    values=dict(rule=rule.name,state='Active',run_as=frappe.session.user,timezone=zone,cron_expression=cron_expression,next_due_at=due,one_shot=int(not cron_expression),last_error=None)
    if name:
        lock('WhatsApp Schedule',name);set_record_values('WhatsApp Schedule',name,values)
    else:name=insert('WhatsApp Schedule',schedule_key=key,**values).name
    set_record_values(rule.doctype,rule.name,{'schedule_record':name,'run_as':frappe.session.user,'automation_active':1})
    return {'name':name,'next_due_at':due,'timezone':zone}


@frappe.whitelist(methods=['POST'])
def control_schedule(name,action):
    require_send_role()
    schedule=lock('WhatsApp Schedule',name)
    if schedule.run_as!=frappe.session.user:require_supervisor()
    if action not in ('Pause','Resume'):frappe.throw('Invalid action')
    rule=get_rule(schedule.rule);rule.check_permission('write')
    if action=='Resume' and schedule.state=='Completed':frappe.throw('Create a new occurrence instead of resuming a completed schedule')
    set_record_values(schedule.doctype,name,{'state':'Active' if action=='Resume' else 'Paused','run_as':frappe.session.user})
    return {'state':'Active' if action=='Resume' else 'Paused'}


@frappe.whitelist(methods=['POST'])
def rerun(name):
    require_send_role();require_outbound_enabled()
    run=frappe.get_doc('WhatsApp Automation Run',name)
    if run.kind=='Campaign':require_supervisor()
    if run.run_as!=frappe.session.user:require_supervisor()
    rule=get_rule(run.rule)
    if run.kind=='Manual':frappe.throw('Compose a deliberate new message from the source record or inbox')
    if run.kind=='Event':
        records=[]
        for row in parsed(run.snapshot_json,{}).get('records',[]):
            source=frappe.get_doc(rule.template_doctype,row['name']);source.check_permission('read')
            records.append({'name':source.name,'modified':str(source.modified)})
        if not records:frappe.throw('This event has no readable source to run again')
    else:records=source_snapshot(rule)
    new=insert('WhatsApp Automation Run',run_key=digest('manual_run',name,frappe.generate_hash(length=20)),rule=rule.name,kind=run.kind,state='Ready',run_as=frappe.session.user,due_at=utcnow(),snapshot_json=json.dumps({'rule_modified':str(rule.modified),'records':records}))
    set_record_values(new.doctype,new.name,'records_selected',len(parsed(new.snapshot_json,{})['records']))
    frappe.enqueue('whatsapp_messaging.messaging.automation.expand_run',name=new.name,enqueue_after_commit=True)
    return {'run':new.name}


def expand_run(name):
    if not frappe.db.get_single_value('WhatsApp Settings','enable_outbound_messages',cache=False):return
    run=lock('WhatsApp Automation Run',name)
    if run.state not in ('Ready','Expanding'):return
    try:
        with as_user(run.run_as):
            if run.kind=='Campaign':require_supervisor()
            elif not enabled():return
            rule=get_rule(run.rule)
            if run.schedule and frappe.db.get_value('WhatsApp Schedule',run.schedule,'state')=='Paused':return
            if run.kind!='Campaign' and not rule.automation_active:frappe.throw('Rule inactive')
            snapshot=parsed(run.snapshot_json,{})
            if str(rule.modified)!=snapshot.get('rule_modified'):frappe.throw('Rule changed after this run was prepared')
            rows=snapshot.get('records',[])
            processed=int(run.records_processed or 0);created=int(run.messages_created or 0);excluded=int(run.records_excluded or 0)
            for row in rows[processed:processed+BATCH]:
                frappe.db.savepoint('expand_source')
                try:
                    source=frappe.get_doc(rule.template_doctype,row['name'])
                    source.check_permission('read')
                    if str(source.modified)!=row['modified']:frappe.throw('Source changed after preview')
                    created+=emit(rule,source,run)
                except Exception:
                    frappe.db.rollback(save_point='expand_source');excluded+=1
                processed+=1
            state='Completed' if processed>=len(rows) else 'Ready'
            set_record_values(run.doctype,name,{'records_processed':processed,'messages_created':created,'records_excluded':excluded,'state':state,'last_error':'Some records were excluded; review permissions, recipients and eligibility' if excluded else None})
            if state=='Ready':frappe.enqueue('whatsapp_messaging.messaging.automation.expand_run',name=name,enqueue_after_commit=True)
    except Exception:
        set_record_values(run.doctype,name,{'state':'Failed','last_error':'Execution user or rule configuration requires review'})
    frappe.db.commit()


def process_due():
    now=utcnow()
    for name in frappe.get_all('WhatsApp Schedule',filters={'state':'Active','next_due_at':['<=',now]},pluck='name',limit_page_length=100):
        schedule=lock('WhatsApp Schedule',name)
        if schedule.state!='Active' or get_datetime(schedule.next_due_at)>now:continue
        try:
            with as_user(schedule.run_as):
                rule=get_rule(schedule.rule)
                due=get_datetime(schedule.next_due_at)
                # Scan bounded occurrences; stale history is reported in a durable skipped run.
                loops=0
                if not schedule.one_shot and due<now-timedelta(hours=1):
                    skipped_key=digest(schedule.name,'skipped',str(due))
                    if not frappe.db.exists('WhatsApp Automation Run',{'run_key':skipped_key}):
                        insert('WhatsApp Automation Run',run_key=skipped_key,schedule=schedule.name,rule=rule.name,kind='Schedule',state='Skipped',run_as=schedule.run_as,due_at=due,last_error='Older occurrences skipped before the one-hour catch-up window')
                    due=next_due(schedule.cron_expression,now-timedelta(hours=1,microseconds=1),schedule.timezone)
                while due<=now and loops<100:
                    key=digest(schedule.name,str(due))
                    active=enabled() and rule.automation_active
                    skip=not active or due<now-timedelta(hours=1)
                    if not frappe.db.exists('WhatsApp Automation Run',{'run_key':key}):
                        records=[] if skip else source_snapshot(rule)
                        run=insert('WhatsApp Automation Run',run_key=key,schedule=schedule.name,rule=rule.name,kind='Schedule',state='Skipped' if skip else 'Ready',run_as=schedule.run_as,due_at=due,records_selected=len(records),snapshot_json=json.dumps({'rule_modified':str(rule.modified),'records':records}),last_error='Dispatch disabled or occurrence older than the one-hour catch-up window' if skip else None)
                        if not skip:frappe.enqueue('whatsapp_messaging.messaging.automation.expand_run',name=run.name,enqueue_after_commit=True)
                    loops+=1
                    if schedule.one_shot:
                        set_record_values(schedule.doctype,name,'state','Completed');break
                    due=next_due(schedule.cron_expression,due,schedule.timezone)
                if not schedule.one_shot:set_record_values(schedule.doctype,name,'next_due_at',due)
        except Exception:
            set_record_values(schedule.doctype,name,{'state':'Paused','last_error':'Schedule user or configuration requires review'})
    for name in frappe.get_all('WhatsApp Automation Run',filters={'state':'Ready'},pluck='name',limit_page_length=20):
        frappe.enqueue('whatsapp_messaging.messaging.automation.expand_run',name=name,enqueue_after_commit=True)


def event_rules(source,events):
    if frappe.flags.in_install or frappe.flags.in_migrate or source.doctype.startswith('WhatsApp') or source.doctype in ('Error Log','Version','File','Scheduled Job Log'):return
    if not enabled():return
    from .campaigns import definitions
    for rule in definitions({'template_doctype':source.doctype,'template_event':['in',events],'disable':0,'automation_active':1,'is_single':0}):
        key=digest('event',rule.name,source.doctype,source.name,str(source.modified),rule.template_event)
        if frappe.db.exists('WhatsApp Automation Run',{'run_key':key}):continue
        if rule.template_event=='Update Field':
            before=source.get_doc_before_save()
            if not before or before.get(rule.template_target_field)==source.get(rule.template_target_field):continue
        frappe.db.savepoint('event_rule')
        try:
            with as_user(rule.run_as):
                from .campaigns import load
                rule=load(rule.name)
                require_send_role();source.check_permission('read');rule.check_permission('read')
                run=insert('WhatsApp Automation Run',run_key=key,rule=rule.name,kind='Event',state='Completed',run_as=rule.run_as,due_at=utcnow(),records_selected=1,records_processed=1,snapshot_json=json.dumps({'rule_modified':str(rule.modified),'records':[{'name':source.name,'modified':str(source.modified)}]}))
                count=emit(rule,source,run,deleted=rule.template_event=='Delete')
                set_record_values(run.doctype,run.name,'messages_created',count)
        except Exception:
            frappe.db.rollback(save_point='event_rule')
            insert('WhatsApp Automation Run',run_key=key,rule=rule.name,kind='Event',state='Failed',run_as=rule.run_as,due_at=utcnow(),records_selected=1,snapshot_json=json.dumps({'rule_modified':str(rule.modified),'records':[{'name':source.name,'modified':str(source.modified)}]}),last_error='Event rule requires review; no messages were queued')
