import base64
from datetime import datetime
from frappe.utils.data import evaluate_filters
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

def doc_matches_filters(doc, filters=None):
	'''
	Check if a document matches the given filters.
	:param doc: The document to check.
	:param filters: A list of filters to apply.
	:return: True if the document matches all filters, False otherwise.
	'''
	if not filters:
		return True
	return evaluate_filters(doc, filters)


@frappe.whitelist(allow_guest=True)
def get_doctype_fields(doctype=None, docname=None, fields_types=None):
	"""
	Retrieve specific fields from a doctype document.

	Args:
		doctype (str): The name of the doctype.
		docname (str): The name of the document.
		fields_types (list, optional): A list of field names to retrieve. If None, all fields are retrieved.

	Returns:
		dict: A dictionary containing the requested fields and their values.
	"""
	if not doctype or not docname:
		return {"error": "Doctype and Docname are required"}

	current_doc = frappe.get_doc(doctype, docname)
	if not current_doc:
		return {"error": "Document not found"}

	FIELDS_TYPES_TO_EXCLUDE = [ "Section Break", "Column Break", "Tab Break", "Image", "Link", "Table"]
	FIELD_PROPERTIES_TO_INCLUDE = ["fieldname", "label", "fieldtype", "options", "hidden"]
 
	data_to_return = []
	
	# Get all the fields of the doctype
	meta = get_meta(doctype)
	# Get the fields in the main doctype.
	filtered_fields = filter(lambda f: f.fieldtype not in FIELDS_TYPES_TO_EXCLUDE and not f.print_hide, meta.fields)
	# Include only the specified properties for each field
	filtered_fields = map(lambda f: {prop: getattr(f, prop) for prop in FIELD_PROPERTIES_TO_INCLUDE if hasattr(f, prop)}, filtered_fields)
	if fields_types:
		data_to_return.append( {
			"label" : doctype,
			"doctype": doctype,
			"fieldname": "self",
			"fields": list(filtered_fields),
		})
	
	# Get fields from the linked doctype
	linked_fields = [field for field in meta.fields if field.fieldtype in ["Link", "Dynamic Link"]]
	for field in linked_fields:
		if field.options != "DocType" and field.options != "Dynamic Link":
			linked_doctype = field.options
			linked_meta = get_meta(linked_doctype)
			
			linked_fields_data = filter(lambda f: f.fieldtype not in FIELDS_TYPES_TO_EXCLUDE and not f.print_hide, linked_meta.fields)
			# Include only the specified properties for each field
			linked_fields_data = map(lambda f: {prop: getattr(f, prop) for prop in FIELD_PROPERTIES_TO_INCLUDE if hasattr(f, prop)}, linked_fields_data)
			
			if linked_fields_data:
				data_to_return.append({
					"label": field.label,
					"doctype": linked_doctype,
					"fieldname": field.fieldname,
					"fields": list(linked_fields_data),
				})
		elif field.options == "DocType":
			# Get the selected doctype from the current document.
			selected_doctype = current_doc.get(field.fieldname)
			if selected_doctype:
				linked_meta = get_meta(selected_doctype)
				linked_fields_data = filter(lambda f: f.fieldtype not in FIELDS_TYPES_TO_EXCLUDE and not f.print_hide, linked_meta.fields)
				# Include only the specified properties for each field
				linked_fields_data = map(lambda f: {prop: getattr(f, prop) for prop in FIELD_PROPERTIES_TO_INCLUDE if hasattr(f, prop)}, linked_fields_data)
				
				# If no fields are found, skip this field
				if linked_fields_data:
					data_to_return.append({
						"label": field.label,
						"fieldname": field.fieldname,
						"doctype": selected_doctype,
						"fields": list(linked_fields_data),
					})
	return data_to_return
	
	