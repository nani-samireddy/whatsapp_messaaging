"""Keep Mac-local conversation-flow replies moving while the global scheduler is off.

Run using the bench Python from its sites directory. Normal installations use
the standard Frappe scheduler and default queue worker instead.
"""
import argparse
import time

import frappe


def tick(site):
    frappe.init(site=site, sites_path='.')
    try:
        frappe.connect()
        from whatsapp_messaging.messaging import flows, outbox
        flows.sweep()
        outbox.sweep(conversation_flows_only=True)
        frappe.db.commit()
    finally:
        frappe.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not args.site.endswith('.localhost'):
        parser.error('This helper is for .localhost development sites. Use the normal scheduler elsewhere.')
    print('Local conversation-flow dispatcher: ' + args.site, flush=True)
    while True:
        try:
            tick(args.site)
        except KeyboardInterrupt:
            break
        except Exception:
            # Keep secrets and provider payloads out of the local console.
            print('Flow dispatcher could not check pending work; retrying in five seconds.', flush=True)
        if args.once:
            break
        time.sleep(5)


if __name__ == '__main__':
    main()
