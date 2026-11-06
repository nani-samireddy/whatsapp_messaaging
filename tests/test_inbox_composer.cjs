const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
    constructor(tag) { this.tag=tag;this.children=[];this.attributes={};this.dataset={};this.classList={add(){},toggle(){}}; }
    append(...items) { for (const item of items) {item.parent=this;this.children.push(item);} }
    setAttribute(name,value) {this.attributes[name]=value;}
    querySelector(selector) {
        for (const child of this.children) {
            if ((selector.startsWith('.') && (child.className||'').split(' ').includes(selector.slice(1))) || child.tag===selector) return child;
            const nested=child.querySelector(selector);if(nested)return nested;
        }
        return null;
    }
    focus() {this.focused=true;}
    remove() {if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}
}
async function fixture({windowOpen=true,enabled=true,blocked=false,busy=false}={}) {
    const context={whatsapp_messaging:{},document:{getElementById:()=>true,createElement:tag=>new Element(tag),createDocumentFragment:()=>new Element('fragment')},
        frappe:{provide(){},utils:{icon:()=>'<svg></svg>'}},crypto:{randomUUID:()=> 'training-request'},console};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../whatsapp_messaging/public/js/messaging.js'),'utf8'),context);
    const inbox=Object.create(context.whatsapp_messaging.Inbox.prototype);
    Object.assign(inbox,{selected:'conversation-1',drafts:new Map(),busy,boot:{outbound_enabled:enabled},
        data:{window_open:windowOpen,peer:{suppressed:blocked}},thread:new Element('section')});
    inbox.draft(inbox.selected).body='Training draft';
    await inbox.composer();
    const all=[];const walk=node=>{all.push(node);node.children.forEach(walk);};walk(inbox.thread);
    return {inbox,find:label=>all.find(node=>node.attributes['aria-label']===label)};
}
test('closed reply window preserves the draft and offers only the template sending path',async()=>{
    const {inbox,find}=await fixture({windowOpen:false});
    assert.equal(inbox.text.readOnly,true);
    assert.equal(inbox.text.value,'Training draft');
    assert.equal(find('Send reply').disabled,true);
    assert.equal(find('Attach image or PDF').disabled,true);
    assert.equal(find('Send a template').disabled,false);
    assert.equal(inbox.draft('conversation-1').body,'Training draft');
});
test('blocked contact or disabled sending cannot use either sending control',async()=>{
    for(const options of [{blocked:true},{enabled:false}]){
        const {inbox,find}=await fixture(options);
        assert.equal(inbox.text.readOnly,true);
        assert.equal(find('Send reply').disabled,true);
        assert.equal(find('Attach image or PDF').disabled,true);
        assert.equal(find('Send a template').disabled,true);
    }
});
test('an open reply window allows editing while an in-flight send locks the existing draft',async()=>{
    const {inbox,find}=await fixture();
    assert.equal(inbox.text.readOnly,false);
    assert.equal(find('Send reply').disabled,false);
    inbox.text.value='Updated training draft';inbox.text.oninput();
    assert.equal(inbox.draft('conversation-1').body,'Updated training draft');
    inbox.busy=true;await inbox.composer();
    assert.equal(inbox.text.readOnly,true);
    assert.equal(inbox.text.value,'Updated training draft');
});

test('date dividers group messages and a quoted reply shows the original plain text',async()=>{
    const {inbox}=await fixture();
    const first={
        direction:'Inbound', message:'<b>Appointment request</b>', message_type:'text',
        provider_message_id:'training-message-1', received_at:'2026-10-24 12:00:00',
    };
    const fragment=inbox.renderMessages([
        first,
        {...first,provider_message_id:'training-message-2'},
        {...first,direction:'Outbound',received_at:'2026-10-25 12:00:00',status:'Read'},
    ]);
    assert.equal(fragment.children.filter(node=>node.className==='wm-chat-date').length,2);
    assert.equal(fragment.querySelector('time').dateTime,'2026-10-24T12:00:00.000Z');
    assert.equal(fragment.querySelector('.wm-message-status').textContent,'Read');
    fragment.querySelector('.wm-message-reply').onclick();
    assert.equal(inbox.draft('conversation-1').reply,'training-message-1');
    assert.equal(inbox.thread.querySelector('.wm-quote-preview').textContent,first.message);
    assert.equal(inbox.text.value,'Training draft');
    assert.equal(inbox.text.focused,true);
    inbox.thread.querySelector('.wm-compose-quote').querySelector('button').onclick();
    assert.equal(inbox.draft('conversation-1').reply,null);
    assert.equal(inbox.thread.querySelector('.wm-quote-preview'),null);
});
