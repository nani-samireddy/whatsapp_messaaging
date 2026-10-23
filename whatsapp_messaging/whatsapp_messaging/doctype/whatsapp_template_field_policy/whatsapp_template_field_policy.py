import json

import frappe
from frappe.model.document import Document
from whatsapp_messaging.messaging.field_policy import synchronize_templates, validate_fields


class WhatsAppTemplateFieldPolicy(Document):
    def validate(self):
        self.allowed_fields = json.dumps(sorted(validate_fields(self.source_doctype, self.allowed_fields)))

    def on_update(self):
        if self.has_value_changed('allowed_fields'):
            synchronize_templates(self.source_doctype, self.allowed_fields)

    def on_trash(self):
        synchronize_templates(self.source_doctype, '[]')
