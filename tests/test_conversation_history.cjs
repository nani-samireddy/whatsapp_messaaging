const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.scrollTop = 0; }
    set textContent(value) { this.text = String(value); this.children = []; }
    get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(''); }
    set innerHTML(_) { throw new Error('Message content must never be parsed as HTML'); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; this.text = ''; }
    setAttribute(name, value) { this.attributes[name] = value; }
    get scrollHeight() { return this.children.length * 30; }
}
function fixture(request) {
    const calls = [];
    const context = {whatsapp_messaging:{}, document:{createElement:tag => new Element(tag)},
        __:(text, values=[]) => text.replace(/\{(\d+)\}/g, (_, i) => values[i]),
        frappe:{provide(){},ui:{form:{on(){}}},call:async args => { calls.push(args); return {message:await request(args)}; }}};
    const file = path.join(__dirname,'../whatsapp_messaging/whatsapp_messaging/doctype/whatsapp_conversation/whatsapp_conversation.js');
    vm.runInNewContext(fs.readFileSync(file,'utf8'),context);
    const frm = {doc:{name:'conversation-1'}};
    const history = new context.whatsapp_messaging.ConversationHistory(frm,new Element('div'));
    frm.__conversation_history = history;
    return {history,frm,calls};
}
const message = sequence => ({name:'message-'+sequence,sequence,direction:'Inbound',message:'Text '+sequence,status:'Received'});
const page = messages => ({messages,peer:{display_name:'Training contact'},conversation:{recipient:'12025550126'}});

test('all messages remain reachable in order using bounded read-only pages', async () => {
    const {history,calls} = fixture(async ({args}) => page(args.before ? [message(1)] : Array.from({length:40},(_, i)=>message(i+2))));
    await history.load();
    assert.equal(history.hasMore,true);
    assert.equal(history.messages.length,40);
    await history.load(true);
    assert.equal(history.messages.length,41);
    assert.equal(history.messages[0].sequence,1);
    assert.equal(history.messages[40].sequence,41);
    assert.equal(history.hasMore,false);
    assert.match(history.notice.textContent,/All 41 messages/);
    assert.equal(calls[1].args.before,2);
    assert.ok(calls.every(call=>call.type==='GET' && call.args.limit===40 && call.method==='whatsapp_messaging.messaging.inbox.get_conversation'));
});
test('HTML-looking text stays literal and private attachments use the authorized download', async () => {
    const body='<img src=x onerror=alert(1)>';
    const item={...message(1),message:body,attachments:[{name:'private & file',file_name:'Leaflet.pdf',state:'Ready'},
        {name:'blocked',file_name:'Untrusted.pdf',state:'Blocked'}]};
    const {history}=fixture(async()=>page([item]));
    await history.load();
    assert.equal(history.timeline.children[0].children[0].textContent,body);
    const links=history.timeline.children[0].children.filter(node=>node.tag==='a');
    assert.equal(links.length,1);
    assert.equal(links[0].href,'/api/method/whatsapp_messaging.messaging.media.download?name=private%20%26%20file');
    assert.equal(links[0].rel,'noopener noreferrer');
});
test('a late response cannot replace history after switching conversations', async () => {
    let resolve;
    const {history,frm}=fixture(()=>new Promise(done=>{resolve=done;}));
    const loading=history.load();
    frm.doc.name='conversation-2';
    resolve(page([message(1)]));
    await loading;
    assert.equal(history.timeline.children.length,0);
});
test('a failed older-page request preserves the visible messages and retry cursor', async () => {
    let fail=false;
    const {history}=fixture(async()=>{if(fail)throw new Error('Permission or network failure');return page(Array.from({length:40},(_,i)=>message(i+2)));});
    await history.load(); fail=true;
    await history.load(true);
    assert.equal(history.messages.length,40);
    assert.equal(history.messages[0].sequence,2);
    assert.equal(history.olderButton.disabled,false);
    assert.match(history.notice.textContent,/could not be loaded/);
});
