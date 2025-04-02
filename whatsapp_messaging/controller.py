import frappe
import json

# Internal imports
from whatsapp_messaging.utils.message_controller import send_bulk_messages, fill_placeholders
from whatsapp_messaging.utils import format_phone_number, get_template_doctypes, doc_matches_filters
from whatsapp_messaging.utils.media_controller import process_whatsapp_media

def process_scheduled_messages(template_name):
	"""Executes scheduled messages based on the given template."""
	if not template_name:
		return

	template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
	process_template_query(template_doc)

	if template_doc.template_event == "Scheduled":
		scheduled_job_type = frappe.get_doc("Scheduled Job Type", template_doc.schedule_job_type_link)
		scheduled_job_type.stopped = True
		scheduled_job_type.save()
		template_doc.schedule_status = "Completed"
		template_doc.save()

@frappe.whitelist()
def wm_handle_on_single_template_trigger(template_name, doctype):
	"""Handle single template trigger for all documents in a doctype."""
	try:
		if not template_name or not doctype:
			frappe.throw("Template and Doctype are required")

		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)

		process_template_query(template_doc)

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
		process_template_and_send(doc, template)
	except Exception as e:
		frappe.log_error(f"Error in wm_handle_on_custom_trigger: {str(e)}")

def handle_doc_events(doc, event=[]):
	"""Handles WhatsApp messaging events like Create, Update, Delete, etc."""
	try:
		if not doc or not event:
			return

		template_doctypes = get_template_doctypes()
		if doc.doctype not in template_doctypes:
			return

		templates = frappe.get_all("WhatsApp Message Template",
				filters={"template_doctype": doc.doctype, "template_event": ['in', event], "is_single": 0},
				fields=["name", "template_event", "template_target_field", "query_filters"])
		if not templates:
			return

		frappe.enqueue("whatsapp_messaging.controller.process_templates_and_send", doc=doc, templates=templates)
	except Exception as e:
		frappe.log_error(f"Error in handle_doc_events: {str(e)}")

def process_template_query(template_doc, doctype=None):
	'''
	Processes the query filters for a given template document and doctype.
	'''
	if template_doc.template_event == 'Scheduled' and template_doc.schedule_status != "Pending":
		return

	query_filters = json.loads(template_doc.query_filters).get("filters", []) if template_doc.query_filters else []
	target_doctype = doctype or template_doc.template_doctype

	documents = frappe.get_all(target_doctype, filters=query_filters, fields=["name"])

	for doc in documents:
		process_template_and_send(frappe.get_doc(target_doctype, doc.name), template_doc)

def process_templates_and_send(doc, templates):
	"""Processes multiple templates and sends WhatsApp messages."""
	try:
		for template in templates:
			# Skip if the doc does not satisfy the query filters for the template.
			if not doc_matches_filters(doc=doc, filters=template.query_filters):
				continue
			if template.template_event == "Update Field":
				field_name = template.template_target_field
				# Skip if the field value has not changed.
				if doc.get(field_name) == doc.get_doc_before_save().get(field_name):
					continue

			process_template_and_send(doc, frappe.get_doc("WhatsApp Message Template", template.name))

	except Exception as e:
		frappe.log_error(f"Error in process_templates_and_send: {str(e)}")


def process_template_and_send(doc, template):
	"""Processes a single template and sends a WhatsApp message."""
	try:
		if not template or not doc:
			return

		message = fill_placeholders(template.text_template_text_message, doc, template.get("text_template_fields"))
		recipients = get_template_recipients(template, doc)
		template_type, media_data = "text", {}

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
		frappe.log_error(f"Error in process_template_and_send: {str(e)}")


def get_template_recipients(template, doc):
	"""Retrieves recipients from a template and document."""
	recipients = []
	try:
		if template.recipient_type in ["Field", "Field+Group"] and template.phone_number_field_name:
			recipients.append(doc.get(template.phone_number_field_name))

		if template.recipient_type in ["Group", "Field+Group"] and template.template_static_recipients:
			recipients.extend([recipient.phone_number for recipient in template.template_static_recipients])

		return list(set(format_phone_number(phone) for phone in recipients))
	except Exception as e:
		frappe.log_error(f"Error in get_template_recipients: {str(e)}")
		return []
