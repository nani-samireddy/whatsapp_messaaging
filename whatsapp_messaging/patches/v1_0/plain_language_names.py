"""Use clearer business names before model sync, retaining IDs and references.

Frappe's DocType rename migrates tables, permissions, attachments, and Link /
Dynamic Link metadata. Fieldnames stay stable for existing campaigns and API
clients. The legacy WhatsApp Static Recipient snapshot table is unrelated.
"""

import json

import frappe
from frappe.model.rename_doc import rename_doc

from whatsapp_messaging.messaging.common import digest


RENAMES = (
    ("Static Recipient", "Additional Numbers"),
    ("Static Recipient Link", "Additional Number Entry"),
    ("WhatsApp Phone Number ID", "WhatsApp Sender"),
    ("WhatsApp Peer", "WhatsApp Contact"),
    ("WhatsApp Approved Template", "WhatsApp Meta Template"),
    ("WhatsApp Template Field Policy", "WhatsApp Template Fields"),
    ("WhatsApp Document Rule", "WhatsApp Document Delivery Rule"),
    ("WhatsApp Document Parameter", "WhatsApp Document Variable"),
)


def execute():
    # Renaming a MariaDB table commits DDL. Check every conflict before starting;
    # never merge independently created types or overwrite either set of numbers.
    for old, new in RENAMES:
        if frappe.db.exists("DocType", old) and (
            frappe.db.exists("DocType", new) or frappe.db.table_exists(new)
            or frappe.db.sql("SELECT 1 FROM `__Auth` WHERE doctype=%s LIMIT 1", new)
        ):
            frappe.throw(f"Cannot rename {old}: {new} already exists. Resolve the naming conflict before migrating.")

    in_patch = frappe.flags.in_patch
    frappe.flags.in_patch = True
    try:
        for old, new in RENAMES:
            if frappe.db.exists("DocType", old):
                # __Auth has no DocField metadata; Frappe's normal DocType rename
                # cannot move encrypted Password entries automatically.
                frappe.db.sql("UPDATE `__Auth` SET doctype=%s WHERE doctype=%s", (new, old))
                rename_doc("DocType", old, new, force=True,
                    ignore_permissions=True, validate=False, rebuild_search=False)
    finally:
        # Also safe when invoked directly for a migration verification.
        frappe.flags.in_patch = in_patch

    # Query builders store a second copy of the record type in JSON. Update only
    # structural DocType references, never filter values or message content.
    replacements = dict(RENAMES)
    for doctype in ('WhatsApp Message Template', 'WhatsApp Campaign'):
        if not frappe.db.table_exists(doctype):
            continue
        for row in frappe.get_all(doctype, filters={'query_filters': ['is', 'set']},
            fields=['name', 'query_filters']):
            try:
                query = json.loads(row.query_filters)
            except (ValueError, TypeError):
                continue  # Existing invalid queries remain blocked by validation.
            if not isinstance(query, dict):
                continue
            original = json.dumps(query, sort_keys=True)
            if isinstance(query.get('doctype'), str):
                query['doctype'] = replacements.get(query['doctype'], query['doctype'])
            for condition in query.get('filters', []) if isinstance(query.get('filters'), list) else []:
                if isinstance(condition, list) and len(condition) == 4 and isinstance(condition[0], str):
                    condition[0] = replacements.get(condition[0], condition[0])
            if json.dumps(query, sort_keys=True) != original:
                frappe.db.set_value(doctype, row.name, 'query_filters', json.dumps(query), update_modified=False)

    # These keys contain the DocType name. Updating them avoids duplicate Inbox
    # record links when a user links the same saved number after the rename.
    if frappe.db.table_exists("WhatsApp Record Link"):
        for row in frappe.get_all("WhatsApp Record Link",
            filters={"reference_doctype": ["in", [new for _, new in RENAMES]]},
            fields=["name", "conversation", "reference_doctype", "reference_name"]):
            frappe.db.set_value("WhatsApp Record Link", row.name, {
                "link_key": digest(row.conversation, row.reference_doctype, row.reference_name),
                "record_title": " · ".join(filter(None, (
                    row.conversation, row.reference_doctype, row.reference_name)))[:140],
            }, update_modified=False)
