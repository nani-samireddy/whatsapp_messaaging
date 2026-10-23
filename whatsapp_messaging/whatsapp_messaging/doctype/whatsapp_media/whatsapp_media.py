import frappe
from frappe.model.document import Document
from whatsapp_messaging.messaging.media_library import update_metadata
from whatsapp_messaging.send_security import require_send_role


class WhatsAppMedia(Document):
    def before_validate(self):
        require_send_role()
        previous = self.get_doc_before_save()
        # Removing a file saves an unavailable library record, never deletes the
        # stored File or a previously queued message's immutable attachment.
        update_metadata(self)
        from whatsapp_messaging.messaging.media_cloud import prepare
        prepare(self, previous)

    def on_update(self):
        from whatsapp_messaging.messaging.media_cloud import enqueue
        enqueue(self)
        if not self.file_reference:
            return
        file = frappe.get_doc('File', self.file_reference)
        if not file.attached_to_doctype and not file.attached_to_name and file.owner == frappe.session.user:
            # Bind a new private upload only after the explicit media Save. Never
            # move a file away from a business record or change its visibility.
            frappe.db.set_value('File', file.name, dict(attached_to_doctype=self.doctype,
                attached_to_name=self.name, attached_to_field='media_attachment'), update_modified=False)

    def on_trash(self):
        # Deleting a library entry must not delete files held by queued messages
        # or history. Physical file removal remains an explicit File action.
        for name in frappe.get_all('File', filters={'attached_to_doctype':self.doctype,
                'attached_to_name':self.name}, pluck='name'):
            frappe.db.set_value('File', name, dict(attached_to_doctype=None,
                attached_to_name=None, attached_to_field=None), update_modified=False)
