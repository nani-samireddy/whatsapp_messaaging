// Copyright (c) 2024, nani-samireddy and contributors
// For license information, please see license.txt
// Custom script for the main DocType
frappe.ui.form.on("WhatsApp Message Template", {
	refresh(frm) {
		setup_meta_editor(frm);
		frm.set_query('media', () => ({filters: {validation_status: 'Ready'}}));
		setup_message_composer(frm);
		update_template_content_type(frm);
		render_shared_source_fields(frm);
	},
	media: update_template_content_type,
	approved_template: update_template_content_type,
	delivery_mode(frm) {
		if (frm.doc.delivery_mode === 'Local message') frm.set_value('approved_template', null);
		setup_meta_editor(frm);
	},
	meta_footer(frm) { render_message_preview(frm); },
	meta_header(frm) { render_message_preview(frm); },

	template_doctype: function (frm) {
		render_shared_source_fields(frm);

	},

    is_single: function(frm) {
        // Campaign preview/start actions are provided by messaging_forms.js.
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

	onload_post_render(frm) {
		setup_message_composer(frm);

	},
	message_preview(frm) { sync_meta_examples(frm); render_message_preview(frm); },
	template_type(frm) { render_message_preview(frm); },
	template_name(frm) { render_message_preview(frm); },
	template_button_label(frm) { render_message_preview(frm); },

    // Scheduling and campaign actions are registered by messaging_forms.js.

});

const template_label_fields = [
	{value: 'template_name', label: __('Template name'), section: 'self'},
	{value: 'template_button_label', label: __('Button label'), section: 'self'},
];

function setup_message_composer(frm) {
	const caption = Boolean(frm.doc.media);
	frm.set_df_property('message_preview', 'label', caption ? __('Caption') : __('Message Text'));
	frm.set_df_property('message_preview', 'placeholder', caption ? __('Add a caption for your attachment…') : __('Write your message…'));
	frm.set_df_property('message_preview', 'description', caption
		? __('Sent below the attachment. Use Insert field to personalize the caption.')
		: __('Use Insert field to personalize the message with information from your records.'));
	const input = frm.fields_dict.message_preview.$input;
	if (input) {
		input.attr('rows', 9).css({'min-height': '210px', 'line-height': '1.6', 'resize': 'vertical'});
		// Keep the native Frappe control for dirty tracking and saving. Only the
		// preview listens to input, so typing never resets the cursor or selection.
		input.off('input.whatsapp-composer').on('input.whatsapp-composer', () => render_message_preview(frm, input.val()));
	}
	for (const field of ['meta_header','meta_footer']) {
		frm.fields_dict[field]?.$input?.attr('maxlength',60).off('input.whatsapp-framing').on('input.whatsapp-framing', () => render_message_preview(frm));
	}
	frm.fields_dict.meta_footer?.$input?.attr('rows',2).css({'height':'64px','min-height':'64px','resize':'vertical'});
	render_message_preview(frm);
}

async function render_shared_source_fields(frm) {
	const wrapper = frm.fields_dict.shared_source_fields.$wrapper;
	const source = frm.doc.template_doctype;
	const request = (frm.__field_picker_request || 0) + 1;
	frm.__field_picker_request = request;
	frm.__message_fields = [...template_label_fields];
	wrapper.empty().append($('<p class="text-muted small"></p>').text(__('Loading shared fields…')));
	try {
		const response = await frappe.call({method: 'whatsapp_messaging.messaging.field_policy.editor_fields', args: {source_doctype: source || null}});
		if (frm.__field_picker_request !== request || frm.doc.template_doctype !== source) return;
		const groups = [...response.message, {label: __('Template labels'), section: 'self', fields: template_label_fields}];
		frm.__message_fields = groups.flatMap(group => group.fields.map(field => ({...field, section: group.section})));
		setup_meta_editor(frm);
		const escape = frappe.utils.escape_html;
		wrapper.html(`<div class="wm-field-toolbar">
			<details class="wm-field-picker">
				<summary>${escape(__('Insert field'))}<span aria-hidden="true">⌄</span></summary>
				<div class="wm-field-menu">
					<label class="small text-muted">${escape(__('Field source'))}</label>
					<select class="form-control input-sm wm-field-source" aria-label="${escape(__('Field source'))}">
					${groups.map((group, i) => `<option value="${i}">${escape(group.section.startsWith('static.') ? __('Static: {0}', [group.label]) : group.label)}</option>`).join('')}
					</select>
					<input type="search" class="form-control input-sm" aria-label="${escape(__('Search message fields'))}" placeholder="${escape(__('Search fields…'))}">
					<div class="wm-field-options"></div>
					<div class="wm-field-policy-action"></div>
				</div>
			</details>
			<span class="wm-shared-note">${escape(__('Shared across templates'))}</span>
		</div>`);
		const open_policy = group => {
			if (group.exists) frappe.set_route('Form', 'WhatsApp Template Field Policy', group.source_doctype);
			else frappe.new_doc('WhatsApp Template Field Policy', {source_doctype: group.source_doctype});
		};
		if (groups[0].can_manage) {
			$('<button type="button" class="btn btn-xs btn-default"></button>').text(__('Manage fields')).on('click', () => open_policy(groups[0])).appendTo(wrapper.find('.wm-field-toolbar'));
		}
		const list = wrapper.find('.wm-field-options');
		const render_options = () => {
			const group = groups[Number(wrapper.find('select').val())];
			const query = wrapper.find('input[type=search]').val().toLowerCase();
			const matches = group.fields.filter(field => `${field.label} ${field.value}`.toLowerCase().includes(query));
			list.empty();
			for (const field of matches) {
				const button = $('<button type="button" class="wm-insert-field"></button>');
				button.append($('<span></span>').text(field.label), $('<small></small>').text(field.value));
				button.on('mousedown', event => event.preventDefault());
				button.on('click', () => {
					insert_message_field(frm, {...field, section: group.section});
					wrapper.find('details').prop('open', false);
				});
				list.append(button);
			}
			if (!matches.length) list.append($('<p class="text-muted small wm-field-empty"></p>').text(group.fields.length ? __('No matching fields.') : __('No fields approved yet. A System Manager can configure them once for all templates.')));
			const action = wrapper.find('.wm-field-policy-action').empty();
			if (group.can_manage) $('<button type="button" class="btn btn-xs btn-default"></button>').text(__('Configure shared fields')).on('click', () => open_policy(group)).appendTo(action);
		};
		render_options();
		wrapper.find('input[type=search]').on('input', render_options);
		wrapper.find('select').on('change', () => { wrapper.find('input[type=search]').val(''); render_options(); });
		wrapper.find('details').on('toggle', event => { if (event.target.open) wrapper.find('input[type=search]').trigger('focus'); });
	} catch (error) {
		if (frm.__field_picker_request !== request) return;
		wrapper.empty().append($('<p class="text-muted small"></p>').text(__('Shared fields could not be loaded. Check your access to the selected DocType.')));
	}
	render_message_preview(frm);
}

function insert_message_field(frm, field) {
	const input = frm.fields_dict.message_preview.$input?.get(0);
	if (!input || input.disabled || input.readOnly) return;
	const start = input.selectionStart ?? input.value.length;
	const end = input.selectionEnd ?? start;
	const token = `{{${field.section}.${field.value}}}`;
	const value = input.value.slice(0, start) + token + input.value.slice(end);
	frm.set_value('message_preview', value).then(() => {
		input.focus();
		input.setSelectionRange(start + token.length, start + token.length);
	});
}

async function load_preview_media(frm) {
	const name = frm.doc.media;
	frm.__preview_media = null;
	render_message_preview(frm);
	if (!name) return;
	try {
		const response = await frappe.db.get_value('WhatsApp Media', name, ['media_attachment']);
		if (frm.doc.media !== name) return;
		const file = response.message?.media_attachment || '';
		// Preview local attachments only. URL media are unsupported by sending.
		frm.__preview_media = {name, file: file.startsWith('/private/files/') ? file : ''};
		render_message_preview(frm);
	} catch (error) {
		// Detection still reports invalid or inaccessible media. The preview
		// keeps a neutral attachment card rather than fetching an arbitrary URL.
	}
}

function render_message_preview(frm, live_text) {
	const wrapper = frm.fields_dict.template_edit_trigger.$wrapper;
	const escape = frappe.utils.escape_html;
	const text = typeof live_text === 'string' ? live_text : (frm.fields_dict.message_preview.$input?.val() ?? frm.doc.message_preview ?? '');
	const fields = frm.__message_fields || template_label_fields;
	let missing = 0;
	const body = text.split(/(\{\{.*?\}\})/gs).map(part => {
		if (!part.startsWith('{{') || !part.endsWith('}}')) return escape(part);
		let path = part.slice(2, -2).trim();
		if (/^\d+$/.test(path)) path = (frm.doc.meta_examples || []).find(row => row.position === Number(path))?.source_path || path;
		const field = fields.find(item => `${item.section}.${item.value}` === path);
		if (field?.section === 'self') return escape(frm.doc[field.value] || field.label);
		if (!field) missing++;
		return `<span class="wm-preview-field${field ? '' : ' wm-preview-field-missing'}" title="${escape(path)}">${escape(field?.label || path)}</span>`;
	}).join('');
	const media = frm.doc.media;
	const header = frm.fields_dict.meta_header?.$input?.val() ?? frm.doc.meta_header ?? '';
	const footer = frm.fields_dict.meta_footer?.$input?.val() ?? frm.doc.meta_footer ?? '';
	const type = frm.doc.template_type;
	const file = media && frm.__preview_media?.name === media ? frm.__preview_media.file : '';
	let attachment = '';
	if (media && type === 'image' && file) {
		attachment = `<div class="wm-preview-image"><img src="${escape(file)}" alt="${escape(__('Selected image attachment'))}"><span>${escape(__('Image attachment'))}</span></div>`;
	} else if (media) {
		const label = type === 'document' ? __('PDF document') : type === 'image' ? __('Image attachment') : __('Attachment');
		attachment = `<div class="wm-preview-attachment"><span class="wm-attachment-icon" aria-hidden="true">${type === 'document' ? 'PDF' : '↗'}</span><div><strong>${escape(label)}</strong><small>${escape(file ? decode_preview_filename(file) : __('Selected media'))}</small></div></div>`;
	}
	wrapper.html(`${message_composer_styles()}
		<div class="wm-preview-heading"><span>${escape(__('Live Preview'))}</span><span class="wm-preview-kind">${escape(media ? __('Media + caption') : __('Text message'))}</span></div>
		<div class="wm-message-stage">
			<div class="wm-message-bubble">${attachment}${header ? `<div class="wm-message-header">${escape(header)}</div>` : ''}<div class="wm-message-body${text ? '' : ' wm-message-empty'}">${body || escape(media ? __('Your caption will appear here…') : __('Your message will appear here…'))}</div>${footer ? `<div class="wm-message-footer">${escape(footer)}</div>` : ''}
			<div class="wm-message-time">${escape(__('Preview'))}<span aria-hidden="true"> ✓✓</span></div></div>
		</div>
		<div class="wm-preview-footer"><span>${escape(__('Fields are replaced when the message is sent.'))}</span><span>${escape(__('{0} characters', [text.length]))}</span></div>
		${missing ? `<p class="wm-preview-warning">${escape(__('Some fields are unavailable. Choose approved fields from Insert field.'))}</p>` : ''}`);
}

function decode_preview_filename(file) {
	const name = file.split('/').pop();
	try { return decodeURIComponent(name); } catch (error) { return name; }
}

function message_composer_styles() {
	return `<style>
	.wm-field-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 12px;font-size:var(--text-sm)}
	.wm-shared-note{color:var(--text-muted);font-size:var(--text-xs);flex:1}
	.wm-field-picker{position:relative}
	.wm-field-picker summary{display:flex;align-items:center;gap:8px;cursor:pointer;padding:6px 10px;border:1px solid var(--border-color);border-radius:var(--border-radius);background:var(--control-bg);list-style:none;font-weight:500}
	.wm-field-picker summary::-webkit-details-marker{display:none}
	.wm-field-count{font-size:var(--text-xs);color:var(--text-muted);padding:0 5px;background:var(--bg-color);border-radius:4px}
	.wm-field-menu{position:absolute;top:calc(100% + 6px);left:0;width:320px;max-width:80vw;background:var(--fg-color);padding:12px;border:1px solid var(--border-color);border-radius:var(--border-radius-lg);box-shadow:var(--shadow-md);z-index:10}
	.wm-field-menu input[type=search]{margin-top:8px}
	.wm-field-empty{padding:12px 6px;margin:0}
	.wm-field-policy-action:not(:empty){padding-top:8px;border-top:1px solid var(--border-color)}
	.wm-field-options{max-height:260px;overflow:auto;margin-top:8px}
	.wm-field-group{padding:8px 6px 4px;color:var(--text-muted);font-size:var(--text-xs);font-weight:600}
	.wm-insert-field{display:flex;flex-direction:column;align-items:flex-start;text-align:left;width:100%;padding:7px 8px;gap:2px;background:transparent;border:0;border-radius:var(--border-radius);color:var(--text-color)}
	.wm-insert-field:hover,.wm-insert-field:focus{background:var(--control-bg)}
	.wm-insert-field small{color:var(--text-muted);font-size:var(--text-xs)}
	.wm-preview-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px;font-size:var(--text-sm);font-weight:500;color:var(--text-color)}
	.wm-preview-kind{font-size:var(--text-xs);font-weight:400;color:var(--text-muted)}
	.wm-message-stage{padding:24px 16px;min-height:268px;background:var(--subtle-fg);border:1px solid var(--border-color);border-radius:var(--border-radius-lg);display:flex;align-items:flex-start;justify-content:flex-end}
	.wm-message-bubble{width:100%;max-width:360px;background:var(--fg-color);border:1px solid var(--border-color);border-radius:12px 12px 3px 12px;box-shadow:var(--shadow-sm);overflow:hidden}
	.wm-message-body{padding:14px 14px 4px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:var(--text-sm);line-height:1.7;color:var(--text-color)}
	.wm-message-header{padding:14px 14px 0;font-size:var(--text-sm);font-weight:600;overflow-wrap:anywhere;color:var(--text-color)}
	.wm-message-footer{padding:8px 14px 0;font-size:var(--text-xs);overflow-wrap:anywhere;color:var(--text-muted)}
	.wm-message-empty{color:var(--text-muted)}
	.wm-preview-field{background:var(--blue-50);color:var(--blue-600);border-radius:4px;padding:1px 5px;box-decoration-break:clone;font-size:var(--text-xs);white-space:normal}
	.wm-preview-field-missing{background:var(--red-50);color:var(--red-600)}
	.wm-message-time{display:flex;justify-content:flex-end;gap:5px;padding:6px 12px 10px;font-size:10px;color:var(--text-muted)}
	.wm-message-time span{color:var(--blue-500)}
	.wm-preview-image{position:relative;margin:5px 5px 0;min-height:80px;background:var(--control-bg);border-radius:8px;overflow:hidden}
	.wm-preview-image img{display:block;width:100%;max-height:240px;object-fit:contain;position:relative;z-index:1;background:var(--control-bg)}
	.wm-preview-image>span{position:absolute;inset:24px 12px;text-align:center;color:var(--text-muted);font-size:var(--text-sm)}
	.wm-preview-attachment{display:flex;gap:12px;align-items:center;margin:6px;padding:14px;background:var(--control-bg);border-radius:8px}
	.wm-preview-attachment strong{display:block;font-size:var(--text-sm);font-weight:500}
	.wm-preview-attachment small{display:block;color:var(--text-muted);font-size:var(--text-xs);overflow-wrap:anywhere}
	.wm-attachment-icon{font-size:11px;font-weight:600;border:1px solid var(--border-color);border-radius:6px;padding:10px 6px;color:var(--text-muted)}
	.wm-preview-footer{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:10px;color:var(--text-muted);font-size:var(--text-xs)}
	.wm-preview-warning{font-size:var(--text-xs);color:var(--red-600);margin-top:8px}
	</style>`;
}


async function update_template_content_type(frm) {
	const request = (frm.__content_type_request || 0) + 1;
	frm.__content_type_request = request;
	setup_message_composer(frm);
	load_preview_media(frm);
	const media = frm.doc.media || null;
	const approved = frm.doc.approved_template || null;
	if (!media && !approved) {
		if (frm.doc.template_type !== 'text') await frm.set_value('template_type', 'text');
		return;
	}
	try {
		const response = await frappe.call({
			method: 'whatsapp_messaging.messaging.template_content.detect',
			args: {media_name: media, approved_template_name: approved}
		});
		if (frm.__content_type_request === request) {
			if (frm.doc.template_type !== response.message) await frm.set_value('template_type', response.message);
		}
	} catch (error) {
		// Frappe displays the server's permission/content error. Keep Type empty until corrected.
		if (frm.__content_type_request === request && frm.doc.template_type) await frm.set_value('template_type', '');
	}
}

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
			input_types: input_fieldtypes.length ? input_fieldtypes : null,
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

function setup_meta_editor(frm) {
    const meta = frm.doc.delivery_mode === 'Meta-approved template';
    frm.set_df_property('meta_section', 'hidden', !meta);
    if (meta && !frm.doc.meta_template_name && frm.doc.template_name) {
        const name = frm.doc.template_name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
        if (name) frm.set_value('meta_template_name', name);
    }
    const choices = ['', ...(frm.__message_fields || []).map(f => `${f.section}.${f.value}`)];
    frm.fields_dict.meta_examples?.grid.update_docfield_property('source_path', 'options', choices.join('\n'));
    if (frm.is_new()) return;
    frm.add_custom_button(__('New campaign'), () => frappe.new_doc('WhatsApp Campaign', {
        message_template:frm.doc.name, phone_number_id:frm.doc.phone_number_id
    }));
    const saved = () => {
        if (frm.is_dirty()) { frappe.msgprint(__('Save your changes first.')); return false; }
        return true;
    };
    const privileged = frappe.user.has_role('System Manager') || frappe.user.has_role('Whatsapp Admin');
    if (meta && privileged) {
        if (!['Submitting','Check submission outcome'].includes(frm.doc.meta_status)) {
            frm.add_custom_button(frm.doc.approved_template ? __('Submit changes to Meta') : __('Submit to Meta'), async () => {
                if (!saved()) return;
                const result = await frappe.call({method:'whatsapp_messaging.messaging.template_editor.submit',args:{name:frm.doc.name},freeze:true,freeze_message:__('Submitting the saved message and review examples to Meta…')});
                await frm.reload_doc();
                if (result.message?.message) frappe.msgprint(result.message.message);
            }, __('Meta'));
        }
        frm.add_custom_button(__('Check Meta status'), async () => {
            if (!saved()) return;
            await frappe.call({method:'whatsapp_messaging.messaging.template_editor.refresh_status',args:{name:frm.doc.name},freeze:true});
            await frm.reload_doc();
        }, __('Meta'));
    }
    frm.add_custom_button(__('Import existing Meta template'), async () => {
        if (!saved()) return;
        const response = await frappe.call({method:'whatsapp_messaging.messaging.template_editor.import_options',args:{account_name:frm.doc.phone_number_id}});
        const options = response.message.map(row => ({value:row.name,label:`${row.template_name} · ${row.language} · ${row.approval_status}`}));
        if (!options.length) { frappe.msgprint(__('No synced Meta templates are available for this account. An Admin can sync them from the Sender form.')); return; }
        frappe.prompt({fieldname:'catalogue_name',fieldtype:'Select',label:__('Existing Meta template'),options,reqd:1}, async values => {
            const imported = await frappe.call({method:'whatsapp_messaging.messaging.template_editor.import_content',args:{name:frm.doc.name,catalogue_name:values.catalogue_name}});
            const {meta_examples, ...fields} = imported.message;
            await frm.set_value(fields);
            frm.clear_table('meta_examples');
            for (const row of meta_examples) frm.add_child('meta_examples',row);
            frm.refresh_field('meta_examples');
            setup_meta_editor(frm); render_message_preview(frm);
            frappe.show_alert(__('Imported into this draft. Choose variable fields and Save.'));
        }, __('Import message content'), __('Import'));
    }, __('Meta'));
}

function sync_meta_examples(frm) {
    if (frm.doc.delivery_mode !== 'Meta-approved template') return;
    const tokens = [...(frm.doc.message_preview || '').matchAll(/\{\{(.*?)\}\}/gs)].map(m => m[1].trim());
    if (tokens.some(token => /^\d+$/.test(token))) return;
    const paths = [...new Set(tokens)];
    const old = frm.doc.meta_examples || [];
    if (old.length === paths.length && paths.every((p,i) => old[i].source_path === p)) return;
    const rows = paths.map((path,i) => ({position:i+1,source_path:path,sample_value:old.find(row => row.source_path===path)?.sample_value || ''}));
    frm.clear_table('meta_examples');
    for (const row of rows) frm.add_child('meta_examples',row);
    frm.refresh_field('meta_examples');
}

frappe.ui.form.on('WhatsApp Template Variable', {
    source_path(frm) { render_message_preview(frm); },
});
