import frappe
import json
import re
  
# Internal imports
from whatsapp_messaging.utils.message_controller import send_bulk_messages
from whatsapp_messaging.utils import format_phone_number, get_template_doctypes, doc_matches_filters, get_language_code
from whatsapp_messaging.utils.media_controller import process_whatsapp_media
from whatsapp_messaging.utils.config import get_cloud_api_url, get_headers

# Setup logger
logger = frappe.logger("whatsapp_messaging", allow_site=True, file_count=50)


def extract_template_parameters(template, doc):
	"""
	Extract parameter values for WhatsApp template message.
	Converts {{template_doctype.field}} to ordered parameter values.
	
	Args:
		template: WhatsApp Message Template document
		doc: The document to extract values from
		
	Returns:
		list: Array of parameter objects for WhatsApp API
	"""
	parameters = []
	
	try:
		raw_message = frappe.get_value(
			"WhatsApp Message Template",
			template.name,
			"message_preview"
		)
		
		if not raw_message:
			return parameters
		
		# Find all {{placeholder}} patterns
		regex_pattern = r'\{\{(.*?)\}\}'
		placeholders = re.findall(regex_pattern, raw_message)
		
		# Build context for evaluation
		data_context = {
			"self": template,
			"template_doctype": doc
		}
		
		# Fetch linked documents
		link_fields = frappe.get_all(
			"DocField",
			filters={"parent": template.doctype, "fieldtype": "Link"},
			fields=["fieldname", "options"]
		)
		
		link_fields = [f for f in link_fields if f["fieldname"] != "template_doctype"]
		
		for link_field in link_fields:
			linked_value = getattr(template, link_field["fieldname"], None)
			if linked_value:
				try:
					linked_doc = frappe.get_doc(link_field["options"], linked_value)
					data_context[link_field["fieldname"]] = linked_doc
				except Exception:
					pass
		
		# Extract parameter values in order
		for placeholder in placeholders:
			placeholder = placeholder.strip()
			if not placeholder:
				continue
			
			# Parse placeholder (e.g., "template_doctype.customer_name")
			parts = placeholder.split(".", 1)
			doctype_part = parts[0] if len(parts) > 1 else None
			field_name = parts[1] if len(parts) > 1 else parts[0]
			
			value = ""
			if doctype_part and doctype_part in data_context:
				value = str(getattr(data_context[doctype_part], field_name, ""))
			elif field_name in data_context:
				value = str(getattr(data_context[field_name], field_name, ""))
			
			parameters.append({
				"type": "text",
				"text": value
			})
		
		return parameters
		
	except Exception as e:
		logger.error("Error extracting template parameters", exc_info=True)
		return []

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
		# Restrict to allowed roles
		frappe.only_for(("System Manager", "Whatsapp Admin", "Whatsapp Editor"))
		if not template_name or not doctype:
			frappe.throw("Template and Doctype are required")

		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		process_template_query(template_doc, doctype)

	except Exception as e:
		logger.error("Error in wm_handle_on_single_template_trigger: template=%s, doctype=%s", template_name, doctype, exc_info=True)

@frappe.whitelist()
def wm_handle_on_custom_trigger(template_name, doctype, docname):
	"""
	Trigger a WhatsApp message for a specific document using the given template.

	:param template_name: The name of the WhatsApp Message Template.
	:param doctype: The target doctype of the document.
	:param docname: The name of the specific document.
	"""
	try:
		# Restrict to allowed roles
		frappe.only_for(("System Manager", "Whatsapp Admin", "Whatsapp Editor"))
		if not template_name or not doctype or not docname:
			frappe.throw("Template, Doctype, and Docname are required")

		doc = frappe.get_doc(doctype, docname)
		template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
		process_template_and_send(doc, template_doc)

	except Exception as e:
		logger.error("Error in wm_handle_on_custom_trigger: template=%s, doctype=%s, docname=%s", template_name, doctype, docname, exc_info=True)

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
		logger.error("Error in handle_doc_events: doctype=%s", doc.doctype if doc else None, exc_info=True)

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
				# Skip if the field value has not changed or before-save doc missing
				before_fn = getattr(doc, "get_doc_before_save", None)
				before_doc = before_fn() if callable(before_fn) else None
				if not before_doc:
					continue
				if doc.get(field_name) == before_doc.get(field_name):
					continue

			process_template_and_send(doc, frappe.get_doc("WhatsApp Message Template", template.name))

	except Exception as e:
		logger.error("Error in process_templates_and_send: doctype=%s", doc.doctype if doc else None, exc_info=True)


def process_template_and_send(doc, template):
	"""
	Processes a single template and sends a WhatsApp message.
	Checks if template is approved and sends as template message if available.
	"""
	try:
		if not template or not doc:
			return

		recipients = get_template_recipients(template=template, doc=doc)
		
		if not recipients:
			logger.warning("No recipients found for template: %s", template.name)
			return
		
		# Check if template is synced with WhatsApp and approved
		if (template.get("sync_with_whatsapp") and 
			template.get("whatsapp_template_id") and 
			template.get("status") == "APPROVED"):
			
			# Send as WhatsApp Template Message (works outside 24hr window)
			send_as_whatsapp_template(doc, template, recipients)
		else:
			logger.info("Template not approved or sync disabled, sending as session message: %s", template.name)
			# Send as regular session message (only within 24hr window)
			send_as_session_message(doc, template, recipients)

	except Exception as e:
		logger.error("Error in process_template_and_send: template=%s, doctype=%s", template.name if template else None, doc.doctype if doc else None, exc_info=True)


