(() => {
    const api = async (method, args = {}) => (await frappe.call({method: 'whatsapp_messaging.messaging.flows.' + method, args, type: 'POST'})).message;
    const node = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
    const btn = (label, fn, primary = false) => { const b = node('button', label, 'btn btn-sm ' + (primary ? 'btn-primary' : 'btn-default')); b.type = 'button'; b.onclick = fn; return b; };
    const manager = () => frappe.user_roles.some(r => ['System Manager', 'Whatsapp Admin'].includes(r));
    const names = frm => (frm.doc.steps || []).map(s => s.step_key);
    // Dialog rows must be plain values. Child-record metadata makes Frappe apply
    // the hidden source table's field permissions and hide the inline inputs.
    const copyChoices = (frm, key) => (frm.doc.choices || []).filter(c => c.from_step === key).map(c => ({choice_key:c.choice_key, label:c.label, next_step:c.next_step}));
    const replaceChoices = (frm, key, choices) => {
        const before = frm.doc.choices || [];
        const previous = new Map(before.filter(c => c.from_step === key).map(c => [c.choice_key,c]));
        const updated = choices.map(c => {
            const row = previous.get(c.choice_key) || frm.add_child('choices');
            Object.assign(row,c); return row;
        });
        // Keep record identities and the untouched menus; only replace this menu's rows.
        const first = before.findIndex(c => c.from_step === key);
        const keep = before.filter(c => c.from_step !== key);
        keep.splice(first < 0 ? keep.length : first,0,...updated);
        frm.doc.choices = keep; frm.doc.choices.forEach((c,i) => c.idx=i+1); frm.refresh_field('choices');
    };
    const snapshot = frm => JSON.stringify({steps:frm.doc.steps,choices:frm.doc.choices,layout_json:frm.doc.layout_json,start_step:frm.doc.start_step});
    const remember = frm => { (frm.__flow_undo ||= []).push(snapshot(frm)); if(frm.__flow_undo.length>40)frm.__flow_undo.shift(); frm.__flow_redo=[]; };
    function travel(frm, backwards) {
        const from = backwards ? frm.__flow_undo : frm.__flow_redo, to = backwards ? (frm.__flow_redo ||= []) : (frm.__flow_undo ||= []);
        if(!from?.length)return;to.push(snapshot(frm));Object.assign(frm.doc,JSON.parse(from.pop()));frm.dirty();render(frm);
    }
    function setConnection(frm,{source,port,target}) {
        const fields={next:'next_step',no_match:'no_match_step',multiple_match:'multiple_match_step',phone_mismatch:'phone_mismatch_step'};
        const step=frm.doc.steps.find(s=>s.step_key===source);
        if(step.step_type==='Menu')frm.doc.choices.find(c=>c.from_step===source&&c.choice_key===port).next_step=target;
        else if(fields[port])step[fields[port]]=target;
    }
    function connect(frm,change){remember(frm);setConnection(frm,change);frm.dirty();render(frm);}
    function editStep(frm, row, initial = {}) {
        const existing = !!row;
        if(!row){let n=(frm.doc.steps||[]).length+1;while(names(frm).includes('step_'+n))n++;row={step_key:names(frm).length?'step_'+n:'main_menu',step_type:initial.step_type||'End',prompt:'Thank you for contacting us.',next_step:initial.connect?.target||''};}
        let bindings={};try{bindings=typeof row.template_bindings==='string'?JSON.parse(row.template_bindings):row.template_bindings||{};}catch{/* Start invalid draft mappings afresh. */}
        let d;
        let templateReady=false,request=0,lookupPhone=row.record_phone_field||'',lookupNoMatch=row.no_match_step||'',lookupMultiple=row.multiple_match_step||'';
        let lookupSelection=row.record_selection||'Exactly one record';
        let lookupFilters=[];try{lookupFilters=typeof row.record_filters==='string'?JSON.parse(row.record_filters):row.record_filters||[];}catch{/* Invalid draft filters can be replaced. */}
        const choose=(label,options,value,changed)=>{const select=node('select');select.className='form-control';select.setAttribute('aria-label',label);for(const [v,t]of options){const o=node('option',t);o.value=v;select.append(o);}select.value=value;select.onchange=()=>changed(select.value);return select;};
        const answerOptions=()=>[['','Choose a value…'],...(frm.doc.steps||[]).filter(s=>s.answer_key).map(s=>['{{answers.'+s.answer_key+'}}','Answer: '+s.answer_key.replaceAll('_',' ')]),['{{contact.phone_number}}','Contact phone number'],['{{contact_name}}','Contact name'],['fixed','Fixed text']];
        function drawLookup(root,info){
            if(info.lookup.reason)root.append(node('p',info.lookup.reason,'text-danger'));
            root.append(node('p','Find one '+info.source_doctype+' record. Template fields come from that record.','text-muted'));
            root.append(node('label','Match the contact phone number in'));
            const phone=choose('Contact phone field',[['','Choose a phone field…'],...info.lookup.phones.map(f=>[f.value,f.label])],lookupPhone,value=>lookupPhone=value);root.append(phone);
            root.append(node('small','Phone numbers must include the country code, stored as digits or +digits. This match always uses the current WhatsApp contact.'));
            const rows=node('div');root.append(node('label','Additional filters'),rows);
            function draw(){rows.replaceChildren();lookupFilters.forEach((filter,i)=>{
                const line=node('div');line.style.cssText='display:flex;flex-wrap:wrap;gap:6px;padding:10px 0;border-bottom:1px solid var(--border-color)';
                const field=choose('Filter '+(i+1)+' field',[['','Choose field…'],...info.lookup.fields.map(f=>[f.value,f.label])],filter.field||'',v=>filter.field=v);
                const op=choose('Filter '+(i+1)+' comparison',['=','!=','>','<','>=','<='].map(v=>[v,v]),filter.operator||'=',v=>filter.operator=v);filter.operator=op.value;
                const value=node('input');value.className='form-control';value.type='text';value.maxLength=1024;value.setAttribute('aria-label','Filter '+(i+1)+' fixed value');
                const previous=filter.value||'',choices=answerOptions();const kind=choose('Filter '+(i+1)+' value from',choices,choices.some(([v])=>v===previous)?previous:previous?'fixed':'',v=>{value.hidden=v!=='fixed';filter.value=v==='fixed'?value.value:v;});value.hidden=kind.value!=='fixed';value.value=kind.value==='fixed'?previous:'';value.oninput=()=>filter.value=value.value;
                for(const input of [field,op,kind,value])input.style.cssText='flex:1 1 130px;min-width:0';
                line.append(field,op,kind,value,btn('Remove filter',()=>{lookupFilters.splice(i,1);draw();}));rows.append(line);
            });}draw();root.append(btn('Add filter',()=>{if(lookupFilters.length<10){lookupFilters.push({field:'',operator:'=',value:''});draw();}}));
            root.append(node('label','Which matching record should be used?'),choose('Choose matching record',[['Exactly one record','Require a single matching record'],['Most recently created','Most recently created']],lookupSelection,value=>lookupSelection=value));
            root.append(node('small','Most recently created uses creation time, not appointment date or the last edit. The contact phone number must still match one registered person.'));
            const destinations=[['','Choose a step…'],...names(frm).map(k=>[k,k.replaceAll('_',' ')])];
            root.append(node('label','If no record matches'),choose('No matching record step',destinations,lookupNoMatch,v=>lookupNoMatch=v),node('label','If more than one record matches'),choose('Multiple matching records step',destinations,lookupMultiple,v=>lookupMultiple=v));
            for(const label of root.querySelectorAll('label'))label.style.cssText='display:block;margin:14px 0 6px';
            root.append(node('p','Use reception handoff for unmatched or ambiguous requests. The selected matching rule applies only to this contact’s records. The flow does not create an appointment.','text-muted'));
        }
        async function loadTemplate(){
            if(!d?.fields_dict?.template_parameters)return;
            const root=d.fields_dict.template_parameters.$wrapper[0], selected=d.get_value('message_template'), turn=++request;
            root.replaceChildren();templateReady=false;if(!selected)return;
            root.append(node('p','Loading template fields…','text-muted'));
            try{
                const info=await api('template_options',{name:selected,account_name:frm.doc.account});if(turn!==request)return;
                root.replaceChildren();root.append(node('p',info.mode+' · '+info.status,'text-muted'));
                const preview=node('pre',info.preview);preview.style.cssText='white-space:pre-wrap;font:inherit;padding:12px;background:var(--control-bg);border-radius:8px';const details=node('details');details.append(node('summary','View template message'),preview);root.append(details);
                if(d.get_value('template_data_source')==='Record lookup'){drawLookup(root,info);templateReady=true;return;}
                const old=bindings;bindings={};
                const answers=(frm.doc.steps||[]).filter(s=>s.answer_key).map(s=>s.answer_key);
                for(const field of info.fields){
                    const group=node('div');group.style.cssText='margin:12px 0;display:grid;gap:6px';
                    const label=node('label',field.label),pick=node('select'),fixed=node('input');pick.className=fixed.className='form-control';fixed.type='text';fixed.maxLength=1024;
                    pick.setAttribute('aria-label','Value for '+field.label);fixed.setAttribute('aria-label','Fixed value for '+field.label);fixed.placeholder='Enter the value to send';
                    for(const [value,text] of [['','Choose a value…'],...([...new Set(answers)].map(k=>['{{answers.'+k+'}}','Answer: '+k.replaceAll('_',' ')])),['{{contact_name}}','Contact’s WhatsApp name'],['{{contact.phone_number}}','Contact phone number'],['fixed','Fixed text']]){const o=node('option',text);o.value=value;pick.append(o);}
                    const previous=old[field.path]||'',tokens=[...pick.options].map(o=>o.value);pick.value=tokens.includes(previous)?previous:previous?'fixed':'';fixed.value=pick.value==='fixed'?previous:'';
                    const changed=()=>{fixed.hidden=pick.value!=='fixed';bindings[field.path]=pick.value==='fixed'?fixed.value:pick.value;};pick.onchange=changed;fixed.oninput=changed;changed();group.append(label,pick,fixed);root.append(group);
                }
                root.append(node('p','Only use a confirmation template after staff confirms the booking. Requested dates are not confirmed appointments.','text-muted'));templateReady=true;
            }catch{if(turn===request){root.replaceChildren(node('p','This template could not be loaded. Check its fields and permissions, then select it again.','text-danger'));}}
        }
        const targets = [...new Set([...names(frm), row.step_key])].join('\n');
        d = new frappe.ui.Dialog({title: existing ? 'Edit step' : 'Add a step', size:'large', fields:[
            {fieldname:'step_key', fieldtype:'Data', label:'Step name', default:row.step_key, reqd:1, read_only:existing, description:'A unique short name, such as main_menu. Use lowercase letters and underscores.'},
            {fieldname:'step_type', fieldtype:'Select', label:'What should happen?', options:'Menu\nQuestion\nMessage\nTemplate\nHandoff\nEnd', default:row.step_type, reqd:1},
            {fieldname:'prompt', fieldtype:'Small Text', label:'Message to send', default:row.prompt, mandatory_depends_on:'eval:doc.step_type!=="Template"', depends_on:'eval:doc.step_type!=="Template"', description:'Use {{answers.name}} to include an answer collected earlier. Maximum 1,024 characters.'},
            {fieldname:'message_template',fieldtype:'Link',options:'WhatsApp Message Template',label:'Message template',default:row.message_template,depends_on:'eval:doc.step_type==="Template"',mandatory_depends_on:'eval:doc.step_type==="Template"',onchange:()=>loadTemplate(),description:'Reuse a saved text template. Meta templates must be approved before publishing the flow.'},
            {fieldname:'template_data_source',fieldtype:'Select',label:'Template data',options:'Flow values\nRecord lookup',default:row.template_data_source||'Flow values',depends_on:'eval:doc.step_type==="Template"',onchange:()=>loadTemplate()},
            {fieldname:'template_parameters',fieldtype:'HTML',depends_on:'eval:doc.step_type==="Template"'},
            {fieldname:'next_step', fieldtype:'Select', label:'Then go to', options:'\n'+targets, default:row.next_step, depends_on:'eval:["Question","Message","Template"].includes(doc.step_type)'},
            {fieldname:'answer_key', fieldtype:'Data', label:'Save answer as', default:row.answer_key, depends_on:'eval:["Question","Menu"].includes(doc.step_type)', description:'For questions, enter a name such as preferred_date. For menus, optionally save the selected option, such as department.'},
            {fieldname:'answer_type', fieldtype:'Select', label:'Answer format', options:'Text\nDate\nPhone', default:row.answer_type || 'Text', depends_on:'eval:doc.step_type==="Question"'},
            {fieldname:'phone_mismatch_step',fieldtype:'Select',label:'If the registered number differs from their WhatsApp number',options:'\n'+targets,default:row.phone_mismatch_step,depends_on:'eval:doc.step_type==="Question" && doc.answer_type==="Phone"',mandatory_depends_on:'eval:doc.step_type==="Question" && doc.answer_type==="Phone"',description:'Send to a help step for a different number. Record lookup only uses the number this person is messaging from.'},
            {fieldname:'options', fieldtype:'Table', label:'Menu choices', depends_on:'eval:doc.step_type==="Menu"', in_place_edit:true, data:copyChoices(frm,row.step_key), fields:[
                {fieldname:'label', fieldtype:'Data', label:'Option text', in_list_view:1, reqd:1, columns:5, length:24},
                {fieldname:'next_step', fieldtype:'Select', label:'Go to step', options:targets, in_list_view:1, reqd:1, columns:5},
                {fieldname:'choice_key', fieldtype:'Data', hidden:1}
            ], description:'Click an option to edit its text or next step. Option text can have up to 24 characters. Up to 3 short choices appear as buttons; larger menus appear as a WhatsApp list.'}
        ], primary_action_label:'Apply step', primary_action:v => {
            if (!/^[a-z][a-z0-9_]{0,39}$/.test(v.step_key)) { frappe.msgprint('Use a step name starting with a lowercase letter, followed by letters, numbers or underscores.'); return; }
            if (!existing && names(frm).includes(v.step_key)) { frappe.msgprint('Choose a unique step name.'); return; }
            const choices = v.step_type === 'Menu' ? (v.options || []) : [];
            if (v.step_type === 'Menu' && (!choices.length || choices.length > 10)) { frappe.msgprint('Add between 1 and 10 menu options.'); return; }
            const labels = new Set(), used = new Set([...copyChoices(frm,v.step_key),...choices].map(c => c.choice_key).filter(Boolean));
            const prepared = [], assigned = new Set();
            for (const c of choices) {
                const label = String(c.label || '').trim();
                if (!label || Array.from(label).length > 24 || labels.has(label.toLowerCase())) { frappe.msgprint('Give every option different text, using 1 to 24 characters.'); return; }
                if (!targets.split('\n').includes(c.next_step)) { frappe.msgprint('Choose an existing destination for every option.'); return; }
                labels.add(label.toLowerCase());
                let key = c.choice_key;
                if (!key || assigned.has(key)) { let n=1; while(used.has('option_'+n))n++; key='option_'+n; used.add(key); }
                assigned.add(key);
                prepared.push({from_step:v.step_key,choice_key:key,label,next_step:c.next_step});
            }
            if(v.step_type==='Template' && (!templateReady || (v.template_data_source!=='Record lookup' && Object.values(bindings).some(value=>!value.trim())))){frappe.msgprint('Choose a template and fill in every template field.');return;}
            if(v.step_type==='Template' && v.template_data_source==='Record lookup' && (!lookupPhone||!lookupNoMatch||!lookupMultiple||lookupFilters.some(f=>!f.field||!f.value))){frappe.msgprint('Choose a contact phone field, fill in every filter and select both fallback steps.');return;}
            remember(frm);
            const target = existing ? row : frm.add_child('steps');
            for (const key of ['step_key','step_type','prompt','next_step','answer_key','answer_type','phone_mismatch_step']) target[key] = v[key] || '';
            target.message_template=v.step_type==='Template'?v.message_template:'';target.template_bindings=v.step_type==='Template'?JSON.stringify(bindings):null;
            target.template_data_source=v.template_data_source||'Flow values';target.record_phone_field=lookupPhone;target.record_filters=JSON.stringify(lookupFilters);target.record_selection=lookupSelection;target.no_match_step=lookupNoMatch;target.multiple_match_step=lookupMultiple;
            if(initial.connect)setConnection(frm,{...initial.connect,target:v.step_key});
            replaceChoices(frm, v.step_key, prepared);
            frm.dirty(); frm.refresh_field('steps'); render(frm); d.hide();
        }}); d.show();if(row.message_template)loadTemplate();
    }
    function removeStep(frm, step) {
        if ((frm.doc.steps || []).some(s=>[s.next_step,s.no_match_step,s.multiple_match_step,s.phone_mismatch_step].includes(step.step_key)) || (frm.doc.choices || []).some(c=>c.from_step!==step.step_key && c.next_step===step.step_key) || frm.doc.start_step===step.step_key) { frappe.msgprint('Change the first step and any connections to this step before removing it.'); return; }
        remember(frm);
        const keep = frm.doc.steps.filter(s=>s.name!==step.name).map(s=>({...s})); frm.clear_table('steps');
        keep.forEach(s=>{const r=frm.add_child('steps'); for(const k of ['step_key','step_type','prompt','next_step','answer_key','answer_type','phone_mismatch_step','message_template','template_bindings','template_data_source','record_phone_field','record_filters','record_selection','no_match_step','multiple_match_step'])r[k]=s[k];});
        replaceChoices(frm,step.step_key,[]);frm.dirty();render(frm);
    }
    function render(frm) {
        const root = frm.fields_dict.builder?.$wrapper[0]; if(!root)return;
        const view=frm.__flow_map?.captureView?.();frm.__flow_map?.dispose();frm.__flow_map=null;root.replaceChildren();
        root.append(node('p','Follow the arrows to see how each choice leads to the next step. Drag cards to arrange the flow, or use a pencil button to edit a step.','text-muted'));
        const tools = node('div'); tools.style.cssText='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px';
        tools.append(btn('Workflow map',()=>{frm.__flow_list=false;render(frm);},!frm.__flow_list),btn('Step list',()=>{frm.__flow_list=true;render(frm);},!!frm.__flow_list));
        if (manager() && frm.__flow_list) tools.append(btn('Add a step',()=>editStep(frm)));
        root.append(tools);
        if(!frm.__flow_list && whatsapp_messaging.FlowMap) {
            frm.__flow_map=new whatsapp_messaging.FlowMap(root,{doc:frm.doc,canEdit:manager(),view,onAdd:(kind,connect)=>editStep(frm,null,{step_type:kind,connect}),onConnect:change=>connect(frm,change),onUndo:()=>travel(frm,true),onRedo:()=>travel(frm,false),canUndo:!!frm.__flow_undo?.length,canRedo:!!frm.__flow_redo?.length,onEdit:step=>editStep(frm,step),onRemove:step=>removeStep(frm,step),
                onLayout:positions=>{remember(frm);frm.doc.layout_json=JSON.stringify({version:1,positions});frm.dirty();},
                onArrange:()=>{if(manager()){remember(frm);frm.doc.layout_json=null;frm.dirty();render(frm);}else{const doc={...frm.doc,layout_json:null};frm.__flow_map?.dispose();frm.__flow_map=new whatsapp_messaging.FlowMap(root,{doc,canEdit:false,onArrange:()=>render(frm)});}}
            });
            return;
        }
        for (const step of frm.doc.steps || []) {
            const card = node('section'); card.style.cssText='padding:16px;border:1px solid var(--border-color);border-radius:12px;margin:12px 0';
            card.append(node('strong',step.step_key + ' · ' + step.step_type + (step.step_key === frm.doc.start_step ? ' · Starts here' : '')));
            const prompt = node('p',step.step_type==='Template'?'Template: '+(step.message_template||'Choose a template'):step.prompt); prompt.style.cssText='white-space:pre-wrap;margin:10px 0'; card.append(prompt);
            for (const c of copyChoices(frm,step.step_key)) card.append(node('p',c.label+' → '+c.next_step,'text-muted'));
            if (step.next_step && ['Message','Template','Question'].includes(step.step_type)) card.append(node('p','Next: '+step.next_step,'text-muted'));
            if (step.answer_key) card.append(node('p','Saves answer as: '+step.answer_key,'text-muted'));
            if (manager()) card.append(btn('Edit step',()=>editStep(frm,step)),btn('Remove step',()=>removeStep(frm,step)));
            root.append(card);
        }
    }
    async function preview(frm) {
        if (frm.is_dirty()) await frm.save();
        const d = new frappe.ui.Dialog({title:'Try this conversation flow',size:'large',fields:[...((frm.doc.steps||[]).some(s=>s.template_data_source==='Record lookup')?[{fieldname:'lookup_result',fieldtype:'Select',label:'Training record lookup result',options:[{label:'One fictional matching record',value:'matched'},{label:'No matching record',value:'no_match'},{label:'Multiple matching records',value:'multiple_match'}],default:'matched',description:'Preview uses fictional values and does not query real records.'}]:[]),{fieldname:'chat',fieldtype:'HTML'}]});
        const root = d.fields_dict.chat.$wrapper[0]; root.append(node('p','Training preview. Messages stay in this window.','text-muted'));
        const history = node('div'); history.style.cssText='max-height:45vh;overflow:auto;padding:4px';root.append(history);
        const answers = node('div'); answers.style.marginTop='12px'; const composer = node('div');composer.style.cssText='display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px';
        const text = node('input');text.className='form-control';text.placeholder='Type your answer or menu';text.setAttribute('aria-label','Preview reply');text.maxLength=4096;
        text.style.cssText='flex:1 1 240px;min-width:0';
        let state=null,busy=false;
        const send = btn('Try reply',()=>turn(text.value),true);
        async function turn(body='',choice=null,label=null) {
            if(busy)return;busy=true;send.disabled=true;
            try {
                const result=await api('preview',{name:frm.doc.name,state:state?JSON.stringify(state):null,text:body,choice,lookup_result:d.get_value('lookup_result')||'matched'});
                history.querySelectorAll('button').forEach(b=>b.disabled=true);
                if(body || label){const p=node('p',body || label);p.style.cssText='text-align:right;padding:10px;background:var(--blue-50);border-radius:8px';history.append(p);}
                state=result.state;text.value='';
                for(const message of result.messages){
                    const bubble=node('div');bubble.style.cssText='padding:12px;background:var(--control-bg);border-radius:10px;margin:10px 0';
                    const p=node('p',message.text);p.style.whiteSpace='pre-wrap';bubble.append(p);
                    const choices=node('div');choices.style.cssText='display:flex;gap:8px;flex-wrap:wrap';
                    for(const c of message.choices)choices.append(btn(c.label,()=>turn('',c.key,c.label)));
                    bubble.append(choices);
                    history.append(bubble);
                }
                answers.replaceChildren(node('strong','Progress: '+state.status));
                for(const [key,value] of Object.entries(state.answers))answers.append(node('p',key.replaceAll('_',' ')+': '+value));
                history.scrollTop=history.scrollHeight;
            } finally {busy=false;send.disabled=!!state && state.status!=='Active';text.disabled=send.disabled;}
        }
        text.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();turn(text.value);}};
        composer.append(text,send,btn('Restart preview',()=>{state=null;history.replaceChildren();turn();}));root.append(composer,answers);d.show();await turn();
    }
    frappe.ui.form.on('WhatsApp Conversation Flow',{
        refresh(frm){
            if(!frm.is_dirty?.()){frm.__flow_undo=[];frm.__flow_redo=[];}
            frm.set_df_property('steps','hidden',1);frm.set_df_property('choices','hidden',1);render(frm);
            if(!frm.is_new())frm.add_custom_button(__('Try flow'),()=>preview(frm));
            if(manager() && !frm.is_new()) {
                frm.add_custom_button(__('Publish and enable'),async()=>{if(frm.is_dirty()){frappe.msgprint('Save your draft before publishing.');return;}await api('publish',{name:frm.doc.name});await frm.reload_doc();});
                if(frm.doc.is_active)frm.add_custom_button(__('Pause automatic replies'),async()=>{await api('pause',{name:frm.doc.name});await frm.reload_doc();});
            }
            if(frm.doc.is_active)frm.dashboard.set_headline_alert('Your published version is running. Save edits as a draft, then Publish and enable to apply them.','blue');
            else frm.dashboard.set_headline_alert('Automatic replies are off for this flow. Try it in preview before publishing.','yellow');
        },
        start_step:render,
        on_hide(frm){if(frm.__flow_map?.expanded)frm.__flow_map.expand(false);}
    });
})();
