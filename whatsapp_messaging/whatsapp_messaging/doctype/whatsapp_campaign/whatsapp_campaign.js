(() => {
frappe.ui.form.on('WhatsApp Campaign', {
    refresh(frm) { campaign_source_fields(frm); campaign_summary(frm); },
    async message_template(frm) {
        if (!frm.doc.message_template) return;
        const template = await frappe.db.get_doc('WhatsApp Message Template',frm.doc.message_template);
        await frm.set_value('template_doctype',template.template_doctype);
        if (!frm.doc.phone_number_id) await frm.set_value('phone_number_id',template.phone_number_id);
        campaign_source_fields(frm); campaign_summary(frm);
    },
    template_doctype(frm) { campaign_source_fields(frm); },
    template_event(frm) {
        if (frm.doc.template_event === 'Date Reminder' && !frm.doc.reminder_timezone)
            frm.set_value('reminder_timezone',frappe.boot.time_zone?.system || frappe.sys_defaults.time_zone);
        campaign_source_fields(frm);
    },
});
function campaign_source_fields(frm) {
    update_parent_doc_field_options(frm,frm.doc.template_doctype,'phone_number_field_name',['Phone']);
    update_parent_doc_field_options(frm,frm.doc.template_doctype,'template_target_field');
    update_parent_doc_field_options(frm,frm.doc.template_doctype,'reminder_date_field',['Date']);
    render_filter_group(frm); refresh_filtered_records(frm);
}
async function campaign_summary(frm) {
    const request = (frm.__summary_request || 0) + 1;
    frm.__summary_request = request;
    const wrapper=frm.fields_dict.message_summary.$wrapper;
    wrapper.empty();
    if (!frm.doc.message_template) { wrapper.text(__('Choose a reusable message template. Define message content and Meta approval in Templates.')); return; }
    const selected=frm.doc.message_template;
    const template=await frappe.db.get_doc('WhatsApp Message Template',selected);
    if (frm.doc.message_template!==selected || frm.__summary_request!==request) return;
    const card=$('<div style="padding:14px;background:var(--subtle-fg);border-radius:var(--border-radius);margin:10px 0"></div>');
    $('<strong></strong>').text(template.template_name).appendTo(card);
    const mode = template.delivery_mode || 'Local message';
    const summary = mode === 'Meta-approved template' ? `${mode} · ${template.meta_status || 'Draft'}` : mode;
    $('<div class="text-muted small" style="margin:6px 0"></div>').text(summary).appendTo(card);
    if (template.meta_header) $('<strong></strong>').text(template.meta_header).appendTo(card);
    $('<div style="white-space:pre-wrap;overflow-wrap:anywhere;margin:10px 0"></div>').text(template.message_preview || __('No message content yet.')).appendTo(card);
    if (template.meta_footer) $('<div class="small text-muted"></div>').text(template.meta_footer).appendTo(card);
    $('<button type="button" class="btn btn-default btn-xs"></button>').text(__('Open template')).on('click',()=>frappe.set_route('Form','WhatsApp Message Template',selected)).appendTo(card);
    wrapper.empty().append(card);
}
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
			input_types: input_fieldtypes.length ? input_fieldtypes : null,
		},
	).then(async (r) => {
		if (r.message) {
            let options = r.message;
            if (target_field_name === 'reminder_date_field') {
                await frappe.model.with_doctype(doctype);
                const fields = frappe.get_meta(doctype).fields;
                options = options.map(value => ({value, label: __(fields.find(field => field.fieldname === value)?.label || value)}));
            }
            if (frm.doc.template_doctype !== doctype) return;
			frm.fields_dict[target_field_name].df.options = options;
			frm.fields_dict[target_field_name].refresh();
		}
	});
}



function render_filter_group(frm) {
	let filter_wrapper = frm.fields_dict.filtered_records_html.$wrapper;

	// Check if a Source DocType is selected
	if (!frm.doc.template_doctype) {
		filter_wrapper.empty();
		filter_wrapper.append(`<p style="color: red;">Please select a Source DocType first.</p>`);
		return;
	}

	const source = frm.doc.template_doctype;
	if (frm.__filter_source === source && frm.filter_group) return;
	frappe.model.with_doctype(source, () => {
		if (frm.doc.template_doctype !== source || (frm.__filter_source === source && frm.filter_group)) return;
		const button = frm.fields_dict.update_query_button.$input;
		if (frm.filter_group) button.off('click shown.bs.popover hidden.bs.popover').popover('dispose');
		frm.__filter_source = source;
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
    const request = (frm.__count_request || 0) + 1;
    frm.__count_request = request;
	let filter_data = frm.doc.query_filters ? JSON.parse(frm.doc.query_filters) : null;
	let wrapper = frm.fields_dict.filtered_records_html.$wrapper;

	wrapper.empty();

	if (!frm.doc.template_doctype) {
		wrapper.append(`<p style="margin-top: 10px; color: red;">Please select a Source DocType to fetch records.</p>`);
		return;
	}

	let filters = filter_data ? filter_data.filters : [];

	// Fetch count of the records and display it
	await frappe.db.count(frm.doc.template_doctype, { filters: filters }).then((count) => {
		if (frm.__count_request !== request) return;
		wrapper.html(
			`<p style="margin-top: 10px; font-weight: bold;">
				Number of records: ${count}
			</p>`
		);
	});
}


})();
