frappe.ui.form.on('WhatsApp Template Field Policy', {
    refresh: render_shared_field_picker,
    source_doctype: render_shared_field_picker,
});

async function render_shared_field_picker(frm) {
    const wrapper = frm.fields_dict.field_picker.$wrapper;
    const source = frm.doc.source_doctype;
    wrapper.empty();
    if (!source) {
        wrapper.text(__('Choose a source DocType to see the available message fields.'));
        return;
    }
    const response = await frappe.call({method: 'whatsapp_messaging.messaging.field_policy.options', args: {source_doctype: source}});
    if (frm.doc.source_doctype !== source) return;
    const data = response.message;
    const escape = frappe.utils.escape_html;
    const selected = new Set(JSON.parse(frm.doc.allowed_fields || '[]'));
    wrapper.html(`<p class="text-muted">${escape(__('Applies to every template using {0}. Save after choosing fields. Unchecking a field revokes its use in all of those templates.', [source]))}</p>
        <input class="form-control input-sm" type="search" placeholder="${escape(__('Find a field'))}" aria-label="${escape(__('Find a field'))}">
        <div class="shared-field-options" style="max-height:420px;overflow:auto;margin-top:var(--margin-sm)">
        ${data.fields.map(field => `<label class="shared-field-choice" style="display:flex;gap:var(--margin-sm);padding:var(--padding-sm);border-bottom:1px solid var(--border-color);align-items:center">
            <input type="checkbox" data-field="${escape(field.value)}" ${selected.has(field.value) ? 'checked' : ''} ${data.can_manage ? '' : 'disabled'}>
            <span><span>${escape(field.label)}</span><br><small class="text-muted">${escape(field.value)} · ${escape(field.fieldtype)}</small></span>
        </label>`).join('') || `<p class="text-muted">${escape(__('No eligible fields are available.'))}</p>`}</div>`);
    wrapper.find('input[type="checkbox"]').on('change', event => {
        const input = event.currentTarget;
        input.checked ? selected.add(input.dataset.field) : selected.delete(input.dataset.field);
        frm.set_value('allowed_fields', JSON.stringify([...selected].sort()));
    });
    wrapper.find('input[type="search"]').on('input', event => {
        const query = event.currentTarget.value.toLowerCase();
        wrapper.find('.shared-field-choice').each((_, row) => $(row).toggle(row.textContent.toLowerCase().includes(query)));
    });
}
