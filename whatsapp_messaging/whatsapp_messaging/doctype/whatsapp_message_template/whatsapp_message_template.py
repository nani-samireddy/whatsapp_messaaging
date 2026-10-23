import frappe
import json
from whatsapp_messaging.messaging.field_policy import get_allowed_source_fields
from whatsapp_messaging.messaging.naming import set_record_values
from frappe.model.document import Document
from whatsapp_messaging.send_security import require_send_role


class WhatsAppMessageTemplate(Document):
    def before_validate(self):
        if self.meta.has_field('delivery_mode'):
            from whatsapp_messaging.messaging.template_editor import prepare
            prepare(self)

    def onload(self):
        from whatsapp_messaging.messaging.template_editor import review_values
        if self.get('delivery_mode'):
            self.update(review_values(self))

    def validate(self):
        from whatsapp_messaging.messaging.template_framing import validate
        try:
            validate(self.get('meta_header'), self.get('meta_footer'))
        except ValueError as exc:
            frappe.throw(str(exc))
        from whatsapp_messaging.messaging.template_content import resolve
        self.template_type = resolve(self.media, self.approved_template)['template_type']
        allowed = get_allowed_source_fields(self.template_doctype)
        self.allowed_source_fields = json.dumps(sorted(allowed))
        self.invalidate_cache()
        from whatsapp_messaging.messaging.campaigns import rule_type
        if not (frappe.flags.in_install or frappe.flags.in_migrate) and rule_type(self.name) != 'WhatsApp Campaign':
            # Activation and every material edit establish the execution principal.
            if self.automation_active:
                require_send_role()
                self.run_as = frappe.session.user
            elif self.has_value_changed("run_as"):
                before = self.get_doc_before_save()
                self.run_as = before.run_as if before else None
        if self.get("parameter_fields"):
            from whatsapp_messaging.template_security import FIELD_NAME
            values = json.loads(self.parameter_fields)
            if not isinstance(values, list) or any(not isinstance(f, str) or not FIELD_NAME.fullmatch(f) or f not in allowed for f in values):
                frappe.throw("Parameter fields must be an ordered list of approved source fields")

    def on_update(self):
        self.invalidate_cache()
        from whatsapp_messaging.messaging.campaigns import rule_type
        if rule_type(self.name) == 'WhatsApp Campaign':
            return  # Content edits never activate or reconfigure a campaign.
        # Pause schedules whenever a rule is disabled or explicitly deactivated.
        if self.schedule_record and (self.disable or not self.automation_active):
            set_record_values("WhatsApp Schedule", self.schedule_record, "state", "Paused")
        if self.schedule_record and self.automation_active and not self.disable:
            set_record_values("WhatsApp Schedule", self.schedule_record, "run_as", self.run_as)
        if self.automation_active and not self.disable and self.template_event in ("Scheduled", "Cron") and not (frappe.flags.in_install or frappe.flags.in_migrate):
            before = self.get_doc_before_save()
            timing = ("template_event", "schedule", "cron_interval", "custom_cron_format")
            if not self.schedule_record or not before or any(before.get(f) != self.get(f) for f in timing):
                from whatsapp_messaging.messaging.automation import save_schedule
                expression = None
                if self.template_event == "Cron":
                    expression = {"Hourly":"0 * * * *", "Daily":"0 0 * * *", "Weekly":"0 0 * * 0", "Monthly":"0 0 1 * *", "Yearly":"0 0 1 1 *"}.get(self.cron_interval)
                    if self.cron_interval == "Custom cron format":
                        expression = self.custom_cron_format
                    if not expression:
                        frappe.throw("Configure a valid recurrence")
                if self.template_event == "Scheduled" and not self.schedule:
                    frappe.throw("Choose a scheduled date and time")
                result = save_schedule(self.name, when=self.schedule if self.template_event == "Scheduled" else None, cron_expression=expression)
                self.schedule_record = result["name"]
                self.modified = frappe.db.get_value(self.doctype, self.name, 'modified')

    def on_trash(self):
        if self.schedule_record:
            set_record_values("WhatsApp Schedule", self.schedule_record, "state", "Paused")

    def invalidate_cache(self):
        frappe.cache.delete_value("template_doctypes_map")
