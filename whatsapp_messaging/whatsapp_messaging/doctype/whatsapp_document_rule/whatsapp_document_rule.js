frappe.ui.form.on('WhatsApp Document Rule', {
    setup(frm) {
        frm.set_query('source_doctype', () => ({filters:{istable:0,issingle:0,is_virtual:0}}));
        frm.set_query('print_format', () => ({filters:{doc_type:frm.doc.source_doctype,disabled:0}}));
        frm.set_query('approved_template', () => ({filters:{name:['in',(frm.document_options?.templates||[]).map(t=>t.name)]}}));
    },
    async refresh(frm) {
        await refresh_options(frm);
        if (!frm.is_new()) {
            frm.add_custom_button(__('Preview'), () => frappe.prompt({fieldname:'source_name',fieldtype:'Link',options:frm.doc.source_doctype,label:__('Source record'),reqd:1}, async values => {
                if(frm.is_dirty()) return frappe.msgprint(__('Save the rule before previewing.'));
                const {message:r}=await frappe.call({method:'whatsapp_messaging.messaging.document_delivery.preview',args:{rule_name:frm.doc.name,source_name:values.source_name}});
                const fields=[{fieldname:'recipient',fieldtype:'Data',label:__('Recipient'),default:r.recipient,read_only:1},{fieldname:'document',fieldtype:'Data',label:__('Document'),default:r.document,read_only:1},{fieldname:'message',fieldtype:'Small Text',label:__('Message'),default:r.message,read_only:1},{fieldname:'status',fieldtype:'Small Text',label:__('Preview only'),default:(r.trigger_matches?'Trigger matches. ':'Trigger does not match. ')+(r.release_required?'Staff release is required. ':'')+'No message was sent.',read_only:1}];
                new frappe.ui.Dialog({title:__('Document delivery preview'),fields}).show();
            },__('Preview document delivery'),__('Preview')));
            frm.add_custom_button(__('Delivery history'), () => frappe.set_route('List','WhatsApp Document Delivery',{rule:frm.doc.name}));
            if(frm.doc.enabled) frm.add_custom_button(__('Prepare current document'),()=>frappe.prompt({fieldname:'source_name',fieldtype:'Link',options:frm.doc.source_doctype,label:__('Source record'),description:__('Creates a delivery for this version. It sends automatically unless staff release is required.'),reqd:1},async values=>{
                if(frm.is_dirty())return frappe.msgprint(__('Save the rule first.'));
                const {message:r}=await frappe.call({method:'whatsapp_messaging.messaging.document_delivery.prepare_current',args:{rule_name:frm.doc.name,source_name:values.source_name}});
                frappe.set_route('Form','WhatsApp Document Delivery',r.name);
            },__('Prepare current document'),__('Prepare')));
        }
    },
    source_doctype: refresh_options,
    recipient_link_field: refresh_options,
    recipient_mode: refresh_options,
    sender: refresh_options,
    async trigger_field(frm) {
        await frm.set_value({trigger_values:'',trigger_text:'',text_match_operator:'Equals'});
        await refresh_trigger_values(frm);
    },
    event_type: refresh_trigger_values,
    async validate(frm) {
        // Keyboard saves must also commit a value still being typed into the chips input.
        if(['Data','Select','Check'].includes(frm.document_options?.fields.find(f=>f.value===frm.doc.trigger_field)?.type)&&frm.doc.event_type==='Field changes to a value') {
            const picker=frm.trigger_value_picker;
            const pending=picker.get_input_value()?.trim();
            if(pending&&!pending.startsWith('/'))await picker.set_value([...picker.get_value(),pending]);
            picker.$input.val('');
        }
    },
    async approved_template(frm) {
        const t=(frm.document_options?.templates||[]).find(t=>t.name===frm.doc.approved_template);
        if(!t)return;
        if((frm.doc.parameters||[]).length)return;
        for(const [i] of JSON.parse(t.parameters_json||'[]').entries()) frm.add_child('parameters',{position:i+1,value_source:'Record'});
        frm.refresh_field('parameters');
    }
});

