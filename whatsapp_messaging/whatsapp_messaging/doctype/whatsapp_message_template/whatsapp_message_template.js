// Copyright (c) 2024, nani-samireddy and contributors
// For license information, please see license.txt
const isLoadingFields = false;
// Custom script for the main DocType
frappe.ui.form.on("WhatsApp Message Template", {

	template_doctype: function (frm) {
		// Add phone number fields of template_doctype to phone_number_field_name as options
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'phone_number_field_name', ["Phone"]);

		// Update the target field options.
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'template_target_field');

		schedule_example_update(frm);
	},

	template_header: function (frm) {
		schedule_example_update(frm);
	},

	template_footer: function (frm) {
		schedule_example_update(frm);
	},

	message_preview: function (frm) {
		schedule_example_update(frm);
	},

	is_single: function (frm) {
		// Add a custom button called Send Message if the is_single is checked.
		if (frm.doc.is_single) {
			frm.add_custom_button("Send Message", () => {
				frappe.call({
					method: "whatsapp_messaging.controller.wm_handle_on_single_template_trigger",

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
		if (!frm.doc.media_attachment) {
			// Clear the media_id field.
			frappe.model.set_value(frm.doctype, frm.docname, "media_id", "");
			frappe.model.set_value(frm.doctype, frm.docname, "wa_media_content_type", "");
			// Save the form.
			frm.save('Save');
		}
	},

	// Trigger when the form is loaded or the child table is refreshed.
	onload_post_render: function (frm) {
		const templateEditTriggerContainer = frm.fields_dict.template_edit_trigger.$wrapper;

		if (!templateEditTriggerContainer.find('#template_edit_trigger_button').length) {
			// Check if template editing should be allowed based on status
			const is_template_editable = check_template_editable(frm);
			
			if (is_template_editable) {
				templateEditTriggerContainer.append(`
					<button class="btn btn-secondary btn-sm" id="template_edit_trigger_button">
						Update Template
					</button>
				`);

				document.getElementById("template_edit_trigger_button").addEventListener("click", () => {
					open_template_editor_dialog(frm);
				});
			} else {
				// Show disabled state or message
				const status = frm.doc.status || 'Unknown';
				templateEditTriggerContainer.append(`
					<button class="btn btn-secondary btn-sm" disabled title="Template editing disabled - Status: ${status}">
						Update Template (Disabled)
					</button>
					<p class="text-muted small" style="margin-top: 5px;">
						Template editing is disabled because status is '${status}'. 
						Wait for approval or rejection to make changes.
					</p>
				`);
			}
		}

		// Add phone number fields of template_doctype to phone_number_field_name as options
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'phone_number_field_name', ["Phone"]);

		// Update the target field options.
		update_parent_doc_field_options(frm, frm.doc.template_doctype, 'template_target_field');

		render_filter_group(frm);
		refresh_filtered_records(frm);
		schedule_example_update(frm);
	},

	// Trigger when the form is refreshed.
	refresh: function (frm) {
		frm.clear_custom_buttons();
		// Add a custom button called Send Message if the is_single is checked.
		if (frm.doc.is_single) {
			frm.add_custom_button("Send Message", () => {
				frappe.call({
					method: "whatsapp_messaging.controller.wm_handle_on_single_template_trigger",

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

		// Determine button states based on status
		const status = frm.doc.status || "DRAFT";
		const has_template_id = !!frm.doc.whatsapp_template_id;
		const isInReview = status === "IN_REVIEW";

		toggle_fields_for_review_status(frm, isInReview);

		const isEditable = ["DRAFT", "APPROVED", "REJECTED", null, ""].includes(status);
		const canRequestReview = isEditable; // allowed in editable states
		const canSyncStatus = status === "IN_REVIEW" || has_template_id;

		// Request review button
		const requestBtn = frm.add_custom_button("Request review", () => {
			if (!is_template_status_requestable(frm.doc.status)) {
				frappe.msgprint(__("Template cannot be sent for review while status is '{0}'", [frm.doc.status]));
				return;
			}
			frappe.call({
				method: "whatsapp_messaging.utils.whatsapp_template_api.request_review",
				args: { template_name: frm.doc.name },
				callback: (r) => {
					if (r.message && r.message.success) {
						frm.reload_doc();
					}
				}
			});
		});
		set_button_state(requestBtn, canRequestReview, __("Template is already in review"));

		// Sync status button
		const syncBtn = frm.add_custom_button("Sync status", () => {
			if (!canSyncStatus) {
				return;
			}
			frappe.call({
				method: "whatsapp_messaging.utils.whatsapp_template_api.sync_template_status",
				args: { template_name: frm.doc.name },
				callback: () => frm.reload_doc()
			});
		});
		set_button_state(syncBtn, canSyncStatus, __("Sync becomes available after the template is submitted"));

		schedule_example_update(frm);
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
	schedule_example_update(frm);
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

/**
 * Check if template is editable based on status (server-side logic reflected in client)
 */
function check_template_editable(frm) {
	const status = frm.doc.status;
	const has_template_id = frm.doc.whatsapp_template_id;
	
	// If template not yet synced, allow editing
	if (!has_template_id) {
		return true;
	}
	
	// Non-editable statuses (based on server-side logic)
	const non_editable_statuses = ['IN_REVIEW', 'PENDING'];
	
	return !non_editable_statuses.includes(status);
}

function toggle_fields_for_review_status(frm, isInReview) {
	const fieldsToToggle = [
		// "template_header",
		// "template_footer",
		"whatsapp_template_language",
		"whatsapp_template_category",
		"media",
		"template_name"
	];

	fieldsToToggle.forEach((fieldname) => {
		frm.set_df_property(fieldname, "read_only", isInReview);
		frm.toggle_enable(fieldname, !isInReview);
		frm.refresh_field(fieldname);
	});
}

function set_button_state(button, enabled, tooltip) {
	if (!button) {
		return;
	}

	if (enabled) {
		button.removeClass("disabled");
		button.prop("disabled", false);
		if (tooltip) {
			button.attr("title", "");
		}
		return;
	}

	button.addClass("disabled");
	button.prop("disabled", true);
	if (tooltip) {
		button.attr("title", tooltip);
	}
}

function is_template_status_requestable(status) {
	return ["DRAFT", "APPROVED", "REJECTED", null, ""].includes(status);
}

const schedule_example_update = frappe.utils.debounce((frm) => {
	if (!frm || !frm.doc) {
		return;
	}

	const hasContent = Boolean(frm.doc.template_header || frm.doc.message_preview || frm.doc.template_footer);
	if (!frm.doc.template_doctype || !hasContent) {
		frm.doc.example = "";
		frm.refresh_field("example");
		return;
	}

	frappe.call({
		doc: frm.doc,
		method: "generate_example_preview",
		callback: (r) => {
			console.log(r);
			const payload = (r && r.message) || {};
			frm.doc.example = payload.example || payload.message || "";
			frm.refresh_field("example");
		}
	});
}, 400);

/**
 * Open template editor dialog
 */
function open_template_editor_dialog(frm) {
	if (!frm.doc || frm.doc.__islocal) {
		frappe.msgprint(__("Save the template before updating the message body."));
		return;
	}

	if (!frm.doc.template_doctype) {
		frappe.msgprint(__("Select a template DocType before updating the message body."));
		return;
	}

	let d = new frappe.ui.Dialog({
		title: 'Edit Message Template',
		fields: [
			{
				label: 'Field Selector',
				fieldname: 'field_selector',
				fieldtype: 'HTML'
			},
			{
				label: 'header',
				fieldname: 'header',
				fieldtype: 'Data',
				default: frm.doc.template_header || ""
			},
			{
				label: 'Message Template',
				fieldname: 'message_template',
				fieldtype: 'Long Text',
				default: frm.doc.message_preview || ""
			},
			{
				label: 'footer',
				fieldname: 'footer',
				fieldtype: 'Data',
				default: frm.doc.template_footer || ""
			}
		],
		size: 'extra-large',
		primary_action_label: 'Apply',
		primary_action(values) {
			frm.set_value("message_preview", values.message_template).then(() => {
				schedule_example_update(frm);
				return d.hide();
			});
		}
	});

	d.show();

	frappe.call({
		method: "whatsapp_messaging.utils.get_doctype_fields",
		args: {
			doctype: frm.doc.doctype,
			docname: frm.doc.name,
		},
		callback: (r) => {
			if (r.message && r.message.length > 0) {
				const doctypes = r.message;

				const renderFieldSelector = (activeIndex = 0) => {
					setTimeout(() => {
						const wrapper = d.fields_dict.field_selector.$wrapper.get(0);
						const activeDoctype = doctypes[activeIndex];

						// Group fields
						const fieldsByType = {};
						activeDoctype.fields.filter(f => !f.hidden).forEach(f => {
							if (!fieldsByType[f.fieldtype]) fieldsByType[f.fieldtype] = [];
							fieldsByType[f.fieldtype].push(f);
						});

						// Build grouped HTML
						const groupedHTML = Object.keys(fieldsByType).map(fieldtype => `
							<div style="margin-bottom: 20px;">
								<h5 style="margin-bottom: 10px;">${fieldtype}</h5>
								<div style="display: flex; flex-wrap: wrap; gap: 8px;">
									${fieldsByType[fieldtype].map(f => `
										<button class="btn btn-sm btn-outline-secondary"
											data-section="${activeDoctype.fieldname}"
											data-field="${f.fieldname}">
											${f.label}
										</button>
									`).join("")}
								</div>
							</div>
						`).join("");

						// Inject into UI
						wrapper.innerHTML = `
							<div style="display: flex; gap: 20px;">
								<div id="doctype-sidebar" style="width: 200px; border-right: 1px solid #ddd;">
									${doctypes.map((dt, i) => `
										<div class="doctype-item ${i === activeIndex ? 'active' : ''}"
											data-index="${i}"
											style="padding: 8px; cursor: pointer; background: ${i === activeIndex ? '#f0f0f0' : 'transparent'};">
											${dt.label}
										</div>
									`).join("")}
								</div>
								<div style="flex: 1; padding: 10px;">
									<p class="underline"><strong>Fields from <em>${activeDoctype.label}</em></strong></p>
									<div id="field-buttons-container">
										${groupedHTML}
									</div>
								</div>
							</div>
						`;

						// Attach click handlers to field buttons
						wrapper.querySelectorAll('button[data-field]').forEach(btn => {
							btn.addEventListener('click', () => {
								const section = btn.dataset.section;
								const field = btn.dataset.field;
								const textarea = d.fields_dict.message_template.$wrapper.find('textarea')[0];

								if (textarea) {
									const cursorPos = textarea.selectionStart;
									const currentVal = textarea.value;
									const insertText = `{{${section}.${field}}}`;
									textarea.value = currentVal.slice(0, cursorPos) + insertText + currentVal.slice(cursorPos);
									textarea.focus();
									textarea.selectionStart = textarea.selectionEnd = cursorPos + insertText.length;
								}
							});
						});

						// Sidebar click events
						wrapper.querySelectorAll('.doctype-item').forEach(item => {
							item.addEventListener('click', () => {
								const index = parseInt(item.dataset.index);
								renderFieldSelector(index);
							});
						});
					}, 100);
				};

				renderFieldSelector();
			} else {
				frappe.msgprint("No fields found for the selected doctype.");
			}
		}
	});
}
