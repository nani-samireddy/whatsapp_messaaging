import json
import frappe
from frappe.integrations.utils import make_post_request
import frappe.utils

@frappe.whitelist()
def get_headers(content_type="application/json"):
	settings = frappe.get_doc("WhatsApp Settings")
	if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
		frappe.throw("WhatsApp API settings are not configured")

	# Prepare the headers
	headers = {
		"content-type": content_type,
		"authorization": f"Bearer {settings.whatsapp_token}"
	}

	return headers

@frappe.whitelist()
def get_url(type="messages"):
	settings = frappe.get_doc("WhatsApp Settings")
	if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
		frappe.throw("WhatsApp API settings are not configured")

	# Prepare the Url
	url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/{type}"

	return url



def format_phone_number(phone):
	"""
	Formats a phone number by removing the leading '+' and any hyphens.

	Args:
		phone (str): The phone number to format.
	Returns:
		str: The formatted phone number without the leading '+' and hyphens.
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


def send_message(payload, media_doc_name = ""):
	"""
	Sends a WhatsApp message using the provided payload.

	This function retrieves WhatsApp API settings from the "WhatsApp Settings"
	document in Frappe, constructs the API URL and headers, and sends a POST
	request to the WhatsApp API to send a message.

	Args:
		payload (dict): The message payload to be sent. This should be a dictionary
						containing the necessary fields as per WhatsApp API requirements.
		media_doc_name (str): The name of the media document to be attached to the message. Default is "".
	Returns:
		dict: The response from the WhatsApp API.
	Raises:
		Exception: If there is an error in sending the message, it logs the error
				   and raises an exception.
	"""

	try:
		# Get the URL and headers
		url = get_url()
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
		recipients (list): A list of recipient phone numbers.
		message (str): The message to be sent.

	Raises:
		frappe.exceptions.ValidationError: If no recipients or message is provided.

	Example:
		send_text_message(["+1234567890"], "Hello, this is a test message.")
	"""
	if not recipients or not payload:
		frappe.throw("Please provide a recipient and a message")

	for recipient in recipients:
		payload['to'] = format_phone_number(recipient)
		# Send the message
		send_message(payload=payload, media_doc_name=media_doc_name)

def log_wa_message( payload, status, media_doc_name = ""):

	# Get the Whatsapp Conversation doc with the phone number.
	# If the conversation does not exist, create a new one.
	conversation_name = frappe.db.exists("Whatsapp Conversation", {"recipient": payload.get("to")})
	if conversation_name:
		conversation = frappe.get_doc("Whatsapp Conversation", conversation_name)
	else:
		conversation = frappe.get_doc({
			"doctype": "Whatsapp Conversation",
			"recipient": payload.get("to"),
			"status": status
		})
		conversation.insert(ignore_permissions=True)
		conversation.save()
	# Create child doc for the Whatsapp Conversation field
	new_conversation_row = conversation.append("conversations", {
		"recipient": payload.get("to"),
		"status": status,
		"message_type": payload.get("type"),
		"message": payload.get("type") == "text" and payload.get("text").get("body") or payload.get(payload.get("type")).get("caption"),
		"media": media_doc_name
	})
	new_conversation_row.insert(ignore_permissions=True)
	new_conversation_row.save()
	new_conversation_row.submit()
