# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe import _

@frappe.whitelist()
def get_template_doctypes():
    cache_key = "template_doctypes_map"
    doctypes = frappe.cache().get_value(cache_key)

    if not doctypes:
        # Query to get distinct template_doctype values from Templates
        doctypes = frappe.db.get_all('WhatsApp Message Template', distinct=True, fields=['name', 'template_doctype', 'template_button_label'])

        # Create a map with the template_doctype values as keys and document names as values
        doctype_map = {}
        for d in doctypes:
            template_details = {'name': d.name, 'label': d.template_button_label}
            if doctype_map.get(d.template_doctype):
                doctype_map[d.template_doctype].append(template_details)
            else:
                doctype_map[d.template_doctype] = [template_details]

        # Cache the result
        frappe.cache().set_value(cache_key, doctype_map)
        return doctype_map
    return doctypes

class WhatsAppMessageTemplate(Document):
    def before_save(self):
        self.invalidate_cache()

    def invalidate_cache(self):
        cache_key = "template_doctypes_map"
        frappe.cache().delete_value(cache_key)

    def after_save(self):
        self.invalidate_cache()
