$(document).on("app_ready", function () {
  frappe.call({
    method:
      "whatsapp_messaging.whatsapp_messaging.doctype.whatsapp_message_template.whatsapp_message_template.get_template_doctypes",
    callback: function (response) {
      if (response.message) {
        var templates_details = response.message;
        $.each(Object.keys(templates_details), function (i, doctype) {
          frappe.ui.form.on(doctype, "refresh", function (frm) {
            addCustomButtons(frm, templates_details[doctype]);
          });
        });
      }
    },
  });
});

function addCustomButtons(frm, templates) {
  for (const template in templates) {
    frm.add_custom_button(
      templates[template].label,
      function () {
        sendWhatsAppMessage(frm, templates[template]);
      },
      __("WhatsApp Messaging"),
    );
  }
}

function sendWhatsAppMessage(frm, template) {
  frappe.call({
    method:
      "whatsapp_messaging.controller.whatsapp_messaging_on_custom_trigger_handler",
    args: {
      template_name: template.name,
      doctype: frm.doctype,
      docname: frm.doc.name,
    },
    callback: function (response) {
      if (response.message) {
        //@todo: show success message
      }
    },
  });
}
