import base64
from datetime import datetime
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

def mime_type_to_message_type(mime_type):
	'''
	This function maps the media file MIME types to WhatsApp message types.

	Parameters:
	- `mime_type` (str): The MIME type of the media file.

 	Returns:
	- str: The WhatsApp message type (image, video, audio, document).
	'''
	if mime_type:
		# Map MIME types to WhatsApp message types
		if mime_type.startswith("image/"):
			return "image"
		elif mime_type.startswith("video/"):
			return "video"
		elif mime_type.startswith("audio/"):
			return "audio"
		else:
			return "document"
	else:
		# Default to document if MIME type is unknown
		return "document"

def datetime_to_cron_format(schedule) -> str:
	"""
	Converts a given datetime to a cron expression.

	Parameters:
	- `schedule` (str): The datetime string in the format "YYYY-MM-DD HH:MM:SS".

	Returns:
	- str: The cron expression.
	"""
	# Create a datetime object
	dt = datetime.strptime(schedule, "%Y-%m-%d %H:%M:%S")
	return f"{dt.minute} {dt.hour} {dt.day} {dt.month} *"

def encode_to_alphanumeric(text: str) -> str:
	'''
	Encodes the given text to an alphanumeric string.

	Parameters:
	- `text` (str): The text to encode.

	Returns:
 	- str: The alphanumeric string.
	'''
	encoded_bytes = base64.b64encode(text.encode("utf-8"))
	return encoded_bytes.decode("utf-8").replace("=", "")

def decode_from_alphanumeric(encoded_text: str) -> str:
	'''
	Decodes the given alphanumeric string to the original text.

	Parameters:
	- `encoded_text` (str): The alphanumeric string to decode.

	Returns:
	- str: The original text.
	'''
	padding = len(encoded_text) % 4
	if padding:
		encoded_text += "=" * (4 - padding)
	decoded_bytes = base64.b64decode(encoded_text.encode("utf-8"))
	return decoded_bytes.decode("utf-8")

def get_cloud_api_url(type="messages"):
	"""
	Prepare the Url for the WhatsApp API request.
	Ensure that the WhatsApp API settings are configured in the "WhatsApp Settings" document.

	Args:
		type (str, optional): The type of API request (e.g., "messages"). Defaults to "messages".

	Returns:
		_type_: The URL for the WhatsApp API request.
	"""
	settings = frappe.get_doc("WhatsApp Settings")
	if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
		frappe.throw("WhatsApp API settings are not configured")

	# Prepare the Url
	url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/{type}"

	return url

def get_headers(content_type="application/json"):
	"""
	Prepare the headers for the WhatsApp API request.
	Ensure that the WhatsApp API settings are configured in the "WhatsApp Settings" document.

	Args:
		content_type (str, optional): The content type for the request. Defaults to "application/json".

	Returns:
		_type_: The headers for the WhatsApp API request.
	"""
	settings = frappe.get_doc("WhatsApp Settings")
	if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
		frappe.throw("WhatsApp API settings are not configured")

	# Prepare the headers
	headers = {
		"content-type": content_type,
		"authorization": f"Bearer {settings.whatsapp_token}"
	}

	return headers

def format_phone_number(phone):
	"""
	Formats a phone number by removing the leading '+' and any hyphens.

	Args:
		`phone` (str): The phone number to format.

	Returns:
		`str`: The formatted phone number without the leading '+' and hyphens.

	Raises:
		Exception: If an error occurs during formatting, it logs the error using frappe.log_error.
	"""
	try:
		if phone.startswith("+"):
			phone = phone[1:]
		if "-" in phone:
			phone = phone.replace("-", "")
		return phone
	except Exception as e:
		frappe.log_error(f"Error in format_phone_number: {str(e)}")

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

