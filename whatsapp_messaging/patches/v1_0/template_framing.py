def execute():
    import frappe
    from whatsapp_messaging.messaging.catalogue import normalize
    from whatsapp_messaging.messaging.common import parsed
    from whatsapp_messaging.messaging.template_editor import refresh_related

    # Re-evaluate stored components without fetching Meta, changing content,
    # activating campaigns or publishing queued work.
    for row in frappe.get_all('WhatsApp Approved Template',
            fields=['name','components_json','approval_status','language']):
        components = parsed(row.components_json,[])
        if not components:
            continue
        normalized = normalize(dict(components=components,
            status=row.approval_status,language=row.language))
        values = {field:normalized[field] for field in ('supported','schema_hash')}
        frappe.db.set_value('WhatsApp Approved Template',row.name,values,update_modified=False)
        refresh_related(row.name)
