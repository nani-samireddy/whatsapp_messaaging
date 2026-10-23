// Discover buttons for the current user on each document refresh, including newly added rules.
$(document).on('form-refresh', async function(event, frm) {
    if (frm.is_new() || !['Whatsapp Editor','Whatsapp Admin','System Manager'].some(role => frappe.user.has_role(role))) return;
    for (const label of frm.whatsapp_button_labels || []) frm.remove_custom_button(label, __('WhatsApp Messaging'));
    frm.whatsapp_button_labels = [];
    try {
        const response = await frappe.call({method:'whatsapp_messaging.utils.get_template_doctypes'});
        if (frm.doc.name !== cur_frm?.doc.name) return;
        for (const template of response.message?.[frm.doctype] || []) {
            const label = frappe.utils.escape_html(template.label || template.name);
            frm.whatsapp_button_labels.push(label);
            frm.add_custom_button(label, () => sendWhatsAppMessage(frm, template), __('WhatsApp Messaging'));
        }
        const linked = await frappe.call({method:'whatsapp_messaging.messaging.api.record_conversations',args:{doctype:frm.doctype,docname:frm.doc.name}});
        if (linked.message?.length) {
            const label = __('View conversation'); frm.whatsapp_button_labels.push(label);
            frm.add_custom_button(label, () => {
                const open = name => {frappe.route_options={conversation:name};frappe.set_route('whatsapp-inbox');};
                if (linked.message.length === 1) open(linked.message[0].name);
                else frappe.prompt({fieldname:'conversation',fieldtype:'Select',label:__('Conversation'),options:linked.message.map(row=>({label:row.account+' · '+row.recipient,value:row.name})),reqd:1},values=>open(values.conversation));
            }, __('WhatsApp Messaging'));
        }
    } catch { /* Normal document access still works when no messaging actions are permitted. */ }
});

function sendWhatsAppMessage(frm, template) {
    frm.whatsapp_requests=frm.whatsapp_requests || {};
    frm.whatsapp_requests[template.name]=frm.whatsapp_requests[template.name] || crypto.randomUUID();
    frappe.call({method:'whatsapp_messaging.controller.wm_handle_on_custom_trigger',args:{template_name:template.name,doctype:frm.doctype,docname:frm.doc.name,request_id:frm.whatsapp_requests[template.name]},freeze:true,freeze_message:__('Queuing message…')}).then(response=>{
        if (response.message) {
            delete frm.whatsapp_requests[template.name];
            frappe.msgprint({title:__('Queued'),message:__('Messages queued. Check Automation runs for acceptance and delivery results.'),indicator:'blue'});
        }
    });
}
