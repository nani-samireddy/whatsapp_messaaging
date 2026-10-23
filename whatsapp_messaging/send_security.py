"""Server-side authorization shared by the existing manual send entry points."""

import frappe


SEND_ROLES = frozenset({"System Manager", "Whatsapp Admin", "Whatsapp Editor"})
BULK_ROLES = frozenset({"System Manager", "Whatsapp Admin"})


def require_outbound_enabled():
	if not frappe.db.get_single_value("WhatsApp Settings", "enable_outbound_messages", cache=False):
		frappe.throw("Outbound WhatsApp requests are disabled in WhatsApp Settings")


def require_send_role(bulk=False):
	roles = BULK_ROLES if bulk else SEND_ROLES
	if frappe.session.user == "Guest" or not roles.intersection(frappe.get_roles()):
		frappe.throw("You are not permitted to send WhatsApp messages", frappe.PermissionError)


@frappe.whitelist()
def get_messaging_access():
	"""UI capabilities for the current Frappe login; send APIs still enforce policy."""
	require_send_role()
	roles = set(frappe.get_roles())
	return {
		"can_read_history": True,
		"can_send": True,
		"can_bulk_send": bool(roles.intersection(BULK_ROLES)),
		"can_manage_credentials": "System Manager" in roles,
		"outbound_enabled": bool(frappe.db.get_single_value(
			"WhatsApp Settings", "enable_outbound_messages", cache=False,
		)),
	}


def check_template_policy(template, doctype, bulk=False):
	if template.disable:
		frappe.throw("This WhatsApp template is disabled")
	if template.template_doctype != doctype:
		frappe.throw("The source DocType does not match the WhatsApp template")
	if template.template_event not in (None, "", "None", "Custom"):
		frappe.throw("This template is not configured for manual sending")
	if bool(template.is_single) != bool(bulk):
		frappe.throw("Use the configured single-document or bulk sending action for this template")


def check_manual_template(template, doctype, bulk=False):
	require_send_role(bulk=bulk)
	template.check_permission("read")
	check_template_policy(template, doctype, bulk=bulk)
	# Existing app roles can read sender metadata. Passwords remain at the
	# System Manager-only permission level; no per-account login is introduced.
	frappe.get_doc("WhatsApp Phone Number ID", template.phone_number_id).check_permission("read")
	if not frappe.has_permission(doctype, "read"):
		frappe.throw("You cannot read the selected source DocType", frappe.PermissionError)
