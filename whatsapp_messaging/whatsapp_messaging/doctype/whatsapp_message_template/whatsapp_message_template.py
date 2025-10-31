# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe import _
from frappe.model.meta import get_meta
from frappe.utils.data import cstr
from frappe.utils.formatters import format_value
from whatsapp_messaging.utils import datetime_to_cron_format, encode_to_alphanumeric
import json
import re

# Setup logger
logger = frappe.logger("whatsapp_messaging", allow_site=True, file_count=50)

class WhatsAppMessageTemplate(Document):

	cron_interval_formats = {
		'Hourly': '0 * * * *',
		'Daily': '0 0 * * *',
		'Weekly': '0 0 * * 0',
		'Monthly': '0 0 1 * *',
		'Yearly': '0 0 1 1 *',
	}

	def before_insert(self):
		if self.is_scheduled_event():
			self.handle_scheduled_job()

	def validate(self):
		"""Validate template edit permissions based on status."""
		self.invalidate_cache()
		self.validate_character_limits()
		self._update_example_preview()
		
		# Check if template is editable based on status
		if self.whatsapp_template_id and self.status:
			non_editable_statuses = ["IN_REVIEW", "PENDING"]
			template_content_fields = ["template_header", "message_preview", "template_footer", "media", "whatsapp_template_category", "whatsapp_template_language"]
			
			if self.status in non_editable_statuses:
				# Check if any content fields changed
				content_changed = any(self.has_value_changed(field) for field in template_content_fields)
				if content_changed:
					frappe.throw(
						_("Template content cannot be modified while status is '{0}'. "
						  "Please wait for approval or rejection before making changes.").format(self.status),
						title=_("Template Edit Restricted")
					)
		
		if self.is_scheduled_event():
			self.handle_scheduled_job(update_existing=True)

	def onload(self):
		"""Check template status before loading form."""
		if self.whatsapp_template_id:
			# Check if status needs updating (every 5 minutes)
			if not self.last_synced or frappe.utils.time_diff_in_seconds(frappe.utils.now(), self.last_synced) > 300:
				try:
					from whatsapp_messaging.utils.whatsapp_template_api import get_template_status
					status_result = get_template_status(self.name)
					if status_result.get("success"):
						# Status will be updated by the get_template_status function
						self.reload()
				except Exception as e:
					logger.error(f"Error auto-checking template status: {str(e)}", exc_info=True)

	def after_insert(self):
		"""Do not auto create on insert; remain in DRAFT until user requests review."""
		if not self.status:
			self.status = "DRAFT"
			self.save()

	def on_update(self):
		"""Check if template needs to be synced with WhatsApp."""
		
		# Fields that require template update in WhatsApp when changed
		template_content_fields = [
			"template_header",
			"message_preview", 
			"template_footer",
			"media", 
			"whatsapp_template_category", 
			"whatsapp_template_language"
		]
		
		# Disable auto sync behavior; only manage scheduled job and validations
		pass

	def on_trash(self):
		"""Delete template from WhatsApp Cloud API when document is deleted."""
		if self.whatsapp_template_id:
			try:
				from whatsapp_messaging.utils.whatsapp_template_api import delete_whatsapp_template
				result = delete_whatsapp_template(self.name)
				if result.get("success"):
					frappe.msgprint(
						_("Template successfully deleted from WhatsApp Cloud API"),
						title=_("WhatsApp Sync"),
						indicator="green"
					)
				else:
					logger.error(f"Failed to delete WhatsApp template on trash: {result.get('message')}")
			except Exception as e:
				logger.error(f"Error deleting WhatsApp template on trash: {str(e)}", exc_info=True)

	def is_scheduled_event(self):
		'''
		Returns True if the template event is Scheduled or Cron.
		'''
		return self.template_event in ["Scheduled", "Cron"]

	def get_cron_interval(self):
		'''
		Returns the cron interval for the given template event.
		'''
		if self.template_event == "Cron":
			if not self.cron_interval:
				frappe.throw(_("Cron Interval is required for Cron Event"))
			return self.cron_interval_formats.get(self.cron_interval) if not self.cron_interval == "Custom cron format" else self.custom_cron_format
		else:
			return datetime_to_cron_format(self.schedule)

	def handle_scheduled_job(self, update_existing=False):
		'''
		Handles creation and updating of Scheduled Job Type.
		'''
		# If the template_event is cron set the status to pending.
		if self.template_event == "Cron":
			self.status = "Pending"

		cron_format = self.get_cron_interval()
		if not self.schedule_job_type_link:
			# @NOTE: We are encoding the template name to alphanumeric to avoid any issues with the function name as Template names can have spaces and special characters.
			encoded_template_name = encode_to_alphanumeric(self.name)
			scheduled_job_type = frappe.get_doc({
				"doctype": "Scheduled Job Type",
				"method": f"whatsapp_messaging.tasks.scheduler.scheduled_message_handler_{encoded_template_name}",
				"frequency": "Cron",
				"cron_format": cron_format,
			})
			scheduled_job_type.insert()
			self.schedule_job_type_link = scheduled_job_type.name
		elif update_existing:
			scheduled_job_type = frappe.get_doc("Scheduled Job Type", self.schedule_job_type_link)
			# Update the cron format only if it is changed.
			if scheduled_job_type.cron_format != cron_format:
				scheduled_job_type.cron_format = cron_format
				scheduled_job_type.stopped = False
				scheduled_job_type.save()

	def invalidate_cache(self):
		cache_key = "template_doctypes_map"
		frappe.cache().delete_value(cache_key)

	def after_save(self):
		self.invalidate_cache()

	def validate_character_limits(self):
		"""Validate WhatsApp template character limits."""
		
		# Header limit: 60 characters
		if self.template_header and len(self.template_header) > 60:
			frappe.throw(
				_("Template header cannot exceed 60 characters. Current length: {0}").format(len(self.template_header)),
				title=_("Header Too Long")
			)
		
		# Body limit: 1024 characters
		if self.message_preview and len(self.message_preview) > 1024:
			frappe.throw(
				_("Template body cannot exceed 1024 characters. Current length: {0}").format(len(self.message_preview)),
				title=_("Body Too Long")
			)
		
		# Footer limit: 60 characters
		if self.template_footer and len(self.template_footer) > 60:
			frappe.throw(
				_("Template footer cannot exceed 60 characters. Current length: {0}").format(len(self.template_footer)),
				title=_("Footer Too Long")
			)

	@frappe.whitelist()
	def generate_example_preview(self):
		"""Generate example preview text using the first record that matches the template filters."""
		result = _build_template_example(self)
		self.example = result.get("example", "")
		return result

	def _update_example_preview(self):
		"""Refresh example preview from server-side when saving."""
		result = _build_template_example(self)
		self.example = result.get("example", "")
		if result.get("message") and not result.get("success"):
			frappe.msgprint(_("Example preview not generated: {0}").format(result.get("message")))


