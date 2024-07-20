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
        frappe.model.set_value(
          new_row.doctype,
          new_row.name,
          "field_position",
          position.toString(),
        );
      }
    });

    // Refresh the child table field
    frm.refresh_field("text_template_fields");
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
  },

  // Trigger when the form is loaded or the child table is refreshed
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
        console.log(options);
        console.log(frm.doc.name);

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

// // Custom script for the child DocType
// frappe.ui.form.on("Whatsapp Message Template Field", {
//   field_doc_type: function (frm, cdt, cdn) {
//     let child = locals[cdt][cdn];
//     if (child.field_doc_type) {
//       frappe.model.with_doctype(child.field_doc_type, () => {
//         let fields = frappe.get_meta(child.field_doc_type).fields;

//         // Filter only input fields
//         let input_fieldtypes = [
//           "Data",
//           "Select",
//           "Date",
//           "Datetime",
//           "Time",
//           "Currency",
//           "Int",
//           "Float",
//           "Check",
//           "Text",
//           "Small Text",
//           "Long Text",
//           "Link",
//           "Dynamic Link",
//           "Password",
//           "Read Only",
//           "Attach",
//           "Attach Image",
//         ];

//         let options = fields
//           .filter((field) => input_fieldtypes.includes(field.fieldtype))
//           .map((field) => field.fieldname); // Use fieldname as value

//         console.log(options);
//         // Update field options for the child table
//         frappe.meta.get_docfield(
//           "Whatsapp Message Template Field",
//           "field_name",
//           frm.doc.name,
//         ).options = options.join("\n");

//         // Refresh the specific field in the child table
//         frm.fields_dict["text_template_fields"].grid.grid_rows_by_docname[
//           cdn
//         ].refresh_field("field_name");
//       });
//     }
//   },
// });
