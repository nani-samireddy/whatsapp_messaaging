import frappe
from whatsapp_messaging.messaging.field_policy import get_allowed_source_fields, static_value
import json
  
# Internal imports
from whatsapp_messaging.utils.message_controller import send_bulk_messages
from whatsapp_messaging.utils import format_phone_number, doc_matches_filters
from whatsapp_messaging.utils.config import get_cloud_api_url, get_headers
from whatsapp_messaging.send_security import check_manual_template, require_outbound_enabled, require_send_role
from whatsapp_messaging.template_security import (
	SAFE_SOURCE_TYPES, SENSITIVE_FIELD, TemplateSecurityError, parse_allowed_fields, render_message,
)

def process_scheduled_messages(template_name):
    """Compatibility entry: old dynamic jobs cannot send or create new runs."""
    return {"retired": True}

@frappe.whitelist(methods=["POST"])
def wm_handle_on_single_template_trigger(template_name, doctype):
	"""
	Trigger WhatsApp messages for all documents of a given doctype using a template.

	:param template_name: The name of the WhatsApp Message Template.
	:param doctype: The target doctype to apply the template to.
	"""
	require_send_role(bulk=True)
	if not template_name or not doctype:
		frappe.throw("Template and Doctype are required")
	from whatsapp_messaging.messaging.campaigns import load
	template_doc = load(template_name)
	check_manual_template(template_doc, doctype, bulk=True)
	return process_template_query(template_doc, doctype, permission_checked=True)

@frappe.whitelist(methods=["POST"])
def wm_handle_on_custom_trigger(template_name, doctype, docname, request_id=None):
	"""
	Trigger a WhatsApp message for a specific document using the given template.

	:param template_name: The name of the WhatsApp Message Template.
	:param doctype: The target doctype of the document.
	:param docname: The name of the specific document.
	"""
	require_send_role()
	if not template_name or not doctype or not docname:
		frappe.throw("Template, Doctype, and Docname are required")
	from whatsapp_messaging.messaging.campaigns import load
	template_doc = load(template_name)
	check_manual_template(template_doc, doctype)
	doc = frappe.get_doc(doctype, docname)
	doc.check_permission("read")
	if not doc_matches_filters(doc, template_doc.query_filters):
		frappe.throw("This document does not match the template filters")
	return process_template_and_send(doc, template_doc, raise_on_error=True, request_id=request_id)

def handle_doc_events(doc, event=[]):
    from whatsapp_messaging.messaging.automation import event_rules
    return event_rules(doc, event)

def process_template_query(template_doc, doctype=None, permission_checked=False):
    """Legacy bulk buttons now create a preview; an explicit start is required."""
    if template_doc.disable:
        return
    from whatsapp_messaging.messaging.automation import preview_campaign
    return preview_campaign(template_doc.name)

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
				previous_doc = doc.get_doc_before_save()
				if previous_doc is None or doc.get(field_name) == previous_doc.get(field_name):
					continue

			process_template_and_send(doc, frappe.get_doc("WhatsApp Message Template", template.name))

	except Exception as e:
		frappe.log_error(f"Error in process_templates_and_send: {str(e)}")


def process_template_and_send(doc, template, raise_on_error=False, request_id=None):
    """Manual compatibility route using the canonical transactional outbox."""
    if not template or not doc or template.disable:
        return
    require_outbound_enabled()
    from whatsapp_messaging.messaging.automation import emit
    from whatsapp_messaging.messaging.common import digest, insert, utcnow
    if not request_id:
        frappe.throw("A stable request identifier is required")
    key = digest("manual", frappe.session.user, template.name, doc.doctype, doc.name, request_id)
    existing = frappe.db.get_value("WhatsApp Automation Run", {"run_key": key}, "name")
    run = frappe.get_doc("WhatsApp Automation Run", existing) if existing else insert("WhatsApp Automation Run", run_key=key, rule=template.name,
        kind="Manual", state="Completed", run_as=frappe.session.user, due_at=utcnow(), records_selected=1, records_processed=1)
    count = emit(template, doc, run)
    frappe.db.set_value(run.doctype, run.name, "messages_created", count)
    return {"run": run.name, "queued": count}

def get_template_recipients(template, doc):
    import re
    from whatsapp_messaging.template_security import SENSITIVE_FIELD, is_recipient_phone_field
    recipients = []
    if template.phone_number_field_name:
        field = doc.meta.get_field(template.phone_number_field_name)
        if not is_recipient_phone_field(field) or field.hidden or SENSITIVE_FIELD.search(field.fieldname) or not doc.has_permlevel_access_to(field.fieldname, df=field, permission_type="read"):
            frappe.throw("Choose a readable Phone field for recipients", frappe.PermissionError)
        value = doc.get(field.fieldname)
        if value:
            recipients.append(value)
    for row in template.get("other_recipients") or []:
        recipient = frappe.get_doc("Static Recipient", row.static_recipient)
        recipient.check_permission("read")
        if recipient.phone_number:
            recipients.append(recipient.phone_number)
    result = []
    for value in recipients:
        number = re.sub(r"[\s()+-]", "", str(value))
        if not re.fullmatch(r"[1-9][0-9]{6,14}", number):
            frappe.throw("A recipient must have a valid international phone number")
        if number not in result:
            result.append(number)
    return result


def parse_message(template, target):
	"""Render approved business fields without loading linked account documents."""
	target.check_permission("read")
	allowed = get_allowed_source_fields(template.template_doctype)

	def source_value(fieldname):
		field = target.meta.get_field(fieldname)
		if (
			not field
			or field.fieldtype not in SAFE_SOURCE_TYPES
			or field.hidden
			or field.print_hide
			or SENSITIVE_FIELD.search(fieldname)
			or not target.has_permlevel_access_to(fieldname, df=field, permission_type="read")
		):
			raise TemplateSecurityError("The message references a field that is not readable or approved")
		return target.get(fieldname)

	return render_message(
		template.message_preview,
		source_value,
		{key: template.get(key) for key in ("template_name", "template_button_label")},
		allowed,
		static_value=static_value,
	)
