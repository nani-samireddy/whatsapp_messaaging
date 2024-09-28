import frappe
# Internal imports
from whatsapp_messaging.whatsapp_messaging.doctype.whatsapp_message_template.whatsapp_message_template import get_template_doctypes
from whatsapp_messaging.message_controller import send_bulk_messages
from whatsapp_messaging.message_controller import format_phone_number


@frappe.whitelist()
def ws_handle_on_single_template_trigger(template_name, doctype):
	'''This function is called when the single template trigger is triggered'''
	try:
		# Check if the template and doctype are provided
		if not template_name or not doctype:
			frappe.throw("Template and Doctype are required")

		# Get all the documents in that doc type.
		documents = frappe.get_all(doctype, fields=["name"])

		# If there are no documents, return
		if not documents:
			return

		# Get the full template document.
		full_template_doc = frappe.get_doc("WhatsApp Message Template", template_name)

		if not full_template_doc:
			return

		# Iterate over the documents and send messages.
		for doc in documents:
			# Get the document
			doc = frappe.get_doc(doctype, doc.name)
			# Parse the template and send the message
			parse_single_template_and_send_whatsapp_message(doc, full_template_doc)

	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_single_template_trigger: {str(e)}")

@frappe.whitelist()
def ws_handle_on_custom_trigger(template_name, doctype, docname):
	'''This function is called when the custom trigger is triggered'''
	try:
		# Check if the template, doctype and docname are provided
		if not template_name or not doctype or not docname:
			frappe.throw("Template, Doctype and Docname are required")

		# Get the document
		doc = frappe.get_doc(doctype, docname)

		# Get the template
		template = frappe.get_doc("WhatsApp Message Template", template_name)

		# Parse the template and send the message
		parse_single_template_and_send_whatsapp_message(doc, template)
	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_custom_trigger: {str(e)}")

def ws_handle_on_cancel(doc, method=None):
	'''This function is called when the document is deleted'''
	try:
		whatsapp_messaging_send_message_handler(doc, ["Cancel"])
	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_cancel: {str(e)}")

def ws_handle_on_trash(doc, method=None):
	'''This function is called when the document is deleted'''
	try:
		whatsapp_messaging_send_message_handler(doc, ["Delete"])
	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_trash: {str(e)}")

def ws_handle_on_submit(doc, method=None):
	'''This function is called when the document is submitted'''
	try:
		whatsapp_messaging_send_message_handler(doc, ["Submit"])
	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_submit: {str(e)}")

def ws_handle_on_update(doc, method=None):
	'''This function is called when the document is updated'''
	try:
		whatsapp_messaging_send_message_handler(doc, ["Update", "Update Field"])
		pass
	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_update: {str(e)}")

def ws_handle_on_create(doc, method=None):
	'''This function is called when the document is created'''
	try:
		whatsapp_messaging_send_message_handler(doc, ["Create"])
	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_create: {str(e)}")

def whatsapp_messaging_send_message_handler(doc, event=[]):
	try:
		# Check if the doc exists and event is provided
		if not doc or not event:
			return

		# Get all the doctypes for which the templates are created
		template_doctypes = get_template_doctypes()

		# Check if the doctype is in the template_doctypes
		if doc.doctype not in list(template_doctypes.keys()):
			return

		# Get all the templates for the doctype
		doc_type = doc.doctype

		templates = frappe.get_all("WhatsApp Message Template", filters={"template_doctype": doc_type, "template_event": ['in',event], "is_single": 0}, fields=["name","template_event", "template_target_field"])
		# If there are no templates, return
		if not templates:
			return

		# Schedule the job to send the message.
		frappe.enqueue("whatsapp_messaging.controller.parse_templates_and_send_whatsapp_message", doc=doc, templates=templates)

		# Parse the templates and send the message
		# parse_templates_and_send_whatsapp_message(doc, templates)
	except Exception as e:
		frappe.log_error(f"Error in whatsapp_messaging_send_message_handler: {str(e)}")

@frappe.whitelist()
def parse_templates_and_send_whatsapp_message(doc, templates):
	'''This function is used to parse the templates and send the message'''
	try:
		# Get the message for each template and fill the placeholders.
		for template in templates:

			# Check if the template event is Update Field
			if template.template_event == "Update Field":
				# Get the field name from the template
				field_name = template.template_target_field

				# Get the field value from the doc
				field_value = doc.get(field_name)

				# Get the previous value of the field
				previous_value = doc.get_doc_before_save().get(field_name)

				# If the field value is not changed, return
				if field_value == previous_value:
					continue

			# Get the full template document.
			full_template_doc = frappe.get_doc("WhatsApp Message Template", template.name)

			# parse the template and send the message
			parse_single_template_and_send_whatsapp_message(doc, full_template_doc)
	except Exception as e:
		frappe.log_error(f"Error in parse_templates_and_send_whatsapp_message: {str(e)}")

def parse_single_template_and_send_whatsapp_message(doc, template):
	try:
		if not template or not doc:
			return
		message_template = template.text_template_text_message

		# Get all the fields for the template
		text_template_fields = template.get("text_template_fields")

		# Fill the placeholders
		message = fill_placeholders(message_template, doc, text_template_fields)

		# Get the recipients
		recipients = get_template_recipients(template, doc)

		# Get the template type.
		template_type = template.template_type

		# Prepare the payload
		payload = {}
		payload['messaging_product'] = "whatsapp"

		media = {}

		if template_type != "text":
			# Get the attchment_type
			attachment_type = template.attachment_type

			# If the attachment_type is URL, get the media_url
			if attachment_type == "URL":
				media["link"] = template.media_url
			elif attachment_type == "Upload":
				media["id"] = template.media_id
			media["caption"] = message

		# send message based on the template type.
		match template_type:
			case "text":
				payload['type'] = "text"
				payload['text'] = {
					"body": message
				}
			case "audio":
				payload['type'] = "audio"
				payload['audio'] = media
			case "image":
				payload['type'] = "image"
				payload['image'] = media
			case "document":
				payload['type'] = "document"
				payload['document'] = media
			case _:
				pass

		# Send the message
		send_bulk_messages(recipients, payload)

	except Exception as e:
		frappe.log_error(f"Error in parse_single_template_and_send_whatsapp_message: {str(e)}")

def get_template_recipients(template, doc):
	try:
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
	except Exception as e:
		frappe.log_error(f"Error in get_template_recipients: {str(e)}")

def fill_placeholders(message_template, doc, text_template_fields):
	try:
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
	except Exception as e:
		frappe.log_error(f"Error in fill_placeholders: {str(e)}")
