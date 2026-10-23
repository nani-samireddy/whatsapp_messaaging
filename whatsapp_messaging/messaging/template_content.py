"""Derive template content from permitted private file bytes, never a chosen type."""
import frappe

from whatsapp_messaging.send_security import require_send_role
from .media import authorized_file, inspect


def resolve(media_name=None, approved_template_name=None):
    if approved_template_name:
        approved = frappe.get_doc('WhatsApp Approved Template', approved_template_name)
        approved.check_permission('read')
        if media_name:
            frappe.throw('Approved templates support a text body with optional text header and footer. Remove Media to use this approved template.')
        if not approved.supported:
            frappe.throw('This approved template has unsupported content. Choose a supported text-body template.')
        return {'template_type': 'text', 'file_id': None}
    if not media_name:
        return {'template_type': 'text', 'file_id': None}

    asset = frappe.get_doc('WhatsApp Media', media_name)
    asset.check_permission('read')
    if asset.media_type != 'Upload':
        frappe.throw('Use a private uploaded JPEG, PNG or PDF. Media URLs cannot be used in message templates.')
    from .media_library import file_metadata
    details = file_metadata(asset.media_attachment)
    return {'template_type': details['document_type'], 'file_id': details['file_reference']}


@frappe.whitelist()
def detect(media_name=None, approved_template_name=None):
    """Read-only form preview; saving and queueing repeat the same validation."""
    require_send_role()
    return resolve(media_name, approved_template_name)['template_type']
