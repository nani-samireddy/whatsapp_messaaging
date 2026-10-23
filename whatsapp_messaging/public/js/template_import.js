const api = 'whatsapp_messaging.messaging.template_import.';

export function syncTemplatesDialog(accountName) {
    const escape = value => frappe.utils.escape_html(String(value || ''));
    const selected = new Set();
    let rows = [], loading = true, busy = false;
    const dialog = new frappe.ui.Dialog({
        title: __('Import templates from Meta'), size: 'extra-large',
        fields: [
            {fieldname: 'intro', fieldtype: 'HTML', options: `<p class="text-muted">${__('Choose templates to add to your local library. Existing templates are preserved. Numbered variables need source fields after import.')}</p>`},
            {fieldname: 'source_doctype', fieldtype: 'Link', options: 'DocType', label: __('Source DocType'), reqd: 1,
                description: __('The record type used to personalize the imported messages. You can change it on each template.'), onchange: () => updateAction()},
            {fieldtype: 'Column Break'},
            {fieldname: 'search', fieldtype: 'Data', label: __('Search templates'), onchange: () => render()},
            {fieldtype: 'Section Break'},
            {fieldname: 'summary', fieldtype: 'HTML'},
            {fieldname: 'templates', fieldtype: 'HTML'},
        ],
        primary_action_label: __('Import selected'),
        primary_action: async () => {
            if (loading || busy || !selected.size) return;
            const values = dialog.get_values();
            if (!values) return;
            busy = true; updateAction();
            try {
                const response = await frappe.call({method: api + 'import_selected', args: {
                    account_name: accountName, source_doctype: values.source_doctype,
                    catalogue_names: [...selected]
                }, freeze: true, freeze_message: __('Importing selected templates…')});
                const result = response.message;
                const links = result.imported.map(item => `<li><a href="#" data-template="${escape(item.name)}">${escape(item.name)}</a>${item.variables ? ` — ${__('Choose source fields for {0} variable(s)', [item.variables])}` : ''}</li>`).join('');
                dialog.fields_dict.summary.$wrapper.html(`<div class="alert alert-success">${__('Imported {0} template(s). Already imported: {1}.', [result.imported.length, result.existing.length])}${links ? `<ul class="mb-0 mt-2">${links}</ul>` : ''}</div>`);
                selected.clear();
                const refreshed = await frappe.call({method: api + 'options', args: {account_name: accountName}});
                rows = refreshed.message; render();
            } finally { busy = false; updateAction(); }
        }
    });
    function updateAction() {
        dialog.get_primary_btn().prop('disabled', loading || busy || !selected.size || !dialog.get_value('source_doctype'))
            .text(__('Import selected ({0})', [selected.size]));
    }
    function render() {
        const wrapper = dialog.fields_dict.templates.$wrapper;
        if (loading) {
            wrapper.html(`<p class="text-muted">${__('Fetching templates from Meta…')}</p>`); updateAction(); return;
        }
        const query = (dialog.get_value('search') || '').trim().toLowerCase();
        const visible = rows.filter(row => [row.template_name, row.language, row.status, row.category].join(' ').toLowerCase().includes(query));
        const eligible = visible.filter(row => row.can_import);
        wrapper.html(`<div class="d-flex align-items-center justify-content-between mb-3"><span class="text-muted">${__('Showing {0} of {1} templates', [visible.length, rows.length])}</span><button class="btn btn-default btn-xs" data-select-visible ${eligible.length ? '' : 'disabled'}>${__('Select available')}</button></div>
            <div style="max-height:440px;overflow:auto"><table class="table table-bordered" style="margin-bottom:0"><thead><tr><th style="width:35px"><input type="checkbox" data-select-all aria-label="${__('Select all available templates')}" ${eligible.length && eligible.every(row => selected.has(row.name)) ? 'checked' : ''} ${eligible.length ? '' : 'disabled'}></th><th>${__('Template / preview')}</th><th>${__('Language')}</th><th>${__('Meta status')}</th><th>${__('Import')}</th></tr></thead><tbody>
            ${visible.map(row => {
                const index = rows.indexOf(row);
                const preview = [row.header, row.body, row.footer].filter(Boolean).join('\n\n');
                const statusColor = row.status === 'APPROVED' ? 'green' : row.status === 'REJECTED' ? 'red' : 'orange';
                return `<tr><td><input type="checkbox" data-choice="${index}" aria-label="${escape(__('Import {0} ({1})', [row.template_name, row.language]))}" ${selected.has(row.name) ? 'checked' : ''} ${row.can_import ? '' : 'disabled'}></td>
                    <td style="min-width:240px"><strong>${escape(row.template_name)}</strong><div class="text-muted small">${escape(row.category)}</div><details><summary class="small text-muted">${__('Preview message')}</summary><div class="mt-2" style="white-space:pre-wrap;overflow-wrap:anywhere">${escape(preview)}</div></details></td>
                    <td>${escape(row.language)}</td><td><span class="indicator-pill ${statusColor}">${escape(row.status)}</span></td>
                    <td style="max-width:260px">${row.reason ? `<span class="small text-muted">${escape(row.reason)}</span>` : `<span>${__('Available')}</span>${row.variable_count ? `<div class="small text-muted">${__('{0} variable(s) to configure', [row.variable_count])}</div>` : ''}`}${row.existing ? `<div><a href="#" data-template="${escape(row.existing)}">${__('Open template')}</a></div>` : ''}</td></tr>`;
            }).join('') || `<tr><td colspan="5" class="text-muted">${rows.length ? __('No matching templates.') : __('No templates were returned by Meta for this Sender.')}</td></tr>`}</tbody></table></div>`);
        updateAction();
    }
    dialog.$wrapper.on('click', '[data-template]', event => {
        event.preventDefault(); dialog.hide();
        frappe.set_route('Form', 'WhatsApp Message Template', event.currentTarget.dataset.template);
    });
    dialog.fields_dict.templates.$wrapper.on('change', '[data-choice]', event => {
        const row = rows[Number(event.currentTarget.dataset.choice)];
        if (!row?.can_import) return;
        if (event.currentTarget.checked) selected.add(row.name); else selected.delete(row.name);
        render();
    }).on('change', '[data-select-all]', event => selectVisible(event.currentTarget.checked))
        .on('click', '[data-select-visible]', () => selectVisible(true));
    function selectVisible(checked) {
        const query = (dialog.get_value('search') || '').trim().toLowerCase();
        for (const row of rows) {
            if (row.can_import && [row.template_name, row.language, row.status, row.category].join(' ').toLowerCase().includes(query)) {
                if (checked) selected.add(row.name); else selected.delete(row.name);
            }
        }
        render();
    }
    dialog.show(); render();
    frappe.call({method: api + 'sync_options', args: {account_name: accountName}}).then(response => {
        rows = response.message.templates; loading = false; render();
    }).catch(() => {
        loading = false;
        dialog.fields_dict.templates.$wrapper.html(`<p class="text-danger">${__('Templates could not be fetched. Correct the reported connection or Sender settings, then close and reopen this dialog to retry.')}</p>`);
        updateAction();
    });
}
