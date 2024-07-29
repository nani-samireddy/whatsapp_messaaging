# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

import frappe
from frappe import _

@frappe.whitelist()
def get_template_doctypes():
	# Query to get distinct template_doctype values from Templates
	doctypes = frappe.db.get_all('WhatsApp Message Template', distinct=True, fields=['name','template_doctype', 'template_button_label'])

	# Create a map with the template_doctype values as keys and document names as values
	doctype_map = {}
	for d in doctypes:
		template_details = {'name': d.name, 'label': d.template_button_label}
		if doctype_map.get(d.template_doctype):
			doctype_map[d.template_doctype].append(template_details)
		else:
			doctype_map[d.template_doctype] = [template_details]

	# Extracting the template_doctype values from the query result
	# doctype_list = [d.template_doctype for d in doctypes]
	return doctype_map


class WhatsAppMessageTemplate(Document):
	pass
