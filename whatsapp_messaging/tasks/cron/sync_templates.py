import frappe


def sync_in_review_templates():
    """Find templates in IN_REVIEW and sync their status from WhatsApp."""
    try:
        frappe.log_error("Starting sync of IN_REVIEW templates")
        names = frappe.get_all(
            "WhatsApp Message Template",
            filters={"status": "IN_REVIEW"},
            pluck="name",
        )
        for name in names:
            try:
                frappe.call(
                    "whatsapp_messaging.utils.whatsapp_template_api.sync_template_status",
                    template_name=name,
                )
            except Exception:
                frappe.log_error(f"Failed to sync template status for {name}")
    except Exception:
        frappe.log_error("Failed to list IN_REVIEW templates for syncing")
