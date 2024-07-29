
// frappe.ui.form.on('*', {
// 	setup: function (frm) {
// 		console.log("Form setup");
// 	},
// 	refresh: function (frm) {
// 		console.log("Form refresh");
// 		// Skip if it's the Template doctype itself to prevent circular reference
// 		if (frm.doc.doctype === 'WhatsApp Message Template') return;

// 		// Fetch Template document where template_doctype equals the current Doctype
// 		frappe.call({
// 			method: 'frappe.client.get_list',
// 			args: {
// 				doctype: 'WhatsApp Message Template',
// 				filters: {
// 					'template_doctype': frm.doc.doctype
// 				},
// 				fields: ['name']
// 			},
// 			callback: function (response) {
// 				console.log(response);
// 				if (response.message && response.message.length > 0) {
// 					// If a Template document exists, add a button
// 					frm.add_custom_button(__('Apply Template'), function () {
// 						// Define your button action here
// 						frappe.msgprint(__('Button clicked!'));
// 					}, __('Actions'));

// 				}
// 			}
// 		});
// 	}
// });

