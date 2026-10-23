"""Cloud lifecycle against Frappe/Redis, with all provider transport mocked."""
from datetime import timedelta
from io import BytesIO
import unittest
from unittest.mock import Mock, patch

import frappe
from frappe.utils import now_datetime
from PIL import Image
import requests

import check_site as fixtures
from whatsapp_messaging.messaging import media, media_cloud


class TestMediaCloud(unittest.TestCase):
    def setUp(self):
        assert frappe.local.site == fixtures.SITE and frappe.conf.db_host == 'db'
        frappe.set_user('Administrator')
        self.assets = []
        self.files = []
        self.addCleanup(self.cleanup_records)
        transport = patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected transport'))
        self.transport = transport.start()
        self.addCleanup(transport.stop)
        self.real_enqueue = frappe.enqueue
        queue = patch('frappe.enqueue')
        self.queue = queue.start()
        self.addCleanup(queue.stop)
        self.gate(1)
        frappe.db.set_value('WhatsApp Phone Number ID', fixtures.ACCOUNT, 'enabled', 1)
        frappe.db.commit()

    def cleanup_records(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()
        for name in self.assets:
            if frappe.db.exists('WhatsApp Media', name):
                frappe.delete_doc('WhatsApp Media', name, ignore_permissions=True)
        for name in self.files:
            if frappe.db.exists('File', name):
                frappe.delete_doc('File', name, ignore_permissions=True)
        self.gate(0)
        frappe.db.set_value('WhatsApp Phone Number ID', fixtures.ACCOUNT, 'enabled', 1)
        frappe.db.set_value('User', fixtures.EDITOR, 'enabled', 1)
        frappe.db.commit()
        frappe.clear_cache(user=fixtures.EDITOR)

    def gate(self, value):
        frappe.db.set_single_value('WhatsApp Settings', 'enable_outbound_messages', value)

    def file(self, color='blue'):
        data = BytesIO()
        Image.new('RGB', (4, 3), color).save(data, format='PNG')
        file = frappe.get_doc(dict(doctype='File', file_name='Cloud-fixture-' + frappe.generate_hash(length=8) + '.png',
            content=data.getvalue(), is_private=1)).insert(ignore_permissions=True)
        self.files.append(file.name)
        return file

    def asset(self, **values):
        values.setdefault('media_attachment', self.file().file_url)
        values.setdefault('phone_number_id', fixtures.ACCOUNT)
        doc = frappe.get_doc(dict(doctype='WhatsApp Media', label='Cloud fixture', **values)).insert()
        self.assets.append(doc.name)
        frappe.db.commit()
        return doc

    def response(self, status=200, payload=None):
        return Mock(status_code=status, json=Mock(return_value=payload or {'id':'123456789012345'}))

    def run_upload(self, doc, response=None):
        with patch.object(media_cloud.requests, 'post', return_value=response or self.response()) as post:
            media_cloud.upload(doc.name, doc.cloud_upload_key)
        doc.reload()
        return post

    def test_create_queues_after_commit_without_sending_or_uploading_inline(self):
        count = frappe.db.count('WhatsApp Message')
        doc = self.asset()
        self.assertEqual(doc.cloud_status, 'Pending')
        self.assertFalse(doc.media_id)
        args = self.queue.call_args.kwargs
        self.assertEqual(args['queue'], 'whatsapp_media')
        self.assertTrue(args['enqueue_after_commit'])
        self.assertEqual(args['upload_key'], doc.cloud_upload_key)
        self.assertEqual(frappe.db.count('WhatsApp Message'), count)
        self.transport.assert_not_called()

    def test_gate_and_sender_block_without_queuing(self):
        self.gate(0)
        doc = self.asset()
        self.assertEqual(doc.cloud_status, 'Blocked')
        self.assertIn('Outbound Requests', doc.cloud_error)
        self.queue.assert_not_called()
        self.gate(1)
        frappe.db.set_value('WhatsApp Phone Number ID', fixtures.ACCOUNT, 'enabled', 0)
        doc.save()
        self.assertEqual(doc.cloud_status, 'Blocked')
        self.assertIn('disabled', doc.cloud_error)
        self.queue.assert_not_called()
        self.transport.assert_not_called()

    def test_missing_worker_configuration_is_actionable_not_a_failed_save(self):
        with patch.object(media_cloud, 'queue_configured', return_value=False):
            doc = self.asset()
        self.assertEqual(doc.cloud_status, 'Blocked')
        self.assertIn('worker', doc.cloud_error)
        self.queue.assert_not_called()

    def test_sender_required_for_new_file_but_older_record_can_be_saved(self):
        with self.assertRaises(frappe.ValidationError):
            self.asset(phone_number_id=None)
        doc = self.asset()
        doc.phone_number_id = None
        doc.save()
        self.assertEqual(doc.cloud_status, 'Needs Sender')
        self.assertFalse(doc.media_id)
        doc.phone_number_id = fixtures.ACCOUNT
        doc.save()
        self.assertEqual(doc.cloud_status, 'Pending')

    def test_upload_uses_exact_private_bytes_and_does_not_create_a_message(self):
        doc = self.asset()
        count = frappe.db.count('WhatsApp Message')
        post = self.run_upload(doc)
        self.assertEqual(doc.cloud_status, 'Uploaded')
        self.assertEqual(doc.media_id, '123456789012345')
        self.assertEqual(doc.cloud_content_hash, doc.content_hash)
        self.assertEqual(doc.cloud_sender, fixtures.ACCOUNT)
        self.assertGreater(doc.cloud_refresh_after, doc.cloud_uploaded_on + timedelta(days=28))
        self.assertEqual(post.call_args.args[0], 'https://graph.facebook.com/v26.0/1234567890/media')
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers'], {'Authorization':'Bearer ' + fixtures.DUMMY_TOKEN})
        self.assertEqual(kwargs['data'], {'messaging_product':'whatsapp', 'type':'image/png'})
        self.assertEqual(kwargs['files']['file'][1], frappe.get_doc('File', doc.file_reference).get_content(encodings=[]))
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(frappe.db.count('WhatsApp Message'), count)
        self.run_upload(doc).assert_not_called()

    def test_provider_error_is_useful_and_never_retains_raw_secret(self):
        doc = self.asset()
        self.run_upload(doc, self.response(401, {'error':{'code':190, 'message':'secret:' + fixtures.DUMMY_TOKEN}}))
        self.assertEqual(doc.cloud_status, 'Failed')
        self.assertIn('token is invalid or expired', doc.cloud_error)
        self.assertNotIn(fixtures.DUMMY_TOKEN, frappe.as_json(doc.as_dict()))
        key = doc.cloud_upload_key
        media_cloud.retry(doc.name)
        doc.reload()
        self.assertEqual(doc.cloud_status, 'Pending')
        self.assertNotEqual(doc.cloud_upload_key, key)

    def test_connection_and_malformed_result_fail_without_storing_exception(self):
        doc = self.asset()
        with patch.object(media_cloud.requests, 'post', side_effect=requests.Timeout(fixtures.DUMMY_TOKEN)):
            media_cloud.upload(doc.name, doc.cloud_upload_key)
        doc.reload()
        self.assertEqual(doc.cloud_status, 'Failed')
        self.assertNotIn(fixtures.DUMMY_TOKEN, doc.cloud_error)
        media_cloud.retry(doc.name)
        doc.reload()
        self.run_upload(doc, self.response(payload={'id':'not-a-media-id'}))
        self.assertEqual(doc.cloud_status, 'Failed')
        self.assertFalse(doc.media_id)

    def test_worker_rechecks_global_switch_and_disabled_actor(self):
        doc = self.asset()
        self.gate(0)
        frappe.db.commit()
        self.run_upload(doc).assert_not_called()
        self.assertEqual(doc.cloud_status, 'Blocked')
        self.gate(1)
        frappe.db.set_value(doc.doctype, doc.name, dict(cloud_status='Pending', cloud_requested_by=fixtures.EDITOR))
        frappe.db.set_value('User', fixtures.EDITOR, 'enabled', 0)
        frappe.db.commit()
        self.run_upload(doc).assert_not_called()
        self.assertEqual(doc.cloud_status, 'Blocked')

    def test_worker_rechecks_actor_role_and_sender(self):
        doc = self.asset()
        frappe.db.set_value(doc.doctype, doc.name, 'cloud_requested_by', fixtures.UNRELATED)
        frappe.db.commit()
        self.run_upload(doc).assert_not_called()
        self.assertEqual(doc.cloud_status, 'Blocked')
        frappe.db.set_value(doc.doctype, doc.name, dict(cloud_status='Pending', cloud_requested_by='Administrator'))
        frappe.db.set_value('WhatsApp Phone Number ID', fixtures.ACCOUNT, 'enabled', 0)
        frappe.db.commit()
        self.run_upload(doc).assert_not_called()
        self.assertEqual(doc.cloud_status, 'Blocked')

    def test_replacement_clears_id_and_stale_job_cannot_update_new_generation(self):
        doc = self.asset()
        self.run_upload(doc)
        key = doc.cloud_upload_key
        doc.media_attachment = self.file('red').file_url
        doc.save()
        frappe.db.commit()
        self.assertEqual(doc.cloud_status, 'Pending')
        self.assertFalse(doc.media_id)
        with patch.object(media_cloud.requests, 'post') as post:
            media_cloud.upload(doc.name, key)
        post.assert_not_called()
        doc.reload()
        self.assertEqual(doc.cloud_status, 'Pending')
        self.assertFalse(doc.media_id)

    def test_inflight_response_cannot_overwrite_a_replacement(self):
        doc = self.asset()
        old_key = doc.cloud_upload_key
        replacement = self.file('yellow')
        frappe.db.commit()
        def response_after_edit(*args, **kwargs):
            edited = frappe.get_doc(doc.doctype, doc.name)
            edited.media_attachment = replacement.file_url
            edited.save()
            frappe.db.commit()
            return self.response()
        with patch.object(media_cloud.requests, 'post', side_effect=response_after_edit):
            media_cloud.upload(doc.name, old_key)
        doc.reload()
        self.assertNotEqual(doc.cloud_upload_key, old_key)
        self.assertEqual(doc.media_attachment, replacement.file_url)
        self.assertEqual(doc.cloud_status, 'Pending')
        self.assertFalse(doc.media_id)

    def test_changed_file_bytes_block_worker(self):
        doc = self.asset()
        replacement = self.file('red')
        content = replacement.get_content(encodings=[])
        with open(frappe.get_doc('File', doc.file_reference).get_full_path(), 'wb') as stream:
            stream.write(content)
        self.run_upload(doc).assert_not_called()
        self.assertEqual(doc.cloud_status, 'Blocked')

    def test_id_cache_requires_same_sender_hash_freshness_and_permission(self):
        doc = self.asset()
        self.run_upload(doc)
        sender = frappe.get_doc('WhatsApp Phone Number ID', fixtures.ACCOUNT)
        self.assertEqual(media_cloud.cached_id(doc.content_hash, sender), doc.media_id)
        self.assertIsNone(media_cloud.cached_id('wrong-hash', sender))
        self.assertIsNone(media_cloud.cached_id(doc.content_hash, frappe._dict(name='other-sender')))
        with patch('frappe.has_permission', return_value=False):
            self.assertIsNone(media_cloud.cached_id(doc.content_hash, sender))
        attachment = frappe._dict(doctype='WhatsApp Attachment', name='fixture', file=doc.file_reference, content_hash=doc.content_hash)
        with patch.object(media, 'set_record_values') as update, patch.object(media.requests, 'post') as post:
            self.assertEqual(media.upload(attachment, sender), doc.media_id)
            post.assert_not_called()
            update.assert_called_once()
        frappe.db.set_value(doc.doctype, doc.name, 'cloud_refresh_after', now_datetime() - timedelta(seconds=1))
        self.assertIsNone(media_cloud.cached_id(doc.content_hash, sender))

    def test_readonly_cloud_results_and_notes_save_cannot_forge_or_reupload(self):
        doc = self.asset()
        self.run_upload(doc)
        original = doc.media_id
        self.queue.reset_mock()
        doc.update(dict(media_id='999999', cloud_status='Failed', cloud_sender=None, media_url='https://example.invalid/forged', caption='Internal note'))
        doc.save()
        self.assertEqual(doc.media_id, original)
        self.assertEqual(doc.cloud_status, 'Uploaded')
        self.assertEqual(doc.cloud_sender, fixtures.ACCOUNT)
        self.assertFalse(doc.media_url)
        self.queue.assert_not_called()

    def test_active_lease_blocks_duplicate_and_retry_and_sweep_recovers_stale(self):
        doc = self.asset()
        frappe.db.set_value(doc.doctype, doc.name, dict(cloud_status='Uploading', cloud_lease_until=now_datetime() + timedelta(minutes=2)))
        frappe.db.commit()
        self.run_upload(doc).assert_not_called()
        with self.assertRaises(frappe.ValidationError):
            media_cloud.retry(doc.name)
        self.queue.reset_mock()
        media_cloud.sweep()
        self.queue.assert_not_called()
        frappe.db.set_value(doc.doctype, doc.name, 'cloud_lease_until', now_datetime() - timedelta(seconds=1))
        media_cloud.sweep()
        self.assertEqual(self.queue.call_args.kwargs['queue'], 'whatsapp_media')
        self.assertEqual(self.queue.call_args.kwargs['upload_key'], doc.cloud_upload_key)
        self.transport.assert_not_called()

    def test_real_redis_job_appears_only_after_commit(self):
        from frappe.utils.background_jobs import get_queue
        queue = get_queue(media_cloud.QUEUE)
        file = self.file()
        frappe.db.commit()
        with patch('frappe.enqueue', self.real_enqueue):
            doc = frappe.get_doc(dict(doctype='WhatsApp Media', label='Queue fixture',
                phone_number_id=fixtures.ACCOUNT, media_attachment=file.file_url)).insert()
            self.assets.append(doc.name)
            before = set(queue.job_ids)
            self.assertFalse(any(doc.cloud_upload_key in key for key in before))
            frappe.db.commit()
        added = set(queue.job_ids) - before
        self.assertEqual(len(added), 1)
        job = queue.fetch_job(added.pop())
        try:
            self.assertEqual(job.kwargs['kwargs'], dict(name=doc.name, upload_key=doc.cloud_upload_key))
            self.assertEqual(job.kwargs['method'], 'whatsapp_messaging.messaging.media_cloud.upload')
            self.transport.assert_not_called()
        finally:
            job.delete()


if __name__ == '__main__':
    fixtures.connect()
    try:
        fixtures.seed()
        from frappe.utils.background_jobs import get_queues_timeout
        # The isolated bench's only extra worker queue; this never enables APIs.
        from frappe.installer import update_site_config
        update_site_config('workers', {'whatsapp_media':{'timeout':120}},
            site_config_path='/testbench/sites/common_site_config.json')
        get_queues_timeout.cache_clear()
        unittest.main(verbosity=2)
    finally:
        frappe.db.rollback()
        frappe.destroy()
