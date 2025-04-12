import frappe

def get_cloud_api_url(type="messages"):
	"""
	Prepare the Url for the WhatsApp API request.
	Ensure that the WhatsApp API settings are configured in the "WhatsApp Settings" document.

	Args:
		type (str, optional): The type of API request (e.g., "messages"). Defaults to "messages".

	Returns:
		_type_: The URL for the WhatsApp API request.
	"""
	settings = frappe.get_doc("WhatsApp Settings")
	if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
		frappe.throw("WhatsApp API settings are not configured")

	# Prepare the Url
	url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/{type}"

	return url

def get_headers(content_type="application/json"):
	"""
	Prepare the headers for the WhatsApp API request.
	Ensure that the WhatsApp API settings are configured in the "WhatsApp Settings" document.

	Args:
		content_type (str, optional): The content type for the request. Defaults to "application/json".

	Returns:
		_type_: The headers for the WhatsApp API request.
	"""
	settings = frappe.get_doc("WhatsApp Settings")
	if not settings.whatsapp_api_url or not settings.whatsapp_token or not settings.whatsapp_app_id or not settings.whatsapp_api_version:
		frappe.throw("WhatsApp API settings are not configured")

	# Prepare the headers
	headers = {
		"content-type": content_type,
		"authorization": f"Bearer {settings.whatsapp_token}"
	}

	return headers
