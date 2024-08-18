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
			"whatsapp_messaging.controller.ws_handle_on_custom_trigger",
		args: {
			template_name: template.name,
			doctype: frm.doctype,
			docname: frm.doc.name,
		},
		success: function (response) {
			if (response.message) {
				// Show success message
				frappe.msgprint({
					title: __("Success"),
					message: __("Message sent successfully"),
					indicator: "green",
				});
			}
		},
		error: function (response) {
			// Show error message
			frappe.msgprint({
				title: __("Error"),
				message: __("Failed to send message"),
				indicator: "red",
			});
		},
		freeze: true,
		freeze_message: __("Sending Message..."),
	});
}
