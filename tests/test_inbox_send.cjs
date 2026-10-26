// Run with: node --test tests/test_inbox_send.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function inboxFixture(request) {
    const alerts = [];
    const context = {
        whatsapp_messaging: {},
        document: {getElementById: () => true},
        frappe: {provide() {}, call: request, show_alert: v => alerts.push(v.message)},
        crypto: {randomUUID: () => 'stable-send-id'},
        console: {warn() {}},
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../whatsapp_messaging/public/js/messaging.js'), 'utf8'), context);
    const inbox = Object.create(context.whatsapp_messaging.Inbox.prototype);
    Object.assign(inbox, {
        selected: 'conversation-1', drafts: new Map(), busy: false,
        composer() {}, async open() {}, async refresh() {},
        error: {textContent: '', focus() {}},
    });
    inbox.draft(inbox.selected).body = 'Fictional training reply';
    return {inbox, alerts};
}

test('uncertain send keeps the draft and request ID without automatically sending again', async () => {
    const requests = [];
    let fail = true;
    const {inbox, alerts} = inboxFixture(async ({args}) => {
        requests.push(args);
        if (fail) throw new Error('Network interrupted');
        return {message: {state: 'Ready'}};
    });
    assert.equal(await inbox.send(), false);
    assert.equal(requests.length, 1);
    assert.equal(inbox.draft(inbox.selected).body, 'Fictional training reply');
    assert.equal(inbox.busy, false);
    assert.match(inbox.error.textContent, /avoid sending twice/);
    assert.match(inbox.error.textContent, /until you reload or leave/);
    fail = false;
    assert.equal(await inbox.send(), true);
    assert.equal(requests[1].request_id, requests[0].request_id);
    assert.equal(inbox.drafts.size, 0);
    assert.deepEqual(alerts, ['Message status: Waiting to send']);
});

test('a refresh failure after submission reports the saved message without restoring a sendable draft', async () => {
    let calls = 0;
    const {inbox} = inboxFixture(async () => { calls++; return {message: {state: 'Ready'}}; });
    inbox.open = async () => { throw new Error('Refresh unavailable'); };
    assert.equal(await inbox.send(), true);
    assert.equal(calls, 1);
    assert.equal(inbox.drafts.size, 0);
    assert.equal(inbox.busy, false);
    assert.match(inbox.error.textContent, /message was saved/);
    assert.doesNotMatch(inbox.error.textContent, /draft/);
});

test('acceptance and uncertain outcomes do not claim delivery', async () => {
    for (const [state, text] of [['Accepted', 'Accepted by WhatsApp'], ['Unknown', 'Send status not confirmed'], ['Held', 'Needs attention']]) {
        const {inbox, alerts} = inboxFixture(async () => ({message: {state}}));
        assert.equal(await inbox.send(), true);
        assert.deepEqual(alerts, ['Message status: ' + text]);
    }
});
