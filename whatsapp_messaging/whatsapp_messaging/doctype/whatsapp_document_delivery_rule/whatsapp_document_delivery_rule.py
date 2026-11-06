from frappe.model.document import Document


class WhatsAppDocumentDeliveryRule(Document):
    def validate(self):
        from whatsapp_messaging.messaging.document_delivery import validate_rule
        validate_rule(self)
