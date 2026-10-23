def execute():
    import frappe
    from whatsapp_messaging.messaging.media_library import READY_MESSAGE
    # No migration uploads: existing assets require a deliberate save or retry.
    for row in frappe.get_all('WhatsApp Media', fields=['name', 'cloud_status', 'validation_status'], limit_page_length=0):
        values = {}
        if not row.cloud_status:
            values['cloud_status'] = 'Not Uploaded'
        if row.validation_status == 'Ready':
            values['validation_message'] = READY_MESSAGE
        if values:
            frappe.db.set_value('WhatsApp Media', row.name, values, update_modified=False)
