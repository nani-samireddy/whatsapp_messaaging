import json
import frappe
from frappe.model.document import Document
from frappe.integrations.utils import make_post_request

def send_whatsapp_message(phone, message):
    settings = frappe.get_doc("WhatsApp Settings")
    if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
        frappe.throw("WhatsApp API settings are not configured")

    # Prepare the Url
    # url = settings.complete_url
    # if not url:
    #     frappe.throw("WhatsApp API URL is not configured")
    url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"

    # Prepare the headers
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {settings.whatsapp_token}"
    }

    # Prepare the payload
    payload = {
       "messaging_product": "whatsapp",
      "to": format_phone_number(phone),
      "type": "text",
      "text": {
        "body" : message
      }
    }

    # Make the request
    response = make_post_request(url, data=json.dumps(payload), headers=headers)response, "WhatsApp Response")
    return response

def format_phone_number(phone):
    if phone.startswith("+"):
        phone = phone[1:]
    return phone
