// Copyright (c) 2025, nani-samireddy and contributors. See license.txt.
frappe.provide('whatsapp_messaging');
(() => {
    const node = (tag, text, cls) => {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        if (cls) element.className = cls;
        return element;
    };
    const action = (label, callback) => {
        const button = node('button', __(label), 'btn btn-default btn-sm');
        button.type = 'button'; button.onclick = callback; return button;
    };
    const status = value => ({Queued:'Waiting to send', Accepted:'Accepted by WhatsApp', Held:'Needs attention',
        Unknown:'Send status not confirmed', Failed:'Failed', Sent:'Sent', Delivered:'Delivered', Read:'Read',
        Received:'Received', Cancelled:'Cancelled'}[value] || value || '');
    const timestamp = value => {
        if (!value) return '';
        const date = new Date(String(value).replace(' ', 'T').replace(/Z?$/, 'Z'));
        return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
    };
    const styles = `
.wm-form-history{border:1px solid var(--border-color);border-radius:var(--border-radius,8px);overflow:hidden}
.wm-form-history-tools{display:flex;gap:8px;flex-wrap:wrap;padding:12px;border-bottom:1px solid var(--border-color)}
.wm-form-history-notice{padding:8px 12px;color:var(--text-muted);font-size:12px}
.wm-form-history-timeline{max-height:50vh;min-height:120px;overflow:auto;padding:12px;overscroll-behavior:contain}
.wm-form-history-message{width:fit-content;max-width:88%;margin:0 0 12px;padding:10px 12px;border-radius:10px;background:var(--subtle-fg);overflow-wrap:anywhere}
.wm-form-history-message.is-outgoing{margin-left:auto;background:var(--blue-50,var(--subtle-fg))}
.wm-form-history-body{white-space:pre-wrap}
.wm-form-history-meta{font-size:12px;color:var(--text-muted);margin-top:6px}
.wm-form-history-message a{display:block;margin-top:6px;overflow-wrap:anywhere}
`;
    whatsapp_messaging.ConversationHistory = class {
        constructor(frm, wrapper) {
            this.frm = frm; this.name = frm.doc.name; this.wrapper = wrapper;
            this.messages = []; this.active = true; this.busy = false; this.hasMore = false;
            const style = node('style', styles);
            this.root = node('section', undefined, 'wm-form-history');
            this.root.setAttribute('aria-label', __('Conversation messages'));
            const tools = node('div', undefined, 'wm-form-history-tools');
            const open = action('Open in Inbox', () => {
                frappe.route_options = {conversation:this.name}; frappe.set_route('whatsapp-inbox');
            });
            this.refreshButton = action('Refresh messages', () => this.load());
            this.olderButton = action('Load older messages', () => this.load(true));
            this.olderButton.hidden = true;
            tools.append(open, this.refreshButton, this.olderButton);
            this.notice = node('div', __('Loading messages…'), 'wm-form-history-notice');
            this.notice.setAttribute('role', 'status');
            this.timeline = node('div', undefined, 'wm-form-history-timeline');
            this.timeline.tabIndex = 0;
            this.timeline.setAttribute('aria-label', __('Message history'));
            this.root.append(tools, this.notice, this.timeline);
            wrapper.replaceChildren(style, this.root);
        }
        current() { return this.active && this.frm.doc.name === this.name && this.frm.__conversation_history === this; }
        destroy() { this.active = false; }
        async load(older = false) {
            if (!this.current() || this.busy || (older && !this.hasMore)) return;
            this.busy = true; this.refreshButton.disabled = true; this.olderButton.disabled = true;
            const previousHeight = this.timeline.scrollHeight, previousTop = this.timeline.scrollTop;
            this.notice.textContent = __('Loading messages…');
            try {
                // The Inbox reader checks permissions. This does not mark the
                // conversation read, change its status or queue a message.
                const response = await frappe.call({method:'whatsapp_messaging.messaging.inbox.get_conversation',
                    type:'GET', args:{name:this.name, limit:40, ...(older ? {before:this.messages[0].sequence} : {})}});
                if (!this.current()) return;
                const page = response.message.messages;
                this.contact = response.message.peer.display_name || response.message.conversation.recipient;
                const rows = older ? [...page, ...this.messages] : page;
                this.messages = [...new Map(rows.map(message => [message.name, message])).values()];
                this.hasMore = page.length === 40 && Number(this.messages[0]?.sequence) > 1;
                this.render();
                this.timeline.scrollTop = older ? previousTop + this.timeline.scrollHeight - previousHeight : this.timeline.scrollHeight;
            } catch {
                if (this.current()) this.notice.textContent = __('Messages could not be loaded. Try Refresh messages or open the Inbox.');
            } finally {
                if (this.current()) {
                    this.busy = false; this.refreshButton.disabled = false;
                    this.olderButton.disabled = false; this.olderButton.hidden = !this.hasMore;
                }
            }
        }
        render() {
            this.timeline.replaceChildren();
            this.notice.textContent = this.messages.length
                ? this.hasMore ? __('Showing the latest {0} messages. Load older messages to see more.', [this.messages.length])
                    : __('All {0} messages are shown. Open the Inbox to reply.', [this.messages.length])
                : __('No messages in this conversation yet.');
            for (const message of this.messages) {
                const outgoing = message.direction === 'Outbound';
                const card = node('article', undefined, 'wm-form-history-message' + (outgoing ? ' is-outgoing' : ''));
                card.append(node('div', message.message || (message.attachments?.length ? '' : __('Attachment')), 'wm-form-history-body'));
                for (const file of message.attachments || []) {
                    const label = file.file_name || file.mime_type || __('Attachment');
                    if (file.state === 'Ready') {
                        const link = node('a', __('Download {0}', [label]));
                        link.href = '/api/method/whatsapp_messaging.messaging.media.download?name=' + encodeURIComponent(file.name);
                        link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link);
                    } else card.append(node('div', label + ' · ' + __({Pending:'Waiting for download',Downloading:'Downloading…',Failed:'Download failed',Blocked:'File unavailable'}[file.state] || 'File unavailable'), 'wm-form-history-meta'));
                }
                card.append(node('div', [outgoing ? message.agent || __('Team') : this.contact,
                    __(status(message.status)), timestamp(message.provider_at || message.received_at)].filter(Boolean).join(' · '), 'wm-form-history-meta'));
                this.timeline.append(card);
            }
        }
    };
    frappe.ui.form.on('WhatsApp Conversation', {refresh(frm) {
        frm.__conversation_history?.destroy();
        frm.toggle_display('record_title', !frm.doc.account);
        if (!frm.is_new() && frm.doc.account) { frm.set_read_only(); frm.disable_save(); }
        else frm.enable_save(); // Keep the existing permission-based legacy/new-record behavior.
        const wrapper = frm.fields_dict.message_history?.$wrapper?.[0];
        if (!wrapper) return;
        if (frm.is_new() || !frm.doc.account) { wrapper.replaceChildren(); return; }
        frm.__conversation_history = new whatsapp_messaging.ConversationHistory(frm, wrapper);
        frm.__conversation_history.load();
    }});
})();
