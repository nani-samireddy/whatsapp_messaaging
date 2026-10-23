"""One shared placeholder-field policy for every template of a source DocType."""
import json

import frappe
from whatsapp_messaging.send_security import require_send_role
from whatsapp_messaging.template_security import SAFE_SOURCE_TYPES, SENSITIVE_FIELD, parse_allowed_fields

POLICY = 'WhatsApp Template Field Policy'


def eligible(field):
    return (field.fieldtype in SAFE_SOURCE_TYPES and not field.hidden and not field.print_hide
        and not SENSITIVE_FIELD.search(field.fieldname))


def validate_fields(source_doctype, value):
    names = parse_allowed_fields(value)
    meta = frappe.get_meta(source_doctype)
    allowed = {field.fieldname for field in meta.fields if eligible(field)}
    if names - allowed:
        frappe.throw('Choose only available, non-sensitive business fields from the field picker.')
    return names


def get_allowed_source_fields(source_doctype):
    value = frappe.db.get_value(POLICY, source_doctype, 'allowed_fields') if source_doctype else None
    return validate_fields(source_doctype, value) if value else frozenset()


def synchronize_templates(source_doctype, allowed_fields):
    # Updating the rule version holds already-queued sends and invalidates stale
    # campaign snapshots. Do not save rules, change run_as, or activate automation.
    frappe.db.set_value('WhatsApp Message Template', {'template_doctype': source_doctype},
        'allowed_source_fields', allowed_fields)
    if frappe.get_meta(source_doctype).issingle:
        # Static approval changes also invalidate templates whose business source
        # is a different DocType, holding queued sends prepared under old policy.
        alias = frappe.scrub(source_doctype)
        references = {row.name for row in frappe.get_all('WhatsApp Message Template',
                filters={'message_preview': ['like', '%static.' + alias + '.%']},
                fields=['name'], limit_page_length=0)}
        if frappe.db.has_table('WhatsApp Template Variable'):
            references.update(frappe.get_all('WhatsApp Template Variable',
                filters={'parenttype':'WhatsApp Message Template', 'source_path':['like','static.' + alias + '.%']},
                pluck='parent', limit_page_length=0))
        for name in references:
            if frappe.db.get_value('WhatsApp Message Template',name,'template_doctype') != source_doctype:
                frappe.db.set_value('WhatsApp Message Template', name, 'modified', frappe.utils.now())
    frappe.cache.delete_value('template_doctypes_map')


@frappe.whitelist()
def options(source_doctype):
    require_send_role()
    from whatsapp_messaging.utils import _check_metadata_permission
    _check_metadata_permission(source_doctype)
    meta = frappe.get_meta(source_doctype)
    permitted = set(meta.get_permitted_fieldnames(permission_type='read'))
    selected = get_allowed_source_fields(source_doctype)
    return {
        'exists': bool(frappe.db.exists(POLICY, source_doctype)),
        'can_manage': 'System Manager' in frappe.get_roles(),
        'fields': [dict(value=field.fieldname, label=field.label or field.fieldname,
            fieldtype=field.fieldtype, selected=field.fieldname in selected)
            for field in meta.fields if eligible(field) and field.fieldname in permitted],
    }


def migrate_legacy_fields():
    """Preserve valid approvals, grouped by source type; safe to run repeatedly."""
    grouped = {}
    for row in frappe.get_all('WhatsApp Message Template',
            fields=['template_doctype', 'allowed_source_fields'], limit_page_length=0):
        if not row.template_doctype:
            continue
        names = grouped.setdefault(row.template_doctype, set())
        try:
            previous = parse_allowed_fields(row.allowed_source_fields)
        except ValueError:
            previous = frozenset()
        meta = frappe.get_meta(row.template_doctype)
        names.update(field.fieldname for field in meta.fields if field.fieldname in previous and eligible(field))
    for source_doctype, names in grouped.items():
        if frappe.db.exists(POLICY, source_doctype):
            continue  # Never re-approve a field an administrator later removed.
        frappe.get_doc(dict(doctype=POLICY, source_doctype=source_doctype,
            allowed_fields=json.dumps(sorted(names)))).insert(ignore_permissions=True)


def static_sources():
    """Stable, collision-free namespaces for installed Single DocTypes."""
    from whatsapp_messaging.template_security import FIELD_NAME
    by_alias = {}
    for name in frappe.get_all('DocType', filters={'issingle': 1, 'is_virtual': 0}, pluck='name', order_by='name'):
        alias = frappe.scrub(name)
        if FIELD_NAME.fullmatch(alias):
            by_alias.setdefault(alias, []).append(name)
    return {alias: names[0] for alias, names in by_alias.items() if len(names) == 1}


@frappe.whitelist()
def editor_fields(source_doctype=None):
    """Offer source fields and every readable Single DocType, including empty policies.

    Only approved, readable field metadata is returned; no record values are sent
    to the editor. Empty groups can be configured once by a System Manager.
    """
    require_send_role()
    groups = []
    if source_doctype:
        data = options(source_doctype)
        groups.append(dict(label=source_doctype, source_doctype=source_doctype,
            section='template_doctype', **data))
    for alias, name in static_sources().items():
        try:
            if not frappe.has_permission(name, 'read'):
                continue
            data = options(name)
        except frappe.PermissionError:
            continue
        groups.append(dict(label=name, source_doctype=name, section='static.' + alias, **data))
    for group in groups:
        group['fields'] = [field for field in group['fields'] if field['selected']]
    return groups


def static_value(alias, fieldname):
    """Resolve a whitelisted Singleton field as the current execution user."""
    from whatsapp_messaging.template_security import TemplateSecurityError
    name = static_sources().get(alias)
    if not name or fieldname not in get_allowed_source_fields(name):
        raise TemplateSecurityError('The static field is not approved')
    doc = frappe.get_doc(name)
    doc.check_permission('read')
    field = doc.meta.get_field(fieldname)
    if not field or not eligible(field) or not doc.has_permlevel_access_to(fieldname, df=field, permission_type='read'):
        raise TemplateSecurityError('The static field is not readable or approved')
    return doc.get(fieldname)


def validate_static_access(message):
    """Recheck static field access immediately before a prepared send dispatches."""
    from whatsapp_messaging.template_security import PLACEHOLDER, FIELD_NAME
    for match in PLACEHOLDER.finditer(message or ''):
        parts = match.group(1).strip().split('.')
        if len(parts) == 3 and parts[0] == 'static' and all(FIELD_NAME.fullmatch(part) for part in parts):
            static_value(parts[1], parts[2])
