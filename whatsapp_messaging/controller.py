import json
import frappe
from frappe.model.document import Document
from frappe.integrations.utils import make_post_request

def send_whatsapp_message_on_create(doc, method=None):
	# Get all the templates for the doctype
	doc_type = doc.doctype

	# return if the doctype is Template
	if doc_type == "WhatsApp Message Template" or doc_type == "WhatsApp Message Template Field" or doc_type == "WhatsApp Message":
		return

	templates = frappe.get_all("WhatsApp Message Template", filters={"template_doctype": doc_type, "template_event": "Create"}, fields=["name"])

	# If there are no templates, return
	if not templates:
		return

	# Parse the templates and send the message
	parse_templates_and_send_whatsapp_message(doc, templates)

def parse_templates_and_send_whatsapp_message(doc, templates):
	# Get the message for each template and fill the placeholders.
	for template in templates:
		# Get the full doc.
		full_template_doc = frappe.get_doc("WhatsApp Message Template", template.name)
		message_template = full_template_doc.text_template_text_message

		# Get all the fields for the template
		text_template_fields = full_template_doc.get("text_template_fields")

		# Fill the placeholders
		message = fill_placeholders(message_template, doc, text_template_fields)

		# Get the recipients
		recipients = get_template_recipients(full_template_doc, doc)

		# Send the message to each recipient
		for recipient in recipients:
			send_whatsapp_message(recipient, message)

def get_template_recipients(template, doc):
	recipients = []
	# Get recipients from template_doc_type if the recipient type is "Field" or "Field+Group" and phone_number_field_name is set.
	if template.recipient_type == "Field" or template.recipient_type == "Field+Group":
		if template.phone_number_field_name:
			recipients.append(doc.get(template.phone_number_field_name))

	# Get the recipients from the template_static_recipients child table if the recipient type is "Group" or "Field+Group"
	if template.recipient_type == "Group" or template.recipient_type == "Field+Group":
		# Check if the template has any static recipients
		if template.template_static_recipients:
			group_recipients = template.get("template_static_recipients")
			for recipient in group_recipients:
				recipients.append(recipient.phone_number)

	# Format the phone numbers (remove the + sign and - sign)
	recipients = [format_phone_number(phone) for phone in recipients]

	# remove duplicates
	recipients = list(set(recipients))

	return recipients

def fill_placeholders(message_template, doc, text_template_fields):

	# iterate over the fields and replace the placeholders with the actual values
	for field in text_template_fields:
		# if the placeholder is for the current doctype. Get the field and replace the placeholder.
		placeholder = "{{" + field.field_position + "}}"
		match field.field_type:
			case "Static":
				message_template = message_template.replace(placeholder, field.field_static_value)
			case "This Doc":
				message_template = message_template.replace(placeholder, doc.get(field.field_name))
			case "Other Doc":
				# Get the doctype and docname
				other_doctype = field.field_doc_type
				other_single_doc = frappe.get_doc(other_doctype, other_doctype)
				message_template = message_template.replace(placeholder, other_single_doc.get(field.field_name))
			case _:
				pass
	return message_template

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
	response = make_post_request(url, data=json.dumps(payload), headers=headers)
	return response

def format_phone_number(phone):
	if phone.startswith("+"):
		phone = phone[1:]
	if "-" in phone:
		phone = phone.replace("-", "")
	return phone