def _build_template_example(template_doc):
	"""Create an example preview by substituting placeholders with data from the first matching record."""
	if not template_doc.template_doctype:
		return {"success": False, "message": _("Select a Template DocType to build an example."), "example": ""}

	filters = _parse_query_filters(template_doc.query_filters)

	try:
		first_record = _get_first_matching_doc(template_doc.template_doctype, filters)
	except Exception as exc:
		logger.error("Error fetching sample record for template %s: %s", template_doc.name, exc, exc_info=True)
		return {"success": False, "message": _(str(exc)), "example": ""}

	if not first_record:
		return {"success": False, "message": _("No records found for the selected DocType/filters."), "example": ""}

	combined_preview = _combine_template_segments(template_doc, first_record)
	return {
		"success": True,
		"example": combined_preview,
		"record_name": first_record.name
	}


def _parse_query_filters(raw_filters):
	if not raw_filters:
		return []

	try:
		payload = json.loads(raw_filters)
	except (TypeError, json.JSONDecodeError):
		logger.warning("Invalid query_filters payload: %s", raw_filters)
		return []

	filters = payload.get("filters") if isinstance(payload, dict) else payload
	if not isinstance(filters, list):
		return []

	parsed = []
	for flt in filters:
		if isinstance(flt, (list, tuple)):
			if len(flt) >= 4:
				parsed.append([flt[0], flt[1], flt[2], flt[3]])
			elif len(flt) == 3:
				parsed.append([flt[0], flt[1], flt[2]])
		elif isinstance(flt, dict):
			fieldname = flt.get("fieldname") or flt.get("field")
			if not fieldname:
				continue
			operator = flt.get("operator") or flt.get("condition") or "="
			value = flt.get("value")
			doctype = flt.get("doctype")
			if doctype:
				parsed.append([doctype, fieldname, operator, value])
			else:
				parsed.append([fieldname, operator, value])

	return parsed


