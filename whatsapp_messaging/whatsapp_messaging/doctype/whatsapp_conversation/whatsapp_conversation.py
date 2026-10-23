from frappe.model.document import Document
from whatsapp_messaging.messaging.documents import protect_canonical


class WhatsAppConversation(Document):
    def validate(self):
        protect_canonical(self)

    def on_trash(self):
        protect_canonical(self)