def send_as_whatsapp_template(doc, template, recipients):
	"""
	Send message using approved WhatsApp template format.
	This format works outside the 24-hour customer service window.
	
	Args:
		doc: The document being processed
		template: WhatsApp Message Template document
		recipients: List of recipient phone numbers
	"""
	try:
		# Extract parameter values from the document
		parameters = extract_template_parameters(template, doc)
		
		# Build WhatsApp template message payload
		template_name = template.template_name.lower().replace(" ", "_")
		
		payload = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"type": "template",
			"template": {
				"name": template_name,
				"language": {
					"code": get_language_code(template.get("whatsapp_template_language", "English"))
				}
			}
		}
		
		# Add components array if parameters exist
		components = []
		
		# Add body component with parameters
		if parameters:
			components.append({
				"type": "body",
				"parameters": parameters
			})
		
		# Add header component for media if present
		if template.media:
			media_doc = frappe.get_doc("WhatsApp Media", template.media)
			
			# Determine media type from content_type
			content_type = media_doc.content_type or ""
			if content_type.startswith('image/'):
				media_type = "image"
			elif content_type.startswith('video/'):
				media_type = "video"
			elif content_type.startswith('application/'):
				media_type = "document"
			else:
				media_type = "document"  # Default fallback
			
			if media_type != "text":
				header_param = {
					"type": media_type
				}
				
				# Use media_id for template messages
				if media_doc.media_id:
					header_param[media_type] = {
						"id": media_doc.media_id
					}
				else:
					logger.warning("Media document %s has no media_id", media_doc.name)
					# Skip adding header component if no valid media reference
					media_type = None
				
				if media_type:
					components.insert(0, {
						"type": "header",
						"parameters": [header_param]
					})
		
		# Add components to payload
		if components:
			payload["template"]["components"] = components
		
		# Get API credentials
		url = get_cloud_api_url(phone_number_id=template.phone_number_id)
		headers = get_headers(phone_number_id=template.phone_number_id)
		
		if not url:
			frappe.throw("Failed to get WhatsApp API URL")
			return
		
		# Send to all recipients
		send_bulk_messages(
			recipients=recipients, 
			payload=payload, 
			media_doc_name=template.media, 
			headers=headers, 
			url=url
		)
		
		frappe.msgprint(f"Sent as approved template message to {len(recipients)} recipient(s)")
		
	except Exception as e:
		logger.error("Error sending WhatsApp template message: template=%s", template.name if template else None, exc_info=True)
		frappe.throw(f"Failed to send template message: {str(e)}")


def send_as_session_message(doc, template, recipients):
	"""
	Send message as regular session message (only works within 24hr window).
	Falls back to this if template is not approved or sync is disabled.
	
	Args:
		doc: The document being processed
		template: WhatsApp Message Template document
		recipients: List of recipient phone numbers
	"""
	try:
		# Show warning if template exists but not approved
		if template.get("whatsapp_template_id"):
			status = template.get("status", "UNKNOWN")
			if status != "APPROVED":
				frappe.msgprint(
					f"Warning: Template status is '{status}'. Sending as session message (only works within 24hr window).",
					indicator="orange"
				)
		
		# Parse message with placeholders
		parsed_message = parse_message(template, doc)
		template_type, media_data = "text", {}

		if template.media:
			media_doc = frappe.get_doc("WhatsApp Media", template.media)
			template_type, media_data = process_whatsapp_media(media_doc)

		# Build regular message payload
		payload = {
			"messaging_product": "whatsapp",
			"recipient_type": "individual",
			"type": template_type,
		}

		if template_type == "text" or not media_data.get(template_type):
			# Fallback to text if media unavailable
			payload["type"] = "text"
			payload["text"] = {"body": parsed_message}
		else:
			payload[template_type] = media_data[template_type]
			# Only add caption for supported types
			if template_type in ("image", "video", "document"):
				payload[template_type]["caption"] = parsed_message
	
		url = get_cloud_api_url(phone_number_id=template.phone_number_id)
		headers = get_headers(phone_number_id=template.phone_number_id)
		
		if not url:
			frappe.throw("Failed to get WhatsApp API URL")
			return
		
		send_bulk_messages(
			recipients=recipients, 
			payload=payload, 
			media_doc_name=template.media, 
			headers=headers, 
			url=url
		)
		
		frappe.msgprint(f"Sent as session message to {len(recipients)} recipient(s)")

	except Exception as e:
		logger.error("Error sending session message: template=%s", template.name if template else None, exc_info=True)
		frappe.throw(f"Failed to send message: {str(e)}")



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

		# Static recipients from Table MultiSelect (child table rows)
		for row in template.get("other_recipients", []) or []:
			# Field `static_recipient` links to "Static Recipient"
			recipient_name = getattr(row, "static_recipient", None)
			if recipient_name:
				phone_number = frappe.get_value("Static Recipient", recipient_name, "phone_number")
				if phone_number:
					recipients.append(phone_number)
		
		# Format and deduplicate phone numbers
		formatted = [format_phone_number(p) for p in recipients if p]
		logger.debug("Formatted recipients: %s", formatted)
		return list(set(formatted))

	except Exception as e:
		logger.error("Error in get_template_recipients: template=%s", template.name if template else None, exc_info=True)
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
                    logger.error("Error fetching linked doc for field %s: %s", link_field['fieldname'], str(link_error), exc_info=True)

        # Process placeholders using regex
        regex_pattern = r"\{\{(.*?)\}\}"
        processed_message = re.sub(
            regex_pattern,
            lambda match: process_placeholder(match, data_context),
            raw_message
        )

        return processed_message

    except Exception as e:
        logger.error("Error in parse_message", exc_info=True)
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
