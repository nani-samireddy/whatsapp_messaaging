import frappe

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

	if not settings.whatsapp_api_url.strip() or not settings.whatsapp_api_version.strip():
		frappe.throw("Please configure WhatsApp API URL and Version in WhatsApp Settings")
		return None

	if not phone_number_id_doc.phone_number_id.strip():
		frappe.throw(f"WhatsApp Phone Number ID {phone_number_id} does not exist")
		return None
	
	# Prepare the Url
	url = f"{settings.whatsapp_api_url}/{settings.whatsapp_api_version}/{phone_number_id_doc.phone_number_id.strip()}/{type}"

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
	if not phone_number_id_doc or not phone_number_id_doc.access_token:
		frappe.throw(f"WhatsApp Phone Number ID {phone_number_id} is not configured properly")

	# Prepare the headers
	headers = {
		"content-type": content_type,
		"authorization": f"Bearer {phone_number_id_doc.access_token}"
	}

	return headers
