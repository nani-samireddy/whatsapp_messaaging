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
		// If media is not attached, clear the media_id field.
		if ( ! frm.doc.media_attachment ) {
			// Clear the media_id field.
			frappe.model.set_value(frm.doctype, frm.docname, "media_id", "");
			frappe.model.set_value(frm.doctype, frm.docname, "wa_media_content_type", "");
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

		render_filter_group(frm);
		refresh_filtered_records(frm);
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

function render_filter_group(frm) {
    let filter_wrapper = frm.fields_dict.filtered_records_html.$wrapper;

    // Check if a Template Doctype is selected
    if (!frm.doc.template_doctype) {
		filter_wrapper.empty();
        filter_wrapper.append(`<p style="color: red;">Please select a Template Doctype first.</p>`);
        return;
    }

    frappe.model.with_doctype(frm.doc.template_doctype, () => {

		frm.filter_group = new frappe.ui.FilterGroup({
            doctype: frm.doc.template_doctype,
            // parent: filter_wrapper,
			filter_button: frm.fields_dict.update_query_button.$input,
            on_change: function () {
                save_filters(frm);
            }
        });

        // Load stored filters from query_filters
        let stored_filters = frm.doc.query_filters ? JSON.parse(frm.doc.query_filters).filters : [];
        if (stored_filters && Array.isArray(stored_filters)) {
            frm.filter_group.add_filters(stored_filters);
        }
    });
}

function save_filters(frm) {
    let filters = frm.filter_group ? frm.filter_group.get_filters() : [];
    let filter_data = JSON.stringify({
        doctype: frm.doc.template_doctype,
        filters: filters
    });

    frm.set_value('query_filters', filter_data);
    refresh_filtered_records(frm);
}

async function refresh_filtered_records(frm) {
    let filter_data = frm.doc.query_filters ? JSON.parse(frm.doc.query_filters) : null;
    let wrapper = frm.fields_dict.filtered_records_html.$wrapper;

    wrapper.empty();

    if (!frm.doc.template_doctype) {
        wrapper.append(`<p style="margin-top: 10px; color: red;">Please select a Template Doctype to fetch records.</p>`);
        return;
    }

    let filters = filter_data ? filter_data.filters : [];

    // Fetch count of the records and display it
	await frappe.db.count(frm.doc.template_doctype, { filters: filters }).then((count) => {
		wrapper.append(
			`<p style="margin-top: 10px; font-weight: bold;">
				Number of records: ${count}
			</p>`
		);
	});
}
