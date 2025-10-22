"""
Utilities for interacting with WhatsApp Cloud API Message Templates.
https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates/
"""

import frappe
import json
import requests
from frappe import _
from whatsapp_messaging.utils import get_language_code
from whatsapp_messaging.whatsapp_messaging.doctype.whatsapp_message_template.whatsapp_message_template import (
	get_placeholder_example_values,
)

# Setup logger
# frappe.utils.logger.set_log_level("DEBUG")
logger = frappe.logger("whatsapp_messaging", allow_site=True, file_count=50)


def get_waba_id():
	"""Get WhatsApp Business Account ID from settings."""
	settings = frappe.get_doc("WhatsApp Settings")
	if not settings.waba_id:
		frappe.throw(_("WhatsApp Business Account ID not configured in WhatsApp Settings"))
	return settings.waba_id


def get_api_base_url():
	"""Get WhatsApp API base URL."""
	settings = frappe.get_doc("WhatsApp Settings")
	version = settings.whatsapp_api_version or "v19.0"
	base_url = settings.whatsapp_api_url or "https://graph.facebook.com"
	return f"{base_url}/{version}"


def get_access_token(phone_number_id):
	"""Get access token for the phone number."""
	phone_doc = frappe.get_doc("WhatsApp Phone Number ID", phone_number_id)
	if not phone_doc.access_token:
		frappe.throw(_("Access token not configured for phone number: {0}").format(phone_number_id))
	return phone_doc.access_token


def build_template_components(template_doc):
	"""
	Build the components array for WhatsApp template API.
	Supports HEADER (text/media), BODY, and FOOTER components.
	For media headers, uses file_handle from resumable upload API.
	"""
	components = []
	has_body_placeholders = False
	placeholder_examples = []

	if getattr(template_doc, "flags", None) is not None:
		template_doc.flags.has_placeholder_parameters = False
		template_doc.flags.placeholder_example_values = []
	
	# Header component (media only - text headers are merged with body)
	header_component = None
	header_text = None
	
	# Check for media header first
	if template_doc.media:
		media_doc = frappe.get_doc("WhatsApp Media", template_doc.media)
		# Use file_handle from resumable upload API for uploaded media
		if media_doc.file_handle:
			content_type = media_doc.content_type
			# Map MIME types to WhatsApp header formats
			if content_type.startswith('image/'):
				format_type = "IMAGE"
			elif content_type.startswith('video/'):
				format_type = "VIDEO"
			elif content_type.startswith('application/pdf') or content_type.startswith('application/'):
				format_type = "DOCUMENT"
			else:
				format_type = "DOCUMENT"  # Default fallback
			
			header_component = {
				"type": "HEADER",
				"format": format_type,
				"example": {
					"header_handle": [media_doc.file_handle]
				}
			}
		else:
			logger.warning(f"Media document {media_doc.name} has no file_handle available")

	# Store header text for potential merging with body
	if template_doc.template_header:
		header_text = template_doc.template_header
	
	# Add header component if created (media only)
	if header_component:
		components.append(header_component)
	
	# Body component with message text (merge header text if no media header)
	if template_doc.message_preview:
		# Convert {{placeholder}} to WhatsApp format {{1}}, {{2}}, etc.
		import re
		message_text = template_doc.message_preview
		
		# If we have header text but no media header, merge header text with body
		if header_text and not header_component:
			message_text = f"{header_text}\n\n{message_text}"
		
		placeholders = re.findall(r'\{\{(.*?)\}\}', message_text)
		has_body_placeholders = bool(placeholders)
		if has_body_placeholders:
			placeholder_examples = get_placeholder_example_values(template_doc, placeholders)
		
		# Replace placeholders with numbered format
		for i, placeholder in enumerate(placeholders, 1):
			message_text = message_text.replace(f"{{{{{placeholder}}}}}", f"{{{{{i}}}}}", 1)
		
		body_component = {
			"type": "BODY",
			"text": message_text
		}
		
		# Add example if placeholder values are available
		if placeholder_examples:
			body_component["example"] = {
				"body_text": [placeholder_examples]
			}
		
		components.append(body_component)
	
	# Footer component
	if template_doc.template_footer:
		footer_component = {
			"type": "FOOTER",
			"text": template_doc.template_footer
		}
		components.append(footer_component)

	if getattr(template_doc, "flags", None) is not None:
		template_doc.flags.has_placeholder_parameters = has_body_placeholders
		template_doc.flags.placeholder_example_values = placeholder_examples
	
	return components


