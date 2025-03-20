# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe import _
from whatsapp_messaging.controller import upload_media_to_whatsapp
from whatsapp_messaging.utils import datetime_to_cron_format, encode_to_alphanumeric

class WhatsAppMessageTemplate(Document):

    def before_insert(self):
        self.handle_scheduled_job_creation()

    def validate(self):
        self.invalidate_cache()
        self.handle_scheduled_job_creation(update_existing=True)

    def handle_scheduled_job_creation(self, update_existing=False):
        '''
        Handles creation and updating of Scheduled Job Type.
        '''
        if self.template_event == "Scheduled":
            if not self.schedule_job_type_link:
                cron_format = datetime_to_cron_format(self.schedule)

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
                frappe.log_error(f"Created Scheduled Job Type: {self.schedule_job_type_link}")
            elif update_existing and self.has_value_changed("schedule"):
                cron_format = datetime_to_cron_format(self.schedule)
                scheduled_job_type = frappe.get_doc("Scheduled Job Type", self.schedule_job_type_link)
                scheduled_job_type.cron_format = cron_format
                scheduled_job_type.stopped = False
                scheduled_job_type.save()
                frappe.log_error(f"Updated Scheduled Job Type: {self.schedule_job_type_link}")

    def invalidate_cache(self):
        cache_key = "template_doctypes_map"
        frappe.cache().delete_value(cache_key)

    def after_save(self):
        self.invalidate_cache()
