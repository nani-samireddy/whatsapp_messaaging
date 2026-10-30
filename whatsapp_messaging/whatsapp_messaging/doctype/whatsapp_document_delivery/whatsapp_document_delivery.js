frappe.ui.form.on('WhatsApp Document Delivery', {
    refresh(frm) {
        if(frm.doc.state==='Awaiting release') frm.add_custom_button(__('Release document'),()=>frappe.call({method:'whatsapp_messaging.messaging.document_delivery.release',args:{name:frm.doc.name},freeze:true}).then(()=>frm.reload_doc()));
        if(['Held','Failed'].includes(frm.doc.state)&&!frm.doc.outbox) frm.add_custom_button(__('Retry preparation'),()=>frappe.call({method:'whatsapp_messaging.messaging.document_delivery.retry',args:{name:frm.doc.name},freeze:true}).then(()=>frm.reload_doc()));
        if(frm.doc.outbox) frm.add_custom_button(__('View message delivery'),()=>frappe.set_route('Form','WhatsApp Outbox',frm.doc.outbox));
        if(frm.doc.outbox&&frm.doc.delivery_status==='Failed') frm.add_custom_button(__('Retry confirmed failure'),()=>frappe.call({method:'whatsapp_messaging.messaging.outbox.retry',args:{name:frm.doc.outbox},freeze:true}).then(()=>frm.reload_doc()));
    }
});