@frappe.whitelist()
def create_whatsapp_template(template_name):
	"""
	Create a message template in WhatsApp Cloud API.
	
	Args:
		template_name: Name of the WhatsApp Message Template document
		
	Returns:
		dict: Response from WhatsApp API
	"""
	try:
		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		
		if not template_doc.sync_with_whatsapp:
			return {"success": False, "message": "Sync with WhatsApp is disabled"}
		
		waba_id = get_waba_id()
		base_url = get_api_base_url()
		access_token = get_access_token(template_doc.phone_number_id)
		
		url = f"{base_url}/{waba_id}/message_templates"
		
		# Build template payload
		language_code = get_language_code(template_doc.whatsapp_template_language) if template_doc.whatsapp_template_language else "en"
		components = build_template_components(template_doc)
		payload = {
			"name": template_doc.template_name.lower().replace(" ", "_"),
			"language": language_code,
			"category": template_doc.whatsapp_template_category or "UTILITY",
			"components": components
		}

		if getattr(template_doc, "flags", None) and getattr(template_doc.flags, "has_placeholder_parameters", False):
			payload["parameter_format"] = "positional"
		
		headers = {
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json"
		}
		logger.error("Creating WhatsApp template with header: %s", headers)
		logger.error("Creating WhatsApp template with payload: %s", payload)
		response = requests.post(url, json=payload, headers=headers)
		response_data = response.json()
		frappe.log_error(f"WhatsApp template creation response: {response_data}")
		if response.status_code == 200 and response_data.get("id"):
			# Update template document with API response
			raw_status = response_data.get("status", "IN_REVIEW")
			normalized_status = normalize_template_status(raw_status)

			template_doc.whatsapp_template_id = response_data.get("id")
			template_doc.whatsapp_template_category = response_data.get("category") or "UTILITY"
			template_doc.status = normalized_status
			template_doc.last_synced = frappe.utils.now()
			# If created on WhatsApp, set to IN_REVIEW unless API returns final state
			# template_doc.status = "IN_REVIEW" if normalized_status not in ("APPROVED", "REJECTED") else normalized_status
			template_doc.save(ignore_permissions=True)
			
			frappe.msgprint(_("Template created successfully in WhatsApp. Status: {0}").format(normalized_status))
			
			return {"success": True, "data": response_data, "normalized_status": normalized_status}
		else:
			error_message = response_data.get("error", {}).get("message", "Unknown error")
			logger.error("WhatsApp Template Creation Failed full response: %s,", response_data)
			logger.error("WhatsApp Template Creation Failed: %s, template=%s", error_message, template_name)
			return {"success": False, "message": error_message, "data": response_data}
			
	except Exception as e:
		logger.error("Error creating WhatsApp template: %s", template_name, exc_info=True)
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def request_review(template_name: str):
	"""User-triggered action to send a DRAFT template for review to WhatsApp Cloud API.

	- Only allowed when status is DRAFT, APPROVED, or REJECTED (editable states)
	- Creates the template on WhatsApp (or updates, if already exists but editable)
	- Sets local status to IN_REVIEW
	"""
	template_doc = frappe.get_doc("WhatsApp Message Template", template_name)

	# Guard: ensure editable states
	editable_statuses = ["DRAFT", "APPROVED", "REJECTED", None, ""]
	if template_doc.status not in editable_statuses:
		frappe.throw("Template cannot be sent for review while status is '{}'".format(template_doc.status))

	# Create template on WhatsApp
	result = create_whatsapp_template(template_name)
	if not result.get("success"):
		return result

	# Move to IN_REVIEW locally
	template_doc.reload()
	template_doc.status = "IN_REVIEW"
	template_doc.last_synced = frappe.utils.now()
	template_doc.save(ignore_permissions=True)
	frappe.msgprint("Template sent for review. Status set to IN_REVIEW")
	return {"success": True}

