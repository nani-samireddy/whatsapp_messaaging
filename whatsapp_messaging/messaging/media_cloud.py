"""After-commit cloud uploads, separate from sending messages."""
from datetime import timedelta

import frappe
import requests
from frappe.utils import get_datetime, now_datetime
from whatsapp_messaging.send_security import require_outbound_enabled, require_send_role
from whatsapp_messaging.utils.config import get_cloud_api_url, get_headers
from .common import account
from .media import authorized_file

QUEUE = 'whatsapp_media'
CLOUD_FIELDS = ('media_id', 'cloud_status', 'cloud_error', 'cloud_uploaded_on', 'cloud_refresh_after',
    'cloud_content_hash', 'cloud_sender', 'cloud_upload_key', 'cloud_requested_by', 'cloud_lease_until')


def enabled():
    return bool(frappe.db.get_single_value('WhatsApp Settings', 'enable_outbound_messages', cache=False))


def queue_configured():
    from frappe.utils.background_jobs import get_queues_timeout
    return QUEUE in get_queues_timeout()


def configure_worker():
    """Bench administrator setup; does not start workers or enable requests."""
    import json
    from pathlib import Path
    from frappe.installer import update_site_config
    from frappe.utils.background_jobs import get_queues_timeout
    from .common import require_manager
    require_manager()
    path = Path(frappe.local.sites_path).resolve() / 'common_site_config.json'
    config = json.loads(path.read_text())
    workers = config.get('workers', {})
    workers.setdefault(QUEUE, {'timeout':120})
    update_site_config('workers', workers, site_config_path=str(path))
    get_queues_timeout.cache_clear()
    return {'queue':QUEUE, 'configured':True}


def prepare(doc, previous):
    doc.flags.enqueue_cloud_upload = False
    retry_requested = bool(doc.flags.retry_cloud_upload)
    doc.flags.retry_cloud_upload = False
    # Readonly UI fields are never trusted as provider results on a normal save.
    for field in CLOUD_FIELDS:
        doc.set(field, previous.get(field) if previous else None)
    doc.cloud_status = doc.cloud_status or 'Not Uploaded'
    changed = not previous or any(doc.get(f) != previous.get(f)
        for f in ('content_hash', 'phone_number_id', 'media_attachment'))
    # Keep old URL records readable, but never accept a URL/provider result from
    # a caller as the source for a new private-file upload.
    doc.media_url = previous.media_url if previous and not changed else None
    if changed or doc.validation_status != 'Ready':
        for field in CLOUD_FIELDS:
            doc.set(field, None)
        doc.cloud_status = 'Not Uploaded'
    if doc.validation_status != 'Ready':
        return
    if not doc.phone_number_id:
        if doc.is_new():
            frappe.throw('Choose the Sender account for the WhatsApp cloud upload.')
        doc.cloud_status = 'Needs Sender'
        doc.cloud_error = 'Choose a Sender and save to upload this file to WhatsApp.'
        return
    sender = account(doc.phone_number_id)
    expired = doc.cloud_refresh_after and get_datetime(doc.cloud_refresh_after) <= now_datetime()
    if not (changed or expired or retry_requested
            or doc.cloud_status in ('Not Uploaded', 'Needs Sender', 'Blocked')):
        return
    for field in CLOUD_FIELDS:
        doc.set(field, None)
    doc.cloud_upload_key = frappe.generate_hash(length=20)
    doc.cloud_requested_by = frappe.session.user
    if not enabled() or not sender.enabled:
        doc.cloud_status = 'Blocked'
        doc.cloud_error = ('Enable Outbound Requests in WhatsApp Settings, then retry upload.'
            if not enabled() else 'This Sender is disabled. Enable it or choose another Sender, then retry upload.')
    elif not queue_configured():
        doc.cloud_status = 'Blocked'
        doc.cloud_error = 'The media upload worker is not configured. Ask the administrator to configure the whatsapp_media queue, then retry.'
    else:
        doc.cloud_status = 'Pending'
        doc.flags.enqueue_cloud_upload = True


def enqueue(doc):
    if doc.flags.enqueue_cloud_upload:
        frappe.enqueue('whatsapp_messaging.messaging.media_cloud.upload', queue=QUEUE,
            enqueue_after_commit=True, name=doc.name, upload_key=doc.cloud_upload_key,
            job_id='whatsapp-media-' + doc.name + '-' + doc.cloud_upload_key, deduplicate=True)


def finish(name, key, values):
    doc = frappe.get_doc('WhatsApp Media', name, for_update=True)
    if doc.cloud_upload_key != key:
        frappe.db.rollback()
        return False
    values['cloud_lease_until'] = None
    frappe.db.set_value(doc.doctype, name, values)
    frappe.db.commit()
    frappe.publish_realtime('doc_update', dict(doctype=doc.doctype, name=name), doctype=doc.doctype, docname=name)
    return True


