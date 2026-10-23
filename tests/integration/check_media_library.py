"""Library lifecycle, metadata, permissions and file retention; disposable site only."""
import hashlib
import unittest
from io import BytesIO
from unittest.mock import patch

import frappe
from PIL import Image
from pypdf import PdfWriter
import check_site as fixtures
from whatsapp_messaging.messaging import media_library, template_content


class TestMediaLibrary(unittest.TestCase):
    def setUp(self):
        assert frappe.local.site == fixtures.SITE and frappe.conf.db_host == 'db'
        frappe.set_user('Administrator')
        frappe.db.savepoint('media_case')
        self.addCleanup(self.cleanup)
        self.network=patch('requests.sessions.Session.request',side_effect=AssertionError('No provider transport'))
        self.transport=self.network.start();self.addCleanup(self.network.stop)
        queue=patch('frappe.enqueue');queue.start();self.addCleanup(queue.stop)

    def cleanup(self):
        frappe.set_user('Administrator');frappe.db.rollback(save_point='media_case')

    def png(self):
        data=BytesIO();Image.new('RGB',(3,2),'green').save(data,format='PNG');return data.getvalue()

    def pdf(self):
        writer=PdfWriter();writer.add_blank_page(width=72,height=72);data=BytesIO();writer.write(data);return data.getvalue()

    def file(self, content=None, **values):
        return frappe.get_doc(dict(doctype='File',file_name=values.pop('file_name','Media-fixture.png'),
            content=content or self.png(),is_private=values.pop('is_private',1),**values)).insert(ignore_permissions=True)

    def asset(self, file=None, **values):
        file=file or self.file()
        return frappe.get_doc(dict(doctype='WhatsApp Media',media_attachment=file.file_url,phone_number_id=fixtures.ACCOUNT,**values)).insert()

    def test_save_derives_metadata_and_ignores_tampering(self):
        content=self.png();file=self.file(content,file_name='Actual-image.bin')
        asset=self.asset(file,media_type='URL',media_id='forged',media_url='https://example.invalid/no-fetch',
            document_type='audio',content_type='audio/mpeg',file_size=1,content_hash='forged',validation_status='Needs Attention')
        self.assertEqual(asset.media_type,'Upload')
        self.assertEqual(asset.document_type,'image');self.assertEqual(asset.content_type,'image/png')
        self.assertEqual(asset.file_size,len(content));self.assertEqual(asset.content_hash,hashlib.sha256(content).hexdigest())
        self.assertEqual(asset.label,file.file_name);self.assertEqual(asset.validation_status,'Ready')
        self.assertIn('PNG',asset.record_title);self.assertEqual(asset.phone_number_id,fixtures.ACCOUNT)
        self.assertFalse(asset.media_id);self.assertFalse(asset.media_url)
        self.assertEqual(media_library.preview(file.file_url)['file_reference'],file.name)

    def test_legacy_direct_helpers_cannot_prepare_url_payloads(self):
        from whatsapp_messaging.utils.media_controller import process_whatsapp_media,upload_media_to_whatsapp
        with self.assertRaises(frappe.ValidationError):process_whatsapp_media(frappe._dict(media_type='URL',media_url='https://example.invalid/no-fetch'))
        with self.assertRaises(frappe.ValidationError):upload_media_to_whatsapp(None,None)
        self.transport.assert_not_called()

    def test_label_is_independent_from_internal_notes(self):
        asset=self.asset(label='Visit instructions',caption='Do not send this internal note')
        self.assertEqual(asset.record_title,'Visit instructions · PNG')
        asset.caption='Another internal note';asset.save()
        self.assertEqual(asset.record_title,'Visit instructions · PNG')

    def test_replace_updates_all_metadata_and_preserves_the_previous_file(self):
        first=self.file();asset=self.asset(first,label='Visit instructions')
        frappe.db.set_value(asset.doctype,asset.name,'media_id','legacy-id');asset.reload()
        second=self.file(self.pdf(),file_name='Visit.pdf');old_hash=asset.content_hash
        asset.media_attachment=second.file_url;asset.save()
        self.assertEqual(asset.document_type,'document');self.assertEqual(asset.content_type,'application/pdf')
        self.assertEqual(asset.file_reference,second.name);self.assertNotEqual(asset.content_hash,old_hash)
        self.assertEqual(asset.record_title,'Visit instructions · PDF');self.assertFalse(asset.media_id)
        self.assertTrue(frappe.db.exists('File',first.name));self.assertEqual(first.get_content(encodings=[]),self.png())
        self.assertEqual(template_content.resolve(asset.name)['file_id'],second.name)

    def test_remove_saves_unavailable_record_without_deleting_stored_file(self):
        file=self.file();asset=self.asset(file)
        asset.media_attachment=None;asset.save()
        self.assertEqual(asset.validation_status,'Needs File')
        for field in media_library.DERIVED_FIELDS:
            self.assertFalse(asset.get(field),field)
        self.assertTrue(frappe.db.exists('File',file.name))
        self.assertEqual(file.get_content(encodings=[]),self.png())
        with self.assertRaises(frappe.ValidationError):template_content.resolve(asset.name)

    def test_quick_entry_schema_contains_only_label_sender_and_file_inputs(self):
        meta=frappe.get_meta('WhatsApp Media')
        inputs=[f.fieldname for f in meta.fields if (f.reqd or f.allow_in_quick_entry) and not f.read_only]
        self.assertEqual(inputs,['label','phone_number_id','media_attachment'])
        for name in ('content_type','document_type','validation_status','file_size_display','media_id'):
            self.assertTrue(meta.get_field(name).read_only)
        self.assertFalse(meta.get_field('phone_number_id').reqd)

    def test_empty_url_public_unsupported_and_corrupt_uploads_are_rejected(self):
        for values in ({},{'media_type':'URL','media_url':'https://example.invalid/no-fetch'}):
            with self.assertRaises(frappe.ValidationError):frappe.get_doc(dict(doctype='WhatsApp Media',**values)).insert()
        for file in (self.file(is_private=0),self.file(b'column\nvalue\n',file_name='Unsupported.csv'),
                self.file(b'\x89PNG\r\n\x1a\nnot-an-image',file_name='Broken.bin'),
                self.file(b'%PDF-1.7 broken',file_name='Broken-pdf.bin')):
            with self.assertRaises(frappe.ValidationError):self.asset(file)

    def test_file_limits_use_actual_bytes(self):
        file=self.file(b'\x89PNG\r\n\x1a\n'+b'x'*(5*1024*1024),file_name='Too-large.bin')
        with self.assertRaises(frappe.ValidationError):self.asset(file)
        file=self.file(self.pdf(),file_name='Oversized.pdf')
        with open(file.get_full_path(),'wb') as stream:stream.write(b'x'*(20*1024*1024+1))
        with self.assertRaises(frappe.ValidationError):media_library.preview(file.file_url)

    def test_roles_and_private_file_permissions_are_checked(self):
        private=self.file()
        frappe.set_user(fixtures.UNRELATED)
        with self.assertRaises(frappe.PermissionError):media_library.preview(private.file_url)
        frappe.set_user(fixtures.EDITOR)
        with self.assertRaises(frappe.PermissionError):media_library.preview(private.file_url)

    def test_new_own_upload_binds_on_save_and_can_be_reused_by_app_roles(self):
        frappe.set_user(fixtures.EDITOR)
        file=self.file();self.assertFalse(file.attached_to_doctype)
        asset=self.asset(file,label='Shared visit image')
        file.reload();self.assertEqual((file.attached_to_doctype,file.attached_to_name),(asset.doctype,asset.name))
        frappe.set_user(fixtures.SUPERVISOR)
        self.assertEqual(media_library.preview(file.file_url)['validation_status'],'Ready')

    def test_business_file_parent_is_not_changed(self):
        file=self.file(attached_to_doctype='ToDo',attached_to_name=fixtures.SOURCE)
        self.asset(file);file.reload()
        self.assertEqual((file.attached_to_doctype,file.attached_to_name),('ToDo',fixtures.SOURCE))

    def test_deleting_library_record_keeps_file(self):
        file=self.file();asset=self.asset(file)
        frappe.delete_doc(asset.doctype,asset.name)
        file.reload();self.assertTrue(frappe.db.exists('File',file.name));self.assertFalse(file.attached_to_name)
        self.assertEqual(file.get_content(encodings=[]),self.png())

    def test_migration_preserves_ids_timestamps_files_and_legacy_urls(self):
        file=self.file();asset=self.asset(file,label='Keep this label')
        modified=str(asset.modified)
        frappe.db.set_value(asset.doctype,asset.name,dict(content_type='audio/mpeg',document_type='audio'),update_modified=False)
        public=self.file(is_private=0,file_name='Existing-public.png')
        old=self.asset(label='Old URL')
        frappe.db.set_value(old.doctype,old.name,dict(media_type='URL',media_attachment=None,media_url='https://example.invalid/keep-this-url'),update_modified=False)
        broken=self.asset(label='Old public file')
        frappe.db.set_value(broken.doctype,broken.name,'media_attachment',public.file_url,update_modified=False)
        media_library.backfill();media_library.backfill()
        asset.reload();old.reload();broken.reload()
        self.assertEqual(asset.label,'Keep this label');self.assertEqual(str(asset.modified),modified)
        self.assertEqual(asset.content_type,'image/png');self.assertEqual(asset.document_type,'image')
        self.assertEqual(old.validation_status,'Legacy URL');self.assertEqual(old.media_url,'https://example.invalid/keep-this-url')
        self.assertEqual(broken.validation_status,'Needs Attention');self.assertFalse(broken.content_type)
        public.reload();self.assertFalse(public.is_private)
        self.transport.assert_not_called()


if __name__=='__main__':
    fixtures.connect()
    try:
        fixtures.seed();unittest.main(verbosity=2)
    finally:
        frappe.db.rollback();frappe.destroy()
