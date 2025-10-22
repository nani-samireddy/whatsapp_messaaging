# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe

# Internal imports
from whatsapp_messaging.utils.media_controller import upload_media_to_whatsapp, upload_media_with_resumable_upload




class WhatsAppMedia(Document):
	# Rename the document title with the file or url
	def autoname(self):
		if self.media_attachment:
			self.name = self.media_attachment
		else:
			self.name = self.media_url

	def after_insert(self):
		if self.media_attachment:
			# Get file size to determine upload method
			from frappe.utils.file_manager import get_file
			try:
				file_data = get_file(self.media_attachment)
				file_size = len(file_data[1])  # file content length
				
				# Use resumable upload for files larger than 5MB (5 * 1024 * 1024 bytes)
				# or if you want to use resumable upload as default
				use_resumable_upload = file_size > (5 * 1024 * 1024) or True  # Set to True to always use resumable upload
				
				if use_resumable_upload:
					frappe.enqueue(
						upload_media_with_resumable_upload,
						queue="long",
						media_file=self.media_attachment,
						docname=self.name
					)
				else:
					frappe.enqueue(
						upload_media_to_whatsapp,
						queue="long",
						media_file=self.media_attachment,
						docname=self.name
					)
			except Exception as e:
				# Fallback to traditional upload if there's an error checking file size
				frappe.log_error(f"Error determining upload method, using traditional upload: {str(e)}")
				frappe.enqueue(
					upload_media_to_whatsapp,
					queue="long",
					media_file=self.media_attachment,
					docname=self.name
				)

	@frappe.whitelist()
	def upload_with_resumable(self):
		"""Manual method to trigger resumable upload"""
		if self.media_attachment:
			frappe.enqueue(
				upload_media_with_resumable_upload,
				queue="long",
				media_file=self.media_attachment,
				docname=self.name
			)
			frappe.msgprint("Resumable upload started in background")
		else:
			frappe.throw("No media file attached")

	@frappe.whitelist()
	def upload_with_traditional(self):
		"""Manual method to trigger traditional upload"""
		if self.media_attachment:
			frappe.enqueue(
				upload_media_to_whatsapp,
				queue="long",
				media_file=self.media_attachment,
				docname=self.name
			)
			frappe.msgprint("Traditional upload started in background")
		else:
			frappe.throw("No media file attached")

	# def on_update(self):
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
