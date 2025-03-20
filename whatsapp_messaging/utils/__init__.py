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
