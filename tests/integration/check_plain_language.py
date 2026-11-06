"""Real-schema naming and data-preservation checks on the isolated test site."""
import os
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from whatsapp_messaging.messaging.common import digest
from whatsapp_messaging.patches.v1_0.plain_language_names import RENAMES, execute


class TestPlainLanguage(unittest.TestCase):
    def test_all_new_types_and_link_targets_exist(self):
        for old, new in RENAMES:
            self.assertFalse(frappe.db.exists('DocType', old))
            self.assertTrue(frappe.db.table_exists(new))
            self.assertIsNotNone(frappe.get_meta(new))
        self.assertEqual(frappe.get_meta('WhatsApp Campaign').get_field('other_recipients').options, 'Additional Number Entry')
        self.assertEqual(frappe.get_meta('Additional Number Entry').get_field('static_recipient').options, 'Additional Numbers')
        self.assertEqual(frappe.get_meta('WhatsApp Message').get_field('recipients').options, 'WhatsApp Static Recipient')

    def test_patch_can_run_again_without_sending_or_changing_switches(self):
        before = frappe.get_single('WhatsApp Settings').as_dict()
        counts = {dt: frappe.db.count(dt) for dt in ('WhatsApp Message', 'WhatsApp Outbox', 'WhatsApp Automation Run')}
        with patch('frappe.enqueue', side_effect=AssertionError('No jobs during rename')), \
             patch('requests.sessions.Session.request', side_effect=AssertionError('No network during rename')):
            execute()
        self.assertEqual(before, frappe.get_single('WhatsApp Settings').as_dict())
        for dt, count in counts.items():
            self.assertEqual(count, frappe.db.count(dt))

    def test_sidebar_uses_the_same_names_as_forms(self):
        sidebar = frappe.get_doc('Sidebar', 'Whatsapp Messaging')
        labels = {row.link_to: row.label for row in sidebar.items if row.link_to}
        self.assertEqual(labels['Additional Numbers'], 'Additional Numbers')
        self.assertEqual(labels['WhatsApp Meta Template'], 'Templates in Meta')
        self.assertEqual(labels['WhatsApp Template Fields'], 'Template fields')
        self.assertEqual(labels['WhatsApp Outbox'], 'Sending queue')

    def test_every_workspace_and_sidebar_target_exists(self):
        sidebar = frappe.get_doc('Sidebar', 'Whatsapp Messaging')
        for row in sidebar.items:
            if row.link_to and row.link_type in ('DocType', 'Page', 'Workspace', 'Report'):
                self.assertTrue(frappe.db.exists(row.link_type, row.link_to), (row.label, row.link_to))
        for name in ('WhatsApp Messaging', 'WhatsApp Templates & Automation', 'WhatsApp Administration'):
            workspace = frappe.get_doc('Workspace', name)
            labels = {row.label for row in workspace.shortcuts}
            for row in workspace.shortcuts:
                if row.type in ('DocType', 'Page', 'Workspace', 'Report'):
                    self.assertTrue(frappe.db.exists(row.type, row.link_to), (name, row.label, row.link_to))
            for block in json.loads(workspace.content):
                if block.get('type') == 'shortcut':
                    self.assertIn(block['data']['shortcut_name'], labels)

    def test_repair_stale_shortcut_without_changing_layout_or_sending(self):
        from whatsapp_messaging.patches.v1_0.repair_workspace_shortcuts import execute as repair
        frappe.db.savepoint('shortcut_repair')
        try:
            name = 'WhatsApp Administration'
            workspace = frappe.get_doc('Workspace', name)
            before = json.loads(workspace.content)
            ids = [row.name for row in workspace.shortcuts]
            shortcut = next(row for row in workspace.shortcuts if row.link_to == 'WhatsApp Template Fields')
            frappe.db.set_value(shortcut.doctype, shortcut.name, {
                'link_to': 'WhatsApp Template Field Policy', 'label': 'Template Field Policies'}, update_modified=False)
            blocks = json.loads(workspace.content)
            for block in blocks:
                if block.get('type') == 'shortcut' and block['data']['shortcut_name'] == shortcut.label:
                    block['data']['shortcut_name'] = 'Template Field Policies'
            frappe.db.set_value('Workspace', name, 'content', json.dumps(blocks), update_modified=False)
            with patch('frappe.enqueue', side_effect=AssertionError('No jobs during repair')), \
                 patch('requests.sessions.Session.request', side_effect=AssertionError('No network during repair')):
                repair()
                repair()
            workspace = frappe.get_doc('Workspace', name)
            self.assertEqual([row.name for row in workspace.shortcuts], ids)
            self.assertEqual(json.loads(workspace.content), before)
            repaired = next(row for row in workspace.shortcuts if row.name == shortcut.name)
            self.assertEqual((repaired.label, repaired.link_to), ('Template fields', 'WhatsApp Template Fields'))
        finally:
            frappe.db.rollback(save_point='shortcut_repair')
            frappe.clear_cache()

    @unittest.skipUnless(os.environ.get('WHATSAPP_EXPECT_UPGRADE'), 'Upgrade fixture only')
    def test_existing_number_selections_file_permission_and_inbox_link_survive(self):
        number = frappe.get_doc('Additional Numbers', 'WM Upgrade Reception')
        self.assertEqual(number.phone_number, '+12025550126')
        template = frappe.get_doc('WhatsApp Message Template', 'WM Upgrade Number Template')
        self.assertEqual(template.other_recipients[0].static_recipient, number.name)
        if frappe.db.exists('WhatsApp Campaign', 'WM Upgrade Numbers'):
            campaign = frappe.get_doc('WhatsApp Campaign', 'WM Upgrade Numbers')
            self.assertEqual(campaign.other_recipients[0].static_recipient, number.name)
        self.assertTrue(frappe.db.exists('File', {'attached_to_doctype': number.doctype, 'attached_to_name': number.name}))
        self.assertTrue(frappe.db.exists('User Permission', {'allow': number.doctype, 'for_value': number.name}))
        fixture = json.loads(Path(frappe.get_site_path('private', 'plain-language-fixtures.json')).read_text())
        if fixture:
            self.assertTrue(frappe.db.exists('WhatsApp Record Link', {'name': fixture['link'], 'reference_doctype': number.doctype,
                'reference_name': number.name, 'link_key': digest(None, number.doctype, number.name)}))
            message = frappe.get_doc('WhatsApp Message', fixture['message'])
            self.assertEqual(message.peer, fixture['contact'])
            self.assertTrue(frappe.db.exists('WhatsApp Contact', message.peer))
            self.assertEqual(message.status, 'Unknown')
            request = frappe.get_doc('WhatsApp Outbox', fixture['request'])
            self.assertEqual((request.state, request.network_started), ('Unknown', 1))
            self.assertEqual(request.request_key, fixture['request_key'])
            self.assertEqual(request.message, message.name)
        self.assertEqual(frappe.get_doc('WhatsApp Sender', 'WM Legacy Upgrade').get_password('access_token'), 'integration-only-legacy-token')
        source = frappe.get_doc('WhatsApp Message Template', 'WM Upgrade Number Source')
        self.assertEqual(source.template_doctype, 'Additional Numbers')
        query = json.loads(source.query_filters)
        self.assertEqual(query['doctype'], 'Additional Numbers')
        self.assertEqual(query['filters'][0], ['Additional Numbers', 'label', '=', 'Static Recipient'])
        if frappe.db.exists('WhatsApp Template Fields', 'Static Recipient'):
            from whatsapp_messaging.messaging.field_policy import get_allowed_source_fields, options
            self.assertEqual(get_allowed_source_fields('Additional Numbers'), frozenset({'label'}))
            self.assertEqual(options('Additional Numbers')['policy_name'], 'Static Recipient')


if __name__ == '__main__':
    frappe.init(site='whatsapp-test.localhost', sites_path='/testbench/sites')
    frappe.connect()
    try:
        assert frappe.conf.db_host == 'db', 'Only the isolated test database is allowed'
        frappe.set_user('Administrator')
        unittest.main(verbosity=2)
    finally:
        frappe.db.rollback()
        frappe.destroy()