async function refresh_options(frm) {
    if(!frm.doc.source_doctype)return;
    const {message:o}=await frappe.call({method:'whatsapp_messaging.messaging.document_delivery.field_options',args:{source_doctype:frm.doc.source_doctype,recipient_link_field:frm.doc.recipient_link_field,sender:frm.doc.sender}});
    frm.document_options=o;
    const values=(fields)=>fields.map(f=>({label:f.label,value:f.value}));
    const choose=(name,fields)=>{const control=frm.fields_dict[name];if(control?.set_data){control.set_data(values(fields));control.refresh();}};
    frm.set_df_property('trigger_field','options',[
        {label:'',value:''},
        ...values(o.fields.filter(f=>['Select','Check','Data','Int','Text','Small Text','Long Text'].includes(f.type)))
    ]);
    choose('recipient_link_field',o.fields.filter(f=>f.type==='Link'));
    choose('file_field',o.fields.filter(f=>f.type==='Attach'));
    choose('phone_field',(frm.doc.recipient_mode==='A linked record'?o.recipient_fields:o.fields).filter(f=>f.type==='Phone'||(f.type==='Data'&&f.options==='Phone')));
    frm.fields_dict.conditions.grid.update_docfield_property('fieldname_value','options',values(o.fields.filter(f=>['Data','Date','Datetime','Time','Currency','Int','Float','Phone','Select','Check'].includes(f.type))));
    await refresh_trigger_values(frm);
}

