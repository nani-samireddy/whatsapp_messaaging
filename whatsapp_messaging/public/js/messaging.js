frappe.provide('whatsapp_messaging');
(() => {
    const prefix = 'whatsapp_messaging.messaging.';
    const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
    const call = async (method, args = {}) => (await frappe.call({method: prefix + method, args, type: 'POST'})).message;
    const route = (target, options = {}) => { frappe.route_options = options; frappe.set_route(target); };
    const button = (text, action, cls = 'btn btn-default btn-sm') => { const n = el('button', text, cls); n.type = 'button'; n.onclick = action; return n; };
    const iconButton = (label, icon, action, cls = 'btn btn-default') => {
        const n = button('', action, cls + ' wm-icon-button'); n.title = label; n.setAttribute('aria-label', label);
        n.innerHTML = frappe.utils.icon(icon, 'md'); n.querySelector('svg')?.setAttribute('aria-hidden', 'true'); return n;
    };
    const input = (placeholder, type = 'text') => { const n = el('input'); n.type = type; n.className = 'form-control'; n.placeholder = placeholder; n.setAttribute('aria-label', placeholder); return n; };
    const select = (label, values) => { const n = el('select', undefined, 'form-control'); n.setAttribute('aria-label', label); for (const [value, text] of values) { const o = el('option', text); o.value = value; n.append(o); } return n; };
    const localStamp = value => value ? frappe.datetime.str_to_user(value) : '';
    const stamp = value => value ? new Date(String(value).replace(' ', 'T').replace(/Z?$/, 'Z')).toLocaleString() : '';
    // Keep API values unchanged; explain them in the language used by the team.
    const conversationStatus = value => ({Open: 'Open', Pending: 'Waiting', Resolved: 'Resolved'}[value] || value);
    const messageStatus = value => ({Ready: 'Waiting to send', Claimed: 'Waiting to send', 'Retry wait': 'Waiting to try again', Queued: 'Waiting to send', Accepted: 'Accepted by WhatsApp', Held: 'Needs attention', Unknown: 'Send status not confirmed', Failed: 'Failed', Sent: 'Sent', Delivered: 'Delivered', Read: 'Read', Received: 'Received', Cancelled: 'Cancelled'}[value] || value);
    const statusHelp = {
        Accepted: 'WhatsApp accepted this message. Delivery has not been confirmed yet.',
        Held: 'Sending is on hold. Ask an administrator to check the reason in the Outbound Queue.',
        Unknown: 'We could not confirm whether this message was sent. Check its status before sending it again.',
        Failed: 'This message could not be sent or delivered. Ask an administrator to check the reason.',
    };
    const styles = `
.wm-shell{padding:16px}
.wm-banner{padding:10px 14px;background:var(--subtle-fg,#f5f6f8);border-radius:8px;margin-bottom:12px;flex-shrink:0}
.wm-error{color:var(--red-600,#a72020);padding:10px;flex-shrink:0}
.wm-error:empty{display:none}
.wm-inbox-shell{height:calc(100dvh - var(--page-head-height,48px) - 1px);min-height:0;display:flex;flex-direction:column;overflow:hidden;container:whatsapp-inbox / inline-size}
.wm-inbox{display:grid;grid-template-columns:clamp(240px,23%,320px) minmax(0,1fr) 260px;gap:12px;flex:1;min-height:0;position:relative}
.wm-list,.wm-thread,.wm-details{min-width:0;min-height:0;border:1px solid var(--border-color,#ddd);border-radius:10px;overflow:hidden;background:var(--card-bg,#fff)}
.wm-list,.wm-thread{display:flex;flex-direction:column}
.wm-filters{display:grid;gap:8px;padding:12px;flex-shrink:0}
.wm-conversations{overflow:auto;min-height:0;flex:1;overscroll-behavior:contain}
.wm-conversation{display:block;width:100%;padding:12px;text-align:left;border:0;border-top:1px solid var(--border-color,#ddd);background:transparent;color:inherit;overflow-wrap:anywhere}
.wm-conversation[aria-current=true]{background:var(--control-bg,#eee)}
.wm-person{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wm-snippet{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:4px}
.wm-meta{display:block;color:var(--text-muted,#666);font-size:12px;line-height:1.5}
.wm-thread-head{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--border-color,#ddd);flex-shrink:0}
.wm-thread-identity{flex:1;min-width:0;overflow-wrap:anywhere}
.wm-thread-identity h4{margin:0 0 4px;font-size:16px}
.wm-back,.wm-details-toggle,.wm-details-close{display:none}
.wm-timeline{padding:14px;overflow:auto;min-height:0;flex:1;overscroll-behavior:contain;scrollbar-gutter:stable}
.wm-message{width:fit-content;max-width:min(88%,680px);padding:10px 12px;border-radius:10px;margin:0 0 12px;background:var(--subtle-fg,#f5f6f8);white-space:pre-wrap;overflow-wrap:anywhere}
.wm-message.outbound{margin-left:auto;background:var(--blue-50,#eef5ff)}
.wm-message .wm-meta{margin-top:6px}
.wm-message img{max-width:min(220px,100%);max-height:180px;display:block;margin:8px 0}
.wm-message a{overflow-wrap:anywhere}
.wm-composer{padding:12px;border-top:1px solid var(--border-color,#ddd);display:grid;gap:8px;flex-shrink:0}
.wm-composer .wm-meta{margin:0}
.wm-compose-frame{border:1px solid var(--border-color,#ddd);border-radius:12px;overflow:hidden;background:var(--card-bg,#fff);position:relative}
.wm-compose-frame:focus-within{border-color:var(--primary,#249b91);box-shadow:0 0 0 1px var(--primary,#249b91)}
.wm-compose-input{position:relative}
.wm-composer textarea.form-control{height:88px;min-height:72px;max-height:180px;resize:vertical;border:0!important;border-radius:0;box-shadow:none!important;background:transparent;padding:12px 56px 12px 12px;line-height:1.5}
.wm-compose-send.btn{position:absolute;right:8px;top:8px;width:36px;height:36px;border-radius:8px;background:transparent;color:var(--primary,#178c83);border:0;box-shadow:none}
.wm-compose-send.btn:hover:not(:disabled){background:var(--control-bg,#f1f4f5)}
.wm-compose-send.btn:disabled{opacity:.4}
.wm-compose-toolbar{display:flex;align-items:center;gap:4px;flex-wrap:wrap;padding:6px 8px;background:var(--subtle-fg,#f5f6f8);border-top:1px solid var(--border-color,#eee)}
.wm-compose-tool.btn{display:inline-flex;align-items:center;gap:5px;padding:5px 7px;min-height:30px;background:transparent;border:0;box-shadow:none;color:var(--text-color,#333);font-size:12px;border-radius:6px}
.wm-compose-tool.btn:hover:not(:disabled){background:var(--control-bg,#e9edef)}
.wm-compose-tool .icon{width:14px;height:14px}
.wm-compose-count{margin-left:auto;padding:0 4px;color:var(--text-muted,#666);font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}
.wm-compose-count.is-over{color:var(--red-600,#a72020)}
.wm-compose-attachment,.wm-compose-quote{display:flex;align-items:center;gap:8px;padding:8px 12px;overflow-wrap:anywhere;border-top:1px solid var(--border-color,#eee);font-size:12px}
.wm-compose-attachment span,.wm-compose-quote span{flex:1;min-width:0}
.wm-compose-attachment .wm-icon-button,.wm-compose-quote .wm-icon-button{width:28px;height:28px;flex-shrink:0}
.wm-emoji-picker{display:grid;grid-template-columns:repeat(8,1fr);gap:4px;padding:8px;border-top:1px solid var(--border-color,#eee)}
.wm-emoji-picker[hidden]{display:none}
.wm-emoji-picker button{background:transparent;border:0;border-radius:6px;font-size:20px;min-width:28px;min-height:32px}
.wm-emoji-picker button:hover,.wm-emoji-picker button:focus-visible{background:var(--control-bg,#eee)}
.wm-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.wm-icon-button{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;padding:0;border-radius:10px}
.wm-icon-button .icon{width:20px;height:20px}
.wm-icon-button:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
.wm-icon-button[aria-busy=true] .icon{animation:wm-spin 1s linear infinite}
@keyframes wm-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.wm-icon-button[aria-busy=true] .icon{animation:none}}
.wm-details{padding:16px;overflow:auto;overflow-wrap:anywhere;overscroll-behavior:contain}
.wm-details h4{margin:20px 0 12px;font-size:15px}
.wm-details h4:first-of-type{margin-top:0}
.wm-details > .btn{margin:0 4px 6px 0;max-width:100%;white-space:normal}
.wm-empty{padding:28px;color:var(--text-muted,#666);text-align:center}
.wm-run{border:1px solid var(--border-color,#ddd);padding:14px;border-radius:10px;margin:12px 0}
.wm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;margin:12px 0}
.wm-stat{padding:14px;border:1px solid var(--border-color,#ddd);border-radius:8px;cursor:pointer;background:var(--card-bg,#fff);color:inherit;text-align:left}
.wm-stat strong{display:block;font-size:24px}
.wm-preview{max-height:50vh;overflow:auto}
.wm-preview-item{padding:12px;border-bottom:1px solid var(--border-color,#ddd);white-space:pre-wrap}
@container whatsapp-inbox (max-width:1000px){
 .wm-inbox{grid-template-columns:240px minmax(0,1fr)}
 .wm-details{display:none}
 .wm-details-toggle,.wm-details-close{display:inline-block}
 .wm-inbox.show-details .wm-details{display:block;position:absolute;inset:0 0 0 auto;width:min(320px,100%);z-index:5;box-shadow:-8px 0 24px #0002}
 .wm-details-close{margin-bottom:16px!important}
}
@container whatsapp-inbox (max-width:640px){
 .wm-inbox{grid-template-columns:minmax(0,1fr)}
 .wm-thread{display:none}
 .wm-inbox.mobile-thread .wm-list{display:none}
 .wm-inbox.mobile-thread .wm-thread{display:flex}
 .wm-back{display:inline-block}
 .wm-thread-head{padding:10px;gap:8px;flex-wrap:wrap}
 .wm-thread-identity{flex-basis:calc(100% - 130px)}
 .wm-composer{padding:10px}
 .wm-timeline{padding:10px}
 .wm-message{max-width:94%}
}
@media(max-width:700px){.wm-inbox-shell{padding:8px}.wm-inbox-shell .wm-banner{font-size:12px;padding:8px 10px;margin-bottom:8px}}
`;
    if (!document.getElementById('wm-style')) { const s = el('style', styles); s.id = 'wm-style'; document.head.append(s); }

    class Base {
        constructor(wrapper, title) {
            this.wrapper = wrapper;
            this.page = frappe.ui.make_app_page({parent: wrapper, title, single_column: true});
            this.page.set_secondary_action(__('User guide'), () => frappe.set_route('whatsapp-guide', title === __('WhatsApp Inbox') ? 'replies' : 'delivery'));
            this.root = el('div', undefined, 'wm-shell'); this.page.main[0].append(this.root);
            this.banner = el('div', 'Loading…', 'wm-banner'); this.error = el('div', '', 'wm-error'); this.error.tabIndex = -1; this.error.setAttribute('role', 'alert');
            this.root.append(this.banner, this.error);
        }
        fail(error, message = 'We couldn’t complete this action. If the problem continues, ask your administrator for help.') { this.error.textContent = message; this.error.focus(); console.warn('WhatsApp action failed', error?.status || 'request'); }
        async init() {
            this.boot = await call('api.bootstrap');
            this.banner.textContent = this.boot.outbound_enabled ? 'Sending is on. Check each message’s status to see whether it was delivered or read.' : 'Sending is off. You can still read conversations. An administrator can enable sending in WhatsApp Settings.';
            if (!this.boot.accounts.length) this.banner.append(el('span', this.boot.manager ? ' Add your business WhatsApp number in Administration to get started.' : ' Ask your administrator to add your business WhatsApp number.'));
        }
        async perform(fn, failureMessage) { this.error.textContent = ''; try { return await fn(); } catch (e) { this.fail(e, failureMessage); } }
    }

    whatsapp_messaging.Inbox = class extends Base {
        constructor(wrapper) {
            super(wrapper, __('WhatsApp Inbox'));
            this.root.classList.add('wm-inbox-shell');
            this.selected = null; this.cursor = null; this.busy = false; this.drafts = new Map(); this.items = [];
            this.start().catch(e => this.fail(e));
        }
        async start() {
            await this.init();
            this.grid = el('div', undefined, 'wm-inbox'); this.root.append(this.grid);
            this.list = el('section', undefined, 'wm-list'); this.list.setAttribute('aria-label', 'Conversations');
            const filters = el('div', undefined, 'wm-filters');
            this.sender = select('Business WhatsApp number', [['', 'All business numbers'], ...this.boot.accounts.map(a => [a.name, a.label])]);
            this.search = input('Search name or number'); this.search.setAttribute('aria-label', 'Search by name or phone number');
            this.status = select('Conversation status', [['', 'All statuses'], ...['Open', 'Pending', 'Resolved'].map(v => [v, conversationStatus(v)])]);
            this.assignment = select('Filter conversations', [['', 'All conversations'], ['Mine', 'Assigned to me'], ['Unassigned', 'Unassigned'], ['Unread', 'Unread messages']]);
            const options = frappe.route_options || {}; this.status.value = options.status || ''; this.assignment.value = options.assignment || ''; frappe.route_options = null;
            for (const n of [this.sender, this.status, this.assignment]) n.onchange = () => this.perform(() => this.refresh());
            let debounce; this.search.oninput = () => { clearTimeout(debounce); debounce = setTimeout(() => this.perform(() => this.refresh()), 250); };
            filters.append(this.sender, this.search, this.status, this.assignment, button('New conversation', () => this.newConversation()));
            this.rows = el('div', undefined, 'wm-conversations'); this.more = button('Load more conversations', () => this.perform(() => this.loadMore())); this.more.hidden = true;
            this.list.append(filters, this.rows, this.more);
            this.thread = el('section', undefined, 'wm-thread'); this.thread.setAttribute('aria-label', 'Message thread'); this.thread.append(el('p', 'Choose a conversation', 'wm-empty'));
            this.details = el('aside', undefined, 'wm-details'); this.details.setAttribute('aria-label', 'Conversation details');
            this.details.id = 'whatsapp-conversation-details';
            this.details.addEventListener('keydown', event => { if (event.key === 'Escape') this.toggleDetails(false); });
            this.grid.append(this.list, this.thread, this.details);
            this.changed = () => { clearTimeout(this.changeTimer); this.changeTimer = setTimeout(() => { if (!this.root.isConnected || this.wrapper.style.display === 'none') return; this.perform(async () => { await this.refresh(); if (this.selected && !this.busy && document.activeElement !== this.text) await this.open(this.selected, true); }, 'We couldn’t check for new messages. We’ll try again automatically. Your draft is still here; keep this page open.'); }, 400); };
            frappe.realtime.on('whatsapp_changed', this.changed);
            // A bounded poll also recovers missed socket events after reconnect.
            this.poll = setInterval(this.changed, 30000);
            $(this.wrapper).on('remove', () => { clearInterval(this.poll); clearTimeout(this.changeTimer); frappe.realtime.off('whatsapp_changed', this.changed); });
            await this.refresh(); if (options.conversation) await this.open(options.conversation);
        }
        async onShow() {
            if (!this.boot || !this.sender) return;
            const options = frappe.route_options || {}; frappe.route_options = null;
            if (options.status !== undefined) this.status.value = options.status;
            if (options.assignment !== undefined) this.assignment.value = options.assignment;
            await this.refresh(); if (options.conversation) await this.open(options.conversation);
        }
        async refresh() { this.cursor = null; this.items = []; await this.loadMore(); }
        async loadMore() {
            const result = await call('inbox.list_conversations', {account_name: this.sender.value || null, status: this.status.value || null, assignment: this.assignment.value || null, search: this.search.value || null, cursor: this.cursor ? JSON.stringify(this.cursor) : null});
            this.items.push(...result.items); this.cursor = result.next_cursor; this.more.hidden = !this.cursor;
            this.rows.replaceChildren();
            if (!this.items.length) this.rows.append(el('p', 'No conversations match these filters.', 'wm-empty'));
            for (const row of this.items) {
                const b = button('', () => this.perform(() => this.open(row.name)), 'wm-conversation');
                b.setAttribute('aria-current', String(row.name === this.selected)); b.dataset.conversation = row.name;
                b.append(el('strong', row.display_name || row.recipient, 'wm-person'), el('span', row.account + ' · ' + conversationStatus(row.workflow_status) + (row.unread ? ' · ' + row.unread + ' unread' : ''), 'wm-meta'), el('span', row.last_message || 'No messages yet', 'wm-snippet'), el('time', stamp(row.activity_at), 'wm-meta')); this.rows.append(b);
            }
        }
        draft(name) { if (!this.drafts.has(name)) this.drafts.set(name, {body: '', request_id: crypto.randomUUID(), file: null, reply: null}); return this.drafts.get(name); }
        async open(name, refreshing = false) {
            if (!refreshing) { this.selected = name; this.oldest = null; }
            const requestName = this.selected; const data = await call('inbox.get_conversation', {name});
            if (this.selected !== requestName) return;
            this.data = data;
            if (!refreshing) this.grid.classList.add('mobile-thread');
            this.thread.replaceChildren();
            const head = el('div', undefined, 'wm-thread-head');
            const identity = el('div', undefined, 'wm-thread-identity');
            identity.append(el('h4', data.peer.display_name || data.conversation.recipient), el('span', 'From: ' + data.conversation.account + ' · ' + conversationStatus(data.conversation.workflow_status), 'wm-meta'));
            this.detailsToggle = button('Details', () => this.toggleDetails(), 'btn btn-default btn-sm wm-details-toggle');
            this.detailsToggle.setAttribute('aria-controls', this.details.id);
            this.detailsToggle.setAttribute('aria-expanded', String(this.grid.classList.contains('show-details')));
            head.append(button('Back to conversations', () => { this.grid.classList.remove('mobile-thread', 'show-details'); }, 'btn btn-default btn-sm wm-back'), identity, this.detailsToggle);
            this.timeline = el('div', undefined, 'wm-timeline'); this.timeline.setAttribute('aria-live', 'polite');
            this.older = button('Load older messages', () => this.perform(() => this.loadOlder())); this.timeline.append(this.older);
            const messages = data.messages; this.oldest = messages[0]?.sequence; this.older.hidden = messages.length < 40;
            for (const message of messages) this.renderMessage(message, this.timeline);
            this.thread.append(head, this.timeline); await this.composer(); this.renderDetails();
            this.timeline.scrollTop = this.timeline.scrollHeight;
            const inbound = messages.filter(m => m.direction === 'Inbound').map(m => m.sequence);
            if (inbound.length && document.visibilityState === 'visible') await call('inbox.mark_read', {name, sequence: Math.max(...inbound)});
        }
        async loadOlder() {
            const data = await call('inbox.get_conversation', {name: this.selected, before: this.oldest});
            const holder = el('div'); for (const row of data.messages) this.renderMessage(row, holder);
            this.timeline.insertBefore(holder, this.older.nextSibling); this.oldest = data.messages[0]?.sequence || this.oldest; this.older.hidden = data.messages.length < 40;
        }
        renderMessage(message, parent) {
            const node = el('article', undefined, 'wm-message ' + (message.direction === 'Outbound' ? 'outbound' : 'inbound'));
            node.append(el('div', message.message || (message.message_type === 'text' ? '' : 'Attachment')));
            for (const attachment of message.attachments || []) {
                const label = attachment.file_name || attachment.mime_type || 'Attachment';
                if (attachment.state === 'Ready') {
                    const url = '/api/method/whatsapp_messaging.messaging.media.download?name=' + encodeURIComponent(attachment.name);
                    if (attachment.mime_type?.startsWith('image/')) { const img = el('img'); img.src = url; img.alt = label; img.loading = 'lazy'; node.append(img); }
                    const a = el('a', 'Download ' + label); a.href = url; a.target = '_blank'; a.rel = 'noopener'; node.append(a);
                } else node.append(el('span', label + ' · ' + ({Pending: 'Waiting for download', Downloading: 'Downloading…', Failed: 'Download failed', Blocked: 'File blocked — ask an administrator for help'}[attachment.state] || 'File unavailable'), 'wm-meta'));
            }
            node.append(el('span', (message.agent || (message.direction === 'Inbound' ? 'Contact' : 'Team member')) + ' · ' + messageStatus(message.status) + ' · ' + stamp(message.provider_at || message.received_at), 'wm-meta'));
            if (statusHelp[message.status]) node.append(el('span', statusHelp[message.status], 'wm-meta'));
            if (message.provider_message_id) { const reply = button('Reply', () => { this.draft(this.selected).reply = message.provider_message_id; this.composer(); }); reply.setAttribute('aria-label', 'Reply to this message'); node.append(reply); }
            parent.append(node);
        }
        async composer() {
            this.thread.querySelector('.wm-composer')?.remove();
            const box = el('div', undefined, 'wm-composer'); const draft = this.draft(this.selected);
            const limit = draft.file ? 1024 : 4096;
            const text = el('textarea', undefined, 'form-control'); text.value = draft.body; text.maxLength = limit;
            text.setAttribute('aria-label', draft.file ? 'Attachment caption' : 'Message text'); text.placeholder = draft.file ? 'Add a caption…' : 'Write your message…';
            text.setAttribute('aria-describedby', 'wm-compose-help wm-compose-count');
            const notice = el('p', !this.boot.outbound_enabled ? 'Sending is off. Ask an administrator to enable it in WhatsApp Settings.' : this.data.peer.suppressed ? 'Messages to this number are blocked. An administrator can review Messaging permissions in Details.' : this.data.window_open ? 'You can reply now. Use a template after 24 hours without a message from this contact.' : 'To message this contact now, choose Template. Direct replies are available for 24 hours after their last message.', 'wm-meta');
            notice.id = 'wm-compose-help';
            const frame = el('div', undefined, 'wm-compose-frame'), inputRow = el('div', undefined, 'wm-compose-input');
            const toolbar = el('div', undefined, 'wm-compose-toolbar'); toolbar.setAttribute('role', 'group'); toolbar.setAttribute('aria-label', 'Message tools');
            const tool = (label, icon, action, help) => {
                const n = button('', action, 'btn btn-sm wm-compose-tool'); n.innerHTML = icon === 'smile' ? '<svg class="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M8 14s1 3 4 3 4-3 4-3"/><path d="M8 9h.01M16 9h.01"/></svg>' : frappe.utils.icon(icon, 'sm'); n.querySelector('svg')?.setAttribute('aria-hidden', 'true'); n.append(el('span', label)); n.title = help; return n;
            };
            const send = iconButton(this.busy ? 'Sending…' : 'Send reply', this.busy ? 'loader-circle' : 'send', () => this.perform(() => this.send()), 'btn wm-compose-send'); send.setAttribute('aria-busy', String(this.busy));
            const count = el('span', '', 'wm-compose-count'); count.id = 'wm-compose-count';
            const refreshInput = () => {
                draft.body = text.value; const length = Array.from(text.value).length;
                count.textContent = length + '/' + limit; count.classList.toggle('is-over', length > limit);
                count.setAttribute('aria-label', length + ' of ' + limit + ' characters');
                send.disabled = !this.boot.outbound_enabled || !this.data.window_open || !!this.data.peer.suppressed || this.busy || (!text.value.trim() && !draft.file) || length > limit;
                send.title = !this.boot.outbound_enabled || !this.data.window_open || this.data.peer.suppressed ? notice.textContent : length > limit ? 'Shorten the caption before sending.' : 'Send reply (Ctrl+Enter or ⌘+Enter)';
            };
            text.oninput = refreshInput;
            text.onkeydown = event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing) { event.preventDefault(); send.click(); } };
            const approved = tool('Template', 'layout-template', () => this.perform(() => this.chooseTemplate()), 'Choose a message template approved by WhatsApp.');
            approved.setAttribute('aria-label', 'Send a template'); approved.disabled = !this.boot.outbound_enabled || !!this.data.peer.suppressed || this.busy;
            if (approved.disabled) approved.title = notice.textContent;
            const picker = el('div', undefined, 'wm-emoji-picker'); picker.hidden = true; picker.setAttribute('role', 'group'); picker.setAttribute('aria-label', 'Choose an emoji');
            const emoji = tool('Emoji', 'smile', () => { picker.hidden = !picker.hidden; emoji.setAttribute('aria-expanded', String(!picker.hidden)); if (!picker.hidden) picker.querySelector('button')?.focus(); }, 'Add an emoji');
            emoji.setAttribute('aria-expanded', 'false');
            for (const [symbol, label] of [['😊','Smiling face'],['👋','Waving hand'],['🙏','Thank you'],['👍','Thumbs up'],['✅','Check mark'],['❤️','Heart'],['📅','Calendar'],['📍','Location'],['🏥','Hospital'],['☎️','Telephone'],['🕘','Nine o’clock'],['ℹ️','Information'],['🎉','Celebration'],['🙂','Slight smile'],['💬','Message'],['⭐','Star']]) {
                const choice = button(symbol, () => { const start = text.selectionStart, end = text.selectionEnd; const value = text.value.slice(0, start) + symbol + text.value.slice(end); if (value.length <= limit) { text.value = value; refreshInput(); text.focus(); text.setSelectionRange(start + symbol.length, start + symbol.length); } picker.hidden = true; emoji.setAttribute('aria-expanded', 'false'); }, '');
                choice.setAttribute('aria-label', label); picker.append(choice);
            }
            picker.onkeydown = event => { if (event.key === 'Escape') { event.stopPropagation(); picker.hidden = true; emoji.setAttribute('aria-expanded', 'false'); emoji.focus(); } };
            const attach = tool('Attach', 'paperclip', () => new frappe.ui.FileUploader({is_private: 1, allow_multiple: false, restrictions: {allowed_file_types: ['.jpg', '.jpeg', '.png', '.pdf'], max_file_size: 20 * 1024 * 1024}, on_success: file => { draft.file = file; this.composer(); }}), 'Attach an image or PDF');
            attach.setAttribute('aria-label', 'Attach image or PDF'); attach.disabled = this.busy;
            inputRow.append(text, send); frame.append(inputRow);
            if (draft.reply) { const quote = el('div', undefined, 'wm-compose-quote'); quote.append(el('span', 'Replying to a specific message'), iconButton('Remove quote', 'x', () => { draft.reply = null; this.composer(); })); frame.append(quote); }
            if (draft.file) { const file = el('div', undefined, 'wm-compose-attachment'); file.append(el('span', draft.file.file_name), iconButton('Remove attachment', 'x', () => { draft.file = null; this.composer(); })); frame.append(file); }
            toolbar.append(approved, emoji, attach, count); frame.append(picker, toolbar); box.append(notice, frame); this.thread.append(box); this.text = text; refreshInput();
        }

        async send(template, parameters, documentFile) {
            if (this.busy) return; this.busy = true; const name = this.selected; const draft = this.draft(name); this.composer();
            let submitted = false;
            try {
                const result = await call('outbox.send', {conversation_name: name, request_id: draft.request_id, body: template ? '' : draft.body, template, parameters: JSON.stringify(parameters || []), file_id: template ? documentFile : draft.file?.name, reply_to: draft.reply});
                submitted = true;
                this.drafts.delete(name); frappe.show_alert({message: 'Message status: ' + messageStatus(result.state), indicator: 'blue'}); await this.open(name); await this.refresh();
                return true;
            } catch (error) {
                this.fail(error, submitted ? 'Your message was saved, but we couldn’t refresh the conversation. Check its status before sending again.' : 'We couldn’t confirm your send request. Check the latest messages before trying again to avoid sending twice. Your draft stays in this tab until you reload or leave the page.');
                return submitted;
            } finally { this.busy = false; if (name === this.selected) this.composer(); }
        }
        async chooseTemplate() {
            const templates = await call('catalogue.list_templates', {account_name: this.data.conversation.account});
            if (!templates.length) { frappe.msgprint('There are no WhatsApp-approved templates available for this business number. Ask an administrator to import approved templates from the sender’s settings.'); return; }
            if (!this.data.peer.consent_recorded) { frappe.msgprint('This contact’s permission to receive messages has not been recorded. Ask an administrator to record their consent under Messaging permissions before sending a template.'); return; }
            const choose = new frappe.ui.Dialog({title: 'Choose a WhatsApp-approved template', fields: [{fieldname: 'template', fieldtype: 'Select', label: 'Template and language', description: 'Choose the wording and language. You can review the message before sending.', reqd: 1, options: templates.map((t, i) => ({label: t.template_name + ' · ' + t.language, value: String(i)}))}], primary_action_label: 'Review message', primary_action: v => { choose.hide(); const t = templates[Number(v.template)]; this.parameterDialog(t); }}); choose.show();
        }
        parameterDialog(template) {
            const fields = [{fieldname: 'preview', fieldtype: 'HTML'}];
            const components = JSON.parse(template.components_json || '[]');
            const needsDocument = components.some(c => c.type === 'HEADER' && c.format === 'DOCUMENT');
            let documentFile = null;
            if (needsDocument) fields.push({fieldname:'document_picker',fieldtype:'Button',label:'Choose private PDF'}, {fieldname:'document_name',fieldtype:'Data',label:'PDF document',read_only:1});
            const params = JSON.parse(template.parameters_json || '[]'); params.forEach((_, i) => fields.push({fieldname: 'p' + i, fieldtype: 'Small Text', label: 'Message detail ' + (i + 1), description: 'Replaces {{' + (i + 1) + '}} in the template above.', reqd: 1}));
            const d = new frappe.ui.Dialog({title: template.template_name + ' · ' + template.language, fields, primary_action_label: 'Send template', primary_action: values => this.perform(async () => {
                if(needsDocument && !documentFile) return frappe.msgprint('Choose the private PDF for this recipient.');
                if (await this.send(template.name, params.map((_, i) => values['p' + i]), documentFile)) d.hide();
            })});
            if(needsDocument) d.fields_dict.document_picker.$input.on('click', () => new frappe.ui.FileUploader({is_private:1,allow_multiple:false,restrictions:{allowed_file_types:['.pdf'],max_file_size:20*1024*1024},on_success:file=>{documentFile=file.name;d.set_value('document_name',file.file_name);}}));
            const header = components.find(c => c.type === 'HEADER')?.text;
            const footer = components.find(c => c.type === 'FOOTER')?.text;
            d.fields_dict.preview.$wrapper.css('white-space','pre-wrap').text([header,template.body,footer].filter(Boolean).join('\n\n')); d.show();
        }
        renderDetails() {
            for (const row of this.rows.children) row.setAttribute('aria-current', String(row.dataset.conversation === this.selected));
            const data = this.data; const doc = data.conversation; this.details.replaceChildren();
            this.details.append(button('Close details', () => this.toggleDetails(false), 'btn btn-default btn-sm wm-details-close'), el('h4', 'Assigned to'), el('p', doc.assigned_to || 'Not assigned'));
            if (!doc.assigned_to || doc.assigned_to === this.boot.user || this.boot.supervisor) this.details.append(button(doc.assigned_to === this.boot.user ? 'Remove assignment' : 'Assign to me', () => this.perform(async () => { await call('inbox.assign', {name: doc.name, version: doc.version, user: doc.assigned_to === this.boot.user ? '' : this.boot.user}); await this.open(doc.name); })));
            if (this.boot.supervisor) this.details.append(button('Assign to someone', () => this.perform(async () => {
                const agents = await call('api.agents'); const d = new frappe.ui.Dialog({title: 'Assign conversation', fields: [{fieldname: 'user', fieldtype: 'Select', label: 'Team member', description: 'Choose who will handle this conversation.', options: [{label: 'Not assigned', value: ''}, ...agents.map(a => ({label: a.full_name + ' (' + a.name + ')', value: a.name}))]}], primary_action_label: 'Save assignment', primary_action: values => this.perform(async () => { await call('inbox.assign', {name: doc.name, version: doc.version, user: values.user}); d.hide(); await this.open(doc.name); })}); d.show();
            })));
            this.details.append(el('h4', 'Status'));
            const statuses = select('Conversation status', ['Open', 'Pending', 'Resolved'].map(v => [v, conversationStatus(v)])); statuses.value = doc.workflow_status; statuses.disabled = !this.boot.supervisor && doc.assigned_to !== this.boot.user; statuses.title = statuses.disabled ? 'Assign this conversation to yourself to change its status.' : 'Open: needs attention. Waiting: awaiting a response. Resolved: finished.'; statuses.onchange = () => this.perform(async () => { await call('inbox.set_status', {name: doc.name, version: doc.version, status: statuses.value}); await this.open(doc.name); }); this.details.append(statuses);
            this.details.append(el('h4', 'Contact'), el('p', doc.recipient), el('span', data.peer.suppressed ? 'Messages to this number are blocked.' : data.peer.consent_recorded ? 'Permission to receive messages recorded. Source: ' + data.peer.consent_source : 'Permission to receive template messages has not been recorded.', 'wm-meta'));
            if (this.boot.supervisor) this.details.append(button('Messaging permissions', () => {
                const d = new frappe.ui.Dialog({title: 'Messaging permissions', fields: [{fieldname: 'suppressed', fieldtype: 'Check', label: 'Block messages to this number', description: 'Stops all outgoing messages, including replies and templates.', default: data.peer.suppressed}, {fieldname: 'consent_recorded', fieldtype: 'Check', label: 'This contact has agreed to receive messages', description: 'Select only if the contact has given permission. Required for template messages.', default: data.peer.consent_recorded}, {fieldname: 'consent_source', fieldtype: 'Data', label: 'How was permission received?', description: 'For example: appointment booking form or a signed consent form.', default: data.peer.consent_source}], primary_action_label: 'Save permissions', primary_action: v => this.perform(async () => { await call('inbox.set_eligibility', {...v, peer: data.peer.name}); d.hide(); await this.open(doc.name); })}); d.show();
            }));
            this.details.append(el('h4', 'Linked records'));
            if (data.flow_session) {
                const session = data.flow_session;
                this.details.append(el('h4', 'Automatic replies'), el('p', session.state === 'Waiting for staff' ? 'Reception requested' : session.state));
                this.details.append(button('Flow details', () => {
                    let answers = {}; try { answers = typeof session.answers_json === 'string' ? JSON.parse(session.answers_json || '{}') : session.answers_json || {}; } catch { /* Older sessions may have no answers. */ }
                    const fields = [{fieldname:'flow',fieldtype:'Link',options:'WhatsApp Conversation Flow',label:'Conversation flow',default:session.flow,read_only:1}, {fieldname:'progress',fieldtype:'Data',label:'Progress',default:session.state,read_only:1}];
                    Object.entries(answers).forEach(([key,value],i)=>fields.push({fieldname:'answer_'+i,fieldtype:'Small Text',label:key.replaceAll('_',' '),default:String(value),read_only:1}));
                    if (session.pause_reason) fields.push({fieldname:'note',fieldtype:'Small Text',label:'Staff note',default:session.pause_reason,read_only:1});
                    new frappe.ui.Dialog({title:'Conversation flow details',fields}).show();
                }));
                this.details.append(button(session.state === 'Active' ? 'Pause automatic replies' : 'Allow menu requests', () => this.perform(async () => {
                    await call('flows.control', {conversation_name:doc.name,action:session.state === 'Active' ? 'Pause' : 'Resume'}); await this.open(doc.name);
                })));
            }
            for (const link of data.links) this.details.append(button(link.reference_doctype + ': ' + link.reference_name, () => route(['Form', link.reference_doctype, link.reference_name])));
            this.details.append(button('Link a record', () => {
                const d = new frappe.ui.Dialog({title: 'Link a record', fields: [{fieldname: 'doctype', fieldtype: 'Link', options: 'DocType', label: 'Record type', description: 'For example: Patient or Appointment. You can only link records you have access to.', reqd: 1}, {fieldname: 'docname', fieldtype: 'Dynamic Link', options: 'doctype', label: 'Choose a record', reqd: 1}], primary_action_label: 'Link record', primary_action: v => this.perform(async () => { await call('inbox.link_record', {name: doc.name, ...v}); d.hide(); await this.open(doc.name); })}); d.show();
            }));
            this.details.append(el('h4', 'Conversation history')); for (const item of data.activity) this.details.append(el('p', ({Assignment: 'Assignment changed', Status: 'Status changed', Link: 'Record linked', Eligibility: 'Messaging permissions updated', Cancel: 'Message cancelled', Retry: 'Message queued again'}[item.action] || item.action) + ' · ' + item.actor + ' · ' + localStamp(item.creation), 'wm-meta'));
        }
        toggleDetails(show = !this.grid.classList.contains('show-details')) {
            this.grid.classList.toggle('show-details', show);
            this.detailsToggle?.setAttribute('aria-expanded', String(show));
            if (show) this.details.querySelector('.wm-details-close')?.focus();
            else this.detailsToggle?.focus();
        }
        newConversation() {
            if (!this.boot.accounts.length) { frappe.msgprint('Ask an administrator to add your business WhatsApp number in Administration first.'); return; }
            const d = new frappe.ui.Dialog({title: 'New conversation', fields: [{fieldname: 'account_name', fieldtype: 'Select', label: 'Business WhatsApp number', description: 'The number your messages will be sent from.', reqd: 1, options: this.boot.accounts.map(a => ({label: a.label, value: a.name}))}, {fieldname: 'recipient', fieldtype: 'Data', label: 'Contact’s WhatsApp number', description: 'Include the country code, for example +91 followed by the mobile number. Opening a conversation does not send a message.', reqd: 1}], primary_action_label: 'Open conversation', primary_action: v => this.perform(async () => { const result = await call('inbox.new_conversation', v); d.hide(); await this.open(result.name); await this.refresh(); })}); d.show();
        }
    };

    whatsapp_messaging.Automation = class extends Base {
        constructor(wrapper) { super(wrapper, __('WhatsApp Automation')); this.start().catch(e => this.fail(e)); }
        async start() {
            await this.init(); const summary = await call('api.overview', {section: 'automation'}); const cards = el('div', undefined, 'wm-grid');
            for (const card of summary.cards) { const b = button('', () => route(card.route, card.route_options), 'wm-stat'); b.append(el('strong', card.value), el('span', card.label)); cards.append(b); } this.root.append(cards);
            const tools = el('div', undefined, 'wm-actions');
            this.kind = select('Run kind', [['', 'All runs'], ['Schedule', 'Schedules'], ['Event', 'Document events'], ['Manual', 'Manual sends'], ...(this.boot.supervisor ? [['Campaign', 'Campaigns']] : [])]);
            this.state = select('Run state', [['', 'All states'], ...['Ready', 'Completed', 'Paused', 'Failed', 'Skipped', 'Cancelled'].map(v => [v, v])]);
            const opts = frappe.route_options || {}; this.kind.value = opts.kind || ''; this.ruleFilter = opts.rule || null; frappe.route_options = null;
            this.kind.onchange = () => this.perform(() => this.refresh()); this.state.onchange = () => this.perform(() => this.refresh());
            tools.append(this.kind, this.state, button('New schedule', () => whatsapp_messaging.scheduleDialog(this.boot)), button('Conversation Flows', () => route(['List', 'WhatsApp Conversation Flow'])), button('Campaigns', () => route(['List', 'WhatsApp Campaign'])), button('Templates', () => route(['List', 'WhatsApp Message Template'])));
            if (this.boot.supervisor) tools.append(button('Preview campaign', () => this.campaignDialog()));
            this.ruleLabel = el('p', this.ruleFilter ? 'Rule: ' + this.ruleFilter : '', 'wm-meta'); tools.append(button('Clear filters', () => { this.ruleFilter = null; this.kind.value = ''; this.state.value = ''; this.ruleLabel.textContent = ''; this.perform(() => this.refresh()); })); this.root.append(tools, this.ruleLabel); this.rows = el('div'); this.root.append(this.rows); this.loadMore = button('Load more runs', () => this.perform(() => this.refresh(true))); this.root.append(this.loadMore);
            await this.refresh();
        }
        async onShow() {
            if (!this.boot || !this.kind) return;
            const opts = frappe.route_options || {}; frappe.route_options = null;
            this.kind.value = opts.kind || ''; this.ruleFilter = opts.rule || null; this.ruleLabel.textContent = this.ruleFilter ? 'Rule: ' + this.ruleFilter : '';
            await this.refresh();
        }
        async refresh(append = false) {
            if (!append) { this.offset = 0; this.rows.replaceChildren(); }
            const runs = await call('api.runs', {kind: this.kind.value || null, state: this.state.value || null, rule: this.ruleFilter, start: this.offset}); this.offset += runs.length; this.loadMore.hidden = runs.length < 40;
            if (!runs.length && !append) this.rows.append(el('p', 'No automation runs yet. Configure a campaign, then create a schedule or preview a bulk run.', 'wm-empty'));
            for (const run of runs) {
                const box = el('article', undefined, 'wm-run'); box.append(el('h4', run.rule + ' · ' + run.kind + ' · ' + run.state), el('span', (run.due_at ? stamp(run.due_at) : localStamp(run.creation)) + ' · ' + run.run_as, 'wm-meta'), el('p', run.records_processed + '/' + run.records_selected + ' records processed · ' + run.messages_created + ' messages queued · ' + run.records_excluded + ' excluded'));
                const states = Object.entries(run.delivery).filter(([, n]) => n).map(([s, n]) => s + ': ' + n).join(' · '); if (states) box.append(el('p', states, 'wm-meta'));
                if (run.last_error) box.append(el('p', run.last_error, 'wm-meta'));
                const actions = el('div', undefined, 'wm-actions'); actions.append(button('View details', () => this.perform(() => this.details(run))));
                if (run.state === 'Preview' && this.boot.supervisor) actions.append(button('Review preview', () => this.perform(() => this.showPreview(run.name))));
                if (['Ready', 'Expanding', 'Completed'].includes(run.state)) actions.append(button('Pause', () => this.control(run, 'Pause')));
                if (run.state === 'Paused') actions.append(button('Resume', () => this.control(run, 'Resume')));
                if (!['Cancelled', 'Skipped', 'Failed', 'Preview'].includes(run.state)) actions.append(button('Cancel remaining', () => this.control(run, 'Cancel')));
                if (run.kind !== 'Manual' && ['Failed', 'Skipped', 'Completed'].includes(run.state)) { const b = button('Create new run', () => frappe.confirm('Create a new run with a fresh source snapshot? This is a deliberate new send.', () => this.perform(async () => { await call('automation.rerun', {name: run.name}); await this.refresh(); }))); b.disabled = !this.boot.outbound_enabled; actions.append(b); }
                box.append(actions); this.rows.append(box);
            }
        }
        control(run, action) { this.perform(async () => { await call('automation.control_run', {name: run.name, action}); await this.refresh(); }); }
        async details(run) {
            const result = await call('api.run_detail', {name: run.name}); const d = new frappe.ui.Dialog({title: run.rule + ' · Send results', size: 'large', fields: [{fieldname: 'results', fieldtype: 'HTML'}]}); const root = d.fields_dict.results.$wrapper[0];
            if (!result.intents.length) root.append(el('p', 'No send intents were created.'));
            for (const row of result.intents) { const item = el('div', undefined, 'wm-preview-item'); item.append(el('p', row.state + ' · attempt ' + row.attempt_count), el('p', row.error_reason || '', 'wm-meta'), button('View conversation', () => { d.hide(); route(['whatsapp-inbox'], {conversation: row.conversation}); }));
                if (row.state === 'Failed') item.append(button('Retry confirmed failure', () => this.perform(async () => { await call('outbox.retry', {name: row.name}); d.hide(); await this.refresh(); })));
                if (['Ready', 'Retry wait', 'Held'].includes(row.state)) item.append(button('Cancel', () => this.perform(async () => { await call('outbox.cancel', {name: row.name, reason: 'Cancelled from run details'}); d.hide(); await this.refresh(); })));
                root.append(item);
            } d.show();
        }
        campaignDialog() {
            const d = new frappe.ui.Dialog({title: 'Preview bulk campaign', fields: [{fieldname: 'rule_name', fieldtype: 'Link', options: 'WhatsApp Campaign', label: 'Campaign', reqd: 1, get_query: () => ({filters: {disable: 0, is_single: 1}})}], primary_action_label: 'Preview records and content', primary_action: v => this.perform(async () => { const result = await call('automation.preview_campaign', v); d.hide(); await this.showPreview(result.run); })}); d.show();
        }
        async showPreview(name) {
            const data = await call('automation.preview_page', {name}); const d = new frappe.ui.Dialog({title: 'Campaign preview · ' + data.records + ' business records', size: 'large', fields: [{fieldname: 'preview', fieldtype: 'HTML'}], primary_action_label: 'Start campaign', primary_action: () => this.perform(async () => { await call('automation.start_campaign', {name}); d.hide(); await this.refresh(); })});
            const root = d.fields_dict.preview.$wrapper[0]; root.append(el('p', 'One message per business record and recipient. Shared phone numbers may receive multiple record-specific messages.'));
            const rows = el('div', undefined, 'wm-preview'); root.append(rows);
            const render = page => { for (const item of page.items) { const row = el('div', undefined, 'wm-preview-item'); row.append(el('strong', item.source || 'Excluded record'), el('p', item.excluded ? item.reason : item.recipients + ' recipient(s)\n' + (item.body || item.parameters.join(' · ')) + (item.attachment ? '\nAttachment included' : ''))); rows.append(row); } };
            render(data); let next = data.next_start;
            const more = button('Load more preview records', () => this.perform(async () => { const page = await call('automation.preview_page', {name, start: next}); render(page); next = page.next_start; more.hidden = next === null; })); more.hidden = next === null; root.append(more);
            d.show(); d.get_primary_btn().prop('disabled', !this.boot.outbound_enabled); if (!this.boot.outbound_enabled) root.prepend(el('p', 'Starting campaigns is disabled by the outbound setting.'));
        }
    };

    whatsapp_messaging.scheduleDialog = async function(boot, ruleName, onSaved) {
        boot = boot || await call('api.bootstrap');
        const d = new frappe.ui.Dialog({title: 'Create or update schedule', fields: [{fieldname: 'rule_name', fieldtype: 'Link', options: 'WhatsApp Campaign', label: 'Campaign', reqd: 1, default: ruleName}, {fieldname: 'when', fieldtype: 'Datetime', label: 'First occurrence (local time)'}, {fieldname: 'cron_expression', fieldtype: 'Data', label: 'Recurrence (cron; leave blank for one-time)'}, {fieldname: 'timezone_name', fieldtype: 'Data', label: 'Timezone', reqd: 1, default: boot.timezone}], primary_action_label: 'Save schedule', primary_action: async values => { try { await call('automation.save_schedule', values); d.hide(); if (onSaved) await onSaved(values.rule_name); frappe.show_alert('Schedule saved. Dispatch still follows the integration switches.'); } catch { /* Frappe shows the server validation error. */ } }}); d.show();
    };
})();
