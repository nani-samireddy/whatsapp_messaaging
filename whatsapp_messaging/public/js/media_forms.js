frappe.provide('whatsapp_messaging.media_form');

(() => {
    const api = whatsapp_messaging.media_form;
    const derived = ['file_reference', 'file_name', 'document_type', 'content_type', 'file_size', 'file_size_display', 'content_hash', 'validated_on'];
    api.configure = (control, frm) => {
        control.df.options = {
            doctype: null, docname: null, fieldname: null,
            make_attachments_public: false, allow_toggle_private: false, allow_web_link: false,
            allow_google_drive: false, allow_take_photo: false,
            upload_notes: __('Private JPEG/PNG images up to 5 MB, or PDFs up to 20 MB. Saving queues a WhatsApp cloud upload for the selected Sender; it does not send a message.'),
            restrictions: {allowed_file_types: ['image/jpeg', 'image/png', 'application/pdf'], max_file_size: 20 * 1024 * 1024},
        };
        // The framework Attach control otherwise saves immediately on upload and
        // deletes the stored File on Clear. Library selection is an explicit edit.
        control.on_upload_complete = async file => {
            await control.parse_validate_and_set_in_model(file.file_url);
            if (frm) frm.attachments.update_attachment(file);
            control.refresh();
        };
        control.clear_attachment = async () => {
            await control.parse_validate_and_set_in_model(null);
            control.refresh();
        };
        control.$value?.find('[data-action="clear_attachment"]').text(__('Remove selection'))
            .css('white-space', 'nowrap').attr('title', __('Removes the selection without deleting the stored file.'));
    };
    api.render = (wrapper, details, file_url) => {
        wrapper.empty();
        if (!file_url || details.validation_status !== 'Ready') {
            $('<div class="text-muted" style="padding:12px;background:var(--subtle-fg);border-radius:var(--border-radius)"></div>')
                .text(details.validation_message || __('Choose a private image or PDF. Choose a Sender, then Save to add the file to your library and upload it to WhatsApp Cloud. No message is sent.')).appendTo(wrapper);
            return;
        }
        const card = $('<div style="padding:14px;border:1px solid var(--border-color);border-radius:var(--border-radius-lg);background:var(--subtle-fg)"></div>');
        const compact = wrapper.closest('.modal').length > 0;
        const content = compact ? $('<div style="display:flex;gap:14px;align-items:center"></div>').appendTo(card) : card;
        if (details.document_type === 'image' && file_url.startsWith('/private/files/')) {
            $('<img>').attr({src: file_url, alt: __('Selected image')}).css({display:'block',maxWidth:'100%',maxHeight:'220px',objectFit:'contain',marginBottom:'12px',borderRadius:'6px'}).appendTo(card);
            const image = card.children('img');
            if (compact) image.css({maxWidth:'140px',maxHeight:'100px',marginBottom:0,flexShrink:0}).prependTo(content);
        }
        const info = compact ? $('<div style="min-width:0;flex:1;overflow-wrap:anywhere"></div>').appendTo(content) : content;
        info.append($('<strong></strong>').text(details.file_name || __('Selected file')));
        info.append($('<div class="small text-muted" style="margin-top:4px"></div>').text(`${details.document_type === 'document' ? __('PDF document') : __('Image')} · ${details.file_size_display} · ${__('Private')}`));
        const uploaded = details.cloud_status === 'Uploaded';
        info.append($('<div class="small text-muted" style="margin-top:8px"></div>').text(uploaded
            ? __('Uploaded to WhatsApp Cloud. The private local copy is kept for future use.')
            : compact ? __('Save queues the cloud upload when enabled. No message is sent.')
                : __('Private file checked. Save to queue its WhatsApp cloud upload when Outbound Requests and the Sender are enabled. No message is sent.')));
        wrapper.append(card);
    };
    api.inspect = async (target, file_url, wrapper, set_values, get_current_file) => {
        const request = (target.__media_check || 0) + 1;
        target.__media_check = request;
        const empty = Object.fromEntries(derived.map(field => [field, null]));
        await set_values({...empty, validation_status:'Needs File', validation_message:__('Choose a private file before using this media in a message.')});
        if (!file_url) { api.render(wrapper, {}, null); return; }
        wrapper.empty().append($('<p class="text-muted"></p>').text(__('Checking file…')));
        try {
            const response = await frappe.call({method:'whatsapp_messaging.messaging.media_library.preview',args:{file_url}});
            if (target.__media_check !== request || get_current_file() !== file_url) return;
            await set_values(response.message);
            api.render(wrapper, response.message, file_url);
        } catch (error) {
            if (target.__media_check !== request || get_current_file() !== file_url) return;
            const details = {validation_status:'Needs Attention',validation_message:__('The file could not be verified. Choose a private, supported file before saving.')};
            await set_values(details); api.render(wrapper, details, file_url);
        }
    };

    frappe.ui.form.WhatsAppMediaQuickEntryForm = class extends frappe.ui.form.QuickEntryForm {
        check_quick_entry_doc() {
            super.check_quick_entry_doc();
            if (!this.doc.label && this.doc.record_title) this.doc.label = this.doc.record_title;
        }
        set_meta_and_mandatory_fields() {
            super.set_meta_and_mandatory_fields();
            this.docfields = this.docfields.filter(field => ['label','phone_number_id','media_attachment'].includes(field.fieldname)).map(field => ({...field, reqd:['media_attachment','phone_number_id'].includes(field.fieldname) ? 1 : 0}));
            this.docfields.push({fieldname:'file_preview',fieldtype:'HTML'});
        }
        render_dialog() {
            this.skip_redirect_on_error = true;
            super.render_dialog();
            const file = this.fields_dict.media_attachment;
            api.configure(file);
            file.df.onchange = () => this.check_file();
            api.render(this.fields_dict.file_preview.$wrapper, this.doc, this.get_value('media_attachment'));
            if (this.get_value('media_attachment')) this.check_file();
        }
        async insert() {
            await this.__media_pending;
            return super.insert();
        }
        check_file() {
            this.__media_pending = api.inspect(this, this.get_value('media_attachment'), this.fields_dict.file_preview.$wrapper,
                async values => { Object.assign(this.doc, values); }, () => this.get_value('media_attachment'));
            return this.__media_pending;
        }
    };
})();
