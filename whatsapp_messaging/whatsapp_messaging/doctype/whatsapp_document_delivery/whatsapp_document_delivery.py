import frappe
from frappe.model.document import Document


class WhatsAppDocumentDelivery(Document):
    def onload(self):
        if self.outbox:
            self.delivery_status = frappe.db.get_value('WhatsApp Message', self.message, 'status') or frappe.db.get_value('WhatsApp Outbox', self.outbox, 'state')

    def validate(self):
        if not frappe.flags.get('whatsapp_document_service'):
            frappe.throw('Document deliveries are created and updated by their delivery rule.')

    def on_trash(self):
        frappe.throw('Document delivery history is retained.')
