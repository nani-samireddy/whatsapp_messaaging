import json
import frappe
from frappe.integrations.utils import make_post_request
import requests


supported_media_types = {
    "audio": [
        '.aac',
        '.amr',
        '.mp3',
        '.m4a',
        '.ogg',
    ],
    "image": [
		'.jpg',
		'.jpeg',
		'.png',
		'.gif',
		'.webp',
	],
}

mime_types = {
    'aac': 'audio/aac',
    'amr': 'audio/amr',
    'mp3': 'audio/mpeg',
    'm4a': 'audio/mp4',
    'ogg': 'audio/ogg',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
}

@frappe.whitelist()
def get_absolute_path(file_name):
	if(file_name.startswith('/files/')):
		file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}/public{file_name}'
	if(file_name.startswith('/private/')):
		file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}{file_name}'
	return file_path

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

@frappe.whitelist()
def upload_whatsapp_media(file):

    if not file:
        frappe.throw("Please provide a file to upload")

	# Get the file static path
    file_path = get_absolute_path(file)

    file_name = file.split("/")[-1]

    media_type = file_name.split(".")[-1]

    if not media_type or not mime_types[media_type]:
        frappe.throw(f"Media type {media_type} is not supported")


    headers = get_headers()
    url = get_url("media")

    headers['content-type'] = 'multipart/form-data'

    # read the file contents.
    file_name = frappe.db.get_value("File", {"file_url": file})
    file_content = frappe.get_doc("File", file_name).get_content()

    payload = {
        "file": (file_name, open(file_path, 'rb')),
		"messaging_product": "whatsapp",
		"type": mime_types[media_type]
		}

    # files = [
	# 	('file', (file_name, open(file_path, 'rb'), mime_types[media_type]))
	# ]


    response = requests.post(url, headers=headers, data=payload)
    frappe.msgprint(response.text)



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


def send_text_message(recipients= [], message = ""):
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

    if not recipients or not message:
        frappe.throw("Please provide a recipient and a message")

    for recipient in recipients:
        payload = {
            "messaging_product": "whatsapp",
            "to": format_phone_number(recipient),
            "type": "text",
            "text": {
                "body": message
            }
        }

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
                "url": media_id,
                "caption": message
            }
        }

        # Send the message
        send_message(payload)
