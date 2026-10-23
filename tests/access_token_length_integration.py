"""Long-token round trips using fictional credentials and rolled-back fixtures.

Run from bench/sites with WHATSAPP_TOKEN_TEST_SITE selecting a local/test site.
No real sender is read or changed, no switch is enabled and no request is sent.
"""
import os
import unittest
from unittest.mock import patch

import frappe
from whatsapp_messaging.utils.config import get_headers


class AccessTokenLengthTests(unittest.TestCase):
    def setUp(self):
        frappe.db.savepoint('long_token_case')
        self.addCleanup(frappe.db.rollback, save_point='long_token_case')
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden'))
        network.start()
        self.addCleanup(network.stop)
        queue = patch('frappe.enqueue', side_effect=AssertionError('Queue forbidden'))
        queue.start()
        self.addCleanup(queue.stop)

    def check_round_trip(self, length):
        field = frappe.get_meta('WhatsApp Phone Number ID').get_field('access_token')
        self.assertEqual(field.fieldtype, 'Password')
        self.assertEqual(field.permlevel, 1)
        self.assertEqual(field.length, 1000)
        token = ('fictional-long-token-' * 60)[:length]
        self.assertEqual(len(token), length)
        doc = frappe.get_doc(dict(doctype='WhatsApp Phone Number ID',
            label='Long token regression fixture', phone_number_id='99887766554433001234',
            access_token=token, enabled=0)).insert()
        doc.reload()
        self.assertEqual(doc.get_password('access_token'), token)
        self.assertEqual(get_headers(doc.name)['authorization'], 'Bearer ' + token)
        masked = frappe.db.get_value(doc.doctype, doc.name, 'access_token')
        self.assertTrue(masked)
        self.assertEqual(set(masked), {'*'})
        self.assertNotIn(token, frappe.as_json(doc.as_dict()))
        encrypted = frappe.db.sql('SELECT password, encrypted FROM `__Auth` '
            'WHERE doctype=%s AND name=%s AND fieldname=%s',
            (doc.doctype, doc.name, 'access_token'))
        self.assertEqual(encrypted[0][1], 1)
        self.assertNotEqual(encrypted[0][0], token)
        # Editing another field must preserve the full encrypted token.
        doc.display_phone = '+1 202 555 0100'
        doc.save()
        doc.reload()
        self.assertEqual(doc.get_password('access_token'), token)

    def test_308_character_token_round_trip(self):
        self.check_round_trip(308)

    def test_1000_character_token_round_trip(self):
        self.check_round_trip(1000)


if __name__ == '__main__':
    site = os.environ.get('WHATSAPP_TOKEN_TEST_SITE')
    assert site in ('hms.localhost', 'development.localhost', 'whatsapp-test.localhost')
    frappe.init(site=site)
    frappe.connect()
    if site == 'whatsapp-test.localhost':
        assert frappe.conf.db_host == 'db', 'Disposable test database required'
    frappe.set_user('Administrator')
    count = frappe.db.count('WhatsApp Phone Number ID')
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(AccessTokenLengthTests))
        frappe.db.rollback()
        assert frappe.db.count('WhatsApp Phone Number ID') == count
        print('All fictional sender/token fixtures rolled back; no provider requests sent.')
        if not result.wasSuccessful():
            raise SystemExit(1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
