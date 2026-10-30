"""Local document rules integration checks. Network transport is always blocked."""
import json
import io
from pypdf import PdfWriter
import sys
import unittest
from unittest.mock import Mock, patch

import frappe
from whatsapp_messaging.messaging import document_delivery as delivery, catalogue, inbox, outbox
from whatsapp_messaging.messaging.common import service_write, utcnow
from whatsapp_messaging.messaging.template_framing import supported

SITE='whatsapp-documents-test.localhost'
GENERIC='Document Delivery Example'
_pdf=PdfWriter();_pdf.add_blank_page(width=595,height=842);_buffer=io.BytesIO();_pdf.write(_buffer);PDF=_buffer.getvalue()


def init_schema():
    text_fields=[dict(fieldname='notes',label='Notes',fieldtype='Text'),
        dict(fieldname='short_notes',label='Short notes',fieldtype='Small Text'),
        dict(fieldname='long_notes',label='Long notes',fieldtype='Long Text')]
    if frappe.db.exists('DocType',GENERIC):
        meta=frappe.get_doc('DocType',GENERIC)
        for field in text_fields:
            if not any(f.fieldname==field['fieldname'] for f in meta.fields):meta.append('fields',field)
        meta.save();frappe.db.commit();return
    frappe.get_doc(dict(doctype='DocType',name=GENERIC,module='HMS',custom=1,autoname='EX-DOC-.######',
        fields=[dict(fieldname='title',label='Title',fieldtype='Data'),dict(fieldname='patient',label='Patient',fieldtype='Link',options='Patient'),
            dict(fieldname='status',label='Status',fieldtype='Select',options='Draft\nReleased\nCancelled',default='Draft'),
            dict(fieldname='document',label='Document',fieldtype='Attach'),*text_fields],
        permissions=[dict(role='System Manager',read=1,write=1,create=1,delete=1,print=1)])).insert(ignore_permissions=True)
    frappe.db.commit()


