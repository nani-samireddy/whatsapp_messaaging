import frappe
from frappe import get_meta
from frappe.utils.file_manager import get_file

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


@frappe.whitelist()
def get_absolute_path(file_name):
	if(file_name.startswith('/files/')):
		file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}/public{file_name}'
	if(file_name.startswith('/private/')):
		file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}{file_name}'
	return file_path


@frappe.whitelist()
def wa_get_file(file_name):
    try:
        file_data = get_file(file_name)
        # file_path = file_data.get('file_url')  # Get the file URL

        # if file_path:
        #     file_path = frappe.utils.get_site_path(file_path.lstrip("/"))  # Get the absolute file path
        #     with open(file_path, 'rb') as f:
        return file_data

    except Exception as e:
        frappe.throw(f"Error fetching file: {str(e)}")
