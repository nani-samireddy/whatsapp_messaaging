"""Recover explicitly configured document deliveries on a .localhost dev site.

Normal deployments use the standard Frappe scheduler. This helper only queues
document-rule work and never enables a rule, a sender or an outbound switch.
"""
import argparse
import time

import frappe


def tick(site):
    frappe.init(site=site, sites_path='.')
    try:
        frappe.connect()
        from whatsapp_messaging.messaging.document_delivery import recover
        recover()
        frappe.db.commit()
    finally:
        frappe.destroy()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not args.site.endswith('.localhost'):
        parser.error('Use the normal Frappe scheduler on non-local sites.')
    while True:
        try:
            tick(args.site)
        except KeyboardInterrupt:
            break
        except Exception:
            print('Document delivery recovery needs review; retrying in five seconds.', flush=True)
        if args.once:
            break
        time.sleep(5)
