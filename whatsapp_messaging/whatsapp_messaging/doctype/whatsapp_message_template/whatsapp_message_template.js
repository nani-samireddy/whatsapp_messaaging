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

				// Set the options for the field name.
				update_template_field_option_names(frm);
			}
		});

		// Refresh the child table field
		frm.refresh_field("text_template_fields");
	},

	template_doctype: function (frm) {
		// Update the field doc type for all the child table rows if field type is "This Doc".
		frm.doc.text_template_fields.forEach((row, index) => {
			if (row.field_type === "This Doc") {
				frappe.model.set_value(
					row.doctype,
					row.name,
					"field_doc_type",
					frm.doc.template_doctype,
				);
			}
		});

		// Add phone number fields of template_doctype to phone_number_field_name as options
		update_phone_number_field_options(frm, frm.doc.template_doctype, ["Phone"]);
	},

	refresh: function (frm) {
		// Attach the change event to the child table.
		frm.fields_dict["text_template_fields"].grid.wrapper.on(
			"change",
			'input[data-fieldname="field_doc_type"]',
			function () {
				update_template_field_option_names(frm);
			},
		);

		// Add phone number fields of template_doctype to phone_number_field_name as options
		update_phone_number_field_options(frm, frm.doc.template_doctype, ["Phone"]);
	},

	// Trigger when the form is loaded or the child table is refreshed.
	onload_post_render: function (frm) {
		frm.fields_dict["text_template_fields"].grid.wrapper.on(
			"change",
			'input[data-fieldname="field_doc_type"]',
			function () {
				update_template_field_option_names(frm);
			},
		);

	},
});

function update_phone_number_field_options(frm, doctype, input_fieldtypes = []) {

	// Add default input field types.
	if (input_fieldtypes.length === 0) {
		input_fieldtypes = [
			"Data",
			"Select",
			"Date",
			"Datetime",
			"Time",
			"Currency",
			"Int",
			"Float",
			"Check",
			"Text",
			"Small Text",
			"Long Text",
			"Link",
			"Dynamic Link",
			"Password",
			"Phone",
			"Read Only",
			"Attach",
			"Attach Image",
		];
	}
	let options = [];
	frappe.model.with_doctype(doctype, () => {
		let fields = frappe.get_meta(doctype).fields;

		// Filter only input fields.
		let input_fields = fields.filter((field) =>
			input_fieldtypes.includes(field.fieldtype),
		);

		// Use fieldname as value.
		options = input_fields.map((field) => field.fieldname);

		frm.fields_dict["phone_number_field_name"].df.options = options;
		frm.fields_dict["phone_number_field_name"].refresh();
	});

	return options;
}

function update_template_field_option_names(frm) {
	frm.doc.text_template_fields.forEach((row, index) => {
		let field_doc_type = row.field_doc_type;
		if (field_doc_type) {
			frappe.model.with_doctype(field_doc_type, () => {
				let fields = frappe.get_meta(field_doc_type).fields;

				// Filter only input fields.
				let input_fieldtypes = [
					"Data",
					"Select",
					"Date",
					"Datetime",
					"Time",
					"Currency",
					"Int",
					"Float",
					"Check",
					"Text",
					"Small Text",
					"Long Text",
					"Link",
					"Dynamic Link",
					"Password",
					"Read Only",
					"Attach",
					"Attach Image",
				];

				// Use fieldname as value.
				let options = fields
					.filter((field) => input_fieldtypes.includes(field.fieldtype))
					.map((field) => field.fieldname);

				// Update field options for the child table.
				frm.fields_dict["text_template_fields"].grid.update_docfield_property(
					"field_name",
					"options",
					[""].concat(options),
				);

				// Refresh the specific field in the child table.
				frm.fields_dict["text_template_fields"].grid.refresh();
			});
		}
	});
}
