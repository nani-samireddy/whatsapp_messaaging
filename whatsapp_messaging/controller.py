import frappe
import json
from requests_toolbelt.multipart.encoder import MultipartEncoder

# Internal imports
from whatsapp_messaging.message_controller import send_bulk_messages, get_headers, format_phone_number, get_url
from whatsapp_messaging.utils import mime_type_to_message_type
from frappe.utils.file_manager import get_file_path, get_file
import mimetypes
from frappe.integrations.utils import make_post_request
from frappe.utils import get_request_session

def ws_handle_cron_messages(interval):
	'''
	This function takes the interval as an argument and checks for any scheduled messages to be sent.
	'''
	# Check if there are any scheduled messages to be sent.
	cron_templates = frappe.get_all(
		"WhatsApp Message Template",
		filters={
			"template_event": "Cron",
			"cron_interval": interval
		},
		fields=["name", "template_doctype", "query_filters", "template_target_field"]
	)

	# Iterate over the pending messages and send the messages.
	for template in cron_templates:
		try:
			# Get the documents based on the query filters
			documents = frappe.get_all(template.template_doctype, filters=json.loads(template.query_filters).get("filters", []), fields=["name"])

			# Iterate over the documents and send the messages
			for doc in documents:
				doc_instance = frappe.get_doc(template.template_doctype, doc.name)
				parse_single_template_and_send_whatsapp_message(doc_instance, frappe.get_doc("WhatsApp Message Template", template.name))
		except Exception as e:
			frappe.log_error(f"Error in ws_handle_cron_messages: {str(e)}")
			


def ws_handle_scheduled_messages():
	'''
	This function checks for any scheduled messages with status "Pending" with date and time less than the current date and time.
	'''
	# Get all the Whatsapp Message Templates with status "Pending" and date and time less than the current date and time.
	scheduled_messages_templates = frappe.get_all(
     "WhatsApp Message Template",
     filters={
         "template_event": "Scheduled",
         "status": ['in', ["Pending", "Failed"]],
         "schedule": ("<=", frappe.utils.now())
        },
     fields=["name", "template_doctype", "query_filters", "template_target_field"]
     )

	# Iterate over the pending messages and send the messages.
	for template in scheduled_messages_templates:
		try:

			# Get the documents based on the query filters
			documents = frappe.get_all(template.template_doctype, filters=json.loads(template.query_filters).get("filters", []), fields=["name"])

			# Iterate over the documents and send the messages
			for doc in documents:
				doc_instance = frappe.get_doc(template.template_doctype, doc.name)
				parse_single_template_and_send_whatsapp_message(doc_instance, frappe.get_doc("WhatsApp Message Template", template.name))

			# Update the status of the template to "Sent"
			template_doc = frappe.get_doc("WhatsApp Message Template", template.name)
			template_doc.status = "Completed"
			template_doc.save()
		except Exception as e:
			frappe.log_error(f"Error in ws_handle_scheduled_messages: {str(e)}")
			template_doc = frappe.get_doc("WhatsApp Message Template", template.name)
			template_doc.status = "Failed"
			template_doc.save()


@frappe.whitelist()
def ws_handle_on_single_template_trigger(template_name, doctype):
	"""Handle single template trigger for all documents in a doctype."""
	try:
		if not template_name or not doctype:
			frappe.throw("Template and Doctype are required")

		documents = frappe.get_all(doctype, fields=["name"])

		if not documents:
			return

		template = frappe.get_doc("WhatsApp Message Template", template_name)
		if not template:
			return

		for doc in documents:
			doc_instance = frappe.get_doc(doctype, doc.name)
			parse_single_template_and_send_whatsapp_message(doc_instance, template)
	except Exception as e:
		frappe.log_error(f"Error in ws_handle_on_single_template_trigger: {str(e)}")

@frappe.whitelist()
def ws_handle_on_custom_trigger(template_name, doctype, docname):
	"""Handle custom trigger for a specific document."""
	try:
		if not template_name or not doctype or not docname:
			frappe.throw("Template, Doctype, and Docname are required")

		doc = frappe.get_doc(doctype, docname)
		template = frappe.get_doc("WhatsApp Message Template", template_name)
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
	"""Handles WhatsApp messaging events like Create, Update, Delete, etc."""
	try:
		if not doc or not event:
			return

		template_doctypes = get_template_doctypes()
		if doc.doctype not in template_doctypes:
			return

		templates = frappe.get_all("WhatsApp Message Template",
								   filters={"template_doctype": doc.doctype, "template_event": ['in', event], "is_single": 0},
								   fields=["name", "template_event", "template_target_field"])
		if not templates:
			return

		frappe.enqueue("whatsapp_messaging.controller.parse_templates_and_send_whatsapp_message", doc=doc, templates=templates)
	except Exception as e:
		frappe.log_error(f"Error in whatsapp_messaging_send_message_handler: {str(e)}")

