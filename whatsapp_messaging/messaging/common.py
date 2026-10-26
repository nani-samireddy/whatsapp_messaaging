"""Shared role, transaction, clock and safe-data helpers for messaging services."""
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone

import frappe
from whatsapp_messaging.messaging.naming import set_record_values
from frappe.utils import get_datetime
from whatsapp_messaging.send_security import require_send_role

ROLES = ('System Manager', 'Whatsapp Admin', 'Whatsapp Editor')


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(*values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def parsed(value, default=None):
    return json.loads(value) if isinstance(value, str) and value else (value if value is not None else default)


def supervisor():
    return bool({'System Manager', 'Whatsapp Admin'}.intersection(frappe.get_roles()))


def require_supervisor():
    require_send_role(bulk=True)


def require_manager():
    if frappe.session.user == 'Guest' or 'System Manager' not in frappe.get_roles():
        frappe.throw('System Manager is required', frappe.PermissionError)


@contextmanager
def service_write():
    previous = frappe.flags.get('whatsapp_service_write')
    frappe.flags.whatsapp_service_write = True
    try:
        yield
    finally:
        frappe.flags.whatsapp_service_write = previous


@contextmanager
def as_user(user):
    previous = frappe.session.user
    if not user or not frappe.db.get_value('User', user, 'enabled'):
        frappe.throw('The execution user is disabled', frappe.PermissionError)
    try:
        frappe.set_user(user)
        require_send_role()
        yield
    finally:
        frappe.set_user(previous)


def insert(doctype, **values):
    if doctype in ('WhatsApp Outbox','WhatsApp Schedule','WhatsApp Automation Run') and values.get('rule'):
        from .campaigns import rule_type
        values['rule_doctype']=rule_type(values['rule'])
    with service_write():
        return frappe.get_doc(dict(doctype=doctype, **values)).insert(ignore_permissions=True)


def lock(doctype, name):
    # Identifiers come only from the fixed application schemas, never RPC parameters.
    if doctype not in {'WhatsApp Conversation', 'WhatsApp Peer', 'WhatsApp Outbox', 'WhatsApp Phone Number ID', 'WhatsApp Schedule', 'WhatsApp Automation Run', 'WhatsApp Webhook Event', 'WhatsApp Conversation Flow'}:
        raise ValueError('Unsupported lock')
    rows = frappe.db.sql(f'SELECT name FROM `tab{doctype}` WHERE name=%s FOR UPDATE', name)
    if not rows:
        frappe.throw('Record not found', frappe.DoesNotExistError)
    return frappe.get_doc(doctype, name)


def account(name, enabled=False):
    require_send_role()
    doc = frappe.get_doc('WhatsApp Phone Number ID', name)
    doc.check_permission('read')
    if enabled and not doc.enabled:
        frappe.throw('This sender account is disabled')
    return doc


def conversation(name, locked=False):
    require_send_role()
    doc = lock('WhatsApp Conversation', name) if locked else frappe.get_doc('WhatsApp Conversation', name)
    doc.check_permission('read')
    if not doc.account or not doc.peer:
        frappe.throw('Legacy history cannot be used as a live conversation')
    account(doc.account)
    return doc


def changed(doc, **values):
    values['version'] = int(doc.version or 0) + 1
    set_record_values(doc.doctype, doc.name, values)
    notify(doc.name, values['version'])


def notify(conversation_name, version=None):
    # Hints contain no message content. Delivery is to authenticated user rooms only.
    target = frappe.get_doc('WhatsApp Conversation', conversation_name)
    users = frappe.get_all('Has Role', filters={'role': ['in', ROLES], 'parenttype': 'User'}, pluck='parent')
    for user in set(users) | {'Administrator'}:
        if frappe.db.get_value('User', user, 'enabled') and frappe.has_permission('WhatsApp Conversation', 'read', doc=target, user=user):
            frappe.publish_realtime('whatsapp_changed', {'conversation': conversation_name, 'version': version}, user=user, after_commit=True)


def check_version(doc, version):
    if int(version) != int(doc.version or 0):
        frappe.throw('This conversation was updated by another agent. Refresh and try again.', frappe.TimestampMismatchError)


def page_size(value=40):
    return max(1, min(int(value), 100))


def public_message(doc):
    return {key: doc.get(key) for key in ('name', 'conversation', 'direction', 'message_type', 'message', 'status', 'sequence', 'provider_at', 'received_at', 'agent', 'reply_to', 'provider_message_id')}


def window_open(doc):
    return bool(doc.window_expires_at and get_datetime(doc.window_expires_at) > utcnow())
