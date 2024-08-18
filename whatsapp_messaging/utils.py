import frappe
from frappe import get_meta

@frappe.whitelist()
def get_input_fields(doctype, input_types=None):
	"""
	This function retrieves the input fields of a given doctype.

	Parameters:
	- doctype (str): The name of the doctype.
	- input_types (list, optional): A list of input field types to filter the result. If no types are provided, all input field types are considered.

	Returns:
	- list: A list of input field names.
	"""
	meta = get_meta(doctype)
	input_fields = []

	if input_types is None:
		input_types = ['Data', 'Select', 'Date', 'Datetime', 'Time', 'Currency', 'Int', 'Float', 'Check', 'Text', 'Small Text', 'Long Text', 'Link', 'Dynamic Link', 'Password', 'Phone', 'Read Only', 'Attach', 'Attach Image']

	for field in meta.fields:
		if field.fieldtype in input_types:
			input_fields.append(field.fieldname)

	return input_fields
