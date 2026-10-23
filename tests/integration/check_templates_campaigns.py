"""Separate content/campaign lifecycle and Meta review, with mocked transport."""
import json
import unittest
from datetime import timedelta, timezone
from unittest.mock import Mock, patch

import frappe
import requests
import check_site as fixtures
from whatsapp_messaging.messaging import template_editor as editor, catalogue, campaigns, automation, inbox, outbox, template_import
from whatsapp_messaging.messaging.common import utcnow


class TestTemplatesCampaigns(unittest.TestCase):
    def setUp(self):
        assert frappe.local.site==fixtures.SITE and frappe.conf.db_host=='db'
        frappe.set_user('Administrator')
        self.templates=[];self.campaigns=[];self.catalogues=[];self.receipts=[]
        self.addCleanup(self.cleanup)
        p=patch('requests.sessions.Session.request',side_effect=AssertionError('No external transport'))
        self.transport=p.start();self.addCleanup(p.stop)
        p=patch('frappe.enqueue');self.queue=p.start();self.addCleanup(p.stop)
        for flag in ('enable_outbound_messages','enable_automation','enable_inbound'):
            frappe.db.set_single_value('WhatsApp Settings',flag,1)
        frappe.db.set_value('WhatsApp Phone Number ID',fixtures.ACCOUNT,dict(enabled=1,waba_id='123456'))
        frappe.db.commit()

    def cleanup(self):
        frappe.set_user('Administrator');frappe.db.rollback()
        for name in self.receipts:frappe.db.delete('WhatsApp Webhook Event',{'name':name})
        for name in self.campaigns:
            for row in frappe.get_all('WhatsApp Outbox',filters={'rule':name},fields=['message']):
                frappe.db.delete('WhatsApp Attachment',{'message':row.message})
                frappe.db.delete('WhatsApp Message',{'name':row.message})
        for dt in ('WhatsApp Outbox','WhatsApp Automation Run','WhatsApp Schedule'):
            for name in self.campaigns:frappe.db.delete(dt,{'rule':name})
        for name in self.campaigns:
            frappe.db.delete('Static Recipient Link',{'parent':name,'parenttype':'WhatsApp Campaign'})
            frappe.db.delete('WhatsApp Campaign',{'name':name})
        for name in self.templates:
            frappe.db.delete('WhatsApp Template Variable',{'parent':name})
            frappe.db.delete('WhatsApp Message Template',{'name':name})
        for name in self.catalogues:frappe.db.delete('WhatsApp Approved Template',{'name':name})
        for flag in ('enable_outbound_messages','enable_automation','enable_inbound'):
            frappe.db.set_single_value('WhatsApp Settings',flag,0)
        frappe.db.commit()

    def template(self,meta=True,**values):
        key=frappe.generate_hash(length=10)
        data=dict(doctype='WhatsApp Message Template',template_name='Template fixture '+key,
            phone_number_id=fixtures.ACCOUNT,template_doctype='ToDo',
            delivery_mode=editor.META if meta else editor.LOCAL,
            message_preview='Hello {{template_doctype.status}}, your appointment is confirmed.',
            meta_template_name='fixture_'+key,meta_language='en_US',meta_category='UTILITY',
            meta_examples=[dict(position=1,source_path='template_doctype.status',sample_value='Booked')])
        data.update(values)
        doc=frappe.get_doc(data).insert();self.templates.append(doc.name);frappe.db.commit();return doc

    def campaign(self,template,**values):
        data=dict(doctype='WhatsApp Campaign',campaign_name='Campaign fixture '+frappe.generate_hash(length=8),
            message_template=template.name,phone_number_id=fixtures.ACCOUNT,disable=0,template_event='Custom',
            phone_number_field_name='wm_test_phone')
        data.update(values)
        doc=frappe.get_doc(data).insert();self.campaigns.append(doc.name);frappe.db.commit();return doc

    def meta_item(self,template,status='APPROVED',**values):
        _,_,components=editor.compile_content(template,examples=True)
        item=dict(id='991234567890',name=template.meta_template_name,language=template.meta_language,
            category=template.meta_category,status=status,components=components,parameter_format='POSITIONAL')
        item.update(values)
        name=catalogue.upsert('123456',item)
        if name not in self.catalogues:self.catalogues.append(name)
        frappe.db.set_value(template.doctype,template.name,'approved_template',name)
        frappe.db.commit();template.reload();return name

    def submit(self,template,response=None,side_effect=None):
        response=response or Mock(status_code=200,json=Mock(return_value={'id':'991234567890','status':'PENDING','category':'UTILITY'}))
        with patch.object(editor.requests,'post',return_value=response,side_effect=side_effect) as post:
            result=editor.submit(template.name)
        template.reload()
        if template.approved_template and template.approved_template not in self.catalogues:self.catalogues.append(template.approved_template)
        return result,post

    def import_entry(self, **values):
        item=dict(id=str(990000+len(self.catalogues)),name='import_fixture_'+frappe.generate_hash(length=10),
            language='en_US',status='APPROVED',category='UTILITY',parameter_format='POSITIONAL',
            components=[dict(type='HEADER',format='TEXT',text='Riverbend Hospital'),
                dict(type='BODY',text='Your appointment is confirmed.'),dict(type='FOOTER',text='Patient Support')])
        item.update(values)
        name=catalogue.upsert('123456',item);self.catalogues.append(name)
        return name

    def import_selection(self,names):
        result=template_import.import_selected(fixtures.ACCOUNT,'ToDo',names)
        self.templates.extend(row['name'] for row in result['imported'])
        return result

    def test_selection_imports_only_chosen_content_without_campaigns_or_sends(self):
        chosen=self.import_entry();other=self.import_entry()
        counts={dt:frappe.db.count(dt) for dt in ('WhatsApp Campaign','WhatsApp Message','WhatsApp Outbox')}
        result=self.import_selection(json.dumps([chosen]))
        self.assertEqual(len(result['imported']),1)
        doc=frappe.get_doc(editor.DOCT,result['imported'][0]['name'])
        self.assertEqual(doc.approved_template,chosen);self.assertEqual(doc.template_doctype,'ToDo')
        self.assertEqual(doc.meta_header,'Riverbend Hospital');self.assertEqual(doc.meta_footer,'Patient Support')
        self.assertTrue(doc.disable);self.assertFalse(doc.automation_active)
        self.assertTrue(editor.matches(doc,frappe.get_doc('WhatsApp Approved Template',chosen)))
        self.assertFalse(frappe.db.exists(editor.DOCT,{'approved_template':other}))
        self.assertEqual(counts,{dt:frappe.db.count(dt) for dt in counts})
        self.queue.assert_not_called();self.transport.assert_not_called()

    def test_repeated_selection_preserves_existing_draft_and_deduplicates_choices(self):
        entry=self.import_entry();result=self.import_selection([entry,entry])
        doc=frappe.get_doc(editor.DOCT,result['imported'][0]['name'])
        doc.message_preview='My unsaved-to-Meta local wording.';doc.save()
        modified=doc.modified
        again=self.import_selection([entry])
        self.assertEqual(again['imported'],[]);self.assertEqual(again['existing'],[doc.name])
        doc.reload();self.assertEqual(doc.message_preview,'My unsaved-to-Meta local wording.')
        self.assertEqual(str(doc.modified),str(modified))
        row=next(row for row in template_import.options(fixtures.ACCOUNT) if row['name']==entry)
        self.assertFalse(row['can_import']);self.assertEqual(row['existing'],doc.name)

    def test_modal_lists_every_review_status_and_explains_unsupported_formats(self):
        approved=self.import_entry();pending=self.import_entry(status='PENDING');rejected=self.import_entry(status='REJECTED')
        unsupported=self.import_entry(components=[dict(type='HEADER',format='IMAGE'),dict(type='BODY',text='Hello')])
        rows={row['name']:row for row in template_import.options(fixtures.ACCOUNT)}
        self.assertEqual([rows[n]['status'] for n in (approved,pending,rejected)],['APPROVED','PENDING','REJECTED'])
        self.assertTrue(rows[rejected]['can_import']);self.assertFalse(rows[unsupported]['can_import'])
        self.assertIn('Unsupported',rows[unsupported]['reason'])
        result=self.import_selection([pending,rejected])
        self.assertEqual({frappe.get_doc(editor.DOCT,r['name']).meta_status for r in result['imported']},{'In review','Rejected'})

    def test_import_leaves_numbered_variables_for_explicit_mapping(self):
        entry=self.import_entry(components=[dict(type='BODY',text='Hello {{1}}, your appointment is confirmed.')])
        result=self.import_selection([entry]);doc=frappe.get_doc(editor.DOCT,result['imported'][0]['name'])
        self.assertEqual(result['imported'][0]['variables'],1)
        self.assertEqual(doc.meta_examples[0].source_path,'')
        with self.assertRaises(frappe.ValidationError):editor.ensure_sendable(doc)
        doc.meta_examples[0].source_path='template_doctype.status';doc.save()
        self.assertEqual(editor.ensure_sendable(doc),['template_doctype.status'])

    def test_import_rechecks_waba_support_and_missing_source_before_any_insert(self):
        valid=self.import_entry();changed=self.import_entry()
        frappe.db.set_value('WhatsApp Approved Template',changed,'supported',0)
        with self.assertRaises(frappe.ValidationError):self.import_selection([valid,changed])
        self.assertFalse(frappe.db.exists(editor.DOCT,{'approved_template':valid}))
        frappe.db.set_value('WhatsApp Approved Template',changed,dict(supported=1,waba_id='different'))
        with self.assertRaises(frappe.ValidationError):self.import_selection([valid,changed])
        with self.assertRaises(frappe.ValidationError):template_import.import_selected(fixtures.ACCOUNT,'',[valid])
        for names in ([],{},'invalid json',[valid]*101,[123]):
            with self.assertRaises(frappe.ValidationError):self.import_selection(names)
        self.assertFalse(frappe.db.exists(editor.DOCT,{'approved_template':valid}))

    def test_selection_import_requires_supervisor_and_sender_access(self):
        entry=self.import_entry();frappe.set_user(fixtures.EDITOR)
        for action in (lambda:template_import.options(fixtures.ACCOUNT),lambda:self.import_selection([entry]),
                lambda:template_import.sync_options(fixtures.ACCOUNT)):
            with self.assertRaises(frappe.PermissionError):action()
        frappe.set_user('Administrator');frappe.db.set_value('WhatsApp Phone Number ID',fixtures.ACCOUNT,'enabled',0)
        with self.assertRaises(frappe.ValidationError):self.import_selection([entry])
        self.transport.assert_not_called()

    def test_same_meta_name_in_two_languages_imports_as_distinct_records(self):
        one=self.import_entry();linked=frappe.get_doc('WhatsApp Approved Template',one)
        two=self.import_entry(name=linked.template_name,language='te')
        result=self.import_selection([one,two]);self.assertEqual(len(result['imported']),2)
        self.assertEqual({frappe.get_doc(editor.DOCT,row['name']).meta_language for row in result['imported']},{'en_US','te'})

    def test_sync_modal_fetches_catalogue_but_waits_for_selection_before_importing(self):
        item=dict(id='987654321',name='sync_fixture_'+frappe.generate_hash(length=8),language='en_US',status='APPROVED',
            category='UTILITY',components=[dict(type='BODY',text='Welcome to Riverbend Hospital.')])
        response=Mock(status_code=200,json=Mock(return_value={'data':[item]}))
        count=frappe.db.count(editor.DOCT)
        with patch.object(catalogue.requests,'get',return_value=response) as get:
            result=template_import.sync_options(fixtures.ACCOUNT)
        row=next(row for row in result['templates'] if row['template_name']==item['name'])
        self.catalogues.append(row['name'])
        self.assertTrue(row['can_import']);self.assertEqual(result['synced'],1)
        self.assertEqual(frappe.db.count(editor.DOCT),count);get.assert_called_once()
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',0)
        with self.assertRaises(frappe.ValidationError):template_import.sync_options(fixtures.ACCOUNT)
        self.queue.assert_not_called();self.transport.assert_not_called()

    def test_saving_content_has_no_campaign_and_never_submits(self):
        t=self.template(meta_status='Approved',meta_provider_id='forged')
        self.assertEqual(t.meta_status,'Draft');self.assertFalse(t.meta_provider_id)
        self.assertEqual(t.meta_examples[0].source_path,'template_doctype.status')
        self.assertEqual(t.meta_examples[0].sample_value,'Booked')
        self.assertFalse(frappe.db.exists('WhatsApp Campaign',t.name))
        self.assertTrue(frappe.get_meta(t.doctype).get_field('template_event').hidden)
        self.queue.assert_not_called();self.transport.assert_not_called()

    def test_submission_uses_review_examples_and_creates_no_messages(self):
        t=self.template();count=frappe.db.count('WhatsApp Message')
        result,post=self.submit(t)
        self.assertEqual(result['status'],'Idle')
        self.assertEqual(t.meta_status,'In review')
        self.assertEqual(t.meta_provider_id,'991234567890')
        self.assertEqual(post.call_args.args[0],'https://graph.facebook.com/v26.0/123456/message_templates')
        payload=post.call_args.kwargs['json']
        self.assertEqual(payload['components'][0]['text'],'Hello {{1}}, your appointment is confirmed.')
        self.assertEqual(payload['components'][0]['example']['body_text'],[['Booked']])
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(frappe.db.count('WhatsApp Message'),count)

    def test_fixed_header_body_and_footer_are_submitted_as_separate_components(self):
        t=self.template(meta_header='Welcome to Riverbend Hospital',meta_footer='Patient Support')
        result,post=self.submit(t)
        self.assertEqual(result['status'],'Idle')
        components=post.call_args.kwargs['json']['components']
        self.assertEqual(components[0],dict(type='HEADER',format='TEXT',text='Welcome to Riverbend Hospital'))
        self.assertEqual(components[1]['type'],'BODY')
        self.assertEqual(components[1]['example']['body_text'],[['Booked']])
        self.assertEqual(components[2],dict(type='FOOTER',text='Patient Support'))

    def test_header_and_footer_constraints_apply_to_both_message_modes(self):
        for meta in (True,False):
            t=self.template(meta=meta,meta_header='H'*60,meta_footer='F'*60)
            for field,value in [('meta_header','H'*61),('meta_footer','F'*61),
                    ('meta_header','Hello {{template_doctype.status}}'),('meta_footer','Line one\nLine two')]:
                t.reload();t.set(field,value)
                with self.assertRaises(frappe.ValidationError):t.save()
        self.transport.assert_not_called()

    def test_header_or_footer_changes_require_approval_again(self):
        t=self.template(meta_header='Welcome',meta_footer='Patient Support');self.meta_item(t)
        for field,value in [('meta_header','New welcome'),('meta_footer','Reception')]:
            t.reload();before=t.get(field);t.set(field,value);t.save()
            self.assertEqual(t.meta_status,'Changes not submitted')
            with self.assertRaises(frappe.ValidationError):editor.ensure_sendable(t)
            t.set(field,before);t.save()
        self.assertEqual(editor.ensure_sendable(t),['template_doctype.status'])

    def test_import_keeps_the_header_footer_and_body_mapping(self):
        t=self.template(meta_header='Welcome',meta_footer='Patient Support');name=self.meta_item(t)
        target=self.template(meta=False);values=editor.import_content(target.name,name)
        self.assertEqual(values['meta_header'],'Welcome');self.assertEqual(values['meta_footer'],'Patient Support')
        target.update(values);target.meta_examples[0].source_path='template_doctype.status';target.save()
        self.assertEqual(editor.ensure_sendable(target),['template_doctype.status'])

    def test_media_variable_and_duplicate_headers_remain_unsupported(self):
        body={'type':'BODY','text':'Hello {{1}}, your visit is confirmed.'}
        self.assertTrue(catalogue.normalize({'components':[dict(type='HEADER',format='TEXT',text='Welcome'),body,dict(type='FOOTER',text='Reception')]})['supported'])
        for components in ([dict(type='HEADER',format='IMAGE'),body],
                [dict(type='HEADER',format='TEXT',text='Hello {{1}}'),body],
                [dict(type='HEADER',format='TEXT',text='H'*61),body],
                [dict(type='HEADER',format='TEXT',text='One'),dict(type='HEADER',format='TEXT',text='Two'),body],
                [body,dict(type='FOOTER',text='Hello {{1}}')]):
            self.assertFalse(catalogue.normalize({'components':components})['supported'])

    def test_meta_history_and_bulk_preview_show_all_components(self):
        t=self.template(meta_header='Welcome',meta_footer='Patient Support');self.meta_item(t)
        c=self.campaign(t,is_single=1,query_filters=json.dumps({'filters':[['ToDo','name','=',fixtures.SOURCE]]}))
        source=frappe.get_doc('ToDo',fixtures.SOURCE)
        frappe.db.set_value(source.doctype,source.name,'wm_test_phone','919000000001');source.reload()
        sender=frappe.get_doc('WhatsApp Phone Number ID',fixtures.ACCOUNT)
        peer=inbox.ensure_peer(source.wm_test_phone,sender);frappe.db.set_value(peer.doctype,peer.name,'consent_recorded',1)
        conv=inbox.ensure_conversation(sender,peer)
        result=outbox.create_intent(conv.name,'framed-'+frappe.generate_hash(length=10),template=t.approved_template,parameters=[source.status],rule=c.name)
        expected='Welcome\n\nHello '+source.status+', your appointment is confirmed.\n\nPatient Support'
        self.assertEqual(frappe.db.get_value('WhatsApp Message',result['message'],'message'),expected)
        payload=json.loads(frappe.db.get_value('WhatsApp Outbox',result['outbox'],'payload_json'))
        self.assertEqual([item['type'] for item in payload['template']['components']],['body'])
        preview=automation.preview_campaign(c.name)
        self.assertEqual(preview['items'][0]['body'],expected)
        entry=next(row for row in catalogue.list_templates(fixtures.ACCOUNT) if row.name==t.approved_template)
        self.assertIn('HEADER',entry['components_json'])

    def test_local_media_captions_include_header_and_footer_and_enforce_total_limit(self):
        from io import BytesIO
        from PIL import Image
        from whatsapp_messaging.messaging.common import insert
        data=BytesIO();Image.new('RGB',(2,2),'green').save(data,format='PNG')
        file=frappe.get_doc(dict(doctype='File',file_name='framing-test.png',content=data.getvalue(),is_private=1)).insert()
        asset=frappe.get_doc(dict(doctype='WhatsApp Media',label='Framing fixture',media_attachment=file.file_url,phone_number_id=fixtures.ACCOUNT)).insert()
        def remove_files():
            frappe.db.rollback();frappe.db.delete('WhatsApp Media',{'name':asset.name});frappe.db.delete('File',{'name':file.name});frappe.db.commit()
        self.addCleanup(remove_files)
        t=self.template(meta=False,meta_header='Welcome',meta_footer='Patient Support',media=asset.name)
        c=self.campaign(t);source=frappe.get_doc('ToDo',fixtures.SOURCE);source.wm_test_phone='919000000001'
        sender=frappe.get_doc('WhatsApp Phone Number ID',fixtures.ACCOUNT)
        conv=inbox.ensure_conversation(sender,inbox.ensure_peer(source.wm_test_phone,sender))
        frappe.db.set_value(conv.doctype,conv.name,'window_expires_at',utcnow()+timedelta(hours=1))
        run=insert('WhatsApp Automation Run',run_key=frappe.generate_hash(length=20),rule=c.name,kind='Manual',state='Completed',run_as='Administrator')
        automation.emit(campaigns.load(c.name),source,run)
        intent=frappe.get_doc('WhatsApp Outbox',{'rule':c.name});payload=json.loads(intent.payload_json)
        expected='Welcome\n\nHello '+source.status+', your appointment is confirmed.\n\nPatient Support'
        self.assertEqual(payload['image']['caption'],expected)
        self.assertEqual(frappe.db.get_value('WhatsApp Message',intent.message,'message'),expected)
        with self.assertRaises(frappe.ValidationError):outbox.create_intent(conv.name,'caption-overflow',body='X'*1025,file_id=file.name)

    def test_component_migration_is_idempotent_without_rewriting_content(self):
        from whatsapp_messaging.patches.v1_0.template_framing import execute
        t=self.template(meta_header='Welcome',meta_footer='Patient Support');name=self.meta_item(t)
        before=str(t.modified);body=t.message_preview
        frappe.db.set_value('WhatsApp Approved Template',name,'supported',0)
        execute();execute();t.reload()
        self.assertTrue(frappe.db.get_value('WhatsApp Approved Template',name,'supported'))
        self.assertEqual(str(t.modified),before);self.assertEqual(t.message_preview,body)
        self.assertEqual(t.meta_status,'Approved');self.transport.assert_not_called()

    def test_submit_requires_supervisor_enabled_sender_and_outbound(self):
        t=self.template();frappe.set_user(fixtures.EDITOR)
        with self.assertRaises(frappe.PermissionError):editor.submit(t.name)
        frappe.set_user('Administrator');frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',0)
        with self.assertRaises(frappe.ValidationError):editor.submit(t.name)
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',1)
        frappe.db.set_value('WhatsApp Phone Number ID',fixtures.ACCOUNT,'enabled',0)
        with self.assertRaises(frappe.ValidationError):editor.submit(t.name)
        self.transport.assert_not_called()

    def test_missing_examples_unapproved_fields_and_bad_format_block_locally(self):
        t=self.template()
        for text,sample in [('Hello {{template_doctype.description}}.','Booked'),('Hello {{template_doctype.status}}.',''),
                ('{{template_doctype.status}} is booked.','Booked'),('Hello {{template_doctype.status}}','Booked')]:
            t.message_preview=text;t.meta_examples[0].sample_value=sample;t.save()
            with self.assertRaises(frappe.ValidationError):editor.submit(t.name)
        self.transport.assert_not_called()

    def test_timeout_is_not_automatically_resubmitted(self):
        t=self.template();result,_=self.submit(t,side_effect=requests.Timeout('fixture token must not be recorded'))
        self.assertEqual(result['status'],'Unknown')
        self.assertEqual(t.meta_status,'Check submission outcome')
        self.assertNotIn('fixture token',t.meta_action_error)
        with self.assertRaises(frappe.ValidationError):editor.submit(t.name)
        self.transport.assert_not_called()

    def test_uncertain_submission_waits_for_complete_status_check_before_manual_retry(self):
        t=self.template();self.submit(t,side_effect=requests.Timeout())
        response=Mock(status_code=200,json=Mock(return_value={'data':[]}))
        with patch.object(catalogue.requests,'get',return_value=response):editor.refresh_status(t.name)
        t.reload();self.assertEqual(t.meta_submission_state,'Unknown')
        frappe.db.set_value(t.doctype,t.name,'meta_submission_at',utcnow()-timedelta(minutes=11))
        with patch.object(catalogue.requests,'get',return_value=response):editor.refresh_status(t.name)
        t.reload();self.assertEqual(t.meta_submission_state,'Failed')
        self.assertIn('No request has been resent',t.meta_action_error)
        self.transport.assert_not_called()

    def test_status_check_preserves_detailed_rejection_from_signed_webhook(self):
        import hashlib,hmac
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request
        from whatsapp_messaging.messaging import webhooks
        t=self.template();self.meta_item(t,'PENDING')
        settings=frappe.get_doc('WhatsApp Settings');settings.app_secret='review-test-secret';settings.save()
        now=int(utcnow().replace(tzinfo=timezone.utc).timestamp())
        value=dict(event='REJECTED',message_template_id=991234567890,reason='INVALID_FORMAT',
            rejection_info={'reason':'More descriptive text is needed.','recommendation':'Separate the variables.'})
        raw=json.dumps({'object':'whatsapp_business_account','entry':[{'id':'123456','time':now,
            'changes':[{'field':'message_template_status_update','value':value}]}]}).encode()
        before=frappe.db.count('WhatsApp Webhook Event')
        for valid in (False,True):
            signature='sha256='+hmac.new(b'review-test-secret',raw,hashlib.sha256).hexdigest() if valid else 'sha256=invalid'
            request=Request(EnvironBuilder(method='POST',data=raw,headers={'Content-Type':'application/json','X-Hub-Signature-256':signature}).get_environ())
            with patch.object(frappe,'request',request):response=webhooks.receive()
            self.assertEqual(response.status_code,200 if valid else 403)
            if not valid:self.assertEqual(frappe.db.count('WhatsApp Webhook Event'),before)
        receipt=frappe.get_all('WhatsApp Webhook Event',order_by='creation desc',pluck='name',limit=1)[0]
        self.receipts.append(receipt);webhooks.process_event(receipt)
        self.assertEqual(frappe.db.get_value('WhatsApp Webhook Event',receipt,'state'),'Processed')
        item=dict(id='991234567890',name=t.meta_template_name,language=t.meta_language,category='UTILITY',
            status='REJECTED',rejected_reason='INVALID_FORMAT',components=editor.compile_content(t)[2])
        with patch.object(catalogue.requests,'get',return_value=Mock(status_code=200,json=Mock(return_value={'data':[item]}))) as get:
            editor.refresh_status(t.name)
        t.reload();self.assertEqual(t.meta_rejection_detail,'More descriptive text is needed.')
        self.assertEqual(t.meta_recommendation,'Separate the variables.')
        self.assertIn('rejected_reason',get.call_args.kwargs['params']['fields'])

    def test_api_error_is_separate_from_review_rejection_and_redacts_token(self):
        t=self.template()
        response=Mock(status_code=400,json=Mock(return_value={'error':{'code':100,'error_user_msg':'Correct the missing example '+fixtures.DUMMY_TOKEN}}))
        result,_=self.submit(t,response)
        self.assertEqual(result['status'],'Failed');self.assertEqual(t.meta_status,'Draft')
        self.assertIn('Correct the missing example',t.meta_action_error)
        self.assertNotIn(fixtures.DUMMY_TOKEN,t.meta_action_error)

    def test_rejection_shows_exact_reason_recommendation_and_fix(self):
        t=self.template();name=self.meta_item(t,'PENDING')
        now=int(utcnow().replace(tzinfo=timezone.utc).timestamp())
        value=dict(event='REJECTED',message_template_id=991234567890,reason='INVALID_FORMAT',
            rejection_info={'reason':'The two variables are adjacent.','recommendation':'Separate variables with descriptive text.'})
        self.assertTrue(catalogue.review_update('123456',value,now))
        t.reload();status=editor.review_values(t)
        self.assertEqual(status['meta_status'],'Rejected')
        self.assertEqual(status['meta_rejection_detail'],'The two variables are adjacent.')
        self.assertEqual(status['meta_recommendation'],'Separate variables with descriptive text.')
        self.assertIn('sequential',status['meta_fix_guidance'])
        with self.assertRaises(frappe.ValidationError):editor.ensure_sendable(t)
        # A late event must not replace the newer rejection.
        catalogue.review_update('123456',dict(event='APPROVED',message_template_id=991234567890),now-1)
        self.assertEqual(frappe.db.get_value('WhatsApp Approved Template',name,'approval_status'),'REJECTED')

    def test_unknown_rejection_does_not_invent_a_specific_reason(self):
        t=self.template();self.meta_item(t,'REJECTED',rejected_reason=None)
        status=editor.review_values(t)
        self.assertIn('without a detailed reason',status['meta_rejection_detail'])
        self.assertIn('has not provided a specific fix',status['meta_fix_guidance'])

    def test_corrected_rejected_content_resubmits_the_same_meta_id(self):
        t=self.template();self.meta_item(t,'REJECTED',rejected_reason='INVALID_FORMAT')
        t.message_preview='Hi {{template_doctype.status}}, your updated appointment is confirmed.';t.save()
        self.assertEqual(t.meta_status,'Changes not submitted')
        result,post=self.submit(t,Mock(status_code=200,json=Mock(return_value={'success':True})))
        self.assertTrue(post.call_args.args[0].endswith('/991234567890'))
        self.assertNotIn('name',post.call_args.kwargs['json'])
        self.assertEqual(t.meta_status,'In review')

    def test_draft_edit_during_submission_is_not_overwritten(self):
        t=self.template()
        def edit_then_respond(*args,**kwargs):
            edited=frappe.get_doc(t.doctype,t.name);edited.message_preview='Changed {{template_doctype.status}} after submit.'
            edited.save();frappe.db.commit()
            return Mock(status_code=200,json=Mock(return_value={'id':'991234567890','status':'APPROVED'}))
        self.submit(t,side_effect=edit_then_respond)
        self.assertEqual(t.message_preview,'Changed {{template_doctype.status}} after submit.')
        self.assertEqual(t.meta_status,'Changes not submitted')
        with self.assertRaises(frappe.ValidationError):editor.ensure_sendable(t)

    def test_approved_text_change_blocks_sending_until_review(self):
        t=self.template();self.meta_item(t)
        self.assertEqual(editor.ensure_sendable(t),['template_doctype.status'])
        t.message_preview='A different {{template_doctype.status}} message.';t.save()
        with self.assertRaises(frappe.ValidationError):editor.ensure_sendable(t)

    def test_switch_to_local_mode_clears_old_approval_on_the_server(self):
        t=self.template();self.meta_item(t)
        t.delivery_mode=editor.LOCAL;t.message_preview='New local message.';t.save()
        self.assertFalse(t.approved_template);self.assertEqual(t.meta_status,'Not requested')
        c=self.campaign(t);source=frappe.get_doc('ToDo',fixtures.SOURCE);source.wm_test_phone='919000000001'
        _,body,parameters,_=automation.render(campaigns.load(c.name),source)
        self.assertEqual(body,'New local message.');self.assertEqual(parameters,[])

    def test_imported_static_mapping_revocation_invalidates_preview_and_queued_send(self):
        from whatsapp_messaging.messaging import field_policy
        from whatsapp_messaging.messaging.common import insert
        policy_name='Website Settings'
        existed=frappe.db.exists(field_policy.POLICY,policy_name)
        previous=frappe.db.get_value(field_policy.POLICY,policy_name,'allowed_fields') if existed else None
        app_name=frappe.db.get_single_value('Website Settings','app_name')
        def restore():
            frappe.set_user('Administrator');frappe.db.rollback()
            if existed:frappe.db.set_value(field_policy.POLICY,policy_name,'allowed_fields',previous)
            else:frappe.db.delete(field_policy.POLICY,{'name':policy_name})
            frappe.db.set_single_value('Website Settings','app_name',app_name);frappe.db.commit()
        self.addCleanup(restore)
        policy=frappe.get_doc(field_policy.POLICY,policy_name) if existed else frappe.new_doc(field_policy.POLICY)
        policy.update(dict(source_doctype=policy_name,allowed_fields='["app_name"]'));policy.save()
        frappe.db.set_single_value('Website Settings','app_name','Riverbend Hospital')
        t=self.template(message_preview='Hello {{1}}, your appointment is confirmed.',
            meta_examples=[dict(position=1,source_path='static.website_settings.app_name',sample_value='Riverbend Hospital')])
        self.meta_item(t);c=self.campaign(t,is_single=1)
        source=frappe.get_doc('ToDo',fixtures.SOURCE);source.wm_test_phone='919000000001'
        sender=frappe.get_doc('WhatsApp Phone Number ID',fixtures.ACCOUNT)
        peer=inbox.ensure_peer(source.wm_test_phone,sender)
        frappe.db.set_value(peer.doctype,peer.name,'consent_recorded',1)
        run=insert('WhatsApp Automation Run',run_key=frappe.generate_hash(length=20),rule=c.name,kind='Manual',state='Completed',run_as='Administrator')
        automation.emit(campaigns.load(c.name),source,run)
        intent=frappe.get_doc('WhatsApp Outbox',{'rule':c.name})
        outbox.validate_dispatch(intent)
        with patch.object(field_policy,'static_value',side_effect=frappe.PermissionError('Access revoked')):
            with self.assertRaises(frappe.PermissionError):outbox.validate_dispatch(intent)
        preview=automation.preview_campaign(c.name)
        policy.allowed_fields='[]';policy.save()
        with self.assertRaises(frappe.ValidationError):automation.start_campaign(preview['run'])
        with self.assertRaises(frappe.ValidationError):outbox.validate_dispatch(intent)

    def test_two_campaigns_share_content_without_copying_it(self):
        t=self.template(meta=False)
        first=self.campaign(t);second=self.campaign(t)
        self.assertFalse(frappe.get_meta(first.doctype).has_field('message_preview'))
        old=campaigns.version(first.name)
        t.message_preview='Updated {{template_doctype.status}} content.';t.save()
        for c in (first,second):self.assertEqual(campaigns.load(c.name).message_preview,t.message_preview)
        self.assertNotEqual(campaigns.version(first.name),old)
        self.assertEqual(frappe.db.get_value(first.doctype,first.name,'message_template'),t.name)

    def test_template_edit_invalidates_a_prepared_campaign(self):
        t=self.template(meta=False);c=self.campaign(t,is_single=1)
        result=automation.preview_campaign(c.name)
        t.message_preview='Changed content.';t.save()
        with self.assertRaises(frappe.ValidationError):automation.start_campaign(result['run'])

    def test_campaign_meta_variables_render_from_the_current_source(self):
        t=self.template();self.meta_item(t)
        c=self.campaign(t)
        source=frappe.get_doc('ToDo',fixtures.SOURCE)
        source.wm_test_phone='919000000001'
        recipients,body,values,file=automation.render(campaigns.load(c.name),source)
        self.assertEqual(recipients,['919000000001']);self.assertEqual(body,'')
        self.assertEqual(values,[source.status]);self.assertIsNone(file)

    def test_campaign_event_has_correct_history_and_content_edit_holds_queued_send(self):
        t=self.template(meta=False);c=self.campaign(t,template_event='Update',automation_active=1)
        source=frappe.get_doc('ToDo',fixtures.SOURCE);source.wm_test_phone='919000000001'
        sender=frappe.get_doc('WhatsApp Phone Number ID',fixtures.ACCOUNT)
        peer=inbox.ensure_peer(source.wm_test_phone,sender)
        conv=inbox.ensure_conversation(sender,peer)
        frappe.db.set_value(conv.doctype,conv.name,'window_expires_at',utcnow()+timedelta(hours=1))
        automation.event_rules(source,['Update'])
        run=frappe.get_doc('WhatsApp Automation Run',{'rule':c.name})
        self.assertEqual(run.state,'Completed');self.assertEqual(run.rule_doctype,'WhatsApp Campaign')
        intent=frappe.get_doc('WhatsApp Outbox',{'rule':c.name})
        self.assertEqual(intent.rule_doctype,'WhatsApp Campaign')
        t.message_preview='Updated {{template_doctype.status}} content.';t.save()
        with self.assertRaises(frappe.ValidationError):outbox.validate_dispatch(intent)

    def test_campaign_schedule_links_campaign_without_editing_content(self):
        t=self.template(meta=False);before=t.modified
        c=self.campaign(t,template_event='Cron',automation_active=1,cron_interval='Daily')
        schedule=frappe.get_doc('WhatsApp Schedule',c.schedule_record)
        self.assertEqual(schedule.rule,c.name);self.assertEqual(schedule.rule_doctype,'WhatsApp Campaign')
        self.assertEqual(schedule.state,'Active');self.assertEqual(schedule.run_as,'Administrator')
        self.assertEqual(str(frappe.db.get_value(t.doctype,t.name,'modified')),str(before))
        c.disable=1;c.save();schedule.reload();self.assertEqual(schedule.state,'Paused')

    def test_import_stays_in_template_editor_with_explicit_variable_mapping(self):
        source=self.template();name=self.meta_item(source)
        target=self.template(meta=False)
        values=editor.import_content(target.name,name)
        self.assertEqual(values['message_preview'],'Hello {{1}}, your appointment is confirmed.')
        self.assertEqual(values['delivery_mode'],editor.META)
        self.assertEqual(values['meta_examples'][0]['source_path'],'')
        target.update(values);target.save()
        with self.assertRaises(ValueError):editor.compile_content(target)
        target.meta_examples[0].source_path='template_doctype.status';target.meta_examples[0].sample_value='Booked';target.save()
        self.assertEqual(editor.ensure_sendable(target),['template_doctype.status'])

    def test_content_migration_creates_campaign_without_sending(self):
        t=self.template(meta=False,template_event='Update',automation_active=0,disable=0)
        before=frappe.db.get_value(t.doctype,t.name,['modified','run_as','message_preview'],as_dict=True)
        count=frappe.db.count('WhatsApp Message')
        frappe.db.savepoint('split_migration')
        try:
            campaigns.backfill();campaigns.backfill()
            c=frappe.get_doc('WhatsApp Campaign',t.name)
            self.assertEqual(c.message_template,t.name);self.assertEqual(c.template_event,'Update')
            self.assertEqual(c.run_as,before.run_as)
            self.assertEqual(frappe.db.get_value(t.doctype,t.name,['modified','run_as','message_preview'],as_dict=True),before)
            self.assertEqual(frappe.db.count('WhatsApp Message'),count)
            self.transport.assert_not_called()
        finally:frappe.db.rollback(save_point='split_migration')


if __name__=='__main__':
    fixtures.connect()
    try:
        fixtures.seed();unittest.main(verbosity=2)
    finally:frappe.db.rollback();frappe.destroy()
