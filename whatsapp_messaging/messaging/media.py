"""Private, bounded image/PDF assets. URLs are never accepted from send callers."""
import hashlib
import base64
from urllib.parse import urlsplit

import frappe
from whatsapp_messaging.messaging.naming import set_record_values
import requests
from whatsapp_messaging.send_security import require_outbound_enabled, require_send_role
from whatsapp_messaging.utils.config import get_headers
from .common import account, conversation, insert, require_manager, utcnow

MAX_SIZE=20*1024*1024


def inspect(content):
    if content.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
    elif content.startswith(b'\x89PNG\r\n\x1a\n'): mime='image/png'
    elif content.startswith(b'%PDF-'): mime='application/pdf'
    else:frappe.throw('Only JPEG, PNG and PDF files are supported')
    if len(content)>(5*1024*1024 if mime.startswith('image/') else MAX_SIZE):frappe.throw('This attachment exceeds the supported size limit')
    return mime


def authorized_file(name):
    require_send_role()
    doc=frappe.get_doc('File',name);doc.check_permission('read')
    if not doc.is_private:frappe.throw('WhatsApp attachments must be private files. Upload the file again with Private enabled; existing public links are not changed automatically.')
    if doc.attached_to_doctype and doc.attached_to_name:
        frappe.get_doc(doc.attached_to_doctype,doc.attached_to_name).check_permission('read')
    elif doc.owner!=frappe.session.user and 'System Manager' not in frappe.get_roles():
        frappe.throw('You cannot use another user’s unattached file',frappe.PermissionError)
    content=read_private_file(doc)
    inspect(content)
    return doc,content


def read_private_file(doc):
    if not doc.is_private or not (doc.file_url or '').startswith('/private/files/'):
        frappe.throw('Choose a private uploaded file. Remote URLs and public files are not supported.')
    doc.validate_file_path()
    doc.validate_file_url()
    try:
        with open(doc.get_full_path(), 'rb') as stream:
            content = stream.read(MAX_SIZE + 1)
    except OSError:
        frappe.throw('This file is no longer available. Choose another file or upload it again.')
    if len(content) > MAX_SIZE:
        frappe.throw('This attachment exceeds the supported size limit')
    return content


def attach(message, file_id):
    file,content=authorized_file(file_id)
    return insert('WhatsApp Attachment',message=message.name,account=message.account,file=file.name,
        file_name=file.file_name,mime_type=inspect(content),size=len(content),content_hash=hashlib.sha256(content).hexdigest(),state='Ready')


@frappe.whitelist()
def download(name):
    require_send_role()
    attachment=frappe.get_doc('WhatsApp Attachment',name);attachment.check_permission('read')
    message=frappe.get_doc('WhatsApp Message',attachment.message)
    conversation(message.conversation)
    if attachment.state!='Ready' or not attachment.file:frappe.throw('Attachment is not available')
    file=frappe.get_doc('File',attachment.file)
    if not file.is_private:frappe.throw('Attachment must be private')
    content=read_private_file(file)
    frappe.local.response.filename=file.file_name
    frappe.local.response.filecontent=content
    frappe.local.response.type='download'
    frappe.local.response.display_content_as='attachment'
    frappe.local.response.content_type=attachment.mime_type


def upload(attachment, sender):
    require_outbound_enabled()
    file=frappe.get_doc('File',attachment.file)
    if not file.is_private:frappe.throw('Attachment must be private')
    content=read_private_file(file)
    if isinstance(content,str):content=content.encode()
    mime=inspect(content)
    if hashlib.sha256(content).hexdigest()!=attachment.content_hash:frappe.throw('Attachment content changed after it was queued')
    from .media_cloud import cached_id
    existing = cached_id(attachment.content_hash, sender)
    if existing:
        set_record_values(attachment.doctype, attachment.name, 'provider_media_id', existing)
        return existing
    version=frappe.db.get_single_value('WhatsApp Settings','whatsapp_api_version')
    from whatsapp_messaging.utils.config import get_cloud_api_url
    response=requests.post(get_cloud_api_url(sender.name,'media'),headers={'Authorization':get_headers(sender.name)['authorization']},data={'messaging_product':'whatsapp','type':mime},files={'file':(file.file_name,content,mime)},timeout=(5,30))
    response.raise_for_status()
    media_id=response.json().get('id')
    if not str(media_id or '').isdigit():frappe.throw('Provider did not return a media identifier')
    # This send had no matching fresh library ID. Keep its own provider result.
    set_record_values(attachment.doctype,attachment.name,'provider_media_id',media_id)
    return media_id


def download_inbound(name):
    if not frappe.db.get_single_value('WhatsApp Settings','enable_inbound',cache=False):return
    attachment=frappe.get_doc('WhatsApp Attachment',name)
    if attachment.state not in ('Pending','Failed') or not attachment.provider_media_id:return
    sender=frappe.get_doc('WhatsApp Phone Number ID',attachment.account)
    if not sender.enabled:return
    media_id=attachment.provider_media_id
    import re
    if not re.fullmatch(r'[0-9]+',media_id):return
    version=frappe.db.get_single_value('WhatsApp Settings','whatsapp_api_version')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+',version or ''):return
    headers={'Authorization':get_headers(sender.name)['authorization']}
    try:
        meta=requests.get(f'https://graph.facebook.com/{version}/{media_id}',headers=headers,timeout=(5,20),allow_redirects=False)
        meta.raise_for_status();url=meta.json()['url'];parts=urlsplit(url)
        if parts.scheme!='https' or parts.netloc not in ('lookaside.fbsbx.com','lookaside.facebook.com') or parts.username:raise ValueError('Untrusted media host')
        response=requests.get(url,headers=headers,timeout=(5,30),allow_redirects=False,stream=True)
        response.raise_for_status()
        if response.is_redirect:raise ValueError('Media redirects are unsupported')
        content=bytearray()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content)>MAX_SIZE:raise ValueError('Attachment too large')
        content=bytes(content);mime=inspect(content)
        if attachment.provider_hash and attachment.provider_hash not in (hashlib.sha256(content).hexdigest(),base64.b64encode(hashlib.sha256(content).digest()).decode()):raise ValueError('Content hash mismatch')
        # Pass bytes directly: the older save_file helper can decode/re-encode an existing image blob.
        file=frappe.get_doc(dict(doctype='File',file_name=('attachment.pdf' if mime=='application/pdf' else 'image.png' if mime=='image/png' else 'image.jpg'),
            content=content,attached_to_doctype='WhatsApp Message',attached_to_name=attachment.message,is_private=1)).insert(ignore_permissions=True)
        set_record_values(attachment.doctype,name,{'file':file.name,'file_name':file.file_name,'mime_type':mime,'size':len(content),'content_hash':hashlib.sha256(content).hexdigest(),'state':'Ready','error_reason':None})
    except Exception:
        set_record_values(attachment.doctype,name,{'state':'Failed','error_reason':'Unable to retrieve this supported attachment'})
