"""Refresh familiar app labels while retaining navigation layout and visibility."""
import json

import frappe
from whatsapp_messaging.patches.v1_0.plain_language_names import RENAMES


LABELS = {
    'Recipients': 'Additional Numbers',
    'Approved templates': 'Templates in Meta',
    'Shared fields': 'Template fields',
    'Campaign runs': 'Sending history',
    'Campaign Runs': 'Sending history',
    'Outbox': 'Sending queue',
    'Send attempts': 'Sending attempts',
    'Delivery events': 'Delivery updates',
    'Webhook events': 'Incoming updates',
    'Delivery & logs': 'Delivery details',
    'Delivery and troubleshooting': 'Delivery details',
    'Phone Numbers': 'Senders',
    'Template Field Policies': 'Template fields',
    'Outbound Queue': 'Sending queue',
    'Send Attempts': 'Sending attempts',
    'Delivery Events': 'Delivery updates',
    'Webhook Events': 'Incoming updates',
}


def execute():
    targets = dict(RENAMES)
    # Update child rows directly. Reimporting whole Workspaces can overwrite
    # customer layouts and invokes developer export/delete hooks on local sites.
    if frappe.db.exists('Sidebar', 'Whatsapp Messaging'):
        child_type = frappe.get_meta('Sidebar').get_field('items').options
        for row in frappe.get_all(child_type, filters={'parent': 'Whatsapp Messaging', 'parenttype': 'Sidebar'}, fields=['name', 'label', 'link_type', 'link_to']):
            values = {}
            if row.label in LABELS:
                values['label'] = LABELS[row.label]
            if row.link_type == 'DocType' and row.link_to in targets:
                values['link_to'] = targets[row.link_to]
            if values:
                frappe.db.set_value(child_type, row.name, values, update_modified=False)
    for name in ('WhatsApp Messaging', 'WhatsApp Templates & Automation', 'WhatsApp Administration'):
        if not frappe.db.exists('Workspace', name):
            continue
        child_type = frappe.get_meta('Workspace').get_field('shortcuts').options
        for row in frappe.get_all(child_type, filters={'parent': name, 'parenttype': 'Workspace'}, fields=['name', 'label', 'type', 'link_to']):
            values = {}
            if row.label in LABELS:
                values['label'] = LABELS[row.label]
            if row.type == 'DocType' and row.link_to in targets:
                values['link_to'] = targets[row.link_to]
            if values:
                frappe.db.set_value(child_type, row.name, values, update_modified=False)
        content = frappe.db.get_value('Workspace', name, 'content')
        try:
            blocks = json.loads(content or '[]')
        except (ValueError, TypeError):
            continue
        changed = False
        for block in blocks if isinstance(blocks, list) else []:
            if not isinstance(block, dict) or block.get('type') != 'shortcut':
                continue
            data = block.get('data')
            if isinstance(data, dict) and data.get('shortcut_name') in LABELS:
                data['shortcut_name'] = LABELS[data['shortcut_name']]
                changed = True
        if changed:
            frappe.db.set_value('Workspace', name, 'content', json.dumps(blocks), update_modified=False)
    frappe.clear_cache()
