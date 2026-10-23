import frappe
from frappe.model.document import Document


class ServiceDocument(Document):
    """State/history is written through authorized operations, including for admins."""
    def before_insert(self):
        self._require_service()

    def validate(self):
        self._require_service()

    def on_trash(self):
        self._require_service()

    def _require_service(self):
        if not (frappe.flags.whatsapp_service_write or frappe.flags.in_migrate or frappe.flags.in_install):
            frappe.throw('Use the WhatsApp service action to change this record', frappe.PermissionError)


def protect_canonical(doc, method=None):
    field = 'conversation' if doc.doctype == 'WhatsApp Message' else 'identity_key'
    existing = frappe.db.get_value(doc.doctype, doc.name, field) if not doc.is_new() else None
    if doc.get(field) or existing:
        ServiceDocument._require_service(doc)