def _get_first_matching_doc(doctype, filters):
	records = frappe.get_list(
		doctype,
		filters=filters or None,
		fields=["name"],
		order_by="creation asc",
		limit_page_length=1
	)
	if not records:
		return None
	return frappe.get_doc(doctype, records[0].name)


def _combine_template_segments(template_doc, source_doc):
	segments = []
	cache = {}

	for content in (template_doc.template_header, template_doc.message_preview, template_doc.template_footer):
		replaced = _substitute_placeholders(content, source_doc, template_doc.template_doctype, cache)
		if replaced:
			replaced_text = replaced.strip()
			if replaced_text:
				segments.append(replaced_text)

	return "\n\n".join(segments)


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _substitute_placeholders(text, doc, doctype, cache):
	if not text:
		return ""

	def replacer(match):
		expression = match.group(1).strip()
		value, fieldmeta = _resolve_expression(doc, doctype, expression, cache)
		if value is None:
			return ""
		if fieldmeta:
			try:
				return cstr(format_value(value, fieldmeta))
			except Exception:
				return cstr(value)
		return cstr(value)

	return PLACEHOLDER_PATTERN.sub(replacer, text)


def _resolve_expression(doc, doctype, expression, cache):
	parts = expression.split('.') if expression else []
	if not parts:
		return None, None

	if parts[0] in {"self", "doc", "template_doctype", doctype}:
		parts = parts[1:] or []

	return _traverse_document(doc, doctype, parts, cache)


def _traverse_document(current_doc, current_doctype, parts, cache):
	if not parts:
		return None, None

	fieldname = parts[0]
	remaining = parts[1:]
	meta = get_meta(current_doctype)
	fieldmeta = meta.get_field(fieldname) if meta else None
	value = current_doc.get(fieldname)

	if not remaining:
		return value, fieldmeta

	if not fieldmeta:
		return None, None

	if fieldmeta.fieldtype in ("Link", "Dynamic Link"):
		linked_doctype = fieldmeta.options if fieldmeta.fieldtype == "Link" else current_doc.get(fieldmeta.options)
		if not linked_doctype or not value:
			return None, None
		linked_doc = _get_cached_doc(linked_doctype, value, cache)
		if not linked_doc:
			return None, None
		return _traverse_document(linked_doc, linked_doctype, remaining, cache)

	if fieldmeta.fieldtype == "Table":
		if not value:
			return None, None
		first_row = value[0] if isinstance(value, (list, tuple)) else None
		if not first_row:
			return None, None
		child_doc = first_row
		child_doctype = getattr(first_row, "doctype", fieldmeta.options)
		if isinstance(child_doc, dict):
			child_doc = frappe._dict(child_doc)
		return _traverse_document(child_doc, child_doctype, remaining, cache)

	return None, None


def _get_cached_doc(doctype, name, cache):
	key = f"{doctype}::{name}"
	if key in cache:
		return cache[key]
	try:
		doc = frappe.get_doc(doctype, name)
		cache[key] = doc
		return doc
	except Exception:
		cache[key] = None
		return None


def get_placeholder_example_values(template_doc, placeholders):
	"""Return ordered example values for provided placeholders using the first matching record."""
	if not placeholders:
		return []

	if not template_doc.template_doctype:
		return []

	filters = _parse_query_filters(template_doc.query_filters)

	try:
		sample_doc = _get_first_matching_doc(template_doc.template_doctype, filters)
	except Exception as exc:
		logger.error("Error retrieving sample document for placeholder values: %s", exc, exc_info=True)
		return []

	if not sample_doc:
		return []

	values = []
	cache = {}

	for placeholder in placeholders:
		expression = (placeholder or "").strip()
		if not expression:
			values.append("")
			continue

		value, fieldmeta = _resolve_expression(sample_doc, template_doc.template_doctype, expression, cache)
		if value is None:
			values.append("")
			continue

		if fieldmeta:
			try:
				formatted_value = format_value(value, fieldmeta, doc=sample_doc)
			except Exception:
				formatted_value = cstr(value)
		else:
			formatted_value = cstr(value)

		values.append(formatted_value)

	return values
