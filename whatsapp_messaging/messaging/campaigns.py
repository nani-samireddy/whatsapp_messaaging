"""Campaign configuration references reusable message content; no content copies."""
import frappe
from .common import digest

DOCTYPE = 'WhatsApp Campaign'
TEMPLATE = 'WhatsApp Message Template'
CONTENT = ('template_name','message_preview','media','template_type','approved_template','parameter_fields',
    'allowed_source_fields','delivery_mode','meta_template_name','meta_language','meta_category','meta_header','meta_footer','meta_examples')
CONFIG = ('phone_number_id','template_doctype','template_button_label','phone_number_field_name','other_recipients',
    'is_single','disable','template_event','schedule','schedule_job_type_link','schedule_status','cron_interval',
    'custom_cron_format','query_filters','template_target_field','automation_active','run_as','schedule_record')


def rule_type(name):
    return DOCTYPE if frappe.db.has_table(DOCTYPE) and frappe.db.exists(DOCTYPE,name) else TEMPLATE


def load(name,check_permissions=True):
    doc=frappe.get_doc(rule_type(name),name)
    if check_permissions:doc.check_permission('read')
    if doc.doctype==DOCTYPE:
        template=frappe.get_doc(TEMPLATE,doc.message_template)
        if check_permissions:template.check_permission('read')
        if template.template_doctype!=doc.template_doctype:
            frappe.throw('The template source DocType changed. Review and save this campaign.')
        doc.update({field:template.get(field) for field in CONTENT})
        # Freeze both versions so editing shared content invalidates pending work.
        doc.modified=digest(str(doc.modified),str(template.modified))
    return doc


def version(name):
    return str(load(name).modified)


def definitions(filters):
    """Legacy API callers remain readable; migrated templates run only once."""
    if frappe.db.has_table(DOCTYPE):
        for name in frappe.get_all(DOCTYPE,filters=filters,pluck='name'):
            yield load(name,check_permissions=False)
    for name in frappe.get_all(TEMPLATE,filters=filters,pluck='name'):
        if rule_type(name)==TEMPLATE:
            # Newly authored content has no event configuration; only old API
            # rules with explicit events can reach this compatibility branch.
            yield load(name,check_permissions=False)


def backfill():
    """Split existing records without sending or changing an execution user."""
    for name in frappe.get_all(TEMPLATE,pluck='name'):
        if frappe.db.exists(DOCTYPE,name):continue
        source=frappe.get_doc(TEMPLATE,name)
        values={field:source.get(field) for field in CONFIG}
        values['other_recipients']=[{'static_recipient':row.static_recipient} for row in source.other_recipients]
        campaign=frappe.get_doc(dict(doctype=DOCTYPE,campaign_name=name,message_template=name,**values))
        campaign.flags.from_template_migration=True
        campaign.insert(ignore_permissions=True,set_name=name)
        frappe.db.set_value(DOCTYPE,name,dict(modified=source.modified,creation=source.creation,
            owner=source.owner,modified_by=source.modified_by),update_modified=False)
    for target in ('WhatsApp Outbox','WhatsApp Schedule','WhatsApp Automation Run'):
        for row in frappe.get_all(target,fields=['name','rule'],filters={'rule':['is','set']}):
            frappe.db.set_value(target,row.name,'rule_doctype',rule_type(row.rule),update_modified=False)
    frappe.cache.delete_value('template_doctypes_map')
