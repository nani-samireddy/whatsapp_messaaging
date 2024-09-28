import frappe
from frappe import get_meta
from frappe.utils.file_manager import get_file
import mimetypes

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
def wa_get_file_upload_info(file_name):
    try:
        file_data = get_file(file_name)
        # get the whatsapp settings.
        settings = frappe.get_doc("WhatsApp Settings")
        if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
            frappe.throw("WhatsApp API settings are not configured")

        mime_type = mimetypes.guess_type(file_name)[0]
        url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/media"

        response = {
            "file": file_data,
            "messaging_product": "whatsapp",
            "token": settings.whatsapp_token,
            "content_type": mime_type,
            "url": url,
        }

        return response

    except Exception as e:
        frappe.throw(f"Error fetching file: {str(e)}")

