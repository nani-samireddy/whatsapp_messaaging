"""Readable record titles; provider identities and permanent names stay independent."""
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import frappe


# Only these fields can affect a generated title. Service updates to counters,
# payloads and leases need no extra title query.
TITLE_INPUTS = {
    'WhatsApp Approved Template': ('template_name', 'language'),
    'WhatsApp Attachment': ('file_name', 'file', 'mime_type', 'message'),
    'WhatsApp Automation Run': ('rule', 'kind', 'due_at'),
    'WhatsApp Conversation': ('account', 'peer', 'recipient'),
    'WhatsApp Conversation Activity': ('conversation', 'action', 'actor', 'creation'),
    'WhatsApp Conversation Read': ('conversation', 'user'),
    'WhatsApp Identity Alias': ('peer', 'identity_kind', 'identity_value'),
    'WhatsApp Media': ('label', 'caption', 'media_attachment', 'media_url', 'document_type', 'content_type'),
    'WhatsApp Message': ('direction', 'peer', 'conversation', 'status'),
    'WhatsApp Message Log': ('recipient', 'type', 'timestamp', 'status'),
    'WhatsApp Outbox': ('message', 'state'),
    'WhatsApp Peer': ('display_name', 'phone_number', 'provider_identity'),
    'WhatsApp Record Link': ('conversation', 'reference_doctype', 'reference_name'),
    'WhatsApp Schedule': ('rule', 'one_shot', 'next_due_at', 'cron_expression', 'timezone'),
    'WhatsApp Send Attempt': ('outbox', 'attempt_number'),
    'WhatsApp Status Event': ('message', 'provider_message_id', 'provider_status'),
    'WhatsApp Webhook Event': ('state', 'received_at'),
}


def _join(*values):
    # Titles contain plain, bounded text, never message bodies, tokens or payloads.
    return ' · '.join(' '.join(str(v).split()) for v in values if v not in (None, ''))[:140]


def _peer(name):
    if not name:
        return None
    row = frappe.db.get_value('WhatsApp Peer', name,
        ['display_name', 'phone_number', 'provider_identity'], as_dict=True)
    return (row.display_name or row.phone_number or row.provider_identity) if row else name


def _filename(value):
    return unquote(PurePosixPath(urlsplit(value or '').path).name)


def schedule_local_time(value, zone):
    """Schedule due times are stored in UTC, independently of the site timezone."""
    if not value:
        return None
    date = datetime.fromisoformat(str(value)) if not isinstance(value, datetime) else value
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(ZoneInfo(zone or 'UTC')).strftime('%Y-%m-%d %H:%M:%S')


def record_title(doc):
    kind = doc.doctype
    if kind == 'WhatsApp Approved Template':
        title = _join(doc.template_name, doc.language)
    elif kind == 'WhatsApp Attachment':
        title = _join(doc.file_name or _filename(doc.file), doc.message)
    elif kind == 'WhatsApp Automation Run':
        title = _join(doc.rule, doc.kind, doc.due_at)
    elif kind == 'WhatsApp Conversation':
        title = _join(doc.account, _peer(doc.peer) or doc.recipient)
    elif kind == 'WhatsApp Conversation Activity':
        title = _join(doc.conversation, doc.action, doc.actor, doc.creation)
    elif kind == 'WhatsApp Conversation Read':
        title = _join(doc.conversation, doc.user)
    elif kind == 'WhatsApp Identity Alias':
        title = _join(_peer(doc.peer), doc.identity_kind, doc.identity_value)
    elif kind == 'WhatsApp Media':
        format_label = {'application/pdf': 'PDF', 'image/png': 'PNG', 'image/jpeg': 'JPEG'}.get(doc.get('content_type'), doc.document_type)
        title = _join(doc.get('label') or doc.caption or _filename(doc.media_attachment) or _filename(doc.media_url), format_label)
    elif kind == 'WhatsApp Message':
        recipient = _peer(doc.peer)
        if not recipient and doc.conversation:
            recipient = frappe.db.get_value('WhatsApp Conversation', doc.conversation, 'recipient')
        title = _join(doc.direction, recipient, doc.status)
    elif kind == 'WhatsApp Message Log':
        title = _join(doc.recipient, doc.type, doc.timestamp, doc.status)
    elif kind == 'WhatsApp Outbox':
        title = _join(doc.message, doc.state)
    elif kind == 'WhatsApp Peer':
        title = _join(doc.display_name or doc.phone_number or doc.provider_identity)
    elif kind == 'WhatsApp Record Link':
        title = _join(doc.conversation, doc.reference_doctype, doc.reference_name)
    elif kind == 'WhatsApp Schedule':
        recurrence = schedule_local_time(doc.next_due_at, doc.timezone) if doc.one_shot else doc.cron_expression
        title = _join(doc.rule, 'Once' if doc.one_shot else 'Recurring', recurrence, doc.timezone)
    elif kind == 'WhatsApp Send Attempt':
        title = _join(doc.outbox, f'Attempt {doc.attempt_number or 1}')
    elif kind == 'WhatsApp Status Event':
        title = _join(doc.message or doc.provider_message_id, doc.provider_status)
    elif kind == 'WhatsApp Webhook Event':
        title = _join(doc.state, doc.received_at)
    else:
        return None
    return title or doc.name or kind


def set_title(doc, method=None):
    if doc.doctype in TITLE_INPUTS:
        doc.record_title = record_title(doc)


def _title_record(doctype, name):
    # Lock just the row and read only title inputs, not large bodies or payloads.
    row = frappe.db.get_value(doctype, name, ['name', 'record_title', *TITLE_INPUTS[doctype]],
        as_dict=True, for_update=True)
    if row:
        row.doctype = doctype
    return row


def set_record_values(doctype, name, fieldname, value=None, **kwargs):
    """Keep titles consistent with the services' deliberate direct DB updates."""
    values = dict(fieldname) if isinstance(fieldname, dict) else {fieldname: value}
    if set(values).intersection(TITLE_INPUTS.get(doctype, ())):
        doc = _title_record(doctype, name)
        if doc:
            doc.update(values)
            values['record_title'] = record_title(doc)
    return frappe.db.set_value(doctype, name, values, **kwargs)


def refresh_peer_titles(doc, method=None):
    """A corrected contact name also updates existing conversation/message titles."""
    if doc.doctype != 'WhatsApp Peer' or not doc.has_value_changed('display_name'):
        return
    for doctype in ('WhatsApp Conversation', 'WhatsApp Message', 'WhatsApp Identity Alias'):
        for name in frappe.get_all(doctype, filters={'peer': doc.name}, pluck='name'):
            linked = _title_record(doctype, name)
            if linked:
                frappe.db.set_value(doctype, name, 'record_title', record_title(linked), update_modified=False)


def backfill_titles():
    """Idempotent, bounded batches. Never save documents or rename existing IDs."""
    for doctype in TITLE_INPUTS:
        previous = ''
        while True:
            rows = frappe.get_all(doctype, filters={'name': ['>', previous]},
                fields=['name', 'record_title', *TITLE_INPUTS[doctype]], order_by='name asc', limit_page_length=500)
            if not rows:
                break
            for row in rows:
                row.doctype = doctype
                title = record_title(row)
                if row.record_title != title:
                    current = _title_record(doctype, row.name)
                    if current:
                        frappe.db.set_value(doctype, row.name, 'record_title', record_title(current), update_modified=False)
            previous = rows[-1].name
