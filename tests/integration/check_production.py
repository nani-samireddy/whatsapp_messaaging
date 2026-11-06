"""Production-boundary regressions on the internal-only integration site."""
from datetime import timedelta
from io import BytesIO
import sys
import unittest
from unittest.mock import patch

import frappe
import requests
from pypdf import PdfWriter

import check_site as fixtures
from check_messaging import TestMessaging, ADMIN, EDITOR
from whatsapp_messaging.messaging import media, outbox, webhooks, readiness, automation
from whatsapp_messaging.messaging.common import utcnow, insert


class TestProductionBoundaries(TestMessaging):
    def pdf_intent(self, key, source=False):
        from frappe.utils.file_manager import save_file
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        stream = BytesIO()
        writer.write(stream)
        file = save_file(key + '.pdf', stream.getvalue(),
            'ToDo' if source else None, fixtures.SOURCE if source else None, is_private=1)
        result = outbox.send(self.conv.name, key, body='Private document', file_id=file.name)
        attachment = frappe.get_doc('WhatsApp Attachment', {'message': result['message']})
        return result, attachment

    def restore_source_access(self):
        frappe.set_user('Administrator')
        frappe.db.set_value('ToDo', fixtures.SOURCE, 'allocated_to', EDITOR)
        frappe.db.commit()

    def restore_source_status(self, value):
        frappe.set_user('Administrator')
        frappe.db.set_value('ToDo', fixtures.SOURCE, 'status', value)
        frappe.db.commit()

    def test_attachment_download_requires_business_record_access(self):
        _, attachment = self.pdf_intent('restricted-download', source=True)
        frappe.set_user(ADMIN)
        with self.assertRaises(frappe.PermissionError):
            media.download(attachment.name)

    def test_new_inbox_upload_is_shared_through_the_message_not_an_unrelated_record(self):
        result, attachment = self.pdf_intent('shared-upload')
        file = frappe.get_doc('File', attachment.file)
        self.assertEqual(file.attached_to_doctype, 'WhatsApp Message')
        self.assertEqual(file.attached_to_name, result['message'])
        frappe.set_user(ADMIN)
        media.download(attachment.name)
        self.assertTrue(frappe.local.response.filecontent.startswith(b'%PDF-'))

    def test_business_file_keeps_its_original_parent(self):
        _, attachment = self.pdf_intent('retained-parent', source=True)
        file = frappe.get_doc('File', attachment.file)
        self.assertEqual(file.attached_to_doctype, 'ToDo')
        self.assertEqual(file.attached_to_name, fixtures.SOURCE)

    def test_legacy_unattached_inbox_upload_keeps_its_original_team_visibility(self):
        _, attachment = self.pdf_intent('legacy-shared-upload')
        frappe.db.set_value('File',attachment.file,{
            'attached_to_doctype':None,'attached_to_name':None})
        frappe.set_user(ADMIN)
        media.download(attachment.name)
        self.assertTrue(frappe.local.response.filecontent.startswith(b'%PDF-'))

    def test_attachment_upload_rechecks_revoked_business_record_access(self):
        result, _ = self.pdf_intent('revoked-upload', source=True)
        frappe.db.commit()
        self.addCleanup(self.restore_source_access)
        frappe.db.set_value('ToDo', fixtures.SOURCE, 'allocated_to', ADMIN)
        frappe.db.commit()
        outbox.dispatch(result['outbox'])
        self.post.assert_not_called()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox', result['outbox'], 'state'), 'Held')

    def test_outbound_requests_disable_redirects(self):
        result = self.intent('no-redirect')
        frappe.db.commit()
        self.post.side_effect = None
        self.post.return_value = self.accepted()
        outbox.dispatch(result['outbox'])
        self.assertIs(self.post.call_args.kwargs.get('allow_redirects'), False)

    def test_media_upload_disables_redirects(self):
        from unittest.mock import Mock
        result, _ = self.pdf_intent('upload-no-redirect')
        frappe.db.commit()
        upload = Mock(status_code=200, json=Mock(return_value={'id': '123456'}))
        self.post.side_effect = [upload, self.accepted()]
        outbox.dispatch(result['outbox'])
        self.assertEqual(len(self.post.call_args_list), 2)
        self.assertTrue(all(call.kwargs.get('allow_redirects') is False
            for call in self.post.call_args_list))

    def test_media_redirect_never_becomes_a_message_send(self):
        from unittest.mock import Mock
        result, _ = self.pdf_intent('rejected-upload-redirect')
        frappe.db.commit()
        self.post.side_effect = None
        self.post.return_value = Mock(status_code=302, json=Mock(return_value={'id': '123456'}))
        outbox.dispatch(result['outbox'])
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox', result['outbox'], 'state'), 'Held')
        self.assertFalse(frappe.db.get_value('WhatsApp Outbox', result['outbox'], 'network_started'))

    def test_timeout_does_not_erase_a_committed_delivery_receipt(self):
        result = self.intent('early-delivery-timeout')
        frappe.db.commit()

        def delivered_then_timeout(*args, **kwargs):
            webhooks.status_event(self.sender, {'id': 'wamid.early-delivery', 'status': 'read',
                'timestamp': self.inbound()['timestamp'], 'biz_opaque_callback_data': result['outbox']})
            frappe.db.commit()
            raise requests.ReadTimeout('Uncertain response')

        self.post.side_effect = delivered_then_timeout
        outbox.dispatch(result['outbox'])
        self.assertEqual(frappe.db.get_value('WhatsApp Message', result['message'], 'status'), 'Read')
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox', result['outbox'], 'state'), 'Accepted')

    def test_superseded_worker_never_sends_or_clears_new_sender_lease(self):
        result, attachment = self.pdf_intent('superseded-worker')
        frappe.db.commit()
        replacement_expiry = utcnow() + timedelta(minutes=10)

        def takeover(*args):
            # Model another worker reclaiming this intent during slow media I/O.
            frappe.db.set_value('WhatsApp Outbox', result['outbox'], {
                'state': 'Claimed', 'lease_owner': 'replacement-worker',
                'lease_until': replacement_expiry})
            frappe.db.set_value(self.sender.doctype, self.sender.name,
                'dispatch_lease_until', replacement_expiry)
            frappe.db.commit()
            return '123456'

        self.post.side_effect = None
        self.post.return_value = self.accepted()
        with patch.object(media, 'upload', side_effect=takeover):
            outbox.dispatch(result['outbox'])
        self.post.assert_not_called()
        intent = frappe.get_doc('WhatsApp Outbox', result['outbox'])
        self.assertEqual(intent.state, 'Claimed')
        self.assertEqual(intent.lease_owner, 'replacement-worker')
        self.assertEqual(frappe.db.get_value(self.sender.doctype, self.sender.name,
            'dispatch_lease_until'), replacement_expiry)

    def test_expired_worker_cannot_start_a_provider_request(self):
        result, _ = self.pdf_intent('expired-worker')
        frappe.db.commit()

        def expire(*args):
            frappe.db.set_value('WhatsApp Outbox', result['outbox'],
                'lease_until', utcnow() - timedelta(seconds=1))
            frappe.db.commit()
            return '123456'

        self.post.side_effect = None
        self.post.return_value = self.accepted()
        with patch.object(media, 'upload', side_effect=expire):
            outbox.dispatch(result['outbox'])
        self.post.assert_not_called()
        intent = frappe.get_doc('WhatsApp Outbox', result['outbox'])
        self.assertEqual(intent.state, 'Ready')
        self.assertFalse(intent.network_started)

    def test_readiness_rejects_non_manager_before_reading_configuration(self):
        frappe.set_user(EDITOR)
        with patch.object(frappe, 'get_single') as read:
            with self.assertRaises(frappe.PermissionError):
                readiness.check()
        read.assert_not_called()

    def test_readiness_never_sends_enqueues_or_discloses_credentials(self):
        import json
        frappe.set_user('Administrator')
        flags = {key: frappe.db.get_single_value('WhatsApp Settings', key) for key in
            ('enable_outbound_messages', 'enable_inbound', 'enable_automation')}
        with patch.object(frappe, 'enqueue') as enqueue:
            report = readiness.check()
        enqueue.assert_not_called()
        self.post.assert_not_called()
        self.get.assert_not_called()
        for key, value in flags.items():
            self.assertEqual(frappe.db.get_single_value('WhatsApp Settings', key), value)
        data = json.dumps(report)
        for credential in (fixtures.DUMMY_TOKEN, 'dummy-app-secret', 'dummy-verify'):
            self.assertNotIn(credential, data)
        self.assertEqual(report['sends_created'], 0)
        self.assertTrue(report['external_verification_required'])

    def test_configured_queue_without_a_worker_is_reported_as_blocked(self):
        frappe.set_user('Administrator')
        with patch('whatsapp_messaging.messaging.media_cloud.queue_configured', return_value=True), \
                patch('frappe.utils.background_jobs.get_workers', return_value=[]):
            report = readiness.check()
        rows = {row['code']: row for row in report['checks']}
        self.assertEqual(rows['media_queue']['status'], 'pass')
        self.assertEqual(rows['media_worker']['status'], 'blocked')
        self.assertEqual(rows['default_worker']['status'], 'blocked')

    def test_worker_health_ignores_expired_heartbeats_and_other_benches(self):
        from types import SimpleNamespace
        from frappe.utils.background_jobs import get_queue
        queue = get_queue('default').name
        worker = lambda names, age: SimpleNamespace(last_heartbeat=utcnow()-timedelta(seconds=age),
            worker_ttl=420, queue_names=lambda: names)
        with patch('frappe.utils.background_jobs.get_workers', return_value=[
                worker([queue], 600), worker(['another-bench:default'], 0), worker([queue], 5)]):
            self.assertEqual(readiness.live_worker_counts(['default']), {'default': 1})

    def test_readiness_handles_queue_failures_without_leaking_connection_details(self):
        frappe.set_user('Administrator')
        with patch('frappe.utils.background_jobs.get_workers', side_effect=RuntimeError('redis://secret@host')):
            report = readiness.check()
        self.assertEqual(report['status'], 'blocked')
        self.assertNotIn('secret@host', str(report))

    def test_scheduler_health_uses_site_time_and_rejects_stale_or_future_ticks(self):
        from frappe.utils import now_datetime
        frappe.set_user('Administrator')
        job=frappe.db.get_value('Scheduled Job Type',{'method':readiness.TICK},'name')
        previous=frappe.db.get_value('Scheduled Job Type',job,['last_execution','stopped'],as_dict=True)
        def restore():
            frappe.db.set_value('Scheduled Job Type',job,dict(previous))
            frappe.db.commit()
        self.addCleanup(restore)
        with patch('frappe.utils.scheduler.is_scheduler_inactive',return_value=False):
            for minutes, expected in ((5,'pass'),(60,'blocked'),(-60,'blocked')):
                frappe.db.set_value('Scheduled Job Type',job,{
                    'stopped':0,'last_execution':now_datetime()-timedelta(minutes=minutes)})
                rows={row['code']:row for row in readiness.check()['checks']}
                self.assertEqual(rows['scheduler']['status'],expected)

    def test_public_url_check_rejects_local_and_credential_urls(self):
        for url in ('http://hospital.example.com', 'https://hms.localhost', 'https://frappe.home.arpa',
                'https://127.0.0.1', 'https://192.168.10.47', 'https://user:secret@hospital.example.com'):
            self.assertFalse(readiness.public_https_url(url), url)
        self.assertTrue(readiness.public_https_url('https://hms.samireddy.com'))

    def prepare_source_message(self, key):
        run=insert('WhatsApp Automation Run',run_key=key,rule=self.rule.name,
            kind='Manual',state='Completed',run_as=EDITOR)
        automation.emit(self.rule,frappe.get_doc('ToDo',fixtures.SOURCE),run)
        frappe.db.commit()
        return frappe.db.get_value('WhatsApp Outbox',{'run':run.name},'name')

    def test_changed_source_phone_holds_prepared_message(self):
        name=self.prepare_source_message('changed-source-phone')
        frappe.db.set_value('ToDo',fixtures.SOURCE,'wm_test_phone','919000000002')
        frappe.db.commit()
        outbox.dispatch(name)
        self.post.assert_not_called()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',name,'state'),'Held')

    def test_changed_source_message_values_hold_prepared_message(self):
        name=self.prepare_source_message('changed-source-body')
        old_status=frappe.db.get_value('ToDo',fixtures.SOURCE,'status')
        self.addCleanup(self.restore_source_status,old_status)
        frappe.db.set_value('ToDo',fixtures.SOURCE,'status','Closed')
        frappe.db.commit()
        outbox.dispatch(name)
        self.post.assert_not_called()
        self.assertEqual(frappe.db.get_value('WhatsApp Outbox',name,'state'),'Held')


if __name__ == '__main__':
    fixtures.connect()
    try:
        fixtures.seed()
        names = [name for name in TestProductionBoundaries.__dict__ if name.startswith('test_')]
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.TestSuite(TestProductionBoundaries(name) for name in names))
    finally:
        frappe.db.rollback()
        frappe.destroy()
    sys.exit(0 if result.wasSuccessful() else 1)
