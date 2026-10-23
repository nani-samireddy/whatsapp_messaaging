frappe.provide('whatsapp_messaging');
(() => {
    const prefix = 'whatsapp_messaging.messaging.';
    const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
    const call = async (method, args = {}) => (await frappe.call({method: prefix + method, args, type: 'POST'})).message;
    const route = (target, options = {}) => { frappe.route_options = options; frappe.set_route(target); };
    const button = (text, action, cls = 'btn btn-default btn-sm') => { const n = el('button', text, cls); n.type = 'button'; n.onclick = action; return n; };
    const input = (placeholder, type = 'text') => { const n = el('input'); n.type = type; n.className = 'form-control'; n.placeholder = placeholder; n.setAttribute('aria-label', placeholder); return n; };
    const select = (label, values) => { const n = el('select', undefined, 'form-control'); n.setAttribute('aria-label', label); for (const [value, text] of values) { const o = el('option', text); o.value = value; n.append(o); } return n; };
    const localStamp = value => value ? frappe.datetime.str_to_user(value) : '';
    const stamp = value => value ? new Date(String(value).replace(' ', 'T').replace(/Z?$/, 'Z')).toLocaleString() : '';
    const styles = `
.wm-shell{padding:16px}.wm-banner{padding:10px 14px;background:var(--subtle-fg,#f5f6f8);border-radius:8px;margin-bottom:12px}.wm-error{color:var(--red-600,#a72020);padding:10px}.wm-inbox{display:grid;grid-template-columns:minmax(240px,28%) minmax(320px,1fr) 240px;gap:12px;min-height:65vh}.wm-list,.wm-thread,.wm-details{border:1px solid var(--border-color,#ddd);border-radius:10px;overflow:hidden;background:var(--card-bg,#fff)}.wm-filters{display:grid;gap:8px;padding:12px}.wm-conversations{max-height:62vh;overflow:auto}.wm-conversation{display:block;width:100%;padding:12px;text-align:left;border:0;border-top:1px solid var(--border-color,#ddd);background:transparent;color:inherit}.wm-conversation[aria-current=true]{background:var(--control-bg,#eee)}.wm-meta{display:block;color:var(--text-muted,#666);font-size:12px}.wm-thread{display:flex;flex-direction:column}.wm-thread-head{padding:12px;border-bottom:1px solid var(--border-color,#ddd)}.wm-timeline{padding:14px;overflow:auto;max-height:53vh;min-height:280px;flex:1}.wm-message{padding:10px 12px;border-radius:10px;margin:10px 0;background:var(--subtle-fg,#f5f6f8);max-width:90%;white-space:pre-wrap;overflow-wrap:anywhere}.wm-message.outbound{margin-left:auto;background:var(--blue-50,#eef5ff)}.wm-message .wm-meta{margin-top:6px}.wm-message img{max-width:220px;max-height:180px;display:block;margin:8px 0}.wm-composer{padding:12px;border-top:1px solid var(--border-color,#ddd);display:grid;gap:8px}.wm-composer textarea{resize:vertical;min-height:75px}.wm-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.wm-details{padding:12px;overflow-wrap:anywhere}.wm-details h4{margin-top:18px}.wm-empty{padding:28px;color:var(--text-muted,#666);text-align:center}.wm-run{border:1px solid var(--border-color,#ddd);padding:14px;border-radius:10px;margin:12px 0}.wm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;margin:12px 0}.wm-stat{padding:14px;border:1px solid var(--border-color,#ddd);border-radius:8px;cursor:pointer;background:var(--card-bg,#fff);color:inherit;text-align:left}.wm-stat strong{display:block;font-size:24px}.wm-preview{max-height:50vh;overflow:auto}.wm-preview-item{padding:12px;border-bottom:1px solid var(--border-color,#ddd);white-space:pre-wrap}@media(max-width:1050px){.wm-inbox{grid-template-columns:260px 1fr}.wm-details{grid-column:1/-1}}@media(max-width:700px){.wm-inbox.mobile-thread .wm-list{display:none}.wm-shell{padding:6px}.wm-inbox{display:block}.wm-thread,.wm-details{display:none}.wm-inbox.mobile-thread .wm-thread{display:flex}.wm-inbox.mobile-thread.show-details .wm-details{display:block}.wm-timeline{max-height:50vh}.wm-list{min-height:60vh}}`;
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
        fail(error) { this.error.textContent = 'This action could not be completed. Review the error, refresh, and try again. Your draft is preserved.'; this.error.focus(); console.warn('WhatsApp action failed', error?.status || 'request'); }
        async init() {
            this.boot = await call('api.bootstrap');
            this.banner.textContent = this.boot.outbound_enabled ? 'Outbound enabled. Provider delivery is tracked separately from acceptance.' : 'Outbound messaging is disabled. You can browse and configure the app.';
            if (!this.boot.accounts.length) this.banner.append(el('span', this.boot.manager ? ' Configure a sender in Administration to get started.' : ' Ask your System Manager to configure a sender account.'));
        }
        async perform(fn) { this.error.textContent = ''; try { return await fn(); } catch (e) { this.fail(e); } }
    }

    whatsapp_messaging.Inbox = class extends Base {
        constructor(wrapper) {
            super(wrapper, __('WhatsApp Inbox'));
            this.selected = null; this.cursor = null; this.busy = false; this.drafts = new Map(); this.items = [];
            this.start().catch(e => this.fail(e));
        }
        async start() {
            await this.init();
            this.grid = el('div', undefined, 'wm-inbox'); this.root.append(this.grid);
            this.list = el('section', undefined, 'wm-list'); this.list.setAttribute('aria-label', 'Conversations');
            const filters = el('div', undefined, 'wm-filters');
            this.sender = select('Business phone', [['', 'All senders'], ...this.boot.accounts.map(a => [a.name, a.label])]);
            this.search = input('Search recipient or name');
            this.status = select('Conversation status', [['', 'All statuses'], ...['Open', 'Pending', 'Resolved'].map(v => [v, v])]);
            this.assignment = select('Assignment and unread', [['', 'All conversations'], ...['Mine', 'Unassigned', 'Unread'].map(v => [v, v])]);
            const options = frappe.route_options || {}; this.status.value = options.status || ''; this.assignment.value = options.assignment || ''; frappe.route_options = null;
            for (const n of [this.sender, this.status, this.assignment]) n.onchange = () => this.perform(() => this.refresh());
            let debounce; this.search.oninput = () => { clearTimeout(debounce); debounce = setTimeout(() => this.perform(() => this.refresh()), 250); };
            filters.append(this.sender, this.search, this.status, this.assignment, button('New conversation', () => this.newConversation()));
            this.rows = el('div', undefined, 'wm-conversations'); this.more = button('Load more conversations', () => this.perform(() => this.loadMore())); this.more.hidden = true;
            this.list.append(filters, this.rows, this.more);
            this.thread = el('section', undefined, 'wm-thread'); this.thread.setAttribute('aria-label', 'Message thread'); this.thread.append(el('p', 'Choose a conversation', 'wm-empty'));
            this.details = el('aside', undefined, 'wm-details'); this.details.setAttribute('aria-label', 'Conversation details');
            this.grid.append(this.list, this.thread, this.details);
            this.changed = () => { clearTimeout(this.changeTimer); this.changeTimer = setTimeout(() => { if (!this.root.isConnected || this.wrapper.style.display === 'none') return; this.perform(async () => { await this.refresh(); if (this.selected && !this.busy && document.activeElement !== this.text) await this.open(this.selected, true); }); }, 400); };
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
                b.append(el('strong', row.display_name || row.recipient), el('span', row.account + ' · ' + row.workflow_status + (row.unread ? ' · ' + row.unread + ' unread' : ''), 'wm-meta'), el('span', row.last_message || 'No messages yet'), el('time', stamp(row.activity_at), 'wm-meta')); this.rows.append(b);
            }
        }
        draft(name) { if (!this.drafts.has(name)) this.drafts.set(name, {body: '', request_id: crypto.randomUUID(), file: null, reply: null}); return this.drafts.get(name); }
        async open(name, refreshing = false) {
            if (!refreshing) { this.selected = name; this.oldest = null; }
            const requestName = this.selected; const data = await call('inbox.get_conversation', {name});
            if (this.selected !== requestName) return;
            this.data = data; this.grid.classList.add('mobile-thread'); this.thread.replaceChildren();
            const head = el('div', undefined, 'wm-thread-head');
            head.append(button('Back to conversations', () => this.grid.classList.remove('mobile-thread')), el('h4', data.peer.display_name || data.conversation.recipient), el('span', data.conversation.account + ' · ' + data.conversation.workflow_status, 'wm-meta'), button('Details', () => this.grid.classList.toggle('show-details')));
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
                } else node.append(el('span', label + ' · ' + attachment.state, 'wm-meta'));
            }
            node.append(el('span', (message.agent || (message.direction === 'Inbound' ? 'Recipient' : 'Agent')) + ' · ' + message.status + ' · ' + stamp(message.provider_at || message.received_at), 'wm-meta'));
            if (message.provider_message_id) node.append(button('Reply', () => { this.draft(this.selected).reply = message.provider_message_id; this.composer(); }));
            parent.append(node);
        }
        async composer() {
            this.thread.querySelector('.wm-composer')?.remove();
            const box = el('div', undefined, 'wm-composer'); const draft = this.draft(this.selected);
            const text = el('textarea', undefined, 'form-control'); text.value = draft.body; text.maxLength = 4096; text.setAttribute('aria-label', 'Message text'); text.placeholder = 'Write a reply'; text.oninput = () => { draft.body = text.value; };
            const notice = el('p', this.data.window_open ? 'Reply window open' : 'Reply window closed. Use an approved template.', 'wm-meta');
            const actions = el('div', undefined, 'wm-actions');
            const attach = button(draft.file ? 'Remove attachment' : 'Attach image / PDF', () => {
                if (draft.file) { draft.file = null; this.composer(); return; }
                new frappe.ui.FileUploader({is_private: 1, allow_multiple: false, restrictions: {allowed_file_types: ['.jpg', '.jpeg', '.png', '.pdf'], max_file_size: 20 * 1024 * 1024}, on_success: file => { draft.file = file; this.composer(); }});
            });
            const send = button(this.busy ? 'Queuing…' : 'Queue reply', () => this.perform(() => this.send()), 'btn btn-primary btn-sm');
            send.disabled = !this.boot.outbound_enabled || !this.data.window_open || !!this.data.peer.suppressed || this.busy;
            const approved = button('Approved template', () => this.perform(() => this.chooseTemplate())); approved.disabled = !this.boot.outbound_enabled || !!this.data.peer.suppressed;
            if (draft.reply) actions.append(button('Clear reply context', () => { draft.reply = null; this.composer(); }));
            actions.append(attach, send, approved); box.append(notice, text);
            if (draft.file) box.append(el('span', draft.file.file_name, 'wm-meta'));
            box.append(actions); this.thread.append(box); this.text = text;
        }
        async send(template, parameters) {
            if (this.busy) return; this.busy = true; const name = this.selected; const draft = this.draft(name); this.composer();
            try {
                const result = await call('outbox.send', {conversation_name: name, request_id: draft.request_id, body: template ? '' : draft.body, template, parameters: JSON.stringify(parameters || []), file_id: template ? null : draft.file?.name, reply_to: draft.reply});
                this.drafts.delete(name); frappe.show_alert({message: 'Message ' + result.state.toLowerCase(), indicator: 'blue'}); await this.open(name); await this.refresh();
            } finally { this.busy = false; if (name === this.selected) this.composer(); }
        }
        async chooseTemplate() {
            const templates = await call('catalogue.list_templates', {account_name: this.data.conversation.account});
            if (!templates.length) { frappe.msgprint('No supported approved templates are available for this sender.'); return; }
            if (!this.data.peer.consent_recorded) { frappe.msgprint('An Admin must record recipient consent before a template message can initiate contact.'); return; }
            const choose = new frappe.ui.Dialog({title: 'Approved template', fields: [{fieldname: 'template', fieldtype: 'Select', label: 'Template and language', reqd: 1, options: templates.map((t, i) => ({label: t.template_name + ' · ' + t.language, value: String(i)}))}], primary_action_label: 'Continue', primary_action: v => { choose.hide(); const t = templates[Number(v.template)]; this.parameterDialog(t); }}); choose.show();
        }
        parameterDialog(template) {
            const fields = [{fieldname: 'preview', fieldtype: 'HTML'}];
            const params = JSON.parse(template.parameters_json || '[]'); params.forEach((_, i) => fields.push({fieldname: 'p' + i, fieldtype: 'Small Text', label: 'Parameter ' + (i + 1), reqd: 1}));
            const d = new frappe.ui.Dialog({title: template.template_name + ' · ' + template.language, fields, primary_action_label: 'Queue template', primary_action: values => this.perform(async () => { await this.send(template.name, params.map((_, i) => values['p' + i])); d.hide(); })});
            const components = JSON.parse(template.components_json || '[]');
            const header = components.find(c => c.type === 'HEADER')?.text;
            const footer = components.find(c => c.type === 'FOOTER')?.text;
            d.fields_dict.preview.$wrapper.css('white-space','pre-wrap').text([header,template.body,footer].filter(Boolean).join('\n\n')); d.show();
        }
        renderDetails() {
            for (const row of this.rows.children) row.setAttribute('aria-current', String(row.dataset.conversation === this.selected));
            const data = this.data; const doc = data.conversation; this.details.replaceChildren(); this.details.append(el('h4', 'Assignment'), el('p', doc.assigned_to || 'Unassigned'));
            if (!doc.assigned_to || doc.assigned_to === this.boot.user || this.boot.supervisor) this.details.append(button(doc.assigned_to === this.boot.user ? 'Release conversation' : 'Claim conversation', () => this.perform(async () => { await call('inbox.assign', {name: doc.name, version: doc.version, user: doc.assigned_to === this.boot.user ? '' : this.boot.user}); await this.open(doc.name); })));
            if (this.boot.supervisor) this.details.append(button('Assign agent', () => this.perform(async () => {
                const agents = await call('api.agents'); const d = new frappe.ui.Dialog({title: 'Assign agent', fields: [{fieldname: 'user', fieldtype: 'Select', label: 'Agent', options: [{label: 'Unassigned', value: ''}, ...agents.map(a => ({label: a.full_name + ' (' + a.name + ')', value: a.name}))]}], primary_action_label: 'Assign', primary_action: values => this.perform(async () => { await call('inbox.assign', {name: doc.name, version: doc.version, user: values.user}); d.hide(); await this.open(doc.name); })}); d.show();
            })));
            this.details.append(el('h4', 'Status'));
            const statuses = select('Change status', ['Open', 'Pending', 'Resolved'].map(v => [v, v])); statuses.value = doc.workflow_status; statuses.disabled = !this.boot.supervisor && doc.assigned_to !== this.boot.user; statuses.onchange = () => this.perform(async () => { await call('inbox.set_status', {name: doc.name, version: doc.version, status: statuses.value}); await this.open(doc.name); }); this.details.append(statuses);
            this.details.append(el('h4', 'Recipient'), el('p', doc.recipient), el('span', data.peer.suppressed ? 'Suppressed' : data.peer.consent_recorded ? 'Consent recorded: ' + data.peer.consent_source : 'No recorded consent for initiating messages', 'wm-meta'));
            if (this.boot.supervisor) this.details.append(button('Update eligibility', () => {
                const d = new frappe.ui.Dialog({title: 'Recipient eligibility', fields: [{fieldname: 'suppressed', fieldtype: 'Check', label: 'Suppress sending', default: data.peer.suppressed}, {fieldname: 'consent_recorded', fieldtype: 'Check', label: 'Consent recorded', default: data.peer.consent_recorded}, {fieldname: 'consent_source', fieldtype: 'Data', label: 'Consent source', default: data.peer.consent_source}], primary_action_label: 'Save', primary_action: v => this.perform(async () => { await call('inbox.set_eligibility', {...v, peer: data.peer.name}); d.hide(); await this.open(doc.name); })}); d.show();
            }));
            this.details.append(el('h4', 'Linked records'));
            for (const link of data.links) this.details.append(button(link.reference_doctype + ': ' + link.reference_name, () => route(['Form', link.reference_doctype, link.reference_name])));
            this.details.append(button('Link business record', () => {
                const d = new frappe.ui.Dialog({title: 'Link permitted business record', fields: [{fieldname: 'doctype', fieldtype: 'Link', options: 'DocType', label: 'Record type', reqd: 1}, {fieldname: 'docname', fieldtype: 'Dynamic Link', options: 'doctype', label: 'Record', reqd: 1}], primary_action_label: 'Link', primary_action: v => this.perform(async () => { await call('inbox.link_record', {name: doc.name, ...v}); d.hide(); await this.open(doc.name); })}); d.show();
            }));
            this.details.append(el('h4', 'Activity')); for (const item of data.activity) this.details.append(el('p', item.action + ' · ' + item.actor + ' · ' + localStamp(item.creation), 'wm-meta'));
        }
        newConversation() {
            if (!this.boot.accounts.length) { frappe.msgprint('Configure a sender account first.'); return; }
            const d = new frappe.ui.Dialog({title: 'New conversation', fields: [{fieldname: 'account_name', fieldtype: 'Select', label: 'Sender', reqd: 1, options: this.boot.accounts.map(a => ({label: a.label, value: a.name}))}, {fieldname: 'recipient', fieldtype: 'Data', label: 'International recipient number', reqd: 1}], primary_action_label: 'Open conversation', primary_action: v => this.perform(async () => { const result = await call('inbox.new_conversation', v); d.hide(); await this.open(result.name); await this.refresh(); })}); d.show();
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
            tools.append(this.kind, this.state, button('New schedule', () => whatsapp_messaging.scheduleDialog(this.boot)), button('Campaigns', () => route(['List', 'WhatsApp Campaign'])), button('Templates', () => route(['List', 'WhatsApp Message Template'])));
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

    whatsapp_messaging.scheduleDialog = async function(boot, ruleName) {
        boot = boot || await call('api.bootstrap');
        const d = new frappe.ui.Dialog({title: 'Create or update schedule', fields: [{fieldname: 'rule_name', fieldtype: 'Link', options: 'WhatsApp Campaign', label: 'Campaign', reqd: 1, default: ruleName}, {fieldname: 'when', fieldtype: 'Datetime', label: 'First occurrence (local time)'}, {fieldname: 'cron_expression', fieldtype: 'Data', label: 'Recurrence (cron; leave blank for one-time)'}, {fieldname: 'timezone_name', fieldtype: 'Data', label: 'Timezone', reqd: 1, default: boot.timezone}], primary_action_label: 'Save schedule', primary_action: async values => { try { await call('automation.save_schedule', values); d.hide(); frappe.show_alert('Schedule saved. Dispatch still follows the integration switches.'); } catch { /* Frappe shows the server validation error. */ } }}); d.show();
    };
})();
