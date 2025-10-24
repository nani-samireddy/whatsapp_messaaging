// Copyright (c) 2024, nani-samireddy and contributors
// For license information, please see license.txt

frappe.ui.form.on("WhatsApp Media", {
    refresh(frm) {
        // Show re-upload actions when document is saved and has essentials
        const can_upload = !frm.is_new() && !!frm.doc.phone_number_id && !!frm.doc.media_attachment;

        if (can_upload) {
            frm.add_custom_button("Reupload (Resumable)", () => {
                frm.call("upload_with_resumable");
            }, __("Upload"));

            frm.add_custom_button("Reupload (Traditional)", () => {
                frm.call("upload_with_traditional");
            }, __("Upload"));
        }
    }
});
