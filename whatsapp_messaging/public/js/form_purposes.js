// Explain each form in the same language used by the Inbox and navigation.
const purposes = {
    'Additional Numbers': 'Save extra phone numbers here, then select them in a campaign. Saving a number does not send a message or record permission to contact it.',
    'WhatsApp Sender': 'Set up the business WhatsApp number your team sends messages from. A system administrator manages its connection to Meta.',
    'WhatsApp Contact': 'A person who has messaged your business or received a message. This record keeps their WhatsApp number and messaging permissions.',
    'WhatsApp Message Template': 'Write a reusable message here. A campaign decides who receives it and when it is sent. Templates sent through Meta must be approved before use.',
    'WhatsApp Meta Template': 'The copy of a template stored by Meta, including its review status. To write or change a message, use Message templates.',
    'WhatsApp Template Fields': 'Choose which record fields your team can insert into messages. This selection is shared by every template that uses this record type.',
    'WhatsApp Campaign': 'Choose a message, the people who receive it and when it should send. Pause the campaign while you prepare and check it.',
    'WhatsApp Schedule': 'Choose when a campaign sends. It can send once or repeat. Automatic messages and the background scheduler must be running.',
    'WhatsApp Conversation Flow': 'Build automatic replies, menus and questions. Connect the steps, test the conversation, then publish it to your business WhatsApp number.',
    'WhatsApp Document Delivery Rule': 'Choose which document to send, who receives it and which record change starts delivery. You can require staff approval before sending.',
    'WhatsApp Document Delivery': 'Track one document from preparation to sending. Check Action needed if it could not be prepared or sent.',
    'WhatsApp Conversation': 'Read this contact’s messages and attachments here. Open the Inbox to reply, assign the conversation or update its status.',
    'WhatsApp Message': 'One incoming or outgoing message. Its delivery status shows whether WhatsApp accepted, delivered or marked it as read.',
    'WhatsApp Outbox': 'A request waiting to send, already sent, or needing attention. Being accepted by WhatsApp does not mean it has reached the contact yet.',
    'WhatsApp Automation Run': 'The results of one automatic or manual sending task. Check individual messages to see their delivery status.',
    'WhatsApp Webhook Event': 'An incoming update from Meta, such as a message or delivery update. Administrators use this record to investigate connection problems.',
    'WhatsApp Status Event': 'A delivery update from WhatsApp: sent, delivered, read or failed. This is recorded automatically.',
    'WhatsApp Send Attempt': 'The result of one attempt to send a message to WhatsApp. This is recorded automatically.',
    'WhatsApp Attachment': 'A private file attached to a message. Open Media to upload a reusable image or PDF.',
    'WhatsApp Conversation Activity': 'A history of team actions, such as assigning a conversation or recording permission to send messages.',
    'WhatsApp Record Link': 'Connects a conversation to a record your team uses, such as a Patient or Appointment. Manage these links from the Inbox.',
    'WhatsApp Conversation Read': 'Tracks how far a team member has read in the Inbox. It is separate from a contact reading a WhatsApp message.',
    'WhatsApp Identity Alias': 'Connects WhatsApp’s contact identifiers to the correct contact. The app maintains this automatically.',
    'WhatsApp Flow Session': 'Shows where a contact is in an automatic conversation and the answers they have provided.',
    'WhatsApp Flow Event': 'Shows how an incoming message was handled by an automatic conversation.',
    'WhatsApp Settings': 'Connect the app to Meta and control sending, incoming updates and automatic messages. A system administrator manages these settings.',
};

// Labels can change without rewriting event values used by saved automations.
const choices = {
    'WhatsApp Campaign': {template_event: {
        None: 'Manual send', Create: 'When a record is created',
        'Date Reminder': 'Before and on a due date', Cron: 'Repeat on a schedule',
        Update: 'When a record is updated', 'Update Field': 'When a selected field changes',
        Delete: 'When a record is deleted', Custom: 'Button on a record',
        Submit: 'When a document is submitted', Scheduled: 'At a scheduled time',
        Cancel: 'When a document is cancelled',
    }},
    'WhatsApp Message Template': {
        delivery_mode: {'Local message': 'Direct message (24-hour reply window)', 'Meta-approved template': 'Template approved by Meta'},
        meta_category: {UTILITY: 'Service update (Utility)', MARKETING: 'Promotional message (Marketing)'},
    },
};

for (const [doctype, purpose] of Object.entries(purposes)) {
    frappe.ui.form.on(doctype, {refresh(frm) {
        frm.set_intro(__(purpose));
        for (const [field, labels] of Object.entries(choices[doctype] || {})) {
            frm.set_df_property(field, 'options', Object.entries(labels).map(([value, label]) => ({value, label: __(label)})));
        }
    }});
}
