frappe.pages["whatsapp-automations"].on_page_load = function(wrapper) {
 frappe.require("whatsapp_inbox.bundle.js", () => wrapper.whatsapp_page = new whatsapp_messaging.Automation(wrapper));
};

frappe.pages['whatsapp-automations'].on_page_show = function(wrapper) { if (wrapper.whatsapp_page?.onShow) wrapper.whatsapp_page.perform(() => wrapper.whatsapp_page.onShow()); };
