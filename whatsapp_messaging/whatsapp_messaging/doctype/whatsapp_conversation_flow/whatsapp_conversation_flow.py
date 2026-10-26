import frappe
from frappe.model.document import Document
from whatsapp_messaging.messaging.flows import validate_flow


class WhatsAppConversationFlow(Document):
    def validate(self):
        validate_flow(self)

    def on_trash(self):
        if self.is_active:
            frappe.throw('Pause this flow before deleting it.')
