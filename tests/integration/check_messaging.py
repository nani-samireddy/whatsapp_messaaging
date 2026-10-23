"""Behavior tests on an isolated Frappe site; transport is always mocked."""
import json
import os
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

import frappe
import requests
import check_site as fixtures
from whatsapp_messaging.messaging import api,automation,catalogue,inbox,media,outbox,webhooks
from whatsapp_messaging.messaging.common import digest,insert,service_write,utcnow

EDITOR=fixtures.EDITOR
ADMIN=fixtures.SUPERVISOR
ACCOUNT=fixtures.ACCOUNT


class TestMessaging(unittest.TestCase):
    def setUp(self):
        frappe.set_user('Administrator')
        assert frappe.local.site==fixtures.SITE and frappe.conf.db_host=='db'
        self.post=patch('requests.post',side_effect=AssertionError('External transport forbidden')).start()
        self.get=patch('requests.get',side_effect=AssertionError('External transport forbidden')).start()
        frappe.db.set_value('WhatsApp Message Template',fixtures.TEMPLATE,{'schedule_record':None,'automation_active':0,'run_as':None,'is_single':0,'template_event':'Custom','disable':0,'media':None,'approved_template':None,'parameter_fields':None,'query_filters':None})
        self.tables=['WhatsApp Status Event','WhatsApp Webhook Event','WhatsApp Attachment','WhatsApp Record Link','WhatsApp Conversation Activity','WhatsApp Conversation Read','WhatsApp Send Attempt','WhatsApp Outbox','WhatsApp Automation Run','WhatsApp Schedule','WhatsApp Approved Template','WhatsApp Identity Alias']
        for doctype in self.tables:frappe.db.delete(doctype)
        frappe.db.delete('WhatsApp Message',{'conversation':['is','set']})
        frappe.db.delete('WhatsApp Conversation',{'identity_key':['is','set']})
        frappe.db.delete('WhatsApp Peer')
        frappe.db.set_value('WhatsApp Phone Number ID',ACCOUNT,{'enabled':1,'waba_id':'123456','portfolio_id':'test-portfolio','dispatch_lease_until':None,'last_dispatch_at':None})
        self.sender=frappe.get_doc('WhatsApp Phone Number ID',ACCOUNT)
        settings=frappe.get_doc('WhatsApp Settings');settings.update({'enable_outbound_messages':1,'enable_automation':1,'enable_inbound':1,'meta_app_id':'dummy-app','app_secret':'dummy-app-secret','verify_token':'dummy-verify'});settings.save()
        self.peer=inbox.ensure_peer('919000000001',self.sender,'Fixture peer')
        self.conv=inbox.ensure_conversation(self.sender,self.peer)
        frappe.db.set_value('WhatsApp Conversation',self.conv.name,{'window_expires_at':utcnow()+timedelta(hours=1),'last_inbound_at':utcnow()})
        self.rule=frappe.get_doc('WhatsApp Message Template',fixtures.TEMPLATE)
        self.rule.update({'phone_number_field_name':'wm_test_phone','message_preview':'Hello {{template_doctype.status}}','allowed_source_fields':'["status"]','automation_active':0});self.rule.save()
        frappe.db.set_value('ToDo',fixtures.SOURCE,'wm_test_phone','919000000001')
        frappe.db.commit()
        frappe.set_user(EDITOR)

    def tearDown(self):
        frappe.db.rollback();frappe.set_user('Administrator')
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',0)
        frappe.db.set_single_value('WhatsApp Settings','enable_automation',0)
        frappe.db.set_single_value('WhatsApp Settings','enable_inbound',0)
        frappe.db.set_value('WhatsApp Message Template',fixtures.TEMPLATE,{'schedule_record':None,'automation_active':0,'run_as':None})
        frappe.db.commit();patch.stopall()
        from frappe.utils.background_jobs import get_queue
        get_queue('default').empty()

    def intent(self,key='request',**kw):
        return outbox.send(self.conv.name,key,body='Hello',**kw)

    def accepted(self,provider='wamid.fixture'):
        return Mock(status_code=200,ok=True,json=Mock(return_value={'messages':[{'id':provider}]}))

    def response(self,status,data):
        return Mock(status_code=status,ok=status<400,json=Mock(return_value=data))

    def inbound(self,id='inbound-1',body='Hello',time=None):
        return {'id':id,'from':'919000000001','timestamp':str(int((time or utcnow()).replace(tzinfo=__import__('datetime').timezone.utc).timestamp())),'type':'text','text':{'body':body}}

    def test_idempotent_send_and_payload_collision(self):
        first=self.intent();second=self.intent()
        self.assertEqual(first,second);self.assertEqual(frappe.db.count('WhatsApp Outbox'),1)
        with self.assertRaises(frappe.ValidationError):outbox.send(self.conv.name,'request',body='Different')
        self.post.assert_not_called()

    def test_default_off_rejects_intent_and_no_backlog(self):
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',0)
        with self.assertRaises(frappe.ValidationError):self.intent()
        self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)

    def test_disabled_account_and_suppression_block(self):
        frappe.db.set_value('WhatsApp Phone Number ID',ACCOUNT,'enabled',0)
        with self.assertRaises(frappe.ValidationError):self.intent()
        frappe.db.set_value('WhatsApp Phone Number ID',ACCOUNT,'enabled',1)
        frappe.db.set_value('WhatsApp Peer',self.peer.name,'suppressed',1)
        with self.assertRaises(frappe.ValidationError):self.intent()

    def test_closed_window_requires_approved_template(self):
        frappe.db.set_value('WhatsApp Conversation',self.conv.name,'window_expires_at',utcnow()-timedelta(seconds=1))
        with self.assertRaises(frappe.ValidationError):self.intent()

    def test_approved_template_eligibility_and_schema_change(self):
        frappe.set_user('Administrator')
        doc=insert('WhatsApp Approved Template',catalogue_key='test',waba_id='123456',template_name='hello',language='en',approval_status='APPROVED',body='Hello {{1}}',parameters_json='["1"]',supported=1,schema_hash='v1')
        frappe.set_user(EDITOR)
        with self.assertRaises(frappe.ValidationError):outbox.send(self.conv.name,'template',template=doc.name,parameters='["World"]')
        frappe.db.set_value('WhatsApp Peer',self.peer.name,'consent_recorded',1)
        intent=outbox.send(self.conv.name,'template',template=doc.name,parameters='["World"]')
        frappe.db.set_value(doc.doctype,doc.name,'schema_hash','v2');frappe.db.commit()
        outbox.dispatch(intent['outbox']);self.post.assert_not_called()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',intent['outbox'],'state'),'Held')

    def test_accepted_response_is_not_delivery(self):
        result=self.intent();frappe.db.commit();self.post.side_effect=None;self.post.return_value=self.accepted()
        outbox.dispatch(result['outbox'])
        self.assertEqual(frappe.db.get_value('WhatsApp Message',result['message'],'status'),'Accepted')
        self.assertEqual(frappe.db.count('WhatsApp Send Attempt'),1)
        outbox.dispatch(result['outbox']);self.assertEqual(self.post.call_count,1)
        row=frappe.get_doc('WhatsApp Outbox',result['outbox'])
        self.assertNotIn(fixtures.DUMMY_TOKEN,row.payload_json)

    def test_timeout_unknown_is_not_retried_by_sweeper(self):
        result=self.intent();frappe.db.commit();self.post.side_effect=requests.ReadTimeout('dummy')
        outbox.dispatch(result['outbox']);self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Unknown')
        outbox.sweep();outbox.dispatch(result['outbox']);self.assertEqual(self.post.call_count,1)
        with self.assertRaises(frappe.ValidationError):outbox.retry(result['outbox'])

    def test_rate_limit_waits_and_is_bounded(self):
        result=self.intent();frappe.db.commit();self.post.side_effect=None;self.post.return_value=self.response(429,{'error':{'code':130429}})
        outbox.dispatch(result['outbox']);row=frappe.get_doc('WhatsApp Outbox',result['outbox'])
        self.assertEqual(row.state,'Retry wait');self.assertGreater(row.next_attempt_at,utcnow())
        outbox.dispatch(row.name);self.assertEqual(self.post.call_count,1)

    def test_known_rejection_can_retry(self):
        result=self.intent();frappe.db.commit();self.post.side_effect=None;self.post.return_value=self.response(400,{'error':{'code':100}})
        outbox.dispatch(result['outbox']);self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Failed')
        self.assertEqual(outbox.retry(result['outbox'])['state'],'Ready')

    def test_revoked_source_permission_holds_send(self):
        result=outbox.create_intent(self.conv.name,'source',body='Hello',source_doctype='ToDo',source_name=fixtures.SOURCE)
        frappe.db.commit();frappe.db.set_value('ToDo',fixtures.SOURCE,'allocated_to',ADMIN);frappe.db.commit()
        outbox.dispatch(result['outbox']);self.post.assert_not_called()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Held')
        frappe.db.set_value('ToDo',fixtures.SOURCE,'allocated_to',EDITOR);frappe.db.commit()

    def test_expired_worker_lease_distinguishes_network_start(self):
        one=self.intent('one');two=self.intent('two')
        for result,started in ((one,0),(two,1)):
            frappe.db.set_value('WhatsApp Outbox',result['outbox'],{'state':'Claimed','network_started':started,'lease_until':utcnow()-timedelta(seconds=1)})
        outbox.sweep()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',one['outbox'],'state'),'Ready')
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',two['outbox'],'state'),'Unknown')

    def test_cancel_before_dispatch_only(self):
        result=self.intent();self.assertEqual(outbox.cancel(result['outbox'],'Changed plan')['state'],'Cancelled')
        with self.assertRaises(frappe.ValidationError):outbox.cancel(result['outbox'],'Again')

    def test_agent_claim_status_and_version_conflict(self):
        version=self.conv.version or 0
        inbox.assign(self.conv.name,version,EDITOR)
        with self.assertRaises(frappe.TimestampMismatchError):inbox.set_status(self.conv.name,version,'Resolved')
        inbox.set_status(self.conv.name,version+1,'Resolved')
        frappe.set_user(ADMIN);inbox.assign(self.conv.name,version+2,ADMIN)
        frappe.set_user(EDITOR)
        with self.assertRaises(frappe.PermissionError):inbox.assign(self.conv.name,version+3,EDITOR)
        with self.assertRaises(frappe.PermissionError):inbox.set_status(self.conv.name,version+3,'Pending')

    def test_personal_read_cursors_and_unread_filter(self):
        webhooks.inbound(self.sender,self.inbound('first'));webhooks.inbound(self.sender,self.inbound('second'))
        inbox.mark_read(self.conv.name,1);inbox.mark_read(self.conv.name,0)
        self.assertEqual(frappe.db.get_value('WhatsApp Conversation Read',{'conversation':self.conv.name,'user':EDITOR},'last_read_sequence'),1)
        self.assertEqual(inbox.list_conversations(assignment='Unread')['items'][0].unread,1)
        self.assertEqual(next(c['value'] for c in api.overview()['cards'] if c['label']=='My unread'),1)
        inbox.mark_read(self.conv.name,2)
        self.assertEqual(inbox.list_conversations(assignment='Unread')['items'],[])
        frappe.set_user(ADMIN)
        self.assertEqual(inbox.list_conversations(assignment='Unread')['items'][0].unread,2)

    def test_pagination_search_and_account_scope(self):
        for i in range(4):inbox.ensure_conversation(self.sender,inbox.ensure_peer('91900000000'+str(i+2),self.sender,'Person '+str(i)))
        page=inbox.list_conversations(limit=2);self.assertEqual(len(page['items']),2)
        second=inbox.list_conversations(limit=2,cursor=json.dumps(page['next_cursor']))
        self.assertFalse(set(r.name for r in page['items']) & set(r.name for r in second['items']))
        self.assertEqual(len(inbox.list_conversations(search='Person 1')['items']),1)
        self.assertEqual(inbox.list_conversations(search="' OR 1=1 --")['items'],[])

    def test_generic_history_and_service_state_cannot_be_edited(self):
        result=self.intent()
        for user in (EDITOR,ADMIN,'Administrator'):
            frappe.set_user(user);doc=frappe.get_doc('WhatsApp Message',result['message']);doc.message='Tampered'
            with self.assertRaises(frappe.PermissionError):doc.save()
        self.assertEqual(frappe.db.get_value('WhatsApp Message',result['message'],'message'),'Hello')

    def test_linking_does_not_grant_source_access(self):
        inbox.link_record(self.conv.name,'ToDo',fixtures.SOURCE)
        self.assertEqual(len(inbox.get_conversation(self.conv.name)['links']),1)
        frappe.set_user(ADMIN)
        self.assertEqual(inbox.get_conversation(self.conv.name)['links'],[])
        with self.assertRaises(frappe.PermissionError):inbox.link_record(self.conv.name,'ToDo',fixtures.SOURCE)

    def test_inbound_is_idempotent_and_reopens(self):
        frappe.db.set_value('WhatsApp Conversation',self.conv.name,'workflow_status','Resolved')
        item=self.inbound();webhooks.inbound(self.sender,item);webhooks.inbound(self.sender,item)
        self.assertEqual(frappe.db.count('WhatsApp Message',{'direction':'Inbound'}),1)
        doc=frappe.get_doc('WhatsApp Conversation',self.conv.name)
        self.assertEqual(doc.workflow_status,'Open');self.assertGreater(doc.window_expires_at,utcnow())

    def test_same_peer_has_distinct_sender_conversations(self):
        frappe.set_user('Administrator')
        sender=frappe.get_doc({'doctype':'WhatsApp Phone Number ID','label':'Second sender','phone_number_id':'9999999','access_token':'dummy','enabled':1,'waba_id':'123456','portfolio_id':'test-portfolio'}).insert()
        peer=inbox.ensure_peer('919000000001',sender)
        other=inbox.ensure_conversation(sender,peer)
        self.assertEqual(peer.name,self.peer.name);self.assertNotEqual(other.name,self.conv.name)
        self.sender_two=sender.name

    def test_status_receipts_do_not_regress_read(self):
        result=self.intent();frappe.db.commit();self.post.side_effect=None;self.post.return_value=self.accepted()
        outbox.dispatch(result['outbox'])
        for state in ('read','sent','delivered','failed'):
            webhooks.status_event(self.sender,{'id':'wamid.fixture','status':state,'timestamp':self.inbound()['timestamp']})
        self.assertEqual(frappe.db.get_value('WhatsApp Message',result['message'],'status'),'Read')
        self.assertEqual(frappe.db.count('WhatsApp Status Event'),4)
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Accepted')

    def test_early_status_correlates_unknown_send(self):
        result=self.intent();frappe.db.set_value('WhatsApp Outbox',result['outbox'],{'state':'Unknown','network_started':1})
        webhooks.status_event(self.sender,{'id':'wamid.late','status':'delivered','timestamp':self.inbound()['timestamp'],'biz_opaque_callback_data':result['outbox']})
        self.assertEqual(frappe.db.get_value('WhatsApp Message',result['message'],'status'),'Delivered')
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Accepted')

    def test_unmatched_receipts_remain_replayable(self):
        webhooks.status_event(self.sender,{'id':'wamid.future','status':'read','timestamp':self.inbound()['timestamp']})
        self.assertEqual(frappe.db.count('WhatsApp Status Event'),1)
        self.assertIsNone(frappe.db.get_value('WhatsApp Status Event',{'provider_message_id':'wamid.future'},'message'))

    def test_future_timestamp_does_not_open_window(self):
        with self.assertRaises(ValueError):webhooks.inbound(self.sender,self.inbound(time=utcnow()+timedelta(hours=3)))
        self.assertEqual(frappe.db.count('WhatsApp Message',{'direction':'Inbound'}),0)

    def test_webhook_hmac_uses_exact_raw_bytes(self):
        import hashlib,hmac
        raw=b'{"object":"whatsapp_business_account"}'
        signature='sha256='+hmac.new(b'dummy',raw,hashlib.sha256).hexdigest()
        self.assertTrue(webhooks.valid_signature(raw,signature,'dummy'))
        self.assertFalse(webhooks.valid_signature(raw+b' ',signature,'dummy'))
        self.assertFalse(webhooks.valid_signature(raw,signature,'other'))

    def test_signed_receipt_processes_every_message_and_status(self):
        payload={'object':'whatsapp_business_account','entry':[{'id':'123456','changes':[{'field':'messages','value':{'metadata':{'phone_number_id':'1234567890'},'messages':[self.inbound('one'),self.inbound('two')],'statuses':[{'id':'unmatched','status':'sent','timestamp':self.inbound()['timestamp']}]}}]}]}
        receipt=insert('WhatsApp Webhook Event',event_key='batch',payload_json=json.dumps(payload),state='Pending',next_attempt_at=utcnow())
        webhooks.process_event(receipt.name)
        self.assertEqual(frappe.db.count('WhatsApp Message',{'direction':'Inbound'}),2)
        self.assertEqual(frappe.db.count('WhatsApp Status Event'),1)
        self.assertEqual(frappe.db.get_value(receipt.doctype,receipt.name,'state'),'Processed')

    def test_unknown_sender_is_quarantined(self):
        payload={'object':'whatsapp_business_account','entry':[{'id':'unknown','changes':[{'field':'messages','value':{'metadata':{'phone_number_id':'987'},'messages':[self.inbound()]}}]}]}
        receipt=insert('WhatsApp Webhook Event',event_key='unknown',payload_json=json.dumps(payload),state='Pending')
        webhooks.process_event(receipt.name)
        self.assertEqual(frappe.db.get_value(receipt.doctype,receipt.name,'state'),'Quarantined')
        self.assertEqual(frappe.db.count('WhatsApp Message',{'direction':'Inbound'}),0)

    def test_private_attachment_validation(self):
        from frappe.utils.file_manager import save_file
        from io import BytesIO
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=72,height=72);buffer=BytesIO();writer.write(buffer);pdf=buffer.getvalue()
        file=save_file('fixture.pdf',pdf,None,None,is_private=1)
        result=outbox.send(self.conv.name,'attachment',body='PDF',file_id=file.name)
        attachment=frappe.get_doc('WhatsApp Attachment',{'message':result['message']})
        self.assertEqual(attachment.mime_type,'application/pdf')
        public=save_file('public.pdf',pdf+b'\n% public',None,None,is_private=0)
        with self.assertRaises(frappe.ValidationError):outbox.send(self.conv.name,'public',body='PDF',file_id=public.name)
        with self.assertRaises(frappe.ValidationError):media.inspect(b'<svg><script/></svg>')

    def test_unsupported_inbound_media_is_visible_but_blocked(self):
        item=self.inbound();item.update(type='document',document={'id':'123','mime_type':'application/x-msdownload','filename':'blocked.exe'})
        webhooks.inbound(self.sender,item)
        data=inbox.get_conversation(self.conv.name)
        self.assertEqual(data['messages'][0]['attachments'][0].state,'Blocked')

    def test_template_catalogue_disables_unsupported_components(self):
        self.assertTrue(catalogue.normalize({'components':[{'type':'BODY','text':'Hello {{1}}'}]})['supported'])
        self.assertFalse(catalogue.normalize({'components':[{'type':'BODY','text':'Hello {{name}}'}]})['supported'])
        self.assertFalse(catalogue.normalize({'components':[{'type':'HEADER','format':'IMAGE'},{'type':'BODY','text':'Hi'}]})['supported'])

    def test_editor_can_activate_schedule_but_not_campaign(self):
        result=automation.save_schedule(self.rule.name,when=str(utcnow()+timedelta(days=1)),timezone_name='UTC')
        schedule=frappe.get_doc('WhatsApp Schedule',result['name'])
        self.assertEqual(schedule.run_as,EDITOR);self.assertEqual(schedule.state,'Active')
        with self.assertRaises(frappe.PermissionError):automation.preview_campaign(self.rule.name)

    def test_schedule_catches_up_within_hour_and_skips_older(self):
        result=automation.save_schedule(self.rule.name,when=str(utcnow()+timedelta(days=1)),timezone_name='UTC')
        now=utcnow();frappe.db.set_value('WhatsApp Schedule',result['name'],'next_due_at',now-timedelta(minutes=59))
        with patch.object(automation,'utcnow',return_value=now):automation.process_due()
        run=frappe.get_doc('WhatsApp Automation Run',{'schedule':result['name']});self.assertEqual(run.state,'Ready')
        automation.process_due();self.assertEqual(frappe.db.count(run.doctype,{'schedule':result['name']}),1)
        frappe.db.set_value('WhatsApp Schedule',result['name'],{'state':'Active','next_due_at':now-timedelta(minutes=61)})
        with patch.object(automation,'utcnow',return_value=now):automation.process_due()
        self.assertEqual(frappe.db.count(run.doctype,{'schedule':result['name'],'state':'Skipped'}),1)

    def test_disabled_schedule_does_not_accumulate_backlog(self):
        result=automation.save_schedule(self.rule.name,when=str(utcnow()+timedelta(days=1)),timezone_name='UTC')
        frappe.db.set_value('WhatsApp Schedule',result['name'],'next_due_at',utcnow()-timedelta(minutes=10))
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',0)
        automation.process_due()
        self.assertEqual(frappe.db.count('WhatsApp Automation Run',{'schedule':result['name'],'state':'Skipped'}),1)
        self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)

    def test_campaign_preview_start_and_one_message_per_record(self):
        frappe.set_user('Administrator')
        other=frappe.get_doc({'doctype':'ToDo','description':'second campaign source','allocated_to':EDITOR,'wm_test_phone':'+919000000001'}).insert()
        self.rule.is_single=1;self.rule.query_filters=json.dumps({'filters':[['name','in',[fixtures.SOURCE,other.name]]]});self.rule.save()
        result=automation.preview_campaign(self.rule.name);self.assertEqual(result['records'],2);self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)
        automation.start_campaign(result['run']);automation.expand_run(result['run'])
        self.assertEqual(frappe.db.count('WhatsApp Outbox',{'run':result['run']}),2)
        automation.expand_run(result['run']);self.assertEqual(frappe.db.count('WhatsApp Outbox',{'run':result['run']}),2)
        frappe.db.set_value(self.rule.doctype,self.rule.name,'query_filters',None)
        frappe.db.delete('ToDo',{'name':other.name})

    def test_preview_rule_change_requires_new_preview(self):
        frappe.set_user('Administrator');self.rule.is_single=1;self.rule.save()
        result=automation.preview_campaign(self.rule.name)
        self.rule.message_preview='Changed';self.rule.save()
        with self.assertRaises(frappe.ValidationError):automation.start_campaign(result['run'])

    def test_schedule_timezone_and_invalid_local_times(self):
        utc=automation.local_to_utc('2026-10-20 10:00:00','Asia/Kolkata')
        self.assertEqual(str(utc),'2026-10-20 04:30:00')
        with self.assertRaises(frappe.ValidationError):automation.local_to_utc('2026-11-01 01:30:00','America/New_York')
        with self.assertRaises(frappe.ValidationError):automation.local_to_utc('2026-03-08 02:30:00','America/New_York')

    def test_workspace_roles_and_admin_summaries(self):
        self.assertEqual(frappe.db.count('Workspace',{'module':'Whatsapp Messaging'}),3)
        self.assertEqual(len(api.overview('messaging')['cards']),4)
        self.assertNotIn('Active campaigns',[c['label'] for c in api.overview('automation')['cards']])
        with self.assertRaises(frappe.PermissionError):api.overview('administration')
        frappe.set_user(ADMIN);self.assertIn('Active campaigns',[c['label'] for c in api.overview('automation')['cards']])
        self.assertEqual(len(api.overview('administration')['cards']),4)

    def test_unrelated_user_cannot_access_any_inbox_surface(self):
        frappe.set_user(fixtures.UNRELATED)
        for operation in (api.bootstrap,inbox.list_conversations,lambda:inbox.get_conversation(self.conv.name),lambda:outbox.send(self.conv.name,'bad',body='Hi')):
            with self.assertRaises(frappe.PermissionError):operation()

    def test_message_and_queue_publish_only_after_commit(self):
        from frappe.utils.background_jobs import get_queue
        queue=get_queue('default');queue.empty();before=queue.count
        result=self.intent();self.assertEqual(queue.count,before)
        frappe.db.rollback();self.assertFalse(frappe.db.exists('WhatsApp Outbox',result['outbox']));self.assertEqual(queue.count,before)
        self.intent('committed');frappe.db.commit();self.assertGreater(queue.count,before)


    def test_duplicate_retry_returns_existing_after_window_closes(self):
        result=self.intent()
        frappe.db.set_value('WhatsApp Conversation',self.conv.name,'window_expires_at',utcnow()-timedelta(seconds=1))
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',0)
        self.assertEqual(self.intent(),result)
        self.assertEqual(frappe.db.count('WhatsApp Outbox'),1)

    def test_disabled_execution_user_holds_intent(self):
        result=self.intent();frappe.db.commit()
        frappe.db.set_value('User',EDITOR,'enabled',0);frappe.db.commit()
        try:
            outbox.dispatch(result['outbox']);self.post.assert_not_called()
            self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Held')
        finally:
            frappe.db.set_value('User',EDITOR,'enabled',1);frappe.db.commit()

    def test_paused_run_waits_and_resumes_without_new_intents(self):
        run=insert('WhatsApp Automation Run',run_key='pause-run',kind='Manual',state='Completed',run_as=EDITOR)
        result=outbox.create_intent(self.conv.name,'paused',body='Hello',run=run.name)
        automation.control_run(run.name,'Pause');frappe.db.commit()
        outbox.dispatch(result['outbox']);self.post.assert_not_called()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Ready')
        automation.control_run(run.name,'Resume');frappe.db.commit()
        self.post.side_effect=None;self.post.return_value=self.accepted()
        outbox.dispatch(result['outbox'])
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Accepted')

    def test_event_and_delete_snapshots_are_transactional(self):
        frappe.set_user('Administrator')
        self.rule.template_event='Update';self.rule.automation_active=1;self.rule.save()
        frappe.set_user(EDITOR)
        source=frappe.get_doc('ToDo',fixtures.SOURCE)
        automation.event_rules(source,['Update'])
        self.assertEqual(frappe.db.count('WhatsApp Outbox'),1)
        automation.event_rules(source,['Update'])
        self.assertEqual(frappe.db.count('WhatsApp Outbox'),1)
        frappe.db.rollback()
        self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)

    def test_deleted_source_is_authorized_before_removal_and_dispatches_snapshot(self):
        frappe.set_user('Administrator')
        self.rule.template_event='Delete';self.rule.automation_active=1;self.rule.save()
        source=frappe.get_doc({'doctype':'ToDo','description':'delete fixture','wm_test_phone':'+919000000001','allocated_to':EDITOR}).insert()
        # Admin created the source; authorize the activation principal and snapshot on deletion.
        automation.event_rules(source,['Delete'])
        row=frappe.get_doc('WhatsApp Outbox',{'source_name':source.name})
        frappe.db.delete('ToDo',{'name':source.name});frappe.db.commit()
        self.post.side_effect=None;self.post.return_value=self.accepted()
        outbox.dispatch(row.name)
        self.assertEqual(frappe.db.get_value(row.doctype,row.name,'state'),'Accepted')

    def test_real_rq_worker_processes_committed_intent(self):
        import subprocess,sys
        from frappe.utils.background_jobs import get_queue
        get_queue('default').empty()
        result=self.intent('rq-job');frappe.db.commit()
        subprocess.run([sys.executable,'/testbench/apps/whatsapp_messaging/tests/integration/worker_once.py'],check=True,timeout=30)
        frappe.db.rollback()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Accepted')
        self.assertEqual(frappe.db.get_value('WhatsApp Message',result['message'],'provider_message_id'),'wamid.rq-fixture')


    def test_manual_rerun_cannot_expand_into_a_bulk_query(self):
        run=insert('WhatsApp Automation Run',run_key='manual-no-bulk',kind='Manual',state='Completed',rule=self.rule.name,run_as=EDITOR)
        with self.assertRaises(frappe.ValidationError):automation.rerun(run.name)

    def test_private_pdf_upload_and_send_are_one_intent(self):
        from frappe.utils.file_manager import save_file
        from io import BytesIO
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=72,height=72);buffer=BytesIO();writer.write(buffer)
        file=save_file('worker.pdf',buffer.getvalue(),None,None,is_private=1)
        result=outbox.send(self.conv.name,'pdf-worker',body='Document',file_id=file.name);frappe.db.commit()
        upload=Mock(json=Mock(return_value={'id':'123456'}));upload.raise_for_status=Mock()
        self.post.side_effect=[upload,self.accepted()]
        outbox.dispatch(result['outbox'])
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'state'),'Accepted')
        self.assertEqual(self.post.call_count,2)
        self.assertEqual(self.post.call_args.kwargs['json']['document']['id'],'123456')

    def test_inbound_pdf_download_uses_private_storage_and_checksum(self):
        from io import BytesIO
        from pypdf import PdfWriter
        import hashlib,base64
        writer=PdfWriter();writer.add_blank_page(width=72,height=72);buffer=BytesIO();writer.write(buffer);pdf=buffer.getvalue()
        item=self.inbound('inbound-pdf');item.update(type='document',document={'id':'123456','mime_type':'application/pdf','sha256':base64.b64encode(hashlib.sha256(pdf).digest()).decode(),'filename':'fixture.pdf'})
        webhooks.inbound(self.sender,item)
        attachment=frappe.get_doc('WhatsApp Attachment',{'provider_media_id':'123456'})
        meta=Mock(json=Mock(return_value={'url':'https://lookaside.fbsbx.com/test-media'}));meta.raise_for_status=Mock()
        response=Mock(is_redirect=False);response.raise_for_status=Mock();response.iter_content=Mock(return_value=[pdf])
        self.get.side_effect=[meta,response]
        media.download_inbound(attachment.name)
        attachment.reload();self.assertEqual(attachment.state,'Ready')
        self.assertEqual(frappe.db.get_value('File',attachment.file,'is_private'),1)

    def test_event_rerun_keeps_original_source_scope(self):
        frappe.set_user('Administrator')
        self.rule.template_event='Update';self.rule.automation_active=1;self.rule.save()
        source=frappe.get_doc('ToDo',fixtures.SOURCE)
        automation.event_rules(source,['Update'])
        run=frappe.get_doc('WhatsApp Automation Run',{'kind':'Event','rule':self.rule.name})
        new=automation.rerun(run.name)
        snapshot=json.loads(frappe.db.get_value('WhatsApp Automation Run',new['run'],'snapshot_json'))
        self.assertEqual([r['name'] for r in snapshot['records']],[source.name])



    def test_desk_application_registration_follows_existing_roles(self):
        from frappe.apps import get_apps
        for user in (EDITOR,ADMIN,'Administrator'):
            frappe.set_user(user)
            # request_cache is per request; separate the simulated identities.
            frappe.local.request_cache = None
            apps=get_apps()
            app=next(a for a in apps if a['name']=='whatsapp_messaging')
            self.assertEqual(app['route'],'/desk/whatsapp-messaging')
        frappe.set_user(fixtures.UNRELATED);frappe.local.request_cache = None
        self.assertNotIn('whatsapp_messaging',[a['name'] for a in get_apps()])



class TestMessagingHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.TestHTTP.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.TestHTTP.tearDownClass.__func__(cls)

    session=fixtures.TestHTTP.session

    def setUp(self):
        frappe.set_user('Administrator')
        settings=frappe.get_doc('WhatsApp Settings');settings.update({'enable_inbound':1,'app_secret':'dummy-app-secret','verify_token':'dummy-verify','enable_outbound_messages':0});settings.save();frappe.db.commit()
        self.client=requests.Session();self.client.headers['Host']=fixtures.SITE

    def tearDown(self):
        frappe.db.rollback();frappe.set_user('Administrator')
        frappe.db.set_single_value('WhatsApp Settings','enable_inbound',0);frappe.db.commit()

    def test_guest_signed_webhook_verification_and_duplicate_receipt(self):
        import hashlib,hmac
        url=self.base+'/api/method/whatsapp_messaging.messaging.webhooks.receive'
        response=self.client.get(url,params={'hub.mode':'subscribe','hub.verify_token':'dummy-verify','hub.challenge':'exact-challenge'},timeout=10)
        self.assertEqual(response.status_code,200);self.assertEqual(response.text,'exact-challenge')
        raw=json.dumps({'object':'whatsapp_business_account','entry':[]}).encode()
        signature='sha256='+hmac.new(b'dummy-app-secret',raw,hashlib.sha256).hexdigest()
        before=frappe.db.count('WhatsApp Webhook Event');frappe.db.rollback()
        for _ in range(2):
            response=self.client.post(url,data=raw,headers={'Content-Type':'application/json','X-Hub-Signature-256':signature},timeout=10)
            self.assertEqual(response.status_code,200,response.text)
        frappe.db.rollback();self.assertEqual(frappe.db.count('WhatsApp Webhook Event'),before+1)

    def test_invalid_signature_does_not_store_event(self):
        url=self.base+'/api/method/whatsapp_messaging.messaging.webhooks.receive'
        before=frappe.db.count('WhatsApp Webhook Event');frappe.db.rollback()
        response=self.client.post(url,data=b'{"object":"whatsapp_business_account","entry":[]}',headers={'Content-Type':'application/json','X-Hub-Signature-256':'sha256=invalid'},timeout=10)
        self.assertEqual(response.status_code,403)
        frappe.db.rollback();self.assertEqual(frappe.db.count('WhatsApp Webhook Event'),before)

    def test_editor_can_load_inbox_but_not_admin_summary(self):
        client=self.session(EDITOR)
        response=client.get(self.base+'/api/method/whatsapp_messaging.messaging.inbox.list_conversations',timeout=10)
        self.assertEqual(response.status_code,200,response.text)
        response=client.get(self.base+'/api/method/whatsapp_messaging.messaging.api.overview',params={'section':'administration'},timeout=10)
        self.assertEqual(response.status_code,403)
        response=client.get(self.base+'/api/method/whatsapp_messaging.messaging.outbox.send',params={'conversation_name':'anything','request_id':'http','body':'Hello'},timeout=10)
        self.assertEqual(response.status_code,403)

    def test_admin_resource_omits_raw_webhook_payload(self):
        receipt=insert('WhatsApp Webhook Event',event_key=digest('http-private',str(utcnow())),state='Pending',payload_json='{"sensitive":"fixture"}')
        frappe.db.commit()
        response=self.session(ADMIN).get(self.base+'/api/resource/WhatsApp%20Webhook%20Event/'+receipt.name,timeout=10)
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn('payload_json',response.json()['data'])



if __name__=='__main__':
    os.chdir('/testbench/sites');fixtures.connect()
    try:
        fixtures.seed()
        from frappe.custom.doctype.custom_field.custom_field import create_custom_field
        if not frappe.db.exists('Custom Field','ToDo-wm_test_phone'):
            create_custom_field('ToDo',{'fieldname':'wm_test_phone','label':'Fixture phone','fieldtype':'Phone'})
        frappe.db.commit()
        unittest.main(verbosity=2)
    finally:frappe.destroy()
