# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe import _
from whatsapp_messaging.utils import datetime_to_cron_format, encode_to_alphanumeric

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
		self.invalidate_cache()
		if self.is_scheduled_event():
			self.handle_scheduled_job(update_existing=True)

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
