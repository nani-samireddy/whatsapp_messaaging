import json
import frappe
from frappe.integrations.utils import make_post_request
from whatsapp_messaging.utils import format_phone_number
from whatsapp_messaging.utils.config import get_cloud_api_url, get_headers
from whatsapp_messaging.utils.log_manager import log_wa_message

def send_message(payload, media_doc_name = ""):
	"""
	Sends a WhatsApp message using the provided payload.

	This function retrieves WhatsApp API settings from the "WhatsApp Settings"
	document in Frappe, constructs the API URL and headers, and sends a POST
	request to the WhatsApp API to send a message.

	Args:
		`payload` (dict): The message payload to be sent. This should be a dictionary
						containing the necessary fields as per WhatsApp API requirements.
		`media_doc_name` (str): The name of the media document to be attached to the message. Default is "".

	Returns:
		dict: The response from the WhatsApp API.

	Raises:
		Exception: If there is an error in sending the message, it logs the error
				   and raises an exception.
	"""

	try:
		# Get the URL and headers
		url = get_cloud_api_url()
		headers = get_headers()
		# Make the request
		response = make_post_request(url, data=json.dumps(payload), headers=headers)

		# Log the message if the response is 200
		if response.get('messages'):
			log_wa_message(payload, "Sent", media_doc_name)
		else:
			log_wa_message(payload, "Failed", media_doc_name)
		return response
	except Exception as e:
		frappe.log_error(f"Error in send_whatsapp_message: {str(e)}")
		log_wa_message(payload, "Failed")

def send_bulk_messages(recipients= [], payload = {}, media_doc_name = ""):
	"""
	Send a text message to a list of recipients via WhatsApp.

	Args:
		`recipients` (list): A list of recipient phone numbers.
		`message` (str): The message to be sent.

	Raises:
		`frappe.exceptions.ValidationError`: If no recipients or message is provided.

	Example:
		send_text_message(["+1234567890"], "Hello, this is a test message.")
	"""
	if not recipients or not payload:
		frappe.throw("Please provide a recipient and a message")

	for recipient in recipients:
		payload['to'] = format_phone_number(recipient)
		# Send the message
		send_message(payload=payload, media_doc_name=media_doc_name)

