// Copyright (c) 2024, nani-samireddy and contributors
// For license information, please see license.txt

// Custom script for the main DocType
frappe.ui.form.on("WhatsApp Message Template", {
	text_template_text_message: function (frm) {
		let message = frm.doc.text_template_text_message;
		let regex = /\{\{(\d+)\}\}/g;
		let matches = [];
		let match;

		// Find all matches
		while ((match = regex.exec(message)) !== null) {
			matches.push(parseInt(match[1], 10));
		}

		// Add unique matches to the child table
		matches = [...new Set(matches)]; // Remove duplicates
		matches.forEach((position) => {
			let exists = frm.doc.text_template_fields.some(
				(field) => field.field_position === position.toString(),
			);

			if (!exists) {
				let new_row = frm.add_child("text_template_fields");

				// Set the field position
				frappe.model.set_value(
					new_row.doctype,
					new_row.name,
					"field_position",
					position.toString(),
				);

				// Set default field type.
				frappe.model.set_value(
					new_row.doctype,
					new_row.name,
					"field_type",
					"This Doc",
				);

				// Set default doc type.
				frappe.model.set_value(
					new_row.doctype,
					new_row.name,
					"field_doc_type",
					frm.doc.template_doctype,
				);
			}
		});

		// Refresh the child table field
		frm.refresh_field("text_template_fields");
	},

	template_doctype: function (frm) {
		// Update the field doc type for all the child table rows if field type is "This Doc".
		frm.doc.text_template_fields.forEach((row, index) => {
			if (row.field_type === "This Doc") {
				if (row.field_doc_type !== frm.doc.template_doctype) {
					frappe.model.set_value(
						row.doctype,
						row.name,
						"field_doc_type",
						frm.doc.template_doctype,
					);

					// Clear the field name
					frappe.model.set_value(row.doctype, row.name, "field_name", "");

					// Set the options for the field name.
					update_child_table_field_options({ frm, cdn: row.name, fetch_from_doctype: frm.doc.template_doctype, table_field_name: "text_template_fields", select_field_name: "field_name" });
				}
			}
		});

		// Add phone number fields of template_doctype to phone_number_field_name as options
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'phone_number_field_name', ["Phone"]);

		// Update the target field options.
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'template_target_field');
	},

	is_single: function (frm) {
		// Add a custom button called Send Message if the is_single is checked.
		if (frm.doc.is_single) {
			frm.add_custom_button("Send Message", () => {
				frappe.call({
					method: "whatsapp_messaging.controller.ws_handle_on_single_template_trigger",

					args: {
						template_name: frm.doc.name,
						doctype: frm.doc.template_doctype,
					},
					callback: (r) => {
						if (r.message) {
							frappe.msgprint(r.message);
						}
					},
				});
			});
		}
	},

	media_attachment: function (frm) {
		// If the media attachment is set, set the media type to "Media".
		if (frm.doc.media_attachment) {
			uploadMediaFileToWhatsApp(frm, frm.doc.media_attachment);
		} else {
			// Clear the media_id field.
			frappe.model.set_value(frm.doctype, frm.docname, "media_id", "");

			// Save the form.
			frm.save('Save');
		}
	},

	// Trigger when the form is loaded or the child table is refreshed.
	onload_post_render: function (frm) {
		// Add phone number fields of template_doctype to phone_number_field_name as options
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'phone_number_field_name', ["Phone"]);

		// Update the target field options.
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'template_target_field');

		// Iterate over the child table rows and update the field options.
		frm.doc.text_template_fields.forEach((row, index) => {
			// Check if the field doc type is set.
			if ("field_doc_type" in row) {
				// Update the field options for the child table.
				update_child_table_field_options({ frm, cdn: row.name, fetch_from_doctype: row.field_doc_type, table_field_name: "text_template_fields", select_field_name: "field_name" });
			}
		});
	},

	// Trigger when the form is refreshed.
	refresh: function (frm) {
		// Add a custom button called Send Message if the is_single is checked.
		if (frm.doc.is_single) {
			frm.add_custom_button("Send Message", () => {
				frappe.call({
					method: "whatsapp_messaging.controller.ws_handle_on_single_template_trigger",

					args: {
						template_name: frm.doc.name,
						doctype: frm.doc.template_doctype,
					},
					callback: (r) => {
						if (r.message) {
							frappe.msgprint(r.message);
						}
					},
				});
			});
		}
	},
});

frappe.ui.form.on("Whatsapp Message Template Field", {

	field_type: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		if (row.field_type === "This Doc") {

			// Check if the field_type is "This Doc" and current field_doc_type is not equal to the template_doctype.
			if (row.field_doc_type !== frm.doc.template_doctype) {

				// Set the field_doc_type to the template_doctype.
				frappe.model.set_value(
					cdt,
					cdn,
					"field_doc_type",
					frm.doc.template_doctype,
				);

				// Clear the field_name.
				frappe.model.set_value(cdt, cdn, "field_name", "");

				// Set the options for the field name.
				update_child_table_field_options({ frm, cdn, fetch_from_doctype: frm.doc.template_doctype, table_field_name: "text_template_fields", select_field_name: "field_name" });

				// Make the field_static_value empty.
				frappe.model.set_value(cdt, cdn, "field_static_value", "");
			}

		} else if (row.field_type === "Other Doc") {

			// If the field doc is set update the options.
			if (row.field_doc_type) {
				update_child_table_field_options({ frm, cdn, fetch_from_doctype: row.field_doc_type, table_field_name: "text_template_fields", select_field_name: "field_name" });
			}

			// Clear the field_name.
			frappe.model.set_value(cdt, cdn, "field_name", "");

			// Make the field_static_value empty.
			frappe.model.set_value(cdt, cdn, "field_static_value", "");

		} else if (row.field_type === "Static") {

			// Clear the field_doc_type.
			frappe.model.set_value(cdt, cdn, "field_doc_type", "");

			// Clear the field_name.
			frappe.model.set_value(cdt, cdn, "field_name", "");

		}

		// Set the field properties based on the field type.
		set_field_properties(frm, row);
	},

	field_doc_type: function (frm, cdt, cdn) {
		update_child_table_field_options({ frm, cdn, fetch_from_doctype: locals[cdt][cdn].field_doc_type, table_field_name: "text_template_fields", select_field_name: "field_name" });
	},
});

