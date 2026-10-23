import {syncTemplatesDialog} from './template_import.js';

(() => {
    const api = 'whatsapp_messaging.messaging.';
    const guides = {'WhatsApp Message Template': 'templates', 'WhatsApp Template Field Policy': 'templates', 'WhatsApp Media': 'media-library', 'WhatsApp Campaign': 'campaigns', 'WhatsApp Schedule': 'schedules', 'WhatsApp Phone Number ID': 'senders', 'WhatsApp Settings': 'senders', 'WhatsApp Approved Template': 'approved-templates', 'WhatsApp Outbox': 'delivery', 'WhatsApp Webhook Event': 'webhooks', 'WhatsApp Message': 'history', 'WhatsApp Conversation': 'assignment', 'Static Recipient': 'recipients', 'WhatsApp Automation Run': 'delivery'};
    for (const [doctype, guide] of Object.entries(guides)) {
        frappe.ui.form.on(doctype, {refresh(frm) {
            frm.add_custom_button(__('User guide'), () => frappe.set_route('whatsapp-guide', guide), __('Help'));
        }});
    }
    frappe.ui.form.on('WhatsApp Campaign', {
        refresh(frm) {
            if (frm.is_new()) return;
            frm.add_custom_button(__('Create schedule'), () => frappe.require('whatsapp_inbox.bundle.js', () => whatsapp_messaging.scheduleDialog(null, frm.doc.name)));
            frm.add_custom_button(__('Automation runs'), () => { frappe.route_options = {rule: frm.doc.name}; frappe.set_route('whatsapp-automations'); });
            if (frm.doc.is_single && !frm.doc.disable && (frappe.user.has_role('Whatsapp Admin') || frappe.user.has_role('System Manager'))) frm.add_custom_button(__('Preview campaign'), async () => {
                await frappe.call({method: api + 'automation.preview_campaign', args: {rule_name: frm.doc.name}});
                frappe.route_options = {kind: 'Campaign'}; frappe.set_route('whatsapp-automations');
            });
        }
    });
    frappe.ui.form.on('WhatsApp Phone Number ID', {refresh(frm) {
        // API tokens use Meta's permissions; password-strength feedback hides their field help.
        const token = frm.fields_dict.access_token;
        token?.disable_password_checks();
        token?.indicator?.addClass('hidden');
        token?.message?.removeClass('hidden');
        token?.set_description();
        if (!frm.is_new() && (frappe.user.has_role('Whatsapp Admin') || frappe.user.has_role('System Manager'))) frm.add_custom_button(__('Sync approved templates'), () => {
            if (frm.is_dirty()) return frappe.msgprint(__('Save the Sender before syncing templates.'));
            syncTemplatesDialog(frm.doc.name);
        });
    }});
    frappe.ui.form.on('WhatsApp Schedule', {refresh(frm) {
        if (frm.is_new() || frm.doc.state === 'Completed') return;
        const action = frm.doc.state === 'Paused' ? 'Resume' : 'Pause';
        frm.add_custom_button(__(action), () => frappe.call({method: api + 'automation.control_schedule', args: {name: frm.doc.name, action}}).then(() => frm.reload_doc()));
    }});
    frappe.ui.form.on('WhatsApp Webhook Event', {refresh(frm) {
        if (['Failed', 'Quarantined'].includes(frm.doc.state)) frm.add_custom_button(__('Replay event'), () => frappe.call({method: api + 'webhooks.replay', args: {name: frm.doc.name}}).then(() => frm.reload_doc()));
    }});
    frappe.ui.form.on('WhatsApp Outbox', {refresh(frm) {
        if (frm.doc.state === 'Failed') frm.add_custom_button(__('Retry confirmed failure'), () => frappe.call({method: api + 'outbox.retry', args: {name: frm.doc.name}}).then(() => frm.reload_doc()));
        if (['Ready', 'Retry wait', 'Held'].includes(frm.doc.state) && !frm.doc.network_started) frm.add_custom_button(__('Cancel send'), () => frappe.prompt({fieldname:'reason',fieldtype:'Small Text',label:'Reason',reqd:1}, values => frappe.call({method: api + 'outbox.cancel', args:{name:frm.doc.name,reason:values.reason}}).then(() => frm.reload_doc())));
        if (frm.doc.state === 'Unknown') frm.set_intro(__('The provider outcome is uncertain. Review receipts before deliberately composing a new message. This request will not be retried automatically.'), 'orange');
    }});
})();
