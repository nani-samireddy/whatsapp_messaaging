"""Validate private media assets independently from their cloud upload status."""
import hashlib
from io import BytesIO

import frappe
from frappe.utils import now_datetime
from whatsapp_messaging.send_security import require_send_role
from .media import authorized_file, inspect

DERIVED_FIELDS = ('file_reference', 'file_name', 'content_type', 'document_type',
    'file_size', 'file_size_display', 'content_hash', 'validated_on')
READY_MESSAGE = 'Private file checked. Saving queues its WhatsApp cloud upload when the Sender and Outbound Requests are enabled. No message is sent.'


def file_metadata(file_url):
    require_send_role()
    if not file_url or not file_url.startswith('/private/files/'):
        frappe.throw('Choose a private JPEG, PNG or PDF from your computer or the file library.')
    files = frappe.get_all('File', filters={'file_url': file_url, 'is_folder': 0}, pluck='name')
    if not files:
        frappe.throw('This file is no longer available. Upload it again or choose another file.')
    # Multiple File rows may share the same stored file; use one the caller can read.
    denied = None
    for name in files:
        try:
            file, content = authorized_file(name)
            break
        except frappe.PermissionError as exc:
            denied = exc
    else:
        raise denied
    mime = inspect(content)
    validate_format(content, mime)
    return dict(file_reference=file.name, file_name=file.file_name, content_type=mime,
        document_type='image' if mime.startswith('image/') else 'document', file_size=len(content),
        file_size_display=(f'{len(content) / 1048576:.1f} MB' if len(content) >= 1048576 else f'{len(content) / 1024:.1f} KB'),
        content_hash=hashlib.sha256(content).hexdigest(), validated_on=now_datetime(),
        validation_status='Ready', validation_message=READY_MESSAGE)


def validate_format(content, mime):
    try:
        if mime.startswith('image/'):
            from PIL import Image
            with Image.open(BytesIO(content)) as image:
                image.verify()
        else:
            from pypdf import PdfReader
            pdf = PdfReader(BytesIO(content))
            if not pdf.is_encrypted and not len(pdf.pages):
                raise ValueError('Unreadable PDF')
    except Exception:
        frappe.throw('This file cannot be read as a supported image or PDF. Choose an undamaged JPEG, PNG or PDF.')


@frappe.whitelist()
def preview(file_url):
    """Read-only inspection for full form and Quick Entry; save repeats every check."""
    return file_metadata(file_url)


def clear_metadata(doc):
    for field in DERIVED_FIELDS:
        doc.set(field, 0 if field == 'file_size' else None)


def update_metadata(doc, *, migration=False):
    clear_metadata(doc)
    if doc.media_attachment:
        details = file_metadata(doc.media_attachment)
        doc.update(details)
        doc.media_type = 'Upload'
        if not doc.label:
            doc.label = doc.file_name[:140]
    else:
        doc.validation_status = 'Legacy URL' if doc.media_type == 'URL' else 'Needs File'
        doc.validation_message = ('URL media is no longer supported. Choose a private JPEG, PNG or PDF instead.'
            if doc.media_type == 'URL' else 'Choose a private file before using this media in a message.')
        if doc.is_new() and not migration:
            frappe.throw('Choose a private JPEG, PNG or PDF before saving this media.')
    return doc


def backfill():
    """Inspect existing local assets without sending, fetching URLs or changing files."""
    from .naming import record_title
    for name in frappe.get_all('WhatsApp Media', pluck='name', limit_page_length=0):
        doc = frappe.get_doc('WhatsApp Media', name)
        if not doc.label:
            doc.label = (doc.caption or '')[:140]
        try:
            update_metadata(doc, migration=True)
        except (frappe.ValidationError, frappe.PermissionError, OSError):
            clear_metadata(doc)
            doc.validation_status = 'Needs Attention'
            doc.validation_message = 'This existing file could not be verified. Choose a supported private file before using it.'
        values = {field: doc.get(field) for field in (*DERIVED_FIELDS, 'label', 'media_type', 'validation_status', 'validation_message')}
        values['record_title'] = record_title(doc)
        frappe.db.set_value(doc.doctype, name, values, update_modified=False)
