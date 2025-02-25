# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe

# Internal imports
from whatsapp_messaging.controller import upload_media_to_whatsapp




class WhatsAppMedia(Document):
    # Rename the document title with the file or url
	def autoname(self):
		if self.media_attachment:
			self.name = self.media_attachment
		else:
			self.name = self.media_url

	def on_update(self):
		# check if the media is updated
		if self.media_attachment:
			# Get the previous version of the document
			doc_before_save = self.get_doc_before_save()

			if hasattr(doc_before_save, 'media_attachment') and self.media_attachment != doc_before_save.media_attachment:
				frappe.enqueue(
					upload_media_to_whatsapp,
					queue='long',
					media_file=self.media_attachment,
					doc=self,
				)