@frappe.whitelist()
def parse_templates_and_send_whatsapp_message(doc, templates):
	"""Parse multiple templates and send WhatsApp messages."""
	try:
		for template in templates:
			if template.template_event == "Update Field":
				field_name = template.template_target_field
				field_value = doc.get(field_name)
				previous_value = doc.get_doc_before_save().get(field_name)
				if field_value == previous_value:
					continue

			full_template = frappe.get_doc("WhatsApp Message Template", template.name)
			parse_single_template_and_send_whatsapp_message(doc, full_template)
	except Exception as e:
		frappe.log_error(f"Error in parse_templates_and_send_whatsapp_message: {str(e)}")

def parse_single_template_and_send_whatsapp_message(doc, template):
	"""Parse a single template and send a WhatsApp message."""
	try:
		if not template or not doc:
			return

		message = fill_placeholders(template.text_template_text_message, doc, template.get("text_template_fields"))
		recipients = get_template_recipients(template, doc)
		template_type = "text"
		media_data = {}

		if template.media:
			media_doc = frappe.get_doc("WhatsApp Media", template.media)
			template_type, media_data = process_whatsapp_media(media_doc)

		payload = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"type": template_type,
		}

		if template_type == "text":
			payload["text"] = {"body": message}
		else:
			payload[template_type] = media_data[template_type]
			payload[template_type]["caption"] = message

		send_bulk_messages(recipients=recipients, payload=payload, media_doc_name=template.media)
	except Exception as e:
		frappe.log_error(f"Error in parse_single_template_and_send_whatsapp_message: {str(e)}")

def process_whatsapp_media(doc):
	'''This function is used to process the WhatsApp media
	#### Args:
		doc (doc): The WhatsApp Media document

  	Returns:
		list: A list containing the document type and media data
 	'''
	media_data = {}
	try:
		# Check if media type is URL or Upload
		if doc.media_type == "URL":
			# If the media type is URL, set the type and link
			document_type = doc.document_type
			media_data[document_type] = {
				"link": doc.media_url,
				"caption": doc.caption
			}
		elif doc.media_type == "Upload":
			# If the media type is Upload, get the media_id, content_type.
			document_type = mime_type_to_message_type(doc.content_type)
			media_data[document_type] = {
				"id": doc.media_id,
				"caption": doc.caption
			}

		return [document_type, media_data]

	except Exception as e:
		frappe.log_error(f"Error in process_whatsapp_media: {str(e)}")
		return ["text", media_data]

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

@frappe.whitelist()
def get_template_doctypes():
	cache_key = "template_doctypes_map"
	doctypes = frappe.cache().get_value(cache_key)

	if not doctypes:
		# Query to get distinct template_doctype values from Templates
		doctypes = frappe.db.get_all('WhatsApp Message Template', distinct=True, fields=['name', 'template_doctype', 'template_button_label'])

		# Create a map with the template_doctype values as keys and document names as values
		doctype_map = {}
		for d in doctypes:
			template_details = {'name': d.name, 'label': d.template_button_label}
			if doctype_map.get(d.template_doctype):
				doctype_map[d.template_doctype].append(template_details)
			else:
				doctype_map[d.template_doctype] = [template_details]

		# Cache the result
		frappe.cache().set_value(cache_key, doctype_map)
		return doctype_map
	return doctypes

def upload_media_to_whatsapp(media_file, doc):
	'''This function is used to upload media to WhatsApp'''
	doc.media_id = "Upload media..."
	doc.save()

	# Get file
	file_data = get_file(media_file)

 	# Get the headers and URL
	headers = get_headers( "multipart/form-data" )
	url = get_url("media")
	mime_type = mimetypes.guess_type(media_file)[0]

	# Set the media content type
	doc.content_type = mime_type
	doc.save()
	try:
		payload = {
			"file" : (file_data[0], file_data[1], mime_type),
			"messaging_product": "whatsapp",
			"type": mime_type
		}
		payload = MultipartEncoder(payload)
		headers["Content-Type"] = payload.content_type
		response = make_post_request(url, data=payload, headers=headers)

		# If media id is present, save it to the doc
		if response.get('id'):
			doc.media_id = response.get('id')
		else:
			doc.media_id = "Failed to upload media"
		doc.save()

	except Exception as e:
		frappe.log_error(f"Error in upload_media_to_whatsapp: {str(e)}")
		doc.media_id = "Failed to upload media"
		doc.save()




