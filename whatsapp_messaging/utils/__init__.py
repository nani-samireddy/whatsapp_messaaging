import base64
from datetime import datetime
from frappe.utils.data import evaluate_filters
import frappe
import json
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
	from whatsapp_messaging.template_security import is_recipient_phone_field, SENSITIVE_FIELD
	_check_metadata_permission(doctype)
	meta = get_meta(doctype)
	permitted = set(meta.get_permitted_fieldnames(permission_type="read"))
	input_fields = []

	if isinstance(input_types, str):
		# Frappe serializes an optional null argument as an empty form value.
		input_types = json.loads(input_types) if input_types.strip() else None
	if input_types is None:
		input_types = ['Data', 'Select', 'Date', 'Datetime', 'Time', 'Currency', 'Int', 'Float', 'Check', 'Text', 'Small Text', 'Long Text', 'Link', 'Phone']
	if not isinstance(input_types, (list, tuple)) or any(not isinstance(kind, str) for kind in input_types):
		frappe.throw("Input field types must be a list")

	phone_only = set(input_types) == {"Phone"}
	for field in meta.fields:
		matches_type = field.fieldtype in input_types or ("Phone" in input_types and is_recipient_phone_field(field))
		if phone_only and SENSITIVE_FIELD.search(field.fieldname):
			continue
		if field.fieldname in permitted and matches_type and field.fieldtype != "Password" and not field.hidden:
			input_fields.append(field.fieldname)

	return input_fields


def _check_metadata_permission(doctype):
	if frappe.session.user == "Guest" or not frappe.has_permission(doctype, "read"):
		frappe.throw("You cannot read this DocType", frappe.PermissionError)

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

def datetime_to_cron_format(schedule):
	"""
	Converts a datetime (string or object) to a cron expression.

	Args:
		schedule (str | datetime): Either a datetime string ("YYYY-MM-DD HH:MM:SS") or a datetime object.

	Returns:
		str: Cron expression (e.g., "35 19 1 4 *" for April 1, 19:32:35).
	"""
	if isinstance(schedule, str):
		dt = datetime.strptime(schedule, "%Y-%m-%d %H:%M:%S")
	else:  # Assume it's a datetime object
		dt = schedule
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
	# Permission filtering is user-specific; never return the former site-wide cache.
	if frappe.session.user == "Guest":
		frappe.throw("Authentication is required", frappe.PermissionError)
	doctypes = frappe.get_list(
		"WhatsApp Message Template",
		filters={"disable": 0, "is_single": 0, "template_event": ["in", ["None", "Custom"]]},
		fields=["name", "template_doctype", "template_button_label"],
		limit_page_length=0,
	)
	from whatsapp_messaging.messaging.campaigns import DOCTYPE, rule_type
	doctypes = [row for row in doctypes if rule_type(row.name) != DOCTYPE]
	if frappe.db.has_table(DOCTYPE):
		doctypes += frappe.get_list(DOCTYPE,
			filters={"disable":0,"is_single":0,"template_event":["in",["None","Custom"]]},
			fields=["name","template_doctype","template_button_label"],limit_page_length=0)
	doctype_map = {}
	for template in doctypes:
		if frappe.has_permission(template.template_doctype, "read"):
			doctype_map.setdefault(template.template_doctype, []).append({
				"name": template.name, "label": template.template_button_label,
			})
	return doctype_map


def doc_matches_filters(doc, filters=None):
	'''
	Check if a document matches the given filters.
	:param doc: The document to check.
	:param filters: A list of filters to apply.
	:return: True if the document matches all filters, False otherwise.
	'''
	if not filters:
		return True
	if isinstance(filters, str):
		filters = json.loads(filters)
	if isinstance(filters, dict) and "filters" in filters:
		filters = filters["filters"]
	return evaluate_filters(doc, filters)


@frappe.whitelist()
def get_doctype_fields(doctype=None, docname=None, fields_types=None):
	"""Return only the approved message-field picker groups, never account metadata."""
	from whatsapp_messaging.template_security import (
		SAFE_SOURCE_TYPES, SAFE_TEMPLATE_FIELDS, SENSITIVE_FIELD, parse_allowed_fields,
	)
	if doctype != "WhatsApp Message Template" or not docname:
		frappe.throw("A saved WhatsApp Message Template is required")
	_check_metadata_permission(doctype)
	template = frappe.get_doc(doctype, docname)
	template.check_permission("read")
	_check_metadata_permission(template.template_doctype)
	from whatsapp_messaging.messaging.field_policy import get_allowed_source_fields
	allowed = get_allowed_source_fields(template.template_doctype)

	def fields_for(meta, allowed_names):
		permitted = set(meta.get_permitted_fieldnames(permission_type="read"))
		return [
			{key: getattr(field, key, None) for key in ("fieldname", "label", "fieldtype", "options", "hidden")}
			for field in meta.fields
			if field.fieldname in allowed_names and field.fieldname in permitted
			and field.fieldtype in SAFE_SOURCE_TYPES and not field.hidden and not field.print_hide
			and not SENSITIVE_FIELD.search(field.fieldname)
		]

	return [
		{"label": "Template labels", "doctype": doctype, "fieldname": "self",
		 "fields": fields_for(get_meta(doctype), SAFE_TEMPLATE_FIELDS)},
		{"label": template.template_doctype, "doctype": template.template_doctype, "fieldname": "template_doctype",
		 "fields": fields_for(get_meta(template.template_doctype), allowed)},
	]
