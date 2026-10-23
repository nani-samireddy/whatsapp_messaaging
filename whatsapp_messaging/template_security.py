"""Pure validation for local message templates; never accepts linked account objects."""

import json
import re


class TemplateSecurityError(ValueError):
	pass


SAFE_SOURCE_TYPES = frozenset({
	"Data", "Select", "Date", "Datetime", "Time", "Currency", "Int", "Float",
	"Check", "Text", "Small Text", "Long Text", "Phone", "Link",
})
SAFE_TEMPLATE_FIELDS = frozenset({"template_name", "template_button_label"})
SENSITIVE_FIELD = re.compile(r"(?:password|secret|token|api_key|private_key|encryption_key)", re.I)
PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
FIELD_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def is_recipient_phone_field(field):
	"""Frappe supports native Phone fields and Data fields with Options = Phone."""
	return bool(field and (
		field.fieldtype == "Phone"
		or (field.fieldtype == "Data" and (getattr(field, "options", None) or "").strip() == "Phone")
	))


def parse_allowed_fields(value):
	"""An administrator must explicitly approve each source field used in a template."""
	try:
		fields = json.loads(value) if isinstance(value, str) and value.strip() else value or []
	except (TypeError, ValueError) as exc:
		raise TemplateSecurityError("Allowed Source Fields must be a JSON list of field names") from exc
	if not isinstance(fields, list) or any(
		not isinstance(field, str) or not FIELD_NAME.fullmatch(field) or SENSITIVE_FIELD.search(field)
		for field in fields
	):
		raise TemplateSecurityError("Allowed Source Fields contains an invalid or sensitive field")
	return frozenset(fields)


def render_message(message, source_value, template_values, allowed_fields, static_value=None):
	"""Resolve only explicit source fields and a small set of template labels.

	Both source and static callbacks must enforce document and field permissions. The source callback is never
	passed a linked document path or a secret/account field.
	"""
	if not isinstance(message, str) or not message.strip():
		raise TemplateSecurityError("Message text is required")

	def replace(match):
		path = match.group(1).strip()
		parts = path.split(".")
		if len(parts) not in (2, 3) or not all(FIELD_NAME.fullmatch(part) for part in parts):
			raise TemplateSecurityError("Use an approved placeholder in the form {{template_doctype.field}}")
		section, fieldname = parts[0], parts[-1]
		if SENSITIVE_FIELD.search(fieldname):
			raise TemplateSecurityError("Sensitive fields cannot be used in messages")
		if len(parts) == 3 and section == "static" and static_value:
			value = static_value(parts[1], fieldname)
		elif len(parts) != 2:
			raise TemplateSecurityError("The message contains an invalid placeholder")
		elif section == "template_doctype" and fieldname in allowed_fields:
			value = source_value(fieldname)
		elif section == "self" and fieldname in SAFE_TEMPLATE_FIELDS:
			value = template_values.get(fieldname)
		else:
			raise TemplateSecurityError("The message contains a placeholder that is not approved")
		if value is None or value == "":
			raise TemplateSecurityError("A required placeholder value is missing")
		return str(value)

	rendered = PLACEHOLDER.sub(replace, message)
	if "{{" in rendered or "}}" in rendered:
		raise TemplateSecurityError("The message contains an unresolved placeholder")
	return rendered
