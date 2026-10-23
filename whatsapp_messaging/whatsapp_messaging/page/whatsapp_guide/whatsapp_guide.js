frappe.pages['whatsapp-guide'].on_page_load = function(wrapper) {
    frappe.require('whatsapp_inbox.bundle.js', () => {
        wrapper.whatsapp_guide = new whatsapp_messaging.UserGuide(wrapper);
    });
};
frappe.pages['whatsapp-guide'].on_page_show = function(wrapper) {
    wrapper.whatsapp_guide?.show();
};
