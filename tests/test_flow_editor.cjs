const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function editor() {
    let handler, mapOptions, dialog; const notices=[];
    const element=()=>({style:{},append(){},replaceChildren(){}});
    const context={document:{createElement:element},__:(v)=>v,
        whatsapp_messaging:{FlowMap:class {constructor(root,options){mapOptions=options;}dispose(){}}},
        frappe:{user_roles:['Whatsapp Admin'],msgprint:v=>notices.push(v),ui:{form:{on:(name,events)=>handler=events},Dialog:class{constructor(options){dialog=options;}show(){}hide(){}}}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../whatsapp_messaging/whatsapp_messaging/doctype/whatsapp_conversation_flow/whatsapp_conversation_flow.js'),'utf8'),context);
    const step={name:'step-row',step_key:'main',step_type:'Menu',prompt:'Welcome'};
    const choice=(name,from_step,choice_key,label,next_step)=>({name,doctype:'WhatsApp Flow Choice',parent:'flow-1',parentfield:'choices',parenttype:'WhatsApp Conversation Flow',from_step,choice_key,label,next_step});
    const form={doc:{start_step:'main',steps:[step,{name:'end-row',step_key:'end',step_type:'End',prompt:'Done'}],choices:[choice('existing-1','main','option_1','First','end'),choice('existing-2','main','option_2','Second','main'),choice('unrelated','other','information','Hospital info','end')]},
        fields_dict:{builder:{$wrapper:[element()]}},set_df_property(){},refresh_field(){},add_custom_button(){},is_new(){return false;},dashboard:{set_headline_alert(){}},dirty(){this.changed=true;},add_child(field,values={}){const row={name:'new-'+this.doc[field].length,...values};this.doc[field].push(row);return row;}};
    handler.refresh(form);mapOptions.onEdit(step);
    const data=dialog.fields.find(f=>f.fieldname==='options').data;
    const apply=rows=>dialog.primary_action({step_key:'main',step_type:'Menu',prompt:'Welcome',options:rows});
    return {form,data,apply,notices,getMap:()=>mapOptions};
}

test('option inputs get independent plain dialog rows, without saved-record permissions',()=>{
    const {form,data}=editor();assert.equal(data[0].label,'First');
    for(const row of data)for(const key of ['doctype','name','parent','parentfield','parenttype'])assert.equal(key in row,false,key);
    data[0].label='Cancelled edit';assert.equal(form.doc.choices[0].label,'First');assert.equal(form.changed,undefined);
});
test('editing text and destination preserves child identity and untouched menus',()=>{
    const {form,data,apply}=editor(),original=form.doc.choices.slice();
    data[0].label='New label';data[0].next_step='main';apply(data);
    assert.equal(form.doc.choices[0],original[0]);assert.equal(form.doc.choices[1],original[1]);assert.equal(form.doc.choices[2],original[2]);
    assert.equal(original[0].label,'New label');assert.equal(original[0].next_step,'main');assert.equal(form.changed,true);
});
test('removing and adding an option does not reuse another option key',()=>{
    const {form,data,apply}=editor();apply([data[1],{label:'New option',next_step:'end'}]);
    const rows=form.doc.choices.filter(c=>c.from_step==='main');assert.equal(rows.length,2);assert.equal(new Set(rows.map(c=>c.choice_key)).size,2);assert.equal(rows[0].name,'existing-2');assert.ok(!form.doc.choices.some(c=>c.name==='existing-1'));
});
test('duplicating a choice gets its own key and child record',()=>{
    const {form,data,apply}=editor();apply([data[0],{...data[0],label:'Another option'}]);
    const rows=form.doc.choices.filter(c=>c.from_step==='main');assert.equal(new Set(rows.map(c=>c.choice_key)).size,2);assert.notEqual(rows[0],rows[1]);
});
test('invalid menu choices are rejected before the draft changes',()=>{
    for(const rows of [[],[{label:'A label that is much too long for WhatsApp',next_step:'end'}],[{label:'Duplicate',next_step:'end'},{label:'duplicate',next_step:'main'}],[{label:'Missing target',next_step:'unknown'}]]){
        const {form,apply,notices}=editor(),before=JSON.stringify(form.doc);apply(rows);assert.ok(notices.length);assert.equal(JSON.stringify(form.doc),before);assert.equal(form.changed,undefined);
    }
});

test('menu choice named next reconnects its choice rather than a step property',()=>{
    const {form,getMap}=editor();form.doc.choices[0].choice_key='next';
    getMap().onConnect({source:'main',port:'next',target:'main'});
    assert.equal(form.doc.choices[0].next_step,'main');assert.equal(form.doc.steps[0].next_step,undefined);
    getMap().onUndo();assert.equal(form.doc.choices[0].next_step,'end');
    getMap().onRedo();assert.equal(form.doc.choices[0].next_step,'main');
});
