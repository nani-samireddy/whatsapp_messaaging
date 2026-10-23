"""Automatic content type and shared field-policy regressions; disposable site only."""
import json
import unittest
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import frappe
from PIL import Image
from pypdf import PdfWriter
import check_site as fixtures
from whatsapp_messaging.messaging import field_policy, template_content, automation, outbox, inbox
from whatsapp_messaging.messaging.common import utcnow, insert
from whatsapp_messaging.template_security import TemplateSecurityError
from whatsapp_messaging.controller import parse_message


class TestTemplateConfiguration(unittest.TestCase):
    def setUp(self):
        frappe.set_user('Administrator')
        assert frappe.local.site == fixtures.SITE and frappe.conf.db_host == 'db'
        frappe.db.savepoint('template_config_case')
        self.addCleanup(frappe.db.rollback, save_point='template_config_case')
        # Guide/browser fixtures may already approve this singleton. Each case
        # needs its own policy baseline; the savepoint restores the guide data.
        frappe.db.delete(field_policy.POLICY, {'source_doctype':'Website Settings'})
        frappe.clear_document_cache(field_policy.POLICY, 'Website Settings')
        network=patch('requests.sessions.Session.request', side_effect=AssertionError('External transport forbidden'))
        network.start(); self.addCleanup(network.stop)
        queue=patch('frappe.enqueue'); queue.start(); self.addCleanup(queue.stop)
        self.policy=frappe.get_doc(field_policy.POLICY, 'ToDo')
        self.policy.allowed_fields='["status"]'; self.policy.save()
        self.rule=frappe.get_doc('WhatsApp Message Template', fixtures.TEMPLATE)
        self.rule.update(dict(media=None, approved_template=None, parameter_fields=None, schedule_record=None,
            template_event='Custom', automation_active=0, is_single=0, disable=0, phone_number_field_name=None,
            message_preview='Hello {{template_doctype.status}}', allowed_source_fields='["status"]'))
        self.rule.save()
        self.source=frappe.get_doc('ToDo', fixtures.SOURCE)
        self.sender=frappe.get_doc('WhatsApp Phone Number ID', fixtures.ACCOUNT)

    def asset(self, name, content, private=1):
        file=frappe.get_doc(dict(doctype='File',file_name=name,content=content,is_private=private)).insert(ignore_permissions=True)
        asset=frappe.get_doc(dict(doctype='WhatsApp Media', media_type='Upload',
            phone_number_id=fixtures.ACCOUNT, media_attachment=file.file_url, content_type='audio/mpeg',
            caption='Fixture attachment')).insert()
        return file,asset

    def png(self):
        buffer=BytesIO(); Image.new('RGB',(2,2),'green').save(buffer,format='PNG'); return buffer.getvalue()

    def test_type_is_read_only_and_manual_override_is_ignored(self):
        meta=frappe.get_meta('WhatsApp Message Template').get_field('template_type')
        self.assertTrue(meta.read_only)
        self.rule.template_type='video'; self.rule.save()
        self.assertEqual(self.rule.template_type,'text')
        self.assertEqual(template_content.detect(),'text')
        from whatsapp_messaging.patches.v1_0.automatic_template_types import execute
        modified=self.rule.modified
        frappe.db.set_value(self.rule.doctype,self.rule.name,'template_type','audio',update_modified=False)
        execute(); execute()
        self.assertEqual(frappe.db.get_value(self.rule.doctype,self.rule.name,'template_type'),'text')
        self.assertEqual(str(frappe.db.get_value(self.rule.doctype,self.rule.name,'modified')),str(modified))

    def test_actual_png_content_sets_image_and_keeps_text_as_caption(self):
        file,asset=self.asset('configuration.png', self.png())
        self.assertEqual(template_content.detect(asset.name),'image')
        self.rule.media=asset.name; self.rule.template_type='document'; self.rule.save()
        self.assertEqual(self.rule.template_type,'image')
        # Type detection is available while outbound messaging is disabled.
        self.assertEqual(template_content.resolve(asset.name)['file_id'],file.name)
        self.rule.media=None; self.rule.save(); self.assertEqual(self.rule.template_type,'text')

    def test_pdf_is_document_and_removal_restores_text(self):
        writer=PdfWriter(); writer.add_blank_page(width=72,height=72); buffer=BytesIO(); writer.write(buffer)
        file,asset=self.asset('configuration.pdf',buffer.getvalue())
        self.rule.media=asset.name; self.rule.save()
        self.assertEqual(self.rule.template_type,'document')
        self.assertEqual(template_content.resolve(asset.name)['file_id'],file.name)
        self.assertEqual(self.rule.message_preview,'Hello {{template_doctype.status}}')
        self.rule.media=None; self.rule.save(); self.assertEqual(self.rule.template_type,'text')

    def test_public_unsupported_and_url_media_are_rejected(self):
        with self.assertRaises(frappe.ValidationError): self.asset('configuration-public.png',self.png(),private=0)
        with self.assertRaises(frappe.ValidationError): self.asset('configuration.csv',b'column\nvalue\n')
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(dict(doctype='WhatsApp Media',media_type='URL',phone_number_id=fixtures.ACCOUNT,
                media_url='https://example.invalid/never-fetch.pdf',document_type='document')).insert()
        _,legacy=self.asset('configuration-legacy.png',self.png())
        frappe.db.set_value(legacy.doctype,legacy.name,dict(media_type='URL',media_attachment=None,media_url='https://example.invalid/never-fetch.pdf'))
        with self.assertRaises(frappe.ValidationError): template_content.detect(legacy.name)

    def test_detection_requires_role_and_approved_body_templates_exclude_media(self):
        approved=insert('WhatsApp Approved Template',template_name='fixture-approved',language='en',supported=1)
        self.assertEqual(template_content.detect(approved_template_name=approved.name),'text')
        _,asset=self.asset('configuration-approved.png',self.png())
        with self.assertRaises(frappe.ValidationError): template_content.detect(asset.name,approved.name)
        frappe.set_user(fixtures.UNRELATED)
        with self.assertRaises(frappe.PermissionError): template_content.detect()
        frappe.set_user('Administrator')

    def test_shared_policy_applies_to_every_template_and_rejects_local_overrides(self):
        other=frappe.get_doc(dict(doctype=self.rule.doctype,template_name='Second shared policy fixture',
            template_doctype='ToDo',phone_number_id=fixtures.ACCOUNT,allowed_source_fields='["description"]',
            message_preview='Hello {{template_doctype.status}}')).insert()
        self.assertEqual(parse_message(other,self.source), 'Hello '+self.source.status)
        self.assertEqual(other.allowed_source_fields,'["status"]')
        self.policy.allowed_fields='[]'; self.policy.save()
        for rule in (self.rule,other):
            with self.assertRaises(TemplateSecurityError): parse_message(rule,self.source)
            self.assertEqual(frappe.db.get_value(rule.doctype,rule.name,'allowed_source_fields'),'[]')
        self.assertTrue(frappe.get_meta(self.rule.doctype).get_field('allowed_source_fields').hidden)

    def test_only_system_manager_can_manage_policy_and_invalid_fields_are_rejected(self):
        for user in (fixtures.EDITOR,fixtures.SUPERVISOR):
            frappe.set_user(user)
            policy=frappe.get_doc(field_policy.POLICY,'ToDo'); policy.allowed_fields='["description"]'
            with self.assertRaises(frappe.PermissionError): policy.save()
        frappe.set_user('Administrator')
        for name in ('access_token','does_not_exist','patient.name'):
            self.policy.allowed_fields=json.dumps([name])
            with self.assertRaises((frappe.ValidationError,TemplateSecurityError)): self.policy.save()
        available=field_policy.options('ToDo')
        self.assertTrue(available['can_manage'])
        self.assertTrue(any(f['value']=='status' for f in available['fields']))

    def test_policy_revocation_invalidates_queued_rule_version_without_changing_run_as(self):
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',1)
        frappe.db.set_value(self.sender.doctype,self.sender.name,'enabled',1)
        self.sender.reload()
        peer=inbox.ensure_peer('12025550100',self.sender)
        conversation=inbox.ensure_conversation(self.sender,peer)
        frappe.db.set_value(conversation.doctype,conversation.name,'window_expires_at',utcnow()+timedelta(hours=1))
        result=outbox.create_intent(conversation.name,'shared-policy-revocation',body='Hello',
            source_doctype='ToDo',source_name=self.source.name,rule=self.rule.name)
        intent=frappe.get_doc('WhatsApp Outbox',result['outbox'])
        outbox.validate_dispatch(intent)
        run_as=frappe.db.get_value(self.rule.doctype,self.rule.name,'run_as')
        self.policy.allowed_fields='[]'; self.policy.save()
        with self.assertRaises(frappe.ValidationError): outbox.validate_dispatch(intent)
        self.assertEqual(frappe.db.get_value(self.rule.doctype,self.rule.name,'run_as'),run_as)

    def test_static_picker_lists_readable_singletons_even_without_approvals(self):
        groups=field_policy.editor_fields('ToDo')
        website=next(group for group in groups if group['source_doctype']=='Website Settings')
        self.assertEqual(website['section'],'static.website_settings')
        self.assertEqual(website['fields'],[])
        self.assertTrue(website['can_manage'])
        self.assertEqual(frappe.get_meta(self.rule.doctype).get_field('message_preview').read_only,0)

    def test_static_fields_use_shared_approval_and_runtime_permissions(self):
        policy=frappe.get_doc(dict(doctype=field_policy.POLICY,source_doctype='Website Settings',
            allowed_fields='["app_name"]')).insert()
        frappe.db.set_single_value('Website Settings','app_name','Riverbend Hospital')
        self.rule.message_preview='Welcome to {{static.website_settings.app_name}}'
        self.rule.save()
        self.assertEqual(parse_message(self.rule,self.source),'Welcome to Riverbend Hospital')
        groups=field_policy.editor_fields('ToDo')
        website=next(group for group in groups if group['source_doctype']=='Website Settings')
        self.assertEqual([f['value'] for f in website['fields']],['app_name'])
        for token in ('static.website_settings.home_page','static.whatsapp_phone_number_id.access_token',
                'static.website_settings.app_name.extra','static.to_do.status'):
            self.rule.message_preview='{{'+token+'}}'
            with self.assertRaises(TemplateSecurityError): parse_message(self.rule,self.source)
        self.rule.message_preview='{{static.website_settings.app_name}}'
        with patch.object(frappe.model.document.Document,'has_permlevel_access_to',return_value=False):
            with self.assertRaises(TemplateSecurityError): parse_message(self.rule,self.source)
        frappe.set_user(fixtures.EDITOR)
        self.assertFalse(any(g['source_doctype']=='Website Settings' for g in field_policy.editor_fields('ToDo')))
        with self.assertRaises(frappe.PermissionError): parse_message(self.rule,self.source)
        frappe.set_user('Administrator')
        policy.allowed_fields='[]';policy.save()
        with self.assertRaises(TemplateSecurityError): parse_message(self.rule,self.source)

    def test_static_access_is_rechecked_before_dispatch(self):
        frappe.get_doc(dict(doctype=field_policy.POLICY,source_doctype='Website Settings',
            allowed_fields='["app_name"]')).insert()
        frappe.db.set_single_value('Website Settings','app_name','Riverbend Hospital')
        frappe.db.set_single_value('WhatsApp Settings','enable_outbound_messages',1)
        frappe.db.set_value(self.sender.doctype,self.sender.name,'enabled',1)
        self.sender.reload()
        self.rule.message_preview='Welcome to {{static.website_settings.app_name}}';self.rule.save()
        peer=inbox.ensure_peer('12025550100',self.sender)
        conversation=inbox.ensure_conversation(self.sender,peer)
        frappe.db.set_value(conversation.doctype,conversation.name,'window_expires_at',utcnow()+timedelta(hours=1))
        result=outbox.create_intent(conversation.name,'static-permission-revocation',body='Welcome to Riverbend Hospital',
            source_doctype='ToDo',source_name=self.source.name,rule=self.rule.name)
        intent=frappe.get_doc('WhatsApp Outbox',result['outbox'])
        outbox.validate_dispatch(intent)
        with patch('whatsapp_messaging.messaging.field_policy.static_value',side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError):outbox.validate_dispatch(intent)

    def test_static_revocation_invalidates_templates_with_other_source_doctypes(self):
        policy=frappe.get_doc(dict(doctype=field_policy.POLICY,source_doctype='Website Settings',
            allowed_fields='["app_name"]')).insert()
        self.rule.message_preview='{{static.website_settings.app_name}}'
        self.rule.save()
        modified=str(self.rule.modified);principal=self.rule.run_as
        policy.allowed_fields='[]';policy.save()
        self.assertNotEqual(str(frappe.db.get_value(self.rule.doctype,self.rule.name,'modified')),modified)
        self.assertEqual(frappe.db.get_value(self.rule.doctype,self.rule.name,'run_as'),principal)
        self.assertEqual(frappe.db.get_value(self.rule.doctype,self.rule.name,'allowed_source_fields'),'["status"]')


if __name__=='__main__':
    fixtures.connect()
    try:
        fixtures.seed()
        unittest.main(verbosity=2)
    finally:
        frappe.db.rollback(); frappe.destroy()
