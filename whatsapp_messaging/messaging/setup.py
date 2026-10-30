"""Idempotent local/install schema cutover. Never enables dispatch or seeds messages."""
import frappe


def install():
    for doctype,fields in (
        ('WhatsApp Conversation',['account','workflow_status','last_activity_at']),
        ('WhatsApp Conversation',['assigned_to','workflow_status','last_activity_at']),
        ('WhatsApp Message',['conversation','sequence']),
        ('WhatsApp Outbox',['state','next_attempt_at']),
        ('WhatsApp Outbox',['run','state']),
        ('WhatsApp Outbox',['lease_until']),
        ('WhatsApp Status Event',['account','provider_message_id']),
        ('WhatsApp Schedule',['state','next_due_at']),
        ('WhatsApp Record Link',['reference_doctype','reference_name']),
        ('WhatsApp Webhook Event',['state','next_attempt_at']),
        ('WhatsApp Flow Event',['conversation','state']),
        ('WhatsApp Conversation Flow',['published_account','is_active']),
        ('WhatsApp Document Rule',['source_doctype','enabled']),
        ('WhatsApp Document Delivery',['state','creation']),
        ('WhatsApp Document Delivery',['outbox']),
    ):
        frappe.db.add_index(doctype,fields)
    # Old encoded scheduler methods are deliberately left stopped, never run alongside the new dispatcher.
    jobs=frappe.get_all('Scheduled Job Type',filters={'method':['like','whatsapp_messaging.tasks.%scheduled_message_handler_%']},pluck='name')
    for name in jobs:frappe.db.set_value('Scheduled Job Type',name,'stopped',1)


def tick():
    from . import automation,outbox,webhooks,media_cloud,flows,document_delivery
    automation.process_due()
    outbox.sweep()
    webhooks.sweep()
    media_cloud.sweep()
    flows.sweep()
    document_delivery.recover()
