import frappe
from urllib.parse import urlsplit
import re

def get_cloud_api_url(phone_number_id, type="messages"):
	"""
	Prepare the Url for the WhatsApp API request.
	Ensure that the WhatsApp API settings are configured in the "WhatsApp Settings" document.

	Args:
		type (str, optional): The type of API request (e.g., "messages"). Defaults to "messages".

	Returns:
		_type_: The URL for the WhatsApp API request.
	"""
	settings = frappe.get_doc("WhatsApp Settings")
	phone_number_id_doc = frappe.get_doc("WhatsApp Phone Number ID", phone_number_id)
	
	if not settings or not settings.whatsapp_api_url:
		frappe.throw("WhatsApp API settings are not configured")
		return None

	api_url = (settings.whatsapp_api_url or "").strip()
	version = (settings.whatsapp_api_version or "").strip()
	if not api_url or not version:
		frappe.throw("Please configure WhatsApp API URL and Version in WhatsApp Settings")
		return None
	parsed_url = urlsplit(api_url)
	if (
		parsed_url.scheme != "https"
		or parsed_url.netloc != "graph.facebook.com"
		or parsed_url.path not in ("", "/")
		or parsed_url.query or parsed_url.fragment
	):
		frappe.throw("WhatsApp API URL must be https://graph.facebook.com")

	external_phone_id = (phone_number_id_doc.phone_number_id or "").strip()
	if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
		frappe.throw("WhatsApp API Version must use the format v26.0")
	if not re.fullmatch(r"[0-9]+", external_phone_id):
		frappe.throw("WhatsApp Phone Number ID must contain digits only")
	if type not in ("messages", "media"):
		frappe.throw("Unsupported WhatsApp API resource")
	
	# Prepare the Url
	url = f"https://graph.facebook.com/{version}/{external_phone_id}/{type}"

	return url

def get_headers(phone_number_id,content_type="application/json"):
	"""
	Prepare the headers for the WhatsApp API request.
	Ensure that the WhatsApp API settings are configured in the "WhatsApp Settings" document.

	Args:
		content_type (str, optional): The content type for the request. Defaults to "application/json".

	Returns:
		_type_: The headers for the WhatsApp API request.
	"""
	phone_number_id_doc = frappe.get_doc("WhatsApp Phone Number ID", phone_number_id)
	access_token = phone_number_id_doc.get_password("access_token", raise_exception=False)
	if not access_token:
		frappe.throw(f"WhatsApp Phone Number ID {phone_number_id} is not configured properly")

	# Prepare the headers
	headers = {
		"content-type": content_type,
		"authorization": f"Bearer {access_token}"
	}

	return headers