/**
 * Function to update the phone number field options.
 *
 * @param {Object} frm - The form object.
 * @param {String} doctype - The doctype to fetch the fields from.
 * @param {String} target_field_name - The target field name to update the options.
 * @param {Array} input_fieldtypes - The input field types to filter the fields.
 */
function update_parent_doc_field_options(
	frm,
	doctype,
	target_field_name,
	input_fieldtypes = [],
) {
	if (!doctype || !target_field_name) {
		return;
	}

	// Get the field options from backend.
	frappe.call(
		"whatsapp_messaging.utils.get_input_fields",
		{
			doctype: doctype,
			input_fieldtypes: input_fieldtypes,
		},
	).then((r) => {
		if (r.message) {
			frm.fields_dict[target_field_name].df.options = r.message;
			frm.fields_dict[target_field_name].refresh();
		}
	});
}

/**
 * Function to update the field options for the child table.
 *
 * @param {Object} args - The arguments object.
 * @param {Object} args.frm - The form object.
 * @param {String} args.cdn - The child table row name.
 * @param {String} args.fetch_from_doctype - The doctype to fetch the fields from.
 * @param {String} args.table_field_name - The child table field name.
 * @param {String} args.select_field_name - The select field name.
 * @param {Array} args.input_types - The input types to filter the fields.
 */
function update_child_table_field_options({ frm, cdn, fetch_from_doctype, table_field_name, select_field_name, input_types = [] }) {
	if (!fetch_from_doctype || !table_field_name || !select_field_name) {
		return;
	}

	// Get the field options from the backend.
	frappe.call(
		"whatsapp_messaging.utils.get_input_fields",
		{
			doctype: fetch_from_doctype,
			input_fieldtypes: input_types,
		},
	).then((r) => {
		if (r.message) {
			let options = r.message;

			// Update field options for the child table.
			frappe.utils.filter_dict(frm.fields_dict[table_field_name].grid.grid_rows_by_docname[cdn].docfields, { 'fieldname': select_field_name })[0].options = options;
			frm.refresh();
		}
	});
}

/**
 * Function to set the field properties based on the field type.
 *
 * @param {*} frm - The form object.
 * @param {*} row - The child table row object.
 */
function set_field_properties(frm, row) {
	switch (row.field_type) {
		case "This Doc":
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_name").df.read_only = 0;
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_static_value").df.read_only = 1;
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_doc_type").df.read_only = 1;
			break;

		case "Other Doc":
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_doc_type").df.read_only = 0;
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_static_value").df.read_only = 1;
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_name").df.read_only = 0;
			break;

		case "Static":
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_doc_type").df.read_only = 1;
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_name").df.read_only = 1;
			frm.fields_dict.text_template_fields.grid.grid_rows_by_docname[row.name].get_field("field_static_value").df.read_only = 0;
			break;
	}

	frm.fields_dict.text_template_fields.grid.refresh();
}



/**
 * Uploads a media file to WhatsApp using the provided file name.
 *
 * This function first retrieves the file upload information from the server,
 * then creates a Blob and File object from the response, and finally uploads
 * the file to WhatsApp using the WhatsApp API.
 *
 * @param {Object} frm - The form object from which the function is called.
 * @param {string} fileName - The name of the file to be uploaded.
 * @returns {Promise<void>} - A promise that resolves when the file upload is complete.
 */
async function uploadMediaFileToWhatsApp(frm, fileName) {
	await frappe.call({
		method: "whatsapp_messaging.utils.wa_get_file_upload_info",
		args: {
			file_name: fileName
		},
		callback: async function (response) {
			console.log(response.message);
			if (!response.message) {
				console.error("File not found");
				return;
			}

			console.log("File upload info", response.message);

			const fileBlob = new Blob([response.message['file']], { type: response.message['content_type'] });
			const file = new File([fileBlob], fileName, { type: fileBlob.type });

			// Create formData to upload the file to WhatsApp.
			const formdata = new FormData();
			formdata.append("messaging_product", "whatsapp");
			formdata.append("file", file);

			// Request options for WhatsApp API
			const requestOptions = {
				method: "POST",
				body: formdata,
				headers: {
					"Authorization": `Bearer ${response.message['token']}`,
				}
			}

			console.log("Request options", requestOptions);

			for (var pair of formdata.entries()) {
				console.log(pair[0] + ', ' + pair[1]);
			}

			try {

				// Send the file to WhatsApp
				await fetch(response.message['url'], requestOptions).then((response) => {
					if (response.ok) {
						// Update the media_id in the form
						response.json().then((response) => {
							frappe.model.set_value(frm.doctype, frm.docname, "media_id", response.id);
							// Save the form
							frm.save('Save');
						});
					} else {

						// Clear the media_id in the form.
						frappe.model.set_value(frm.doctype, frm.docname, "media_id", "");
						// Save the form
						frm.save('Save');
					}
				});
			} catch (error) {
				console.error("Error uploading file to WhatsApp", error);

			}
		}
	});
}
