import frappe
import json
import re
  
# Internal imports
from whatsapp_messaging.utils.message_controller import send_bulk_messages
from whatsapp_messaging.utils import format_phone_number, get_template_doctypes, doc_matches_filters
from whatsapp_messaging.utils.media_controller import process_whatsapp_media

def process_scheduled_messages(template_name):
	"""
	Process and finalize scheduled WhatsApp messages based on the template.

	:param template_name: The name of the WhatsApp Message Template.
	"""
	if not template_name:
		return

	template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
	process_template_query(template_doc)

	if template_doc.template_event == "Scheduled":
		# Stop the associated scheduled job and mark template as completed
		scheduled_job_type = frappe.get_doc("Scheduled Job Type", template_doc.schedule_job_type_link)
		scheduled_job_type.stopped = True
		scheduled_job_type.save()

		template_doc.schedule_status = "Completed"
		template_doc.save()

@frappe.whitelist()
def wm_handle_on_single_template_trigger(template_name, doctype):
	"""
	Trigger WhatsApp messages for all documents of a given doctype using a template.

	:param template_name: The name of the WhatsApp Message Template.
	:param doctype: The target doctype to apply the template to.
	"""
	try:
		if not template_name or not doctype:
			frappe.throw("Template and Doctype are required")

		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		process_template_query(template_doc, doctype)

	except Exception as e:
		frappe.log_error(f"Error in wm_handle_on_single_template_trigger: {str(e)}")

@frappe.whitelist()
def wm_handle_on_custom_trigger(template_name, doctype, docname):
	"""
	Trigger a WhatsApp message for a specific document using the given template.

	:param template_name: The name of the WhatsApp Message Template.
	:param doctype: The target doctype of the document.
	:param docname: The name of the specific document.
	"""
	try:
		if not template_name or not doctype or not docname:
			frappe.throw("Template, Doctype, and Docname are required")

		doc = frappe.get_doc(doctype, docname)
		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		process_template_and_send(doc, template_doc)

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
	'''Processes the query filters for a given template document and doctype.'''
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

		parsed_message = parse_message(template, doc)
		recipients = get_template_recipients(template=template, doc=doc)
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
			payload["text"] = {"body": parsed_message}
		else:
			payload[template_type] = media_data[template_type]
			payload[template_type]["caption"] = parsed_message

		send_bulk_messages(recipients=recipients, payload=payload, media_doc_name=template.media)

	except Exception as e:
		frappe.log_error(f"Error in process_template_and_send: {str(e)}")


def get_template_recipients(template, doc):
	"""
	Retrieves recipient phone numbers based on template settings and document values.

	:param template: WhatsApp Message Template document with phone_number_field_name
	                 and a MultiSelect Table field (other_recipients).
	:param doc: The target document from which dynamic fields are evaluated.
	:return: List of unique, formatted phone numbers as strings.
	"""
	recipients = []

	try:
		# Primary recipient from the document (dynamic field)
		if template.phone_number_field_name:
			primary_number = doc.get(template.phone_number_field_name)
			if primary_number:
				recipients.append(primary_number)

		# Static recipients from MultiSelect Table (child table rows)
		for row in template.get("other_recipients", []):
			phone_number = frappe.get_value( "Static Recipient", row, "phone_number" )
			if phone_number:
				recipients.append(phone_number)
		
		# Format and deduplicate phone numbers
		formatted = [format_phone_number(p) for p in recipients if p]
		frappe.log_error(f"Formatted recipients: {formatted}")
		return list(set(formatted))

	except Exception as e:
		frappe.log_error(f"Error in get_template_recipients: {str(e)}")
		return []


def parse_message(template, target):
    """Parses a WhatsApp message template using a document and a context target."""
    try:
        if not target or not template:
            return ""

        raw_message = frappe.get_value(
            "WhatsApp Message Template",
            template.name,
            "message_preview"
        )
        if not raw_message:
            return ""

        data_context = {
            "self": template,
            "template_doctype": target
        }

        # Fetch all Link-type fields from the template's doctype
        link_fields = frappe.get_all(
            "DocField",
            filters={"parent": template.doctype, "fieldtype": "Link"},
            fields=["fieldname", "options"]
        )

        # Exclude template_doctype to avoid circular processing
        link_fields = [
            field for field in link_fields
            if field["fieldname"] != "template_doctype"
        ]

        # Populate context with linked documents
        for link_field in link_fields:
            linked_value = getattr(template, link_field["fieldname"], None)
            if linked_value:
                try:
                    linked_doc = frappe.get_doc(link_field["options"], linked_value)
                    data_context[link_field["fieldname"]] = linked_doc
                except Exception as link_error:
                    frappe.log_error(
                        f"Error fetching linked doc for field {link_field['fieldname']}: {str(link_error)}"
                    )

        # Process placeholders using regex
        regex_pattern = r"\{\{(.*?)\}\}"
        processed_message = re.sub(
            regex_pattern,
            lambda match: process_placeholder(match, data_context),
            raw_message
        )

        return processed_message

    except Exception as e:
        frappe.log_error(f"Error in parse_message: {str(e)}")
        return ""

def process_placeholder(match, context):
    """Processes a single placeholder from the message template."""
    placeholder = match.group(1).strip()
    if not placeholder:
        return match.group(0)  # leave {{}} as-is

    doctype_part, field_name = placeholder.split(".", 1) if "." in placeholder else (None, placeholder)

    if doctype_part and doctype_part in context:
        return str(getattr(context[doctype_part], field_name, ""))
    elif field_name in context:
        return str(getattr(context[field_name], field_name, ""))
    else:
        return match.group(0)  # leave unchanged if not found
