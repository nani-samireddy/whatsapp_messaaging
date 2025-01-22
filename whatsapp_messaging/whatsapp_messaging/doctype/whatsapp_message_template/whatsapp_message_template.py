# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe import _
from whatsapp_messaging.controller import upload_media_to_whatsapp



class WhatsAppMessageTemplate(Document):
	def before_save(self):
		self.invalidate_cache()

	def on_update(self):
		# check if the media is updated
		if self.media_attachment and self.media_attachment != self.get_doc_before_save().media_attachment:
			frappe.enqueue(
				upload_media_to_whatsapp,
				queue='long',
				media_file=self.media_attachment,
				doc=self,
			)


	def invalidate_cache(self):
		cache_key = "template_doctypes_map"
		frappe.cache().delete_value(cache_key)

	def after_save(self):
		self.invalidate_cache()
