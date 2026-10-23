frappe.ui.form.on('WhatsApp Media', {
    refresh(frm) {
        frm.__media_check = (frm.__media_check || 0) + 1;
        const ui = whatsapp_messaging.media_form;
        ui.configure(frm.fields_dict.media_attachment, frm);
        ui.render(frm.fields_dict.file_preview.$wrapper, frm.doc, frm.doc.media_attachment);
        frm.set_df_property('phone_number_id', 'reqd', frm.is_new() ? 1 : 0);
        frm.set_df_property('media_attachment', 'reqd', frm.is_new() ? 1 : 0);
        frm.set_intro(__('Choose a Sender and private file, then Save. The app uploads it to WhatsApp Cloud in the background without sending a message.'));
        if (!frm.is_new() && frm.doc.validation_status === 'Ready') {
            frm.add_custom_button(frm.doc.cloud_status === 'Uploaded' ? __('Refresh cloud upload') : __('Upload / Retry'), async () => {
                if (frm.is_dirty()) { frappe.msgprint(__('Save your changes before requesting a cloud upload.')); return; }
                await frappe.call({method:'whatsapp_messaging.messaging.media_cloud.retry',args:{name:frm.doc.name}});
                await frm.reload_doc();
            });
        }
    },
    before_save(frm) { return frm.__media_pending; },
    media_attachment(frm) {
        frm.__media_pending = whatsapp_messaging.media_form.inspect(frm, frm.doc.media_attachment, frm.fields_dict.file_preview.$wrapper,
            values => frm.set_value(values), () => frm.doc.media_attachment);
        return frm.__media_pending;
    },
});