async function refresh_trigger_values(frm) {
    const field=frm.document_options?.fields.find(f=>f.value===frm.doc.trigger_field);
    const active=frm.doc.event_type==='Field changes to a value';
    const is_text=active&&['Text','Small Text','Long Text'].includes(field?.type);
    const use_picker=active&&['Select','Check','Data'].includes(field?.type);
    frm.toggle_display('text_match_operator',is_text);
    frm.toggle_display('trigger_text',is_text);
    frm.toggle_display('trigger_values',active&&!use_picker&&!is_text);
    frm.toggle_display('trigger_values_picker',use_picker);
    if(!use_picker)return;

    const selected=(frm.doc.trigger_values||'').split('\n').map(v=>v.trim()).filter(Boolean);
    const custom=field.type==='Data';
    const choices=field.type==='Check'
        ? [{value:'1',label:__('Checked')},{value:'0',label:__('Unchecked')}]
        : (field.options||'').split('\n').map(v=>v.trim()).filter(Boolean).map(value=>({value,label:__(value)}));
    // Retain saved values if a source field's options have since changed.
    for(const value of selected) {
        if(!choices.some(o=>o.value===value))choices.push({value,label:value,description:__('Previously selected value')});
    }
    frm.trigger_value_choices=choices.map(o=>({description:'',...o,label:frappe.utils.escape_html(o.label)}));
    if(!frm.trigger_value_picker||frm.trigger_value_picker_kind!==field.type) {
        frm.fields_dict.trigger_values_picker.$wrapper.empty();
        frm.trigger_value_picker_kind=field.type;
        frm.trigger_value_picker=frappe.ui.form.make_control({
            parent:frm.fields_dict.trigger_values_picker.$wrapper,
            df:{
                fieldname:'selected_trigger_values',fieldtype:'MultiSelectPills',
                label:__('Send when value is'),placeholder:__('Type / for options'),
                description:custom
                    ? __('Type / to find existing values, or type a new value and press Enter. Matches are exact and case-sensitive. This changes only the rule.')
                    : __('Type / to select the available options. You can select several; new source options cannot be created here.'),
                get_data:(text)=>trigger_suggestions(frm,text,custom),
                onchange:()=>{
                    if(frm.syncing_trigger_values)return;
                    const picker=frm.trigger_value_picker;
                    const values=[...new Set(picker.get_value().flatMap(v=>v.split('\n')).map(v=>v.trim()).filter(Boolean))];
                    picker.set_formatted_input(values);
                    return frm.set_value('trigger_values',values.join('\n'));
                }
            },render_input:true
        });
        const picker=frm.trigger_value_picker;
        const pill_html=picker.get_pill_html.bind(picker);
        picker.get_pill_html=value=>pill_html(value).replace('<button ',
            '<button aria-label="'+frappe.utils.escape_html(__('Remove {0}',[value]))+'" ');
        // Keep input blur from racing a chip removal; the whole chip is keyboard-removable.
        picker.$input_area.on('mousedown','.tb-selected-value',e=>e.preventDefault());
        picker.$input_area.on('click','.tb-selected-value',e=>{
            if(!$(e.target).closest('.btn-remove').length)$(e.currentTarget).find('.btn-remove').trigger('click');
        });
        const parse=picker.parse.bind(picker);
        picker.parse=value=>typeof value==='string'&&value.startsWith('/')&&!picker._data?.some(o=>o.value===value)
            ? picker.rows : parse(value);
        picker.validate=values=>{
            const clean=[...new Set((values||[]).flatMap(v=>v.split('\n')).map(v=>v.trim()).filter(Boolean))];
            if(!custom&&clean.some(value=>!frm.trigger_value_choices.some(o=>o.value===value))) {
                frappe.throw(__('Select a defined source option from the suggestions.'));
            }
            return clean;
        };
        picker.awesomplete.filter=(item,input)=>{
            const query=(input.startsWith('/')?input.slice(1):input).toLocaleLowerCase();
            const option=picker._data?.find(o=>o.value===item.value);
            return (option?.value||item.value).toLocaleLowerCase().includes(query)
                || $('<span>').html(option?.label||item.label).text().toLocaleLowerCase().includes(query);
        };
    }
    const picker=frm.trigger_value_picker;
    picker.df.read_only=!frappe.model.can_write(frm.doctype)||Boolean(frm.read_only);
    picker.refresh();
    picker.set_data(frm.trigger_value_choices);
    frm.syncing_trigger_values=true;
    try {
        await picker.set_value(selected);
    } finally {
        frm.syncing_trigger_values=false;
    }
}

function trigger_suggestions(frm,text='',custom) {
    const picker=frm.trigger_value_picker;
    const unselected=options=>options.filter(o=>!picker?.get_value().includes(o.value));
    if(!custom)return unselected(frm.trigger_value_choices||[]);
    if(!text.startsWith('/'))return text.trim()?[{value:text.trim(),label:frappe.utils.escape_html(text.trim())}]:[];
    const source_doctype=frm.doc.source_doctype,trigger_field=frm.doc.trigger_field;
    return frappe.call({
        method:'whatsapp_messaging.messaging.document_delivery.trigger_value_options',type:'GET',
        args:{source_doctype,trigger_field,search:text.slice(1)}
    }).then(({message:values})=>{
        if(frm.doc.source_doctype!==source_doctype||frm.doc.trigger_field!==trigger_field||picker.$input.val()!==text)return picker._data||[];
        return unselected(values.map(value=>({value,label:frappe.utils.escape_html(value)})));
    });
}

frappe.ui.form.on('WhatsApp Document Parameter', {
    value_source(frm,cdt,cdn) {
        const row=locals[cdt][cdn],fields=row.value_source==='Recipient'?frm.document_options?.recipient_fields:frm.document_options?.fields;
        frm.fields_dict.parameters.grid.update_docfield_property('fieldname_value','options',(fields||[]).filter(f=>['Data','Date','Datetime','Time','Currency','Int','Float','Phone','Select'].includes(f.type)).map(f=>({label:f.label,value:f.value})));
    }
});
