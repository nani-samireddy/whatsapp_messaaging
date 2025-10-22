import base64
from datetime import datetime
from frappe.utils.data import evaluate_filters
import frappe
from frappe import get_meta

# Setup logger
logger = frappe.logger("whatsapp_messaging", allow_site=True, file_count=50)

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
		Exception: If an error occurs during formatting, it logs the error using the logger.
	"""
	try:
		if phone.startswith("+"):
			phone = phone[1:]
		if "-" in phone:
			phone = phone.replace("-", "")
		return phone
	except Exception as e:
		logger.error(f"Error in format_phone_number: {str(e)}", exc_info=True)

def get_language_code(language_name):
	"""
	Maps user-friendly language names to WhatsApp API language codes.
	
	Args:
		language_name (str): The display name of the language
		
	Returns:
		str: The corresponding WhatsApp API language code
	"""
	language_mapping = {
		"Afrikaans": "af",
		"Albanian": "sq",
		"Arabic": "ar",
		"Arabic (Egypt)": "ar_EG",
		"Arabic (UAE)": "ar_AE",
		"Arabic (Lebanon)": "ar_LB",
		"Arabic (Morocco)": "ar_MA",
		"Arabic (Qatar)": "ar_QA",
		"Azerbaijani": "az",
		"Belarusian": "be_BY",
		"Bengali": "bn",
		"Bengali (India)": "bn_IN",
		"Bulgarian": "bg",
		"Catalan": "ca",
		"Chinese (China)": "zh_CN",
		"Chinese (Hong Kong)": "zh_HK",
		"Chinese (Taiwan)": "zh_TW",
		"Croatian": "hr",
		"Czech": "cs",
		"Danish": "da",
		"Dari": "prs_AF",
		"Dutch": "nl",
		"Dutch (Belgium)": "nl_BE",
		"English": "en",
		"English (UK)": "en_GB",
		"English (US)": "en_US",
		"English (UAE)": "en_AE",
		"English (Australia)": "en_AU",
		"English (Canada)": "en_CA",
		"English (Ghana)": "en_GHA",
		"English (Ireland)": "en_IE",
		"English (India)": "en_IN",
		"English (Jamaica)": "en_JM",
		"English (Malaysia)": "en_MY",
		"English (New Zealand)": "en_NZ",
		"English (Qatar)": "en_QA",
		"English (Singapore)": "en_SG",
		"English (Uganda)": "en_UG",
		"English (South Africa)": "en_ZA",
		"Estonian": "et",
		"Filipino": "fil",
		"Finnish": "fi",
		"French": "fr",
		"French (Belgium)": "fr_BE",
		"French (Canada)": "fr_CA",
		"French (Switzerland)": "fr_CH",
		"French (Ivory Coast)": "fr_CI",
		"French (Morocco)": "fr_MA",
		"Georgian": "ka",
		"German": "de",
		"German (Austria)": "de_AT",
		"German (Switzerland)": "de_CH",
		"Greek": "el",
		"Gujarati": "gu",
		"Hausa": "ha",
		"Hebrew": "he",
		"Hindi": "hi",
		"Hungarian": "hu",
		"Indonesian": "id",
		"Irish": "ga",
		"Italian": "it",
		"Japanese": "ja",
		"Kannada": "kn",
		"Kazakh": "kk",
		"Kinyarwanda": "rw_RW",
		"Korean": "ko",
		"Kyrgyz (Kyrgyzstan)": "ky_KG",
		"Lao": "lo",
		"Latvian": "lv",
		"Lithuanian": "lt",
		"Macedonian": "mk",
		"Malay": "ms",
		"Malayalam": "ml",
		"Marathi": "mr",
		"Norwegian": "nb",
		"Pashto": "ps_AF",
		"Persian": "fa",
		"Polish": "pl",
		"Portuguese (Brazil)": "pt_BR",
		"Portuguese (Portugal)": "pt_PT",
		"Punjabi": "pa",
		"Romanian": "ro",
		"Russian": "ru",
		"Serbian": "sr",
		"Sinhala": "si_LK",
		"Slovak": "sk",
		"Slovenian": "sl",
		"Spanish": "es",
		"Spanish (Argentina)": "es_AR",
		"Spanish (Chile)": "es_CL",
		"Spanish (Colombia)": "es_CO",
		"Spanish (Costa Rica)": "es_CR",
		"Spanish (Dominican Republic)": "es_DO",
		"Spanish (Ecuador)": "es_EC",
		"Spanish (Honduras)": "es_HN",
		"Spanish (Mexico)": "es_MX",
		"Spanish (Panama)": "es_PA",
		"Spanish (Peru)": "es_PE",
		"Spanish (Spain)": "es_ES",
		"Spanish (Uruguay)": "es_UY",
		"Swahili": "sw",
		"Swedish": "sv",
		"Tamil": "ta",
		"Telugu": "te",
		"Thai": "th",
		"Turkish": "tr",
		"Ukrainian": "uk",
		"Urdu": "ur",
		"Uzbek": "uz",
		"Vietnamese": "vi",
		"Zulu": "zu"
	}
	
	return language_mapping.get(language_name, "en")  # Default to English if not found

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
	
	