frappe.listview_settings['WhatsApp Conversation Flow'] = {
    add_fields:['flow_title','status','is_active'],
    get_indicator:doc=>[doc.is_active?'Published and enabled':doc.status,doc.is_active?'green':'orange','status,=,'+doc.status],
    onload(listview){
        if(!frappe.user_roles.some(r=>['System Manager','Whatsapp Admin'].includes(r)))return;
        listview.page.add_inner_button(__('Create hospital starter flow'),()=>{
            const d=new frappe.ui.Dialog({title:'Create a hospital starter flow',fields:[{fieldname:'account_name',fieldtype:'Link',options:'WhatsApp Phone Number ID',label:'Business WhatsApp number',reqd:1}],primary_action_label:'Create draft',primary_action:async values=>{
                const result=await frappe.call({method:'whatsapp_messaging.messaging.flows.hospital_draft',args:values,type:'POST'});d.hide();frappe.set_route('Form','WhatsApp Conversation Flow',result.message.name);
            }});d.show();
        });
    }
};
