"""Read-only launch diagnostics. Never contacts Meta, queues jobs or changes settings."""
import ipaddress
import re
from datetime import timedelta, timezone
from urllib.parse import urlsplit

import frappe
from frappe.utils import get_datetime, now_datetime

from .common import require_manager, utcnow

TICK = 'whatsapp_messaging.messaging.setup.tick'


def public_https_url(value):
    try:
        parts = urlsplit(value or '')
        host = parts.hostname or ''
        if (parts.scheme != 'https' or not host or parts.username or parts.password
                or parts.query or parts.fragment or parts.path not in ('', '/')
                or host == 'localhost' or host.endswith(('.localhost', '.home.arpa', '.invalid', '.test'))):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' in host
    except ValueError:
        return False


def has_password(doc, field):
    try:
        return bool(doc.get_password(field, raise_exception=False))
    except Exception:
        # Missing encryption keys must not reveal decrypted values or credential errors.
        return False


def live_worker_counts(queue_names):
    from frappe.utils.background_jobs import get_queue, get_workers
    queues = {name: get_queue(name).name for name in queue_names}
    counts = dict.fromkeys(queue_names, 0)
    for worker in get_workers():
        heartbeat = worker.last_heartbeat
        if not heartbeat:
            continue
        heartbeat = get_datetime(heartbeat)
        if heartbeat.tzinfo:
            heartbeat = heartbeat.astimezone(timezone.utc).replace(tzinfo=None)
        if utcnow() - heartbeat > timedelta(seconds=max(120, getattr(worker, 'worker_ttl', 420) or 420)):
            continue
        subscriptions = set(worker.queue_names())
        for name, queue in queues.items():
            if queue in subscriptions:
                counts[name] += 1
    return counts


@frappe.whitelist(methods=['GET'])
def check():
    """Check saved configuration and recent runtime evidence, not provider delivery.

    System Managers can also run `bench --site SITE execute ...readiness.check`.
    External acceptance is required even when configuration checks pass.
    """
    require_manager()
    checks = []

    def add(code, label, passed, action):
        checks.append(dict(code=code, label=label, status='pass' if passed else 'blocked',
            detail='Verified locally.' if passed else action))

    required = ('WhatsApp Outbox', 'WhatsApp Conversation Flow', 'WhatsApp Document Delivery Rule',
        'WhatsApp Document Delivery', 'WhatsApp Media', 'WhatsApp Webhook Event')
    schema_ok = all(frappe.db.has_table(name) for name in required)
    add('schema', 'Database setup', schema_ok, 'Run bench migrate for this site before enabling messaging.')
    settings = frappe.get_single('WhatsApp Settings')
    add('graph', 'Meta connection', (settings.whatsapp_api_url or '').rstrip('/') == 'https://graph.facebook.com'
        and bool(re.fullmatch(r'v[0-9]+\.[0-9]+', settings.whatsapp_api_version or '')),
        'Configure the official HTTPS Graph endpoint and a supported API version.')
    senders = frappe.get_all('WhatsApp Sender', filters={'enabled': 1}, pluck='name')
    sender_ok = bool(senders)
    for name in senders:
        sender = frappe.get_doc('WhatsApp Sender', name)
        sender_ok = sender_ok and bool(re.fullmatch(r'[0-9]+', sender.phone_number_id or '')
            and re.fullmatch(r'[0-9]+', sender.waba_id or '') and has_password(sender, 'access_token'))
    add('sender', 'Business number connection', sender_ok,
        'Configure an enabled Sender with numeric Phone Number ID, WABA ID and a decryptable access token.')
    add('webhook', 'Incoming update verification', bool(settings.meta_app_id
        and has_password(settings, 'app_secret') and has_password(settings, 'verify_token')),
        'Set the Meta App ID, App Secret and Verify Token. Then verify the HTTPS callback in Meta.')
    add('https', 'Secure public address', public_https_url(frappe.conf.get('host_name')),
        'Set this site’s host_name to its public HTTPS URL and verify it externally.')
    for field, label in (('enable_outbound_messages', 'Sending and file uploads'),
            ('enable_inbound', 'Incoming messages and updates'), ('enable_automation', 'Automatic messages')):
        add(field, label, bool(settings.get(field)),
            'Disabled intentionally by default. Enable only after configuration and previews are reviewed.')

    from frappe.utils.scheduler import is_scheduler_inactive
    job = frappe.db.get_value('Scheduled Job Type', {'method': TICK},
        ['stopped', 'last_execution'], as_dict=True)
    # Frappe stores Scheduled Job Type timestamps in site-local time; the app's
    # outbox timestamps use UTC. Mixing them hides stale jobs in positive offsets.
    tick_age = now_datetime() - get_datetime(job.last_execution) if job and job.last_execution else None
    recent_tick = bool(job and not job.stopped and tick_age is not None
        and -timedelta(minutes=1) <= tick_age <= timedelta(minutes=10))
    add('scheduler', 'Automatic scheduling is running',
        not is_scheduler_inactive(verbose=False) and recent_tick,
        'Enable this site’s scheduler, run bench schedule, and wait for its messaging tick. '
        'This is recent execution evidence; verify actual 9 AM execution separately.')
    from .media_cloud import queue_configured
    media_configured = queue_configured()
    add('media_queue', 'File upload processing is configured', media_configured,
        'Run bench --site SITE execute whatsapp_messaging.messaging.media_cloud.configure_worker; '
        'then restart web/worker processes and run a worker subscribed to whatsapp_media.')
    try:
        counts = live_worker_counts(['default'] + (['whatsapp_media'] if media_configured else []))
        add('default_worker', 'Message processing is running', counts['default'] > 0,
            'Start a worker subscribed to default; schedules, flows, document delivery and webhooks need it.')
        add('media_worker', 'File upload processing is running', counts.get('whatsapp_media', 0) > 0,
            'Start a worker subscribed to whatsapp_media. Queue configuration alone does not start a worker.')
    except Exception:
        add('workers', 'Background message and file processing', False,
            'Check Redis queue connectivity and worker processes. No jobs were submitted by this check.')

    warnings = []
    if schema_ok:
        for doctype, filters, label in (
                ('WhatsApp Outbox', {'state': 'Unknown'}, 'Uncertain sends require review; do not automatically resend.'),
                ('WhatsApp Webhook Event', {'state': ['in', ['Failed', 'Quarantined']]},
                    'Some incoming updates could not be processed or were set aside for review.')):
            count = frappe.db.count(doctype, filters)
            if count:
                warnings.append(dict(count=count, detail=label))
    return dict(status='configuration_ready' if all(row['status'] == 'pass' for row in checks) else 'blocked',
        checks=checks, warnings=warnings, sends_created=0,
        external_verification_required=[
            'Public HTTPS, Meta callback verification, signed inbound messages and delivery receipts.',
            'An opted-in recipient receives a template, reply, image and private PDF on this deployment.',
            'Recurring 9 AM reminders, restart recovery, roles and hospital record mappings.',
            'Successful backup restore rehearsal and operational monitoring.'])
