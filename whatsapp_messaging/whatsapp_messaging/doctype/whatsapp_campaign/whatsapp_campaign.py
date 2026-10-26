import frappe
from frappe.model.document import Document
from whatsapp_messaging.messaging.naming import set_record_values
from whatsapp_messaging.send_security import require_send_role


class WhatsAppCampaign(Document):
    def validate(self):
        require_send_role()
        template=frappe.get_doc('WhatsApp Message Template',self.message_template)
        template.check_permission('read')
        self.template_doctype=template.template_doctype
        if self.template_event=='Date Reminder':
            if self.is_single:frappe.throw('Date reminders use their daily schedule. Turn off bulk sending.')
            from frappe.utils import get_system_timezone
            from whatsapp_messaging.messaging.automation import validate_date_reminder
            self.reminder_timezone=self.reminder_timezone or get_system_timezone()
            validate_date_reminder(self)
        sender=frappe.get_doc('WhatsApp Phone Number ID',self.phone_number_id)
        sender.check_permission('read')
        if template.get('delivery_mode')=='Meta-approved template':
            template_waba=frappe.db.get_value('WhatsApp Phone Number ID',template.phone_number_id,'waba_id')
            if not sender.waba_id or sender.waba_id!=template_waba:
                frappe.throw('Choose a Sender from the same WABA as this Meta template.')
        migrating=bool(self.flags.from_template_migration or frappe.flags.in_migrate or frappe.flags.in_install)
        if not migrating:
            if self.automation_active:
                self.run_as=frappe.session.user
            else:
                previous=self.get_doc_before_save()
                self.run_as=previous.run_as if previous else None
        frappe.cache.delete_value('template_doctypes_map')

    def on_update(self):
        if self.flags.from_template_migration or frappe.flags.in_migrate or frappe.flags.in_install:return
        if self.schedule_record and (self.disable or not self.automation_active):
            set_record_values('WhatsApp Schedule',self.schedule_record,'state','Paused')
        elif self.schedule_record:
            set_record_values('WhatsApp Schedule',self.schedule_record,'run_as',self.run_as)
        if self.automation_active and not self.disable and self.template_event in ('Scheduled','Cron','Date Reminder'):
            before=self.get_doc_before_save()
            timing=('template_event','schedule','cron_interval','custom_cron_format','reminder_date_field','reminder_days_before','reminder_time','reminder_timezone')
            paused=self.schedule_record and frappe.db.get_value('WhatsApp Schedule',self.schedule_record,'state')=='Paused'
            if not self.schedule_record or not before or paused or any(before.get(f)!=self.get(f) for f in timing):
                from whatsapp_messaging.messaging.automation import save_schedule
                expression=None
                if self.template_event=='Date Reminder':
                    from whatsapp_messaging.messaging.reminders import daily_cron
                    expression=daily_cron(self.reminder_time)
                if self.template_event=='Cron':
                    expression={'Hourly':'0 * * * *','Daily':'0 0 * * *','Weekly':'0 0 * * 0','Monthly':'0 0 1 * *','Yearly':'0 0 1 1 *'}.get(self.cron_interval)
                    if self.cron_interval=='Custom cron format':expression=self.custom_cron_format
                    if not expression:frappe.throw('Configure a valid recurrence.')
                result=save_schedule(self.name,when=self.schedule if self.template_event=='Scheduled' else None,cron_expression=expression,timezone_name=self.reminder_timezone if self.template_event=='Date Reminder' else None)
                self.schedule_record=result['name']
                self.modified=frappe.db.get_value(self.doctype,self.name,'modified')

    def on_trash(self):
        if self.schedule_record:set_record_values('WhatsApp Schedule',self.schedule_record,'state','Paused')
