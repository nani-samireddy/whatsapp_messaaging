import frappe
import json

# Internal imports
from whatsapp_messaging.utils.message_controller import send_bulk_messages, fill_placeholders
from whatsapp_messaging.utils import format_phone_number, get_template_doctypes
from whatsapp_messaging.utils.media_controller import process_whatsapp_media

def wm_handle_cron_messages(interval):
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
			frappe.log_error(f"Error in wm_handle_cron_messages: {str(e)}")


def wm_handle_scheduled_messages(template_doc_name):
	'''
	This function executes the scheduled messages.

	:param `template_doc_name`: str - The name of the template document.
	'''

	# Early return if the template_doc_name is not provided.
	if not template_doc_name:
		return

	# Get the template doc.
	template_doc = frappe.get_doc("WhatsApp Message Template", template_doc_name)

	# Early return if the template_doc is a scheduled type and the schedule_status is not "Pending" which means the scheduled job is stopped/completed.
	if template_doc.template_event == 'Scheduled' and template_doc.schedule_status != "Pending":
		return

	query_filters = json.loads(template_doc.query_filters).get("filters", []) if template_doc.query_filters else []

	# Get the documents based on the query filters.
	documents = frappe.get_all(template_doc.template_doctype, filters=query_filters, fields=["name"])

	# Iterate over the documents and send the messages.
	for doc in documents:
		doc_instance = frappe.get_doc(template_doc.template_doctype, doc.name)
		parse_single_template_and_send_whatsapp_message(doc_instance, template_doc)

	# If the template_event is `Scheduled` then, Update the schedule_job_type_link stopped to True to stop the scheduled job running again.
	if template_doc.template_event == "Scheduled":
		scheduled_job_type = frappe.get_doc("Scheduled Job Type", template_doc.schedule_job_type_link)
		scheduled_job_type.stopped = True
		scheduled_job_type.save()
		# Update the schedule_status of the template to "Sent"
		template_doc.schedule_status = "Completed"
		template_doc.save()

@frappe.whitelist()
def wm_handle_on_single_template_trigger(template_name, doctype):
	"""Handle single template trigger for all documents in a doctype."""
	try:
		if not template_name or not doctype:
			frappe.throw("Template and Doctype are required")

		if not documents:
			return

		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		if not template_doc:
			return

		query_filters = json.loads(template_doc.query_filters).get("filters", []) if template_doc.query_filters else []

		# Get the documents based on the query filters
		documents = frappe.get_all(doctype, filters=query_filters, fields=["name"])

		for doc in documents:
			doc_instance = frappe.get_doc(doctype, doc.name)
			parse_single_template_and_send_whatsapp_message(doc_instance, template_doc)
	except Exception as e:
		frappe.log_error(f"Error in wm_handle_on_single_template_trigger: {str(e)}")

@frappe.whitelist()
def wm_handle_on_custom_trigger(template_name, doctype, docname):
	"""Handle custom trigger for a specific document."""
	try:
		if not template_name or not doctype or not docname:
			frappe.throw("Template, Doctype, and Docname are required")

		doc = frappe.get_doc(doctype, docname)
		template = frappe.get_doc("WhatsApp Message Template", template_name)
		parse_single_template_and_send_whatsapp_message(doc, template)
	except Exception as e:
		frappe.log_error(f"Error in wm_handle_on_custom_trigger: {str(e)}")

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
		return []
