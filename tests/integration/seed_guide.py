"""Fictional screenshot fixtures. Refuses any site except the isolated test database.

Run after integration/run.sh in the same disposable Compose project. No worker or
scheduler is started; provider transport is mocked and the network stays internal.
"""
import json
import os
from datetime import timedelta
from unittest.mock import Mock, patch
from pathlib import Path

import frappe
import check_site as fixtures
from whatsapp_messaging.messaging import inbox, webhooks, outbox, automation
from whatsapp_messaging.messaging.common import insert, digest, utcnow


def seed():
    assert frappe.local.site == 'whatsapp-test.localhost' and frappe.conf.db_host == 'db'
    frappe.set_user('Administrator')
    for dt in ['WhatsApp Send Attempt','WhatsApp Status Event','WhatsApp Webhook Event','WhatsApp Attachment','WhatsApp Record Link','WhatsApp Conversation Activity','WhatsApp Conversation Read','WhatsApp Outbox','WhatsApp Automation Run','WhatsApp Schedule','WhatsApp Message','WhatsApp Conversation','WhatsApp Identity Alias','WhatsApp Peer','WhatsApp Approved Template','WhatsApp Campaign','WhatsApp Template Variable','WhatsApp Message Template','WhatsApp Phone Number ID','Static Recipient']:
        frappe.db.delete(dt)
    from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    if not frappe.db.exists('Custom Field','ToDo-wm_test_phone'):
        create_custom_field('ToDo',{'fieldname':'wm_test_phone','label':'Recipient phone','fieldtype':'Phone'})
    frappe.db.set_value('Custom Field','ToDo-wm_test_phone','label','Recipient phone')
    for field, label in [('wm_patient_name','Patient name'),('wm_appointment_reference','Appointment reference'),('wm_appointment_time','Appointment time')]:
        if not frappe.db.exists('Custom Field','ToDo-'+field):
            create_custom_field('ToDo',{'fieldname':field,'label':label,'fieldtype':'Data'})
    for user, first, role in [('priya@riverbend.example','Priya — Reception','Whatsapp Editor'),('anil@riverbend.example','Anil — Front Desk Lead','Whatsapp Admin')]:
        if not frappe.db.exists('User',user):
            frappe.get_doc(dict(doctype='User',email=user,first_name=first,send_welcome_email=0,user_type='System User',roles=[{'role':role}],new_password='integration-only-user-password')).insert()
    frappe.db.set_single_value('System Settings','time_zone','Asia/Kolkata')
    frappe.db.set_single_value('System Settings','setup_complete',1)
    frappe.db.set_value('Installed Application',{'app_name':'frappe'},'is_setup_complete',1)
    settings=frappe.get_doc('WhatsApp Settings')
    settings.update(dict(enable_outbound_messages=1,enable_inbound=1,enable_automation=0,meta_app_id='riverbend-training-application',app_secret='training-only-secret',verify_token='training-only-token'))
    settings.save()
    sender=frappe.get_doc(dict(doctype='WhatsApp Phone Number ID',label='Riverbend Patient Services',phone_number_id='100000000000001',access_token='training-only-token',waba_id='100000000000002',portfolio_id='riverbend-hospital',display_phone='+1 202-555-0100',enabled=1)).insert()
    peer=inbox.ensure_peer('12025550123',sender,'Meera Rao')
    frappe.db.set_value('WhatsApp Peer',peer.name,dict(consent_recorded=1,consent_source='Appointment booking form'))
    conv=inbox.ensure_conversation(sender,peer)
    now=utcnow()
    for ident, body, minutes in [('hospital-inbound-1','Hello, could you confirm my appointment with Dr. Sen tomorrow?',12),('hospital-inbound-2','Thank you. Could you share the visit instructions as well?',2)]:
        webhooks.inbound(sender,dict(id=ident,**{'from':peer.provider_identity},timestamp=str(int((now-timedelta(minutes=minutes)).replace(tzinfo=__import__('datetime').timezone.utc).timestamp())),type='text',text={'body':body}))
    frappe.db.set_value('WhatsApp Conversation',conv.name,dict(assigned_to='priya@riverbend.example',window_expires_at=now+timedelta(hours=23)))
    for number, label, status in [('12025550124','Anita Shah','Pending'),('12025550125','Vikram Das','Resolved')]:
        c=inbox.ensure_conversation(sender,inbox.ensure_peer(number,sender,label))
        frappe.db.set_value('WhatsApp Conversation',c.name,'workflow_status',status)
    from whatsapp_messaging.messaging import catalogue, campaigns, template_editor
    approved_name=catalogue.upsert(sender.waba_id,dict(id='100000000000003',name='appointment_confirmation',language='en_US',category='UTILITY',status='APPROVED',components=[{'type':'BODY','text':'Hello {{1}}, your appointment {{2}} is confirmed. Reply if you need help.'}]))
    approved=frappe.get_doc('WhatsApp Approved Template',approved_name)
    source=frappe.get_doc(dict(doctype='ToDo',description='Cardiology appointment — OPD-1042',status='Open',allocated_to='priya@riverbend.example',wm_test_phone='+1-'+peer.provider_identity[1:],wm_patient_name='Meera Rao',wm_appointment_reference='OPD-1042',wm_appointment_time='tomorrow at 9:30 AM')).insert()
    second=frappe.get_doc(dict(doctype='ToDo',description='General medicine appointment — OPD-1043',status='Open',wm_test_phone='+1-2025550124',wm_patient_name='Anita Shah',wm_appointment_reference='OPD-1043',wm_appointment_time='tomorrow at 10:15 AM')).insert()
    inbox.link_record(conv.name,'ToDo',source.name)
    policy=frappe.get_doc('WhatsApp Template Field Policy','ToDo')
    policy.allowed_fields='["wm_patient_name","wm_appointment_reference","wm_appointment_time"]'
    policy.save()
    static_policy = frappe.get_doc('WhatsApp Template Field Policy', 'Website Settings') if frappe.db.exists('WhatsApp Template Field Policy', 'Website Settings') else frappe.new_doc('WhatsApp Template Field Policy')
    static_policy.update(dict(source_doctype='Website Settings', allowed_fields='["app_name"]'))
    static_policy.save()
    frappe.db.set_single_value('Website Settings', 'app_name', 'Riverbend Hospital')
    def rule(name,**extra):
        values=dict(doctype='WhatsApp Message Template',template_name=name,phone_number_id=sender.name,template_doctype='ToDo',template_event='Custom',phone_number_field_name='wm_test_phone',template_button_label='Send appointment reminder',template_type='text',message_preview='Hello {{template_doctype.wm_patient_name}}, your appointment {{template_doctype.wm_appointment_reference}} is confirmed for {{template_doctype.wm_appointment_time}}. Please arrive 15 minutes early.',allowed_source_fields='["wm_patient_name","wm_appointment_reference","wm_appointment_time"]',query_filters=json.dumps({'filters':[['ToDo','name','in',[source.name,second.name]]]}),is_single=0,disable=0)
        values.update(extra)
        return frappe.get_doc(values).insert()
    manual=rule('Appointment confirmation')
    event=rule('Appointment status update',template_event='Update',automation_active=1)
    bulk=rule('Tomorrow’s appointment reminders',is_single=1)
    campaigns.backfill()
    welcome=rule('Hospital welcome',delivery_mode=template_editor.META,disable=1,
        meta_header='Welcome to Riverbend Hospital',meta_footer='Patient Support',
        meta_template_name='hospital_welcome',meta_language='en_US',meta_category='MARKETING',
        message_preview='Hello {{template_doctype.wm_patient_name}},\n\nThank you for choosing us for your care.\n\nPlease reply here if you need help booking an appointment, checking visiting hours or finding your way to the hospital.\n\nWe look forward to welcoming you.',
        meta_examples=[dict(position=1,source_path='template_doctype.wm_patient_name',sample_value='Meera Rao')])
    rejected=rule('Appointment reschedule notice',delivery_mode=template_editor.META,disable=1,
        meta_template_name='appointment_reschedule',meta_language='en_US',meta_category='UTILITY',
        message_preview='Hello {{template_doctype.wm_patient_name}}, your appointment {{template_doctype.wm_appointment_reference}} has changed. Please reply to confirm a suitable time.',
        meta_examples=[dict(position=1,source_path='template_doctype.wm_patient_name',sample_value='Meera Rao'),dict(position=2,source_path='template_doctype.wm_appointment_reference',sample_value='OPD-1042')])
    rejected_name=catalogue.upsert(sender.waba_id,dict(id='100000000000004',name='appointment_reschedule',language='en_US',category='UTILITY',status='REJECTED',rejected_reason='INVALID_FORMAT',components=template_editor.compile_content(rejected,examples=True)[2]))
    frappe.db.set_value(rejected.doctype,rejected.name,'approved_template',rejected_name)
    # Simulated review detail for the user guide, never a live Meta response.
    catalogue.review_update(sender.waba_id,dict(event='REJECTED',message_template_id='100000000000004',reason='INVALID_FORMAT',rejection_info={'reason':'The submitted version needs clearer text around its variables.','recommendation':'Separate variables with descriptive words and include review examples.'}),int(now.replace(tzinfo=__import__('datetime').timezone.utc).timestamp()))
    schedule=insert('WhatsApp Schedule',schedule_key='hospital-schedule',rule=manual.name,state='Paused',run_as='Administrator',timezone='Asia/Kolkata',cron_expression='0 9 * * *',next_due_at=now+timedelta(days=1))
    run=insert('WhatsApp Automation Run',run_key='hospital-completed-run',rule=manual.name,kind='Manual',state='Completed',run_as='Administrator',records_selected=1,records_processed=1,messages_created=1,snapshot_json='{}')
    with patch('requests.post',return_value=Mock(status_code=200,ok=True,json=Mock(return_value={'messages':[{'id':'hospital-outbound-accepted'}]}))):
        result=outbox.create_intent(conv.name,'hospital-reply',body='Your appointment is confirmed for tomorrow at 9:30 AM. Please arrive 15 minutes early.',source_doctype='ToDo',source_name=source.name,rule=manual.name,run=run.name)
        frappe.db.commit()
        outbox.dispatch(result['outbox'])
    # Receipt fixture, not a live provider claim.
    frappe.db.set_value('WhatsApp Message',result['message'],'status','Delivered')
    frappe.db.set_value('WhatsApp Outbox',result['outbox'],'state','Delivered')
    receipt=insert('WhatsApp Webhook Event',event_key='hospital-quarantined-event',state='Quarantined',received_at=now,attempt_count=1,error_reason='Unknown sender account. Check the external Phone Number ID mapping before replaying.',payload_json='{}')
    recipient=frappe.get_doc(dict(doctype='Static Recipient',label='Reception coordinator',phone_number='+1-2025550126')).insert()
    preview=automation.preview_campaign(bulk.name)
    frappe.db.commit()
    from frappe.utils.background_jobs import get_queue
    get_queue('default').empty()
    routes=dict(conversation=conv.name,source=source.name,manual=manual.name,event=event.name,bulk=bulk.name,schedule=schedule.name,run=run.name,webhook=receipt.name,recipient=recipient.name,account=sender.name,preview=preview['run'],rejected=rejected.name,welcome=welcome.name)
    Path('/testbench/guide-fixtures.json').write_text(json.dumps(routes,indent=2))
    print(json.dumps(routes))


if __name__=='__main__':
    os.chdir('/testbench/sites')
    fixtures.connect()
    try:
        with patch('requests.get',side_effect=AssertionError('Live requests forbidden')),patch('requests.post',side_effect=AssertionError('Live requests forbidden')):
            seed()
    finally:frappe.destroy()