def upload(name, upload_key):
    """Dedicated worker entry: recheck the actor, source, sender and API gate."""
    if not frappe.db.exists('WhatsApp Media', name):
        return
    doc = frappe.get_doc('WhatsApp Media', name, for_update=True)
    if doc.cloud_upload_key != upload_key or doc.cloud_status not in ('Pending', 'Uploading'):
        frappe.db.rollback(); return
    if doc.cloud_lease_until and get_datetime(doc.cloud_lease_until) > now_datetime():
        frappe.db.rollback(); return
    previous_user = frappe.session.user
    try:
        if not doc.cloud_requested_by or not frappe.db.get_value('User', doc.cloud_requested_by, 'enabled'):
            frappe.throw('The upload user is disabled.', frappe.PermissionError)
        frappe.set_user(doc.cloud_requested_by)
        require_send_role(); doc.check_permission('read'); require_outbound_enabled()
        sender = account(doc.phone_number_id, enabled=True)
        from .media_library import file_metadata
        details = file_metadata(doc.media_attachment)
        if details['content_hash'] != doc.content_hash:
            frappe.throw('The file changed. Save the media record again before uploading.')
        file, content = authorized_file(details['file_reference'])
        frappe.db.set_value(doc.doctype, name, dict(cloud_status='Uploading', cloud_error=None,
            cloud_lease_until=now_datetime()+timedelta(minutes=3)))
        frappe.db.commit()
        require_outbound_enabled()
        sender = account(sender.name, enabled=True)
        response = requests.post(get_cloud_api_url(sender.name, 'media'),
            headers={'Authorization':get_headers(sender.name)['authorization']},
            data={'messaging_product':'whatsapp', 'type':details['content_type']},
            files={'file':(file.file_name, content, details['content_type'])},
            timeout=(5,30), allow_redirects=False)
        if response.status_code >= 300:
            # Never persist provider response bodies, credentials or raw exceptions.
            finish(name, upload_key, dict(cloud_status='Failed', cloud_error=
                provider_error(response)))
            return
        media_id = response.json().get('id')
        if not str(media_id or '').isdigit():
            raise ValueError('Missing provider ID')
        timestamp = now_datetime()
        finish(name, upload_key, dict(cloud_status='Uploaded', cloud_error=None, media_id=str(media_id),
            cloud_uploaded_on=timestamp, cloud_refresh_after=timestamp+timedelta(days=29),
            cloud_content_hash=details['content_hash'], cloud_sender=sender.name))
    except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
        frappe.db.rollback()
        if frappe.db.exists('WhatsApp Media', name):
            finish(name, upload_key, dict(cloud_status='Blocked', cloud_error=
                'Upload eligibility changed. Check Outbound Requests, Sender access and the private file, then retry.'))
    except Exception:
        frappe.db.rollback()
        if frappe.db.exists('WhatsApp Media', name):
            finish(name, upload_key, dict(cloud_status='Failed', cloud_error=
                'The cloud upload did not complete. Check the connection and Sender settings, then retry.'))
    finally:
        frappe.set_user(previous_user)


def provider_error(response):
    try:
        code = int(response.json().get('error', {}).get('code', 0))
    except (ValueError, TypeError, AttributeError):
        code = 0
    if code == 190:
        return 'The Sender access token is invalid or expired. Update its token, then retry upload.'
    if code in (10, 200):
        return 'The Sender token does not have the required WhatsApp permissions. Check its access, then retry upload.'
    return f'Meta rejected the upload (HTTP {response.status_code}, code {code}). Check the Sender and file, then retry.'


@frappe.whitelist(methods=['POST'])
def retry(name):
    require_send_role()
    doc = frappe.get_doc('WhatsApp Media', name)
    doc.check_permission('write')
    if doc.cloud_status == 'Uploading' and doc.cloud_lease_until and get_datetime(doc.cloud_lease_until) > now_datetime():
        frappe.throw('An upload is already in progress. Wait for it to finish before retrying.')
    doc.flags.retry_cloud_upload = True
    doc.save()
    return dict(status=doc.cloud_status, message=doc.cloud_error)


def cached_id(content_hash, sender):
    for row in frappe.get_all('WhatsApp Media', filters=dict(validation_status='Ready', cloud_status='Uploaded',
            cloud_content_hash=content_hash, cloud_sender=sender.name,
            cloud_refresh_after=['>', now_datetime()]), fields=['name','media_id'],
            order_by='cloud_uploaded_on desc', limit_page_length=0):
        if str(row.media_id or '').isdigit() and frappe.has_permission('WhatsApp Media', 'read', row.name):
            return row.media_id
    return None


def sweep():
    if not enabled() or not queue_configured(): return
    for row in frappe.get_all('WhatsApp Media', filters={'cloud_status':['in',['Pending','Uploading']]},
            fields=['name','cloud_upload_key','cloud_lease_until'], limit_page_length=100):
        if row.cloud_upload_key and (not row.cloud_lease_until or get_datetime(row.cloud_lease_until) <= now_datetime()):
            frappe.enqueue('whatsapp_messaging.messaging.media_cloud.upload', queue=QUEUE,
                enqueue_after_commit=True, name=row.name, upload_key=row.cloud_upload_key,
                job_id='whatsapp-media-' + row.name + '-' + row.cloud_upload_key, deduplicate=True)
