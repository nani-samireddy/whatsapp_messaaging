# Copyright (c) 2024, nani-samireddy and contributors
# For license information, please see license.txt

import frappe
from whatsapp_messaging.controller import send_whatsapp_message
from frappe.model.document import Document


class WhatsAppMessage(Document):
    def before_save(self):
        # Get the to and message
        to = self.to
        message = self.message
        try:
            # Send the message
            send_whatsapp_message(to, message)
            self.status = "Sent"
        except Exception as e:
            self.status = "Failed"
            frappe.throw("Failed to send the message.")