class TestDocumentDelivery(unittest.TestCase):
    def setUp(self):
        assert frappe.local.site==SITE
        frappe.set_user('Administrator')
        self.addCleanup(frappe.db.rollback)
        self.transport=patch('requests.sessions.Session.request',side_effect=AssertionError('No external transport')).start()
        self.addCleanup(patch.stopall)
        self.queue=patch('frappe.enqueue').start()
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',1)
        frappe.db.set_single_value('WhatsApp Settings','enable_automation',1)
        suffix=frappe.generate_hash(length=8)
        self.sender=frappe.get_doc(dict(doctype='WhatsApp Phone Number ID',label='Document checks '+suffix,
            phone_number_id='100'+str(int(suffix,16)),waba_id='123456',access_token='local-integration-token',enabled=1)).insert(ignore_permissions=True)
        self.patient=frappe.get_doc(dict(doctype='Patient',patient_name='Arjun Reddy',patient_gender='Male',patient_location='Peddapuram',patient_phone_number='+91 90000 00001')).insert(ignore_permissions=True)
        self.source=frappe.get_doc(dict(doctype=GENERIC,title='Consultation document',patient=self.patient.name,status='Draft')).insert(ignore_permissions=True)
        self.fmt=frappe.get_doc(dict(doctype='Print Format',name='Document checks '+suffix,doc_type=GENERIC,standard='No',custom_format=1,
            print_format_type='Jinja',html='<html><body><h1>Consultation document</h1><p>{{ doc.title|e }}</p></body></html>')).insert(ignore_permissions=True)
        self.template=catalogue.upsert('123456',dict(id='100000000000',name='document_checks_'+suffix,language='en',category='UTILITY',status='APPROVED',
            components=[dict(type='HEADER',format='DOCUMENT'),dict(type='BODY',text='Hello {{1}}, your document is attached. Thank you.'),dict(type='FOOTER',text='Hospital reception')]))
        self.rule=frappe.get_doc(dict(doctype='WhatsApp Document Rule',rule_name='Document checks '+suffix,enabled=1,source_doctype=GENERIC,
            event_type='Field changes to a value',trigger_field='status',trigger_values='Released',recipient_mode='A linked record',recipient_link_field='patient',phone_field='patient_phone_number',
            document_mode='Generate PDF',print_format=self.fmt.name,sender=self.sender.name,approved_template=self.template,
            parameters=[dict(position=1,value_source='Recipient',fieldname_value='patient_name')])).insert(ignore_permissions=True)
        self.peer=inbox.ensure_peer('919000000001',self.sender)
        with service_write():
            frappe.db.set_value('WhatsApp Peer',self.peer.name,dict(consent_recorded=1,consent_source='Recorded permission for service documents'))
        self.addCleanup(frappe.db.rollback)

    def issue(self):
        self.source.status='Released';self.source.save()
        names=frappe.get_all('WhatsApp Document Delivery',filters={'source_name':self.source.name,'rule':self.rule.name},pluck='name')
        self.assertEqual(len(names),1)
        return names[0]

    def prepare(self,real_pdf=False):
        name=self.issue()
        if real_pdf:delivery.process(name)
        else:
            with patch('frappe.get_print',return_value=PDF):delivery.process(name)
        return frappe.get_doc('WhatsApp Document Delivery',name)

    def test_document_header_supported_but_buttons_and_video_are_not(self):
        self.assertTrue(supported([dict(type='HEADER',format='DOCUMENT'),dict(type='BODY',text='Document attached.')]))
        self.assertFalse(supported([dict(type='HEADER',format='VIDEO'),dict(type='BODY',text='Document attached.')]))
        self.assertFalse(supported([dict(type='BODY',text='Document attached.'),dict(type='BUTTONS')]))

    def test_draft_does_not_send_transition_queues_once(self):
        self.assertFalse(frappe.db.exists('WhatsApp Document Delivery',{'source_name':self.source.name}))
        name=self.issue()
        self.source.title='Updated title';self.source.save()
        self.assertEqual(frappe.db.count('WhatsApp Document Delivery',{'source_name':self.source.name,'rule':self.rule.name}),1)
        self.assertEqual(frappe.db.get_value('WhatsApp Document Delivery',name,'state'),'Pending')
        self.assertTrue(any(c.kwargs.get('enqueue_after_commit') for c in self.queue.call_args_list))

    def test_source_rollback_removes_delivery(self):
        self.issue();frappe.db.rollback()
        self.assertFalse(frappe.db.exists('WhatsApp Document Delivery',{'source_name':self.source.name}))

    def test_generated_document_uses_private_pdf_and_document_header(self):
        doc=self.prepare()
        self.assertEqual(doc.state,'Queued',doc.last_error)
        self.assertEqual(frappe.db.get_value('File',doc.file,'is_private'),1)
        intent=frappe.get_doc('WhatsApp Outbox',doc.outbox)
        payload=json.loads(intent.payload_json)
        self.assertEqual(payload['type'],'template')
        self.assertEqual(payload['to'],'919000000001')
        header=next(c for c in payload['template']['components'] if c['type']=='header')
        self.assertEqual(header['parameters'][0]['type'],'document')
        self.assertTrue(header['parameters'][0]['document']['filename'].endswith('.pdf'))
        delivery.process(doc.name)
        self.assertEqual(frappe.db.count('WhatsApp Outbox',{'origin_key':'document:'+doc.delivery_key}),1)

    def test_actual_pdf_renderer(self):
        doc=self.prepare(real_pdf=True)
        self.assertEqual(doc.state,'Queued',doc.last_error)
        self.assertTrue(frappe.get_doc('File',doc.file).get_content().startswith(b'%PDF-'))

    def test_missing_phone_is_held(self):
        frappe.db.set_value('Patient',self.patient.name,'patient_phone_number','')
        doc=self.prepare();self.assertEqual(doc.state,'Held');self.assertFalse(doc.outbox)

    def test_missing_consent_and_optout_are_held(self):
        with service_write():frappe.db.set_value('WhatsApp Peer',self.peer.name,'consent_recorded',0)
        doc=self.prepare();self.assertEqual(doc.state,'Held');self.assertFalse(doc.outbox)
        with service_write():frappe.db.set_value('WhatsApp Peer',self.peer.name,dict(consent_recorded=1,suppressed=1))
        delivery.retry(doc.name);delivery.process(doc.name);doc.reload()
        self.assertEqual(doc.state,'Held');self.assertFalse(doc.outbox)

    def test_release_required_is_enforced(self):
        self.rule.require_release=1;self.rule.save()
        name=self.issue();delivery.process(name)
        self.assertEqual(frappe.db.get_value('WhatsApp Document Delivery',name,'state'),'Awaiting release')
        delivery.release(name)
        with patch('frappe.get_print',return_value=PDF):delivery.process(name)
        doc=frappe.get_doc('WhatsApp Document Delivery',name)
        self.assertEqual(doc.state,'Queued',doc.last_error)
        self.assertEqual(doc.released_by,'Administrator')

    def test_changed_or_cancelled_record_is_held(self):
        name=self.issue();self.source.status='Cancelled';self.source.save()
        delivery.process(name)
        self.assertEqual(frappe.db.get_value('WhatsApp Document Delivery',name,'state'),'Held')

    def test_preparation_failure_can_retry_without_duplicate(self):
        name=self.issue()
        with patch('frappe.get_print',side_effect=RuntimeError('renderer failure')):delivery.process(name)
        self.assertEqual(frappe.db.get_value('WhatsApp Document Delivery',name,'state'),'Failed')
        delivery.retry(name)
        with patch('frappe.get_print',return_value=PDF):delivery.process(name)
        doc=frappe.get_doc('WhatsApp Document Delivery',name)
        self.assertEqual(doc.state,'Queued',doc.last_error)
        with self.assertRaises(frappe.ValidationError):delivery.retry(name)

    def test_dispatch_rechecks_phone_consent_rule_and_source(self):
        doc=self.prepare();intent=frappe.get_doc('WhatsApp Outbox',doc.outbox)
        outbox.validate_dispatch(intent)
        frappe.db.set_value('Patient',self.patient.name,'patient_phone_number','919000000002')
        with self.assertRaises(frappe.ValidationError):outbox.validate_dispatch(intent)
        frappe.db.set_value('Patient',self.patient.name,'patient_phone_number','919000000001')
        with service_write():frappe.db.set_value('WhatsApp Peer',self.peer.name,'suppressed',1)
        with self.assertRaises(frappe.ValidationError):outbox.validate_dispatch(intent)

    def test_preview_is_read_only(self):
        before=frappe.db.count('WhatsApp Outbox');files=frappe.db.count('File')
        result=delivery.preview(self.rule.name,self.source.name)
        self.assertFalse(result['sent']);self.assertEqual(result['recipient'],'919000000001')
        self.assertEqual(before,frappe.db.count('WhatsApp Outbox'));self.assertEqual(files,frappe.db.count('File'))

    def test_arbitrary_attachment_must_belong_to_source_and_be_private(self):
        self.rule.document_mode='Private attachment';self.rule.file_field='document';self.rule.save()
        file=frappe.get_doc(dict(doctype='File',file_name='consultation.pdf',content=PDF,is_private=1,
            attached_to_doctype=GENERIC,attached_to_name=self.source.name)).insert(ignore_permissions=True)
        self.source.document=file.file_url
        doc=self.prepare()
        self.assertEqual(doc.state,'Queued',doc.last_error)
        self.assertEqual(doc.file,file.name)

    def test_unrelated_attachment_is_held(self):
        self.rule.document_mode='Private attachment';self.rule.file_field='document';self.rule.save()
        other=frappe.get_doc(dict(doctype=GENERIC,title='Other document',patient=self.patient.name,status='Draft')).insert(ignore_permissions=True)
        file=frappe.get_doc(dict(doctype='File',file_name='other.pdf',content=PDF,is_private=1,
            attached_to_doctype=GENERIC,attached_to_name=other.name)).insert(ignore_permissions=True)
        name=self.issue()
        frappe.db.set_value(GENERIC,self.source.name,'document',file.file_url,update_modified=False)
        delivery.process(name)
        doc=frappe.get_doc('WhatsApp Document Delivery',name)
        self.assertEqual(doc.state,'Held');self.assertFalse(doc.outbox)

    def test_receipt_or_invoice_is_not_sent_as_draft(self):
        self.rule.enabled=0;self.rule.save()
        fmt=frappe.get_doc(dict(doctype='Print Format',name=self.fmt.name+' invoice',doc_type='HMS Invoice',standard='No',custom_format=1,
            print_format_type='Jinja',html='<h1>Invoice</h1><p>{{ doc.total }}</p>')).insert(ignore_permissions=True)
        self.rule.source_doctype='HMS Invoice';self.rule.trigger_values='Issued\nPartly Paid\nPaid\nRefund Due';self.rule.print_format=fmt.name;self.rule.enabled=1;self.rule.save()
        invoice=frappe.get_doc(dict(doctype='HMS Invoice',patient=self.patient.name,payer_name='Arjun Reddy',invoice_date=frappe.utils.today(),currency='INR',
            items=[dict(description='Consultation',quantity=1,rate=500)])).insert(ignore_permissions=True)
        self.assertFalse(frappe.db.exists('WhatsApp Document Delivery',{'source_name':invoice.name}))
        invoice.issue()
        self.assertEqual(frappe.db.count('WhatsApp Document Delivery',{'source_name':invoice.name}),1)
        invoice.reload();invoice.issue()
        self.assertEqual(frappe.db.count('WhatsApp Document Delivery',{'source_name':invoice.name}),1)

    def test_non_supervisor_cannot_configure_or_preview(self):
        previous=frappe.session.user
        frappe.set_user('Guest')
        try:
            with self.assertRaises(frappe.PermissionError):delivery.preview(self.rule.name,self.source.name)
        finally:frappe.set_user(previous)

    def test_only_when_condition_excludes_other_records(self):
        self.rule.append('conditions',dict(fieldname_value='title',expected_value='Released result'))
        self.rule.save()
        self.source.status='Released';self.source.save()
        self.assertFalse(frappe.db.exists('WhatsApp Document Delivery',{'source_name':self.source.name,'rule':self.rule.name}))

    def test_prepare_current_is_explicit_and_does_not_duplicate(self):
        self.issue()
        first=delivery.prepare_current(self.rule.name,self.source.name)
        second=delivery.prepare_current(self.rule.name,self.source.name)
        self.assertTrue(first['existing']);self.assertEqual(first['name'],second['name'])
        self.assertEqual(frappe.db.count('WhatsApp Document Delivery',{'source_name':self.source.name,'rule':self.rule.name}),1)

    def test_dispatch_uploads_document_into_template_header(self):
        doc=self.prepare();frappe.db.commit()
        reply=Mock(status_code=200,ok=True,json=Mock(return_value={'messages':[{'id':'wamid.document-check'}]}))
        with patch('whatsapp_messaging.messaging.media.upload',return_value='99112233'),patch.object(outbox.requests,'post',return_value=reply) as post:
            outbox.dispatch(doc.outbox)
        payload=post.call_args.kwargs['json']
        self.assertEqual(payload['type'],'template')
        header=next(c for c in payload['template']['components'] if c['type']=='header')
        self.assertEqual(header['parameters'][0]['document']['id'],'99112233')
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',doc.outbox,'state'),'Accepted')

    def test_uncertain_document_send_is_not_replayed(self):
        doc=self.prepare();frappe.db.commit()
        with patch('whatsapp_messaging.messaging.media.upload',return_value='99112233'),patch.object(outbox.requests,'post',side_effect=TimeoutError('uncertain')) as post:
            outbox.dispatch(doc.outbox)
            outbox.dispatch(doc.outbox)
        self.assertEqual(post.call_count,1)
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',doc.outbox,'state'),'Unknown')

    def test_recovery_only_queues_document_delivery_work(self):
        doc=self.prepare();self.queue.reset_mock()
        delivery.recover()
        jobs=[c for c in self.queue.call_args_list if c.args and c.args[0]=='whatsapp_messaging.messaging.outbox.dispatch']
        self.assertTrue(any(c.kwargs.get('name')==doc.outbox and c.kwargs.get('enqueue_after_commit') for c in jobs))

    def test_internal_metadata_cannot_be_a_document_source(self):
        self.rule.enabled=0;self.rule.source_doctype='User'
        with self.assertRaises(frappe.ValidationError):self.rule.save()

    def test_custom_data_values_only_change_the_rule_and_match_exactly(self):
        source_before=frappe.get_doc(GENERIC,self.source.name).as_dict()
        fields_before=frappe.get_doc('DocType',GENERIC).as_dict()
        self.rule.trigger_field='title';self.rule.trigger_values='Ready for collection\nCourier requested'
        self.rule.save()
        self.assertEqual(frappe.get_doc(GENERIC,self.source.name).as_dict(),source_before)
        self.assertEqual(frappe.get_doc('DocType',GENERIC).as_dict(),fields_before)
        for title,expected in [('Ready for collection',1),('Courier requested',1),('ready for collection',1),('Ready for collection',2)]:
            self.source.title=title;self.source.save()
            self.assertEqual(frappe.db.count('WhatsApp Document Delivery',{'source_name':self.source.name,'rule':self.rule.name}),expected)
        self.source.title=None
        self.assertFalse(delivery.trigger_matches(self.rule,self.source))

    def test_text_equals_preserves_multiline_text_spaces_and_case(self):
        for field in ('notes','short_notes','long_notes'):
            with self.subTest(field=field):
                self.rule.trigger_field=field;self.rule.text_match_operator='Equals'
                self.rule.trigger_text='Reviewed by doctor\nReady for collection '
                self.rule.trigger_values='';self.rule.save()
                for value,expected in [(self.rule.trigger_text,True),('Reviewed by doctor\nReady for collection',False),
                        ('reviewed by doctor\nReady for collection ',False),(None,False)]:
                    self.source.set(field,value)
                    self.assertEqual(delivery.trigger_matches(self.rule,self.source),expected)

    def test_text_contains_only_sends_when_entering_a_match(self):
        self.rule.trigger_field='notes';self.rule.trigger_values='';self.rule.text_match_operator='Contains'
        self.rule.trigger_text='ready for collection';self.rule.save()
        for text,count in [('Report reviewed',0),('Report reviewed\nready for collection',1),
                ('Report ready for collection at reception',1),('Awaiting review',1),('Now ready for collection',2)]:
            self.source.notes=text;self.source.save()
            self.assertEqual(frappe.db.count('WhatsApp Document Delivery',{'source_name':self.source.name,'rule':self.rule.name}),count)
        self.source.notes='Ready for collection'
        self.assertFalse(delivery.trigger_matches(self.rule,self.source))

    def test_text_matching_rejects_empty_operands_and_unsupported_operators(self):
        self.rule.trigger_field='notes';self.rule.text_match_operator='Contains';self.rule.trigger_text=' \n '
        with self.assertRaises(frappe.ValidationError):self.rule.save()
        self.assertFalse(delivery.trigger_matches(self.rule,self.source))
        self.rule.trigger_text='Ready';self.rule.text_match_operator='Regex'
        with self.assertRaises(frappe.ValidationError):self.rule.save()

    def test_text_rule_configuration_does_not_change_source_text_or_options(self):
        before=frappe.get_doc(GENERIC,self.source.name).as_dict()
        fields_before=frappe.get_doc('DocType',GENERIC).as_dict()
        self.rule.trigger_field='notes';self.rule.trigger_values='';self.rule.text_match_operator='Contains'
        self.rule.trigger_text='Ready for collection';self.rule.save()
        self.assertEqual(frappe.get_doc(GENERIC,self.source.name).as_dict(),before)
        self.assertEqual(frappe.get_doc('DocType',GENERIC).as_dict(),fields_before)

    def test_slash_suggestions_use_existing_distinct_data_values(self):
        for title in ('Ready for collection','Ready for collection','Courier requested'):
            frappe.get_doc(dict(doctype=GENERIC,title=title,patient=self.patient.name,status='Draft')).insert()
        values=delivery.trigger_value_options(GENERIC,'title','collection')
        self.assertEqual(values,['Ready for collection'])
        self.assertIn('Courier requested',delivery.trigger_value_options(GENERIC,'title'))
        with self.assertRaises(frappe.ValidationError):delivery.trigger_value_options(GENERIC,'notes')

    def test_slash_suggestions_require_supervisor_and_source_access(self):
        original=frappe.session.user;frappe.set_user('Guest')
        try:
            with self.assertRaises(frappe.PermissionError):delivery.trigger_value_options(GENERIC,'title')
        finally:frappe.set_user(original)
        with patch.object(frappe,'has_permission',return_value=False):
            with self.assertRaises(frappe.PermissionError):delivery.trigger_value_options(GENERIC,'title')

    def test_slash_suggestions_apply_record_query_permissions(self):
        frappe.get_doc(dict(doctype=GENERIC,title='Private title',patient=self.patient.name,status='Draft')).insert()
        original=frappe.get_hooks
        def hooks(key=None,*args,**kwargs):
            if key=='permission_query_conditions':
                return {GENERIC:['document_suggestion_test_permission']}
            return original(key,*args,**kwargs)
        original_attr=frappe.get_attr
        def get_attr(name):
            if name=='document_suggestion_test_permission':
                return lambda user=None,**kwargs: "`tabDocument Delivery Example`.`title` != 'Private title'"
            return original_attr(name)
        with patch.object(frappe,'get_hooks',side_effect=hooks),patch.object(frappe,'get_attr',side_effect=get_attr):
            self.assertNotIn('Private title',delivery.trigger_value_options(GENERIC,'title'))


if __name__=='__main__':
    frappe.init(site=SITE);frappe.connect();frappe.set_user('Administrator')
    try:
        init_schema()
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TestDocumentDelivery))
    finally:
        frappe.db.rollback()
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',0)
        frappe.db.set_single_value('WhatsApp Settings','enable_automation',0)
        frappe.db.commit();frappe.destroy()
    sys.exit(0 if result.wasSuccessful() else 1)
