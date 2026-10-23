frappe.pages["whatsapp-inbox"].on_page_load = function(wrapper) {
 frappe.require("whatsapp_inbox.bundle.js", () => wrapper.whatsapp_page = new whatsapp_messaging.Inbox(wrapper));
};

frappe.pages['whatsapp-inbox'].on_page_show = function(wrapper) { if (wrapper.whatsapp_page?.onShow) wrapper.whatsapp_page.perform(() => wrapper.whatsapp_page.onShow()); };
