"""Transactional naming regressions on an explicitly selected local development site.

Run from bench/sites with the bench Python; fixtures and series counters roll back.
No provider requests, queue jobs, switch changes or commits are allowed.
"""
import os
import re
import unittest
from datetime import datetime
from unittest.mock import patch

import frappe
from whatsapp_messaging.messaging.common import digest, insert, service_write
from whatsapp_messaging.messaging.inbox import ensure_peer, ensure_conversation
from whatsapp_messaging.messaging.naming import backfill_titles, set_record_values


class RecordNamingTests(unittest.TestCase):
    def setUp(self):
        frappe.db.savepoint('record_naming_case')
        self.network = patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden'))
        self.queue = patch('frappe.enqueue', side_effect=AssertionError('Queue forbidden'))
        self.network.start()
        self.queue.start()
        self.sender = frappe.get_doc(dict(doctype='WhatsApp Phone Number ID', label='Naming QA sender',
            phone_number_id='99887766554433221100', access_token='fictional-test-token', enabled=0)).insert()
        self.peer = ensure_peer('919999000001', self.sender, 'Naming QA contact')
        self.conversation = ensure_conversation(self.sender, self.peer)

    def tearDown(self):
        frappe.db.rollback(save_point='record_naming_case')
        self.queue.stop()
        self.network.stop()

    def message(self, **values):
        return insert('WhatsApp Message', conversation=self.conversation.name, account=self.sender.name,
            peer=self.peer.name, direction='Outbound', status='Queued', **values)

    def test_sequences_and_legacy_conversation_creation(self):
        self.assertRegex(self.peer.name, r'^WA-PEER-\d{6}$')
        self.assertRegex(self.conversation.name, r'^WA-CONV-\d{6}$')
        self.assertEqual(ensure_conversation(self.sender, self.peer).name, self.conversation.name)
        first, second = self.message(), self.message()
        year = frappe.utils.now_datetime().year
        self.assertRegex(first.name, rf'^WA-MSG-{year}-\d{{6}}$')
        self.assertEqual(int(second.name.rsplit('-', 1)[1]), int(first.name.rsplit('-', 1)[1])+1)
        legacy = insert('WhatsApp Conversation', recipient='legacy-fixture')
        self.assertRegex(legacy.name, r'^WA-CONV-\d{6}$')
        self.assertNotEqual(legacy.name, legacy.recipient)

    def test_all_new_series_and_internal_ids(self):
        from io import BytesIO
        from pypdf import PdfWriter
        writer=PdfWriter(); writer.add_blank_page(width=72,height=72); data=BytesIO();writer.write(data)
        file=frappe.get_doc(dict(doctype='File',file_name='Naming-visit.pdf',content=data.getvalue(),is_private=1)).insert()
        fixtures = [
            ('WhatsApp Approved Template', 'WA-ATPL-', dict(template_name='appointment_confirmation', language='en')),
            ('WhatsApp Attachment', 'WA-ATT-', dict(message=self.message().name, file_name='visit.pdf')),
            ('WhatsApp Automation Run', 'WA-RUN-', dict(rule=None, kind='Schedule')),
            ('WhatsApp Media', 'WA-MEDIA-', dict(media_attachment=file.file_url, phone_number_id=self.sender.name, label='Visit instructions')),
            ('WhatsApp Outbox', 'WA-OUT-', dict(message=self.message().name, state='Ready')),
            ('WhatsApp Schedule', 'WA-SCH-', dict(cron_expression='0 9 * * *', timezone='Asia/Kolkata')),
            ('WhatsApp Send Attempt', 'WA-TRY-', dict(attempt_number=1)),
            ('WhatsApp Status Event', 'WA-STE-', dict(provider_message_id='fixture-message', provider_status='delivered')),
            ('WhatsApp Webhook Event', 'WA-WHE-', dict(state='Pending', received_at=datetime(2026,10,18,9,0))),
        ]
        for doctype, prefix, values in fixtures:
            with self.subTest(doctype=doctype):
                doc = insert(doctype, **values)
                self.assertTrue(doc.name.startswith(prefix), doc.name)
                self.assertTrue(doc.record_title)
        activity = insert('WhatsApp Conversation Activity', conversation=self.conversation.name, action='Claimed', actor='Administrator')
        self.assertEqual(len(activity.name), 10)
        self.assertIn('Claimed', activity.record_title)

    def test_titles_and_link_search_metadata(self):
        self.assertEqual(self.sender.name, self.sender.label)
        self.assertEqual(self.peer.record_title, 'Naming QA contact')
        self.assertEqual(self.conversation.record_title, 'Naming QA sender · Naming QA contact')
        doc = self.message()
        self.assertEqual(doc.record_title, 'Outbound · Naming QA contact · Queued')
        for doctype in ('WhatsApp Message', 'WhatsApp Peer', 'WhatsApp Conversation'):
            meta = frappe.get_meta(doctype)
            self.assertEqual(meta.title_field, 'record_title')
            self.assertTrue(meta.show_title_field_in_link)
        # Real standard Link lookup must find by contact title, and return the stable ID.
        from frappe.desk.search import search_link
        results = search_link('WhatsApp Conversation', 'Naming QA contact')
        self.assertIn(self.conversation.name, [r['value'] for r in results])

    def test_direct_service_updates_keep_titles_current(self):
        message = self.message()
        outbox = insert('WhatsApp Outbox', message=message.name, state='Ready')
        set_record_values(outbox.doctype, outbox.name, {'state':'Accepted', 'attempt_count':1})
        set_record_values(message.doctype, message.name, 'status', 'Delivered')
        self.assertEqual(frappe.db.get_value(message.doctype,message.name,'record_title'), 'Outbound · Naming QA contact · Delivered')
        self.assertEqual(frappe.db.get_value(outbox.doctype,outbox.name,'record_title'), message.name+' · Accepted')
        status = insert('WhatsApp Status Event', provider_message_id='fixture-provider', provider_status='delivered')
        set_record_values(status.doctype,status.name,'message',message.name)
        self.assertIn(message.name, frappe.db.get_value(status.doctype,status.name,'record_title'))
        template = insert('WhatsApp Approved Template',template_name='appointment',language='en')
        set_record_values(template.doctype,template.name,{'language':'te'})
        self.assertEqual(frappe.db.get_value(template.doctype,template.name,'record_title'), 'appointment · te')

    def test_backfill_is_idempotent_and_preserves_ids_timestamps_and_keys(self):
        message = self.message(provider_key=digest('fixture-provider'), sequence_key=digest('fixture-sequence'))
        legacy_name = 'legacy-message-naming-qa'
        frappe.db.sql('UPDATE `tabWhatsApp Message` SET name=%s, record_title=NULL WHERE name=%s', (legacy_name,message.name))
        before = frappe.db.get_value(message.doctype,legacy_name,['name','modified','provider_key','sequence_key'],as_dict=True)
        backfill_titles()
        backfill_titles()
        after = frappe.db.get_value(message.doctype,legacy_name,['name','modified','provider_key','sequence_key'],as_dict=True)
        self.assertEqual(before,after)
        self.assertEqual(frappe.db.get_value(message.doctype,legacy_name,'record_title'), 'Outbound · Naming QA contact · Queued')
        doc=frappe.get_doc(message.doctype,legacy_name)
        with service_write(): doc.save()
        self.assertEqual(doc.name,legacy_name)

    def test_contact_title_corrections_propagate(self):
        message=self.message()
        with service_write():
            self.peer.display_name='Corrected QA contact'
            self.peer.save()
        self.assertIn('Corrected QA contact',frappe.db.get_value(message.doctype,message.name,'record_title'))
        self.assertIn('Corrected QA contact',frappe.db.get_value(self.conversation.doctype,self.conversation.name,'record_title'))

    def test_no_payload_or_password_in_titles(self):
        doc=self.message(message='PRIVATE BODY MUST NOT BE IN TITLE')
        self.assertNotIn('PRIVATE BODY',doc.record_title)
        token=self.sender.get_password('access_token')
        self.assertNotIn(token,self.conversation.record_title)
        from whatsapp_messaging.messaging.naming import record_title
        self.peer.display_name='Long\ncontact '+('x'*200)
        title=record_title(self.peer)
        self.assertLessEqual(len(title),140)
        self.assertNotIn('\n',title)


if __name__ == '__main__':
    site=os.environ.get('WHATSAPP_NAMING_TEST_SITE')
    assert site in ('hms.localhost','development.localhost','whatsapp-test.localhost'), 'Select an explicit development/test site'
    frappe.init(site=site)
    frappe.connect()
    if site == 'whatsapp-test.localhost':
        assert frappe.conf.db_host == 'db', 'Disposable test database required'
    frappe.set_user('Administrator')
    # Capture only counts/settings, never credentials or record contents.
    doctypes=[d.name for d in frappe.get_all('DocType',filters={'module':'Whatsapp Messaging','istable':0,'issingle':0})]
    before={kind:frappe.db.count(kind) for kind in doctypes}
    switches=frappe.get_single('WhatsApp Settings').as_dict()
    try:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecordNamingTests))
        frappe.db.rollback()
        assert before=={kind:frappe.db.count(kind) for kind in doctypes}, 'Fixture records escaped rollback'
        for field in ('enable_outbound_messages','enable_inbound','enable_automation'):
            assert frappe.db.get_single_value('WhatsApp Settings',field)==switches[field]
        print('All fixture rows rolled back; site switches unchanged.')
        if not result.wasSuccessful():raise SystemExit(1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
