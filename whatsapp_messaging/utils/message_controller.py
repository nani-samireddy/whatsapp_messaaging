"""Compatibility names retained; all transport now belongs to the durable outbox."""
import frappe
from frappe.integrations.utils import make_post_request
from whatsapp_messaging.send_security import require_outbound_enabled


def send_message(payload, media_doc_name="", headers=None, url=None):
    require_outbound_enabled()
    frappe.throw("Direct transport is retired; create a WhatsApp outbox intent")


def send_bulk_messages(recipients=None, payload=None, media_doc_name="", headers=None, url=None):
    require_outbound_enabled()
    frappe.throw("Use the campaign preview and start actions")
