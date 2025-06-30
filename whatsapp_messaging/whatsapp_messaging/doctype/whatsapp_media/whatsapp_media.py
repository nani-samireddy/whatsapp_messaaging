# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe

# Internal imports
from whatsapp_messaging.utils.media_controller import upload_media_to_whatsapp




class WhatsAppMedia(Document):
	# Rename the document title with the file or url
	def autoname(self):
		if self.media_attachment:
			self.name = self.media_attachment
		else:
			self.name = self.media_url

	def after_insert(self):
		frappe.enqueue(
			upload_media_to_whatsapp,
			queue="long",
			media_file=self.media_attachment,
			doc=self
		)

	# def after_save(self):
	# 	"""
	# 	Triggers media upload to WhatsApp:
	# 	- For new documents
	# 	- When the media_attachment field is updated
	# 	"""
	# 	if not self.media_attachment or not self.phone_number_id:
	# 		return  # skip if essential fields are missing

	# 	doc_before_save = self.get_doc_before_save()

	# 	is_new = self.is_new()
	# 	frappe.log_error(f"WhatsApp Media Document {'created' if is_new else 'updated'}: {self.name}")
	# 	media_changed = (
	# 		doc_before_save and
	# 		getattr(doc_before_save, "media_attachment", None) != self.media_attachment
	# 	)

	# 	if is_new or media_changed:
	# 		frappe.log_error(f"{'New' if is_new else 'Updated'} WhatsApp Media uploaded: {self.media_attachment}")
	# 		frappe.enqueue(
	# 			upload_media_to_whatsapp,
	# 			queue="long",
	# 			media_file=self.media_attachment,
	# 			doc=self
	# 	 )
