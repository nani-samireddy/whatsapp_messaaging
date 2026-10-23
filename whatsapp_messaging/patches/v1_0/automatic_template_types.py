"""Normalize valid existing templates without saving or activating automation."""
import frappe
from whatsapp_messaging.messaging.template_content import resolve


def execute():
    previous = ''
    while True:
        rows = frappe.get_all('WhatsApp Message Template', filters={'name': ['>', previous]},
            fields=['name', 'media', 'approved_template', 'template_type'], order_by='name asc', limit_page_length=200)
        if not rows:
            break
        for row in rows:
            try:
                kind = resolve(row.media, row.approved_template)['template_type']
            except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError):
                # Invalid legacy content is reported when opened/saved; never fetch URLs or guess.
                frappe.clear_last_message()
                continue
            if row.template_type != kind:
                frappe.db.set_value('WhatsApp Message Template', row.name, 'template_type', kind, update_modified=False)
        previous = rows[-1].name
