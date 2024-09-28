import json
import frappe
from frappe.integrations.utils import make_post_request
import requests


def get_headers():
    settings = frappe.get_doc("WhatsApp Settings")
    if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
        frappe.throw("WhatsApp API settings are not configured")

    # Prepare the headers
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {settings.whatsapp_token}"
    }

    return headers

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


def send_message(payload):
    """
    Sends a WhatsApp message using the provided payload.

    This function retrieves WhatsApp API settings from the "WhatsApp Settings"
    document in Frappe, constructs the API URL and headers, and sends a POST
    request to the WhatsApp API to send a message.

    Args:
        payload (dict): The message payload to be sent. This should be a dictionary
                        containing the necessary fields as per WhatsApp API requirements.
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
        return response
    except Exception as e:
        frappe.log_error(f"Error in send_whatsapp_message: {str(e)}")


def send_bulk_messages(recipients= [], payload = {}):
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
        payload['to'] = format_phone_number(recipient),

        # frappe.msgprint(f"Payload: {payload}")
        # Send the message
        send_message(payload)


def send_audio_message( recipients= [], message = "", media_id = ""):
    """
    Send an audio message to a list of recipients via WhatsApp.

    Args:
        recipients (list): A list of recipient phone numbers.
        message (str): The message to be sent.
        audio_url (str): The URL of the audio file to be sent.

    Raises:
        frappe.exceptions.ValidationError: If no recipients, message, or audio_url is provided.

    Example:
        send_audio_message(["+1234567890"], "Hello, this is an audio message.", "https://example.com/audio.mp3")
    """

    if not recipients or not message or not media_id:
        frappe.throw("Please provide a recipient, a message, and an audio URL")

    for recipient in recipients:
        payload = {
            "messaging_product": "whatsapp",
            "to": format_phone_number(recipient),
            "type": "audio",
            "audio": {
                "id": media_id,
                "caption": message
            }
        }

        # Send the message
        send_message(payload)

def send_document_message(recipients= [], message = "", media_id = ""):
    """
    Send a document message to a list of recipients via WhatsApp.

    Args:
        recipients (list): A list of recipient phone numbers.
        message (str): The message to be sent.
        document_url (str): The URL of the document to be sent.

    Raises:
        frappe.exceptions.ValidationError: If no recipients, message, or document_url is provided.

    Example:
        send_document_message(["+1234567890"], "Hello, this is a document message.", "https://example.com/document.pdf")
    """

    if not recipients or not message or not media_id:
        frappe.throw("Please provide a recipient, a message, and a document URL")

    for recipient in recipients:
        payload = {
            "messaging_product": "whatsapp",
            "to": format_phone_number(recipient),
            "type": "document",
            "document": {
                "id": media_id,
                "caption": message
            }
        }

        # Send the message
        send_message(payload)

