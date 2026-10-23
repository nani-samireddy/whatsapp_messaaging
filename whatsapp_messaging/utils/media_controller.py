"""Compatibility guards for the retired direct media path."""
import frappe
from whatsapp_messaging.send_security import require_outbound_enabled, require_send_role


def upload_media_to_whatsapp(media_file, doc):
    require_outbound_enabled()
    frappe.throw('Direct media upload is retired; attach a private image or PDF to a queued message')


def process_whatsapp_media(doc):
    require_send_role()
    frappe.throw('Direct media payloads are retired. Use a saved private image or PDF with a queued message.')