@frappe.whitelist()
def sync_template_status(template_name: str):
	"""Fetch and update status for a template from WhatsApp Cloud API."""
	return get_template_status(template_name)

def update_whatsapp_template(template_name):
	"""
	Update a message template in WhatsApp Cloud API.
	Uses the correct endpoint: https://graph.facebook.com/{{Version}}/<TEMPLATE_ID>
	"""
	try:
		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		
		if not template_doc.whatsapp_template_id:
			return create_whatsapp_template(template_name)
		
		if not template_doc.sync_with_whatsapp:
			return {"success": False, "message": "Sync with WhatsApp is disabled"}
		
		base_url = get_api_base_url()
		access_token = get_access_token(template_doc.phone_number_id)
		
		# Use the correct endpoint with template ID directly
		url = f"{base_url}/{template_doc.whatsapp_template_id}"
		
		# Build template payload for update
		components = build_template_components(template_doc)
		payload = {
			"category": template_doc.whatsapp_template_category or "UTILITY",
			"components": components
		}

		if getattr(template_doc, "flags", None) and getattr(template_doc.flags, "has_placeholder_parameters", False):
			payload["parameter_format"] = "positional"
		
		headers = {
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json"
		}
		
		response = requests.post(url, json=payload, headers=headers)
		response_data = response.json()
		
		if response.status_code == 200:
			# Update template document with response
			if response_data.get("status"):
				normalized_status = normalize_template_status(response_data["status"])
				template_doc.status = normalized_status
			template_doc.last_synced = frappe.utils.now()
			template_doc.save(ignore_permissions=True)
			
			current_status = template_doc.status or "Updated"
			frappe.msgprint(_("Template updated successfully in WhatsApp. Status: {0}").format(current_status))
			
			return {"success": True, "data": response_data}
		else:
			error_message = response_data.get("error", {}).get("message", "Unknown error")
			logger.error("WhatsApp Template Update Failed: %s, template=%s", error_message, template_name)
			return {"success": False, "message": error_message, "data": response_data}
		
	except Exception as e:
		logger.error("Error updating WhatsApp template: %s", template_name, exc_info=True)
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def delete_whatsapp_template(template_name):
	"""
	Delete a message template from WhatsApp Cloud API.
	
	Args:
		template_name: Name of the WhatsApp Message Template document
		
	Returns:
		dict: Response from WhatsApp API
	"""
	try:
		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		
		if not template_doc.whatsapp_template_id:
			return {"success": False, "message": "Template not synced with WhatsApp"}
		
		waba_id = get_waba_id()
		base_url = get_api_base_url()
		access_token = get_access_token(template_doc.phone_number_id)
		
		# Use template name instead of ID for deletion
		template_api_name = template_doc.template_name.lower().replace(" ", "_")
		url = f"{base_url}/{waba_id}/message_templates"
		
		headers = {
			"Authorization": f"Bearer {access_token}",
			"Content-Type": "application/json"
		}
		
		# Delete using name parameter
		params = {
			"name": template_api_name
		}
		
		response = requests.delete(url, params=params, headers=headers)
		
		if response.status_code == 200:
			response_data = response.json()
			
			# Clear template sync fields
			template_doc.whatsapp_template_id = None
			template_doc.status = None
			template_doc.last_synced = frappe.utils.now()
			template_doc.save(ignore_permissions=True)
			
			frappe.msgprint(_("Template deleted successfully from WhatsApp"))
			return {"success": True, "data": response_data}
		else:
			response_data = response.json() if response.text else {}
			error_message = response_data.get("error", {}).get("message", "Unknown error")
			logger.error("WhatsApp Template Deletion Failed: %s, template=%s", error_message, template_name)
			return {"success": False, "message": error_message}
			
	except Exception as e:
		logger.error("Error deleting WhatsApp template: %s", template_name, exc_info=True)
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_template_status(template_name):
	"""
	Fetch the current status of a template from WhatsApp Cloud API.
	
	Args:
		template_name: Name of the WhatsApp Message Template document
		
	Returns:
		dict: Template status information
	"""
	try:
		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		if not template_doc.whatsapp_template_id:
			return {"success": False, "message": "Template not synced with WhatsApp"}
		frappe.log_error(f"Fetching status for WhatsApp template: {template_name}")
		
		waba_id = get_waba_id()
		base_url = get_api_base_url()
		access_token = get_access_token(template_doc.phone_number_id)
		
		# Get templates and filter by name
		url = f"{base_url}/{waba_id}/message_templates"
		
		headers = {
			"Authorization": f"Bearer {access_token}"
		}
		
		# Fetch templates with filters
		params = {
			"fields": "id,name,status,language,category,rejected_reason",
			"name": template_doc.template_name.lower().replace(" ", "_")
		}
		
		response = requests.get(url, params=params, headers=headers)
		response_data = response.json()
		
		if response.status_code == 200 and response_data.get("data"):
			templates = response_data["data"]
			
			if templates:
				template_info = templates[0]
				
				# Normalize status
				raw_status = template_info.get("status")
				normalized_status = normalize_template_status(raw_status)
				
				# Update template document
				template_doc.status = normalized_status
				template_doc.last_synced = frappe.utils.now()
				
				if template_info.get("rejected_reason"):
					template_doc.rejection_reason = template_info.get("rejected_reason")
				else:
					template_doc.rejection_reason = None
				
				template_doc.save(ignore_permissions=True)
				
				status_message = _("Status updated: {0}").format(normalized_status)
				if normalized_status == "REJECTED" and template_info.get("rejected_reason"):
					status_message += f" - {template_info.get('rejected_reason')}"
				
				frappe.msgprint(status_message)
				return {"success": True, "data": template_info, "normalized_status": normalized_status}
			else:
				return {"success": False, "message": "Template not found in WhatsApp"}
		else:
			error_message = response_data.get("error", {}).get("message", "Unknown error")
			return {"success": False, "message": error_message}
			
	except Exception as e:
		logger.error("Error fetching WhatsApp template status: %s", template_name, exc_info=True)
		return {"success": False, "message": str(e)}


