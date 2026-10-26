"""Conversation-flow integration on the network-isolated disposable test site."""
import json
import unittest
from unittest.mock import patch
import frappe
import check_site as fixtures
import check_messaging as messaging_fixtures
from whatsapp_messaging.messaging import flows, webhooks, inbox, outbox
from whatsapp_messaging.messaging.common import utcnow

class FlowIntegration(unittest.TestCase):
    def setUp(self):
        messaging_fixtures.TestMessaging.setUp(self)
        frappe.set_user('Administrator')
        for dt in ('WhatsApp Flow Event','WhatsApp Flow Session','WhatsApp Flow Choice','WhatsApp Flow Step','WhatsApp Conversation Flow'):frappe.db.delete(dt)
        self.enqueue=patch('frappe.enqueue').start()
        self.flow=frappe.get_doc('WhatsApp Conversation Flow',flows.hospital_draft(self.sender.name)['name'])
        for row in self.flow.steps:
            if '[Add ' in row.prompt:row.prompt='Fictional hospital information for this test.'
        self.flow.save();flows.publish(self.flow.name);self.flow.reload();frappe.db.commit();frappe.set_user(fixtures.EDITOR)
        self.seq=0
    def tearDown(self):messaging_fixtures.TestMessaging.tearDown(self)
    def receive(self,text='hello',choice=None):
        self.seq+=1
        item=messaging_fixtures.TestMessaging.inbound(self,id='flow-incoming-'+str(self.seq),body=text)
        if choice:item.update(type='interactive',interactive={'type':'button_reply','button_reply':{'id':choice,'title':'Selected option'}})
        webhooks.inbound(self.sender,item)
        name=frappe.db.get_value('WhatsApp Message',{'provider_message_id':item['id']},'name')
        event=frappe.db.get_value('WhatsApp Flow Event',{'message':name},'name')
        frappe.db.commit()
        if event:flows.process_event(event)
        return frappe.get_doc('WhatsApp Flow Event',event) if event else None
    def session(self):return frappe.get_doc('WhatsApp Flow Session',{'conversation':self.conv.name})
    def latest_payload(self):
        intent=frappe.get_doc('WhatsApp Outbox',self.session().last_outbox);return intent,json.loads(intent.payload_json)
    def test_first_message_creates_one_menu_and_duplicate_does_not_repeat(self):
        event=self.receive();self.assertEqual(event.state,'Processed');self.assertEqual(frappe.db.count('WhatsApp Outbox'),1)
        _,payload=self.latest_payload();self.assertEqual(payload['type'],'interactive');self.assertEqual(payload['interactive']['type'],'button')
        flows.process_event(event.name);self.assertEqual(frappe.db.count('WhatsApp Outbox'),1);self.post.assert_not_called()
    def test_dispatch_sends_the_interactive_object_through_the_existing_outbox(self):
        self.receive();intent,_=self.latest_payload()
        self.post.side_effect=None;self.post.return_value=messaging_fixtures.TestMessaging.accepted(self)
        outbox.dispatch(intent.name)
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args.kwargs['json']['type'],'interactive')
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',intent.name,'state'),'Accepted')
    def test_first_message_can_request_reception_directly(self):
        self.receive('reception');self.assertEqual(self.session().state,'Waiting for staff')
    def test_real_button_selection_records_readable_text_and_routes(self):
        self.receive();_,payload=self.latest_payload();choice=payload['interactive']['action']['buttons'][0]['reply']['id']
        event=self.receive(choice=choice);self.assertEqual(event.state,'Processed');self.assertEqual(self.session().current_step,'department')
        self.assertEqual(frappe.get_doc('WhatsApp Message',event.message).message,'Selected option')
    def test_old_menu_and_other_conversation_tokens_are_ignored(self):
        self.receive();_,p=self.latest_payload();token=p['interactive']['action']['buttons'][0]['reply']['id']
        self.receive(choice=token);count=frappe.db.count('WhatsApp Outbox');event=self.receive(choice=token)
        self.assertEqual(event.state,'Skipped');self.assertEqual(frappe.db.count('WhatsApp Outbox'),count)
        self.assertEqual(self.receive(choice='wa-flow:unrelated').state,'Skipped')
    def test_staff_assignment_pauses_and_holds_pending_automatic_message(self):
        self.receive();intent,_=self.latest_payload();doc=frappe.get_doc('WhatsApp Conversation',self.conv.name)
        inbox.assign(doc.name,doc.version,fixtures.EDITOR);self.assertEqual(self.session().state,'Paused')
        frappe.set_user(intent.requester)
        with self.assertRaises(frappe.ValidationError):outbox.validate_dispatch(intent)
        count=frappe.db.count('WhatsApp Outbox');self.receive('hello');self.assertEqual(frappe.db.count('WhatsApp Outbox'),count)
    def test_manual_reply_pauses_flow_but_is_allowed(self):
        self.receive();result=outbox.send(self.conv.name,'manual-staff-reply',body='Reception can help.')
        self.assertEqual(self.session().state,'Paused');self.assertEqual(result['state'],'Ready')
    def test_local_sweep_queues_only_flow_replies(self):
        self.receive();intent,_=self.latest_payload()
        manual=outbox.send(self.conv.name,'separate-manual-reply',body='Staff reply')
        self.enqueue.reset_mock();outbox.sweep(conversation_flows_only=True);frappe.db.commit()
        names=[call.kwargs.get('name') for call in self.enqueue.call_args_list]
        self.assertIn(intent.name,names);self.assertNotIn(manual['outbox'],names)
    def test_disabled_automation_does_not_build_backlog(self):
        frappe.db.set_single_value('WhatsApp Settings','enable_automation',0);event=self.receive()
        self.assertEqual(event.state,'Skipped');self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)
    def test_disabled_at_arrival_stays_skipped_after_reenabling(self):
        frappe.db.set_single_value('WhatsApp Settings','enable_automation',0);event=self.receive()
        frappe.db.set_single_value('WhatsApp Settings','enable_automation',1);flows.process_event(event.name)
        self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)
    def test_a_message_older_than_the_published_flow_is_not_replayed(self):
        item=messaging_fixtures.TestMessaging.inbound(self,id='older-inbound',body='hello')
        webhooks.inbound(self.sender,item)
        event=frappe.get_doc('WhatsApp Flow Event',{'conversation':self.conv.name})
        from datetime import timedelta
        frappe.db.set_value('WhatsApp Message',event.message,'received_at',utcnow()-timedelta(days=1));frappe.db.commit()
        flows.process_event(event.name);event.reload()
        self.assertEqual(event.state,'Skipped');self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)
    def test_published_pause_rechecked_before_dispatch(self):
        self.receive();intent,_=self.latest_payload();frappe.set_user('Administrator');flows.pause(self.flow.name)
        with self.assertRaises(frappe.ValidationError):outbox.validate_dispatch(intent)
    def test_preview_has_no_messages_or_sessions(self):
        before=frappe.db.count('WhatsApp Outbox');result=flows.preview(self.flow.name)
        self.assertEqual(result['state']['step'],'main_menu');self.assertEqual(frappe.db.count('WhatsApp Flow Session'),0);self.assertEqual(frappe.db.count('WhatsApp Outbox'),before)
    def test_preview_accepts_browser_empty_choice_for_a_typed_answer(self):
        result=flows.preview(self.flow.name)
        result=flows.preview(self.flow.name,state=result['state'],choice='appointment')
        result=flows.preview(self.flow.name,state=result['state'],choice='general_medicine')
        result=flows.preview(self.flow.name,state=result['state'],text='Training visitor',choice='')
        self.assertEqual(result['state']['answers']['name'],'Training visitor')
        self.assertEqual(result['state']['step'],'preferred_date')
    def test_editing_draft_does_not_change_published_words(self):
        frappe.set_user('Administrator');self.flow.steps[0].prompt='Draft wording only';self.flow.save();self.receive()
        _,p=self.latest_payload();self.assertNotIn('Draft wording',p['interactive']['body']['text'])
    def test_canvas_positions_survive_save_without_changing_published_flow(self):
        frappe.set_user('Administrator');version=self.flow.published_version;snapshot=self.flow.published_definition
        self.flow.layout_json=json.dumps({'version':1,'positions':{'main_menu':{'x':501.4,'y':42},'removed_step':{'x':20,'y':20}}})
        self.flow.save();self.flow.reload()
        self.assertEqual(json.loads(self.flow.layout_json),{'version':1,'positions':{'main_menu':{'x':501,'y':42}}})
        self.assertEqual(self.flow.published_version,version);self.assertEqual(self.flow.published_definition,snapshot)
    def test_invalid_canvas_positions_are_rejected(self):
        frappe.set_user('Administrator');self.flow.layout_json=json.dumps({'version':1,'positions':{'main_menu':{'x':-10,'y':True}}})
        with self.assertRaises(frappe.ValidationError):self.flow.save()
    def test_editor_cannot_publish_or_modify_published_snapshot(self):
        with self.assertRaises(frappe.PermissionError):flows.publish(self.flow.name)
        frappe.set_user('Administrator');self.flow.published_definition='{}'
        with self.assertRaises(frappe.PermissionError):self.flow.save()
    def test_one_active_flow_per_business_number(self):
        frappe.set_user('Administrator');second=frappe.get_doc('WhatsApp Conversation Flow',flows.hospital_draft(self.sender.name)['name'])
        for row in second.steps:
            if '[Add ' in row.prompt:row.prompt='Fictional information.'
        second.save()
        with self.assertRaises(frappe.ValidationError):flows.publish(second.name)
    def test_appointment_request_collects_answers_and_hands_off(self):
        self.receive();self.receive('1');self.receive('1');self.receive('Training visitor');self.receive(utcnow().date().isoformat());self.receive('1')
        session=self.session();self.assertEqual(session.state,'Waiting for staff');self.assertEqual(json.loads(session.answers_json)['department'],'General medicine')
        before=frappe.db.count('WhatsApp Outbox');self.receive('hello');self.assertEqual(frappe.db.count('WhatsApp Outbox'),before)
    def test_handoff_resume_waits_for_explicit_menu(self):
        self.receive();self.receive('3');self.assertEqual(self.session().state,'Waiting for staff')
        flows.control(self.conv.name,'Resume');before=frappe.db.count('WhatsApp Outbox');self.receive('Thanks');self.assertEqual(frappe.db.count('WhatsApp Outbox'),before)
        self.receive('menu');self.assertEqual(self.session().state,'Active')
    def test_disabled_publishing_user_does_not_create_response(self):
        frappe.db.set_value('WhatsApp Conversation Flow',self.flow.name,'run_as',fixtures.SUPERVISOR)
        frappe.db.set_value('User',fixtures.SUPERVISOR,'enabled',0)
        try:
            event=self.receive();self.assertEqual(event.state,'Failed');self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)
        finally:
            frappe.db.set_value('User',fixtures.SUPERVISOR,'enabled',1);frappe.db.commit()

    def template_step(self,lookup=False,meta=False):
        from whatsapp_messaging.messaging import template_editor, catalogue
        frappe.set_user('Administrator')
        self.rule=frappe.get_doc(dict(doctype='WhatsApp Message Template',template_name='Flow template fixture '+frappe.generate_hash(length=10),template_doctype='ToDo',phone_number_id=self.sender.name,delivery_mode=template_editor.META if meta else template_editor.LOCAL,
            message_preview='Your booking status is {{template_doctype.status}}.',meta_header='Booking information',meta_footer='Training hospital',
            meta_template_name='flow_confirmation_fixture',meta_language='en_US',meta_category='UTILITY',
            meta_examples=[dict(position=1,source_path='template_doctype.status',sample_value='Open')])).insert()
        def cleanup_template():
            frappe.set_user('Administrator')
            frappe.db.delete('WhatsApp Template Variable',{'parent':self.rule.name})
            frappe.db.delete(self.rule.doctype,{'name':self.rule.name});frappe.db.commit()
        self.addCleanup(cleanup_template)
        if meta:
            _,_,components=template_editor.compile_content(self.rule,examples=True)
            name=catalogue.upsert('123456',dict(id='991234567890',name=self.rule.meta_template_name,language='en_US',category='UTILITY',status='APPROVED',components=components,parameter_format='POSITIONAL'))
            frappe.db.set_value(self.rule.doctype,self.rule.name,'approved_template',name);self.rule.reload()
        original_phones=frappe.get_all('ToDo',fields=['name','wm_test_phone'])
        def restore_phones():
            for original in original_phones:
                if frappe.db.exists('ToDo',original.name):frappe.db.set_value('ToDo',original.name,'wm_test_phone',original.wm_test_phone)
            frappe.db.commit()
        self.addCleanup(restore_phones)
        frappe.db.set_value('ToDo',{},'wm_test_phone',None)
        frappe.db.set_value('ToDo',fixtures.SOURCE,dict(status='Open',wm_test_phone='919000000001'))
        row=next(s for s in self.flow.steps if s.step_key=='hours')
        row.update(dict(step_type='Template',prompt='',message_template=self.rule.name,template_bindings=json.dumps({'template_doctype.status':'Confirmed'}),
            template_data_source='Record lookup' if lookup else 'Flow values',record_phone_field='wm_test_phone',record_filters='[]',no_match_step='reception',multiple_match_step='reception'))
        self.flow.save();flows.publish(self.flow.name);self.flow.reload();frappe.db.commit()
        return next(s for s in self.flow.steps if s.step_key=='hours')
    def reach_template(self):
        self.receive();self.receive('2');event=self.receive('Opening hours')
        return event
    def template_intent(self):
        name=frappe.db.get_value('WhatsApp Outbox',{'flow_step':'hours'},'name')
        self.assertTrue(name,'Template should have produced an outbox message')
        return frappe.get_doc('WhatsApp Outbox',name)
    def test_local_template_renders_fields_and_header_footer(self):
        self.template_step();event=self.reach_template();self.assertEqual(event.state,'Processed')
        intent=self.template_intent();payload=json.loads(intent.payload_json)
        self.assertEqual(payload['text']['body'],'Booking information\n\nYour booking status is Confirmed.\n\nTraining hospital')
        self.assertEqual(intent.conversation_flow,self.flow.name);self.post.assert_not_called()
    def test_meta_template_uses_approved_payload_and_consent(self):
        self.template_step(meta=True);frappe.db.set_value('WhatsApp Peer',self.peer.name,'consent_recorded',1)
        self.assertEqual(self.reach_template().state,'Processed')
        payload=json.loads(self.template_intent().payload_json)
        self.assertEqual(payload['type'],'template');self.assertEqual(payload['template']['components'][0]['parameters'][0]['text'],'Confirmed')
    def test_meta_without_consent_does_not_create_template_intent(self):
        self.template_step(meta=True)
        self.assertEqual(self.reach_template().state,'Failed')
        self.assertFalse(frappe.db.exists('WhatsApp Outbox',{'flow_step':'hours'}));self.post.assert_not_called()
    def test_changed_template_holds_queued_message(self):
        self.template_step();self.reach_template();intent=self.template_intent()
        self.rule.message_preview='Changed {{template_doctype.status}}';self.rule.save();frappe.db.commit()
        outbox.dispatch(intent.name);intent.reload()
        self.assertEqual(intent.state,'Held');self.post.assert_not_called()
    def test_record_lookup_selects_only_contact_record(self):
        self.template_step(lookup=True);self.assertEqual(self.reach_template().state,'Processed')
        intent=self.template_intent();self.assertEqual(intent.source_doctype,'ToDo');self.assertEqual(intent.source_name,fixtures.SOURCE)
        self.assertIn('status is Open',json.loads(intent.payload_json)['text']['body'])
    def test_record_lookup_does_not_read_another_contacts_record(self):
        self.template_step(lookup=True);frappe.db.set_value('ToDo',fixtures.SOURCE,'wm_test_phone','919000000002')
        self.assertEqual(self.reach_template().state,'Processed');self.assertEqual(self.session().state,'Waiting for staff')
        self.assertFalse(frappe.db.exists('WhatsApp Outbox',{'flow_step':'hours'}))
    def test_multiple_records_handoff_and_filter_can_disambiguate(self):
        row=self.template_step(lookup=True)
        other=frappe.get_doc(dict(doctype='ToDo',description='Fictional second booking',status='Closed',wm_test_phone='+919000000001',allocated_to=fixtures.EDITOR)).insert()
        self.addCleanup(lambda:frappe.db.delete('ToDo',{'name':other.name}))
        self.assertEqual(self.reach_template().state,'Processed');self.assertEqual(self.session().state,'Waiting for staff')
        self.assertFalse(frappe.db.exists('WhatsApp Outbox',{'flow_step':'hours'}))
        row.record_filters=json.dumps([dict(field='status',operator='=',value='Open')]);self.flow.save();flows.publish(self.flow.name);frappe.db.commit()
        flows.control(self.conv.name,'Resume');self.receive('menu');self.receive('2');self.receive('Opening hours')
        self.assertEqual(self.template_intent().source_name,fixtures.SOURCE)
    def test_lookup_rechecks_record_details_before_network(self):
        self.template_step(lookup=True);self.reach_template();intent=self.template_intent()
        frappe.db.set_value('ToDo',fixtures.SOURCE,'status','Closed');frappe.db.commit()
        outbox.dispatch(intent.name);intent.reload();self.assertEqual(intent.state,'Held');self.post.assert_not_called()
    def test_lookup_rechecks_contact_ownership_before_network(self):
        self.template_step(lookup=True);self.reach_template();intent=self.template_intent()
        frappe.db.set_value('ToDo',fixtures.SOURCE,'wm_test_phone','919000000002');frappe.db.commit()
        outbox.dispatch(intent.name);intent.reload();self.assertEqual(intent.state,'Held');self.post.assert_not_called()
    def test_preview_uses_fictional_records_and_handles_missing_match(self):
        self.template_step(lookup=True)
        with patch('whatsapp_messaging.messaging.flow_templates.resolve_lookup',side_effect=AssertionError('Preview must not query records')):
            result=flows.preview(self.flow.name);result=flows.preview(self.flow.name,state=result['state'],choice='information')
            result=flows.preview(self.flow.name,state=result['state'],choice='hours',lookup_result='no_match')
        self.assertEqual(result['state']['status'],'Waiting for staff');self.assertEqual(frappe.db.count('WhatsApp Outbox'),0)
    def test_changed_template_source_holds_queued_message(self):
        self.template_step();self.reach_template();intent=self.template_intent()
        if not frappe.db.exists('WhatsApp Template Field Policy','Communication'):
            frappe.get_doc(dict(doctype='WhatsApp Template Field Policy',source_doctype='Communication',allowed_fields='["status"]')).insert()
        self.rule.template_doctype='Communication';self.rule.save();frappe.db.commit()
        outbox.dispatch(intent.name);intent.reload();self.assertEqual(intent.state,'Held');self.post.assert_not_called()
    def test_record_filter_uses_collected_answer(self):
        row=self.template_step(lookup=True)
        self.flow.start_step='booking_status'
        self.flow.set('steps',[dict(step_key='booking_status',step_type='Question',prompt='Which booking status?',answer_key='status',answer_type='Text',next_step='lookup'),
            dict(step_key='lookup',step_type='Template',message_template=self.rule.name,template_data_source='Record lookup',record_phone_field='wm_test_phone',record_filters=json.dumps([dict(field='status',operator='=',value='{{answers.status}}')]),next_step='done',no_match_step='reception',multiple_match_step='reception'),
            dict(step_key='done',step_type='End',prompt='Thank you.'),dict(step_key='reception',step_type='Handoff',prompt='Reception will help.')])
        self.flow.set('choices',[]);self.flow.save();flows.publish(self.flow.name);frappe.db.commit()
        self.receive();self.assertEqual(self.receive('Open').state,'Processed')
        name=frappe.db.get_value('WhatsApp Outbox',{'flow_step':'lookup'},'name');self.assertTrue(name)
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',name,'source_name'),fixtures.SOURCE)
    def test_unapproved_meta_template_cannot_be_published(self):
        self.template_step(meta=True)
        frappe.db.set_value('WhatsApp Approved Template',self.rule.approved_template,'approval_status','PENDING')
        with self.assertRaises(frappe.ValidationError):flows.publish(self.flow.name)
    def test_revoked_shared_field_holds_queued_lookup(self):
        self.template_step(lookup=True);self.reach_template();intent=self.template_intent()
        policy=frappe.get_doc('WhatsApp Template Field Policy','ToDo');policy.allowed_fields='[]';policy.save();frappe.db.commit()
        try:
            outbox.dispatch(intent.name);intent.reload();self.assertEqual(intent.state,'Held');self.post.assert_not_called()
        finally:
            policy.allowed_fields='["status"]';policy.save();frappe.db.commit()
    def test_linked_phone_lookup_reads_parent_record(self):
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
        row=self.template_step(lookup=True)
        create_custom_fields({'ToDo':[dict(fieldname='wm_test_link',label='Training linked record',fieldtype='Link',options='ToDo')]})
        child=frappe.get_doc(dict(doctype='ToDo',description='Fictional linked contact',wm_test_phone='+919000000001',allocated_to=fixtures.EDITOR)).insert()
        self.addCleanup(lambda:frappe.db.delete('ToDo',{'name':child.name}))
        frappe.db.set_value('ToDo',fixtures.SOURCE,dict(wm_test_link=child.name,wm_test_phone='919000000002'))
        row.record_phone_field='wm_test_link.wm_test_phone';self.flow.save();flows.publish(self.flow.name);frappe.db.commit()
        self.assertEqual(self.reach_template().state,'Processed');self.assertEqual(self.template_intent().source_name,fixtures.SOURCE)

    def latest_step(self):
        row=self.template_step(lookup=True);row.record_selection='Most recently created'
        row.record_filters=json.dumps([dict(field='status',operator='=',value='Open')]);self.flow.save();flows.publish(self.flow.name);self.flow.reload();frappe.db.commit()
        old_creation=frappe.db.get_value('ToDo',fixtures.SOURCE,'creation')
        self.addCleanup(lambda:frappe.db.set_value('ToDo',fixtures.SOURCE,'creation',old_creation))
        frappe.db.set_value('ToDo',fixtures.SOURCE,'creation','2020-01-01 00:00:00')
    def booking(self,created,status='Open',phone='+919000000001'):
        doc=frappe.get_doc(dict(doctype='ToDo',description='Fictional booked appointment',status=status,wm_test_phone=phone,allocated_to=fixtures.EDITOR)).insert()
        frappe.db.set_value('ToDo',doc.name,'creation',created)
        self.addCleanup(lambda:frappe.db.delete('ToDo',{'name':doc.name}))
        return doc
    def test_latest_created_matching_status_is_selected_without_date(self):
        self.latest_step();selected=self.booking('2026-01-02 00:00:00')
        self.booking('2026-01-03 00:00:00',status='Closed');self.booking('2026-02-01 00:00:00',phone='+919000000002')
        frappe.db.set_value('ToDo',fixtures.SOURCE,'modified','2026-03-01 00:00:00')
        self.assertEqual(self.reach_template().state,'Processed');self.assertEqual(self.template_intent().source_name,selected.name)
    def test_newer_booking_before_dispatch_holds_the_old_confirmation(self):
        self.latest_step();self.booking('2026-01-02 00:00:00');self.reach_template();intent=self.template_intent()
        self.booking('2026-01-03 00:00:00');frappe.db.commit()
        outbox.dispatch(intent.name);intent.reload();self.assertEqual(intent.state,'Held');self.post.assert_not_called()
    def test_latest_selection_has_deterministic_creation_tie_break(self):
        self.latest_step();first=self.booking('2026-01-02 00:00:00');second=self.booking('2026-01-02 00:00:00')
        self.reach_template();self.assertEqual(self.template_intent().source_name,max(first.name,second.name))
    def test_unknown_record_selection_is_rejected(self):
        from whatsapp_messaging.messaging.flow_templates import compile_lookup,snapshot
        self.template_step(lookup=True)
        row=next(row.as_dict() for row in self.flow.steps if row.step_key=='hours');row['record_selection']='arbitrary SQL'
        with self.assertRaises(frappe.ValidationError):compile_lookup(row,snapshot(self.rule.name,self.sender.name))
    def phone_confirmation_flow(self):
        self.latest_step();self.flow.start_step='confirm_phone'
        self.flow.set('steps',[dict(step_key='confirm_phone',step_type='Menu',prompt='Is +{{contact.phone_number}} your registered number?'),
            dict(step_key='registered_phone',step_type='Question',prompt='Enter your registered number with country code.',answer_key='registered_phone',answer_type='Phone',next_step='hours',phone_mismatch_step='verify'),
            dict(step_key='hours',step_type='Template',message_template=self.rule.name,template_data_source='Record lookup',record_phone_field='wm_test_phone',record_selection='Most recently created',record_filters='[{"field":"status","operator":"=","value":"Open"}]',next_step='done',no_match_step='verify',multiple_match_step='verify'),
            dict(step_key='done',step_type='End',prompt='Thank you.'),dict(step_key='verify',step_type='Handoff',prompt='Reception will verify your registered number.')])
        self.flow.set('choices',[dict(from_step='confirm_phone',choice_key='yes',label='Yes, this number',next_step='hours'),dict(from_step='confirm_phone',choice_key='no',label='No, enter number',next_step='registered_phone')])
        self.flow.save();flows.publish(self.flow.name);frappe.db.commit()
    def test_no_collects_number_and_other_number_does_not_lookup_booking(self):
        self.phone_confirmation_flow();self.receive();self.receive('2')
        self.assertEqual(self.session().current_step,'registered_phone')
        with patch('whatsapp_messaging.messaging.flow_templates.resolve_lookup',side_effect=AssertionError('Do not look up an unverified number')):
            self.assertEqual(self.receive('+91 90000 00002').state,'Processed')
        self.assertEqual(self.session().state,'Waiting for staff');self.assertEqual(json.loads(self.session().answers_json)['registered_phone'],'919000000002')
        self.assertFalse(frappe.db.exists('WhatsApp Outbox',{'flow_step':'hours'}))
    def test_no_then_matching_phone_finds_latest_booking(self):
        self.phone_confirmation_flow();selected=self.booking('2026-01-02 00:00:00');self.receive();self.receive('2');self.receive('+91 90000 00001')
        self.assertEqual(self.template_intent().source_name,selected.name)

if __name__=='__main__':
    fixtures.connect();fixtures.seed()
    try:unittest.main(verbosity=2)
    finally:frappe.destroy()
