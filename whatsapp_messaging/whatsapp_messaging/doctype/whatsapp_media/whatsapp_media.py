# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe

# Internal imports
from whatsapp_messaging.message_controller import upload_whatsapp_media



class WhatsAppMedia(Document):
    pass
	# def before_save(self):
	# 	file = self.get("wa_media_attachment")

	# 	if not file:
	# 		frappe.throw("Please attach a file")

	# 	self.media_id = upload_whatsapp_media(file)