def normalize_template_status(whatsapp_status):
	"""
	Normalize WhatsApp status to consistent format.
	Maps various WhatsApp API status responses to our simplified statuses.
	
	Args:
		whatsapp_status: Raw status from WhatsApp API
		
	Returns:
		str: Normalized status
	"""
	status_mapping = {
		# WhatsApp API statuses -> Our normalized statuses
		"PENDING": "IN_REVIEW",
		"IN_REVIEW": "IN_REVIEW", 
		"APPROVED": "APPROVED",
		"REJECTED": "REJECTED",
		"PAUSED": "PAUSED",
		"DISABLED": "DISABLED",
		"LIVE": "APPROVED",  # Some APIs return LIVE for approved
		"ACTIVE": "APPROVED",  # Some APIs return ACTIVE for approved
		"PENDING_DELETION": "DISABLED",
		"APPEAL_REQUESTED": "APPEAL_REQUESTED",
		# Quality-based statuses map to APPROVED since they can be sent
		"ACTIVE - QUALITY PENDING": "APPROVED",
		"ACTIVE - HIGH QUALITY": "APPROVED", 
		"ACTIVE - MEDIUM QUALITY": "APPROVED",
		"ACTIVE - LOW QUALITY": "APPROVED"
	}
	
	return status_mapping.get(whatsapp_status, whatsapp_status)


def is_template_editable(status):
	"""
	Check if template is editable based on status.
	
	Args:
		status: Template status
		
	Returns:
		bool: True if editable, False otherwise
	"""
	editable_statuses = ["APPROVED", "REJECTED", None, ""]
	return status in editable_statuses
