// Drawflow interaction adapter. The saved graph remains the server-validated flow.
import Drawflow from '../vendor/drawflow/drawflow.js';
import drawflowCss from '../vendor/drawflow/style.js';
const WIDTH=240, BASE=88, PORT=28, PAD=56, GAP_X=140, GAP_Y=36;
const labelFor=key=>String(key||'Unnamed step').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const kinds={Menu:'Menu',Question:'Ask a question',Message:'Send a message',Template:'Send a template',Handoff:'Reception handoff',End:'Finish',Missing:'Missing step'};
const icons={Menu:'list',Question:'circle-question-mark',Message:'message-circle',Template:'layout-template',Handoff:'headset',End:'flag',Missing:'circle-alert'};
const colors={Menu:'var(--blue-500,#3b82f6)',Question:'var(--purple-500,#8b5cf6)',Message:'var(--cyan-500,#06b6d4)',Template:'var(--pink-500,#ec4899)',Handoff:'var(--orange-500,#f97316)',End:'var(--green-500,#22c55e)',Missing:'var(--red-500,#ef4444)'};

export function layoutFlow(doc){
    const byKey=new Map(),warnings=[],edges=[];
    for(const row of doc.steps||[]){
        if(!row.step_key){warnings.push('Give every step a name.');continue;}
        if(byKey.has(row.step_key)){warnings.push('Step names must be unique: '+row.step_key);continue;}
        const ports=row.step_type==='Menu'?(doc.choices||[]).filter(c=>c.from_step===row.step_key).map(c=>({key:c.choice_key,label:c.label||'Untitled option',target:c.next_step})):
            ['Question','Message','Template'].includes(row.step_type)?[{key:'next',label:row.step_type==='Question'?(row.answer_type==='Phone'?'Number matches':'After answer'):'Continue',target:row.next_step}]:[];
        if(row.step_type==='Question'&&row.answer_type==='Phone')ports.push({key:'phone_mismatch',label:'Different registered number',target:row.phone_mismatch_step});
        if(row.step_type==='Template'&&row.template_data_source==='Record lookup')ports.push({key:'no_match',label:'No record found',target:row.no_match_step},{key:'multiple_match',label:'Multiple records',target:row.multiple_match_step});
        byKey.set(row.step_key,{key:row.step_key,title:labelFor(row.step_key),kind:row.step_type,row,ports,width:WIDTH,height:ports.length?BASE+ports.length*PORT+8:BASE+10});
    }
    for(const n of [...byKey.values()]){
        if(n.kind==='Menu'&&!n.ports.length)warnings.push('Add menu choices to '+n.title+'.');
        for(const port of n.ports){
            if(!port.target){warnings.push('Connect '+n.title+' → '+port.label+'.');continue;}
            if(!byKey.has(port.target)){byKey.set(port.target,{key:port.target,title:labelFor(port.target),kind:'Missing',row:null,ports:[],width:WIDTH,height:BASE+10});warnings.push('The destination '+port.target+' does not exist yet.');}
            edges.push({source:n.key,target:port.target,port:port.key,label:port.label,labels:[port.label]});
        }
    }
    const start=byKey.get(doc.start_step)?.row?doc.start_step:null;
    if(byKey.size&&!start)warnings.push('Choose an existing step as the first step.');
    const order=[],levels=[];
    function visit(key,connected){
        if(byKey.get(key).depth!==undefined)return;
        byKey.get(key).depth=0;const queue=[key];
        for(let i=0;i<queue.length;i++){
            const n=byKey.get(queue[i]);n.connected=connected;n.isStart=n.key===start;order.push(n);(levels[n.depth]||=[]).push(n);
            for(const e of edges.filter(e=>e.source===n.key)){const target=byKey.get(e.target);if(target.depth===undefined){target.depth=n.depth+1;queue.push(target.key);}}
        }
    }
    if(start)visit(start,true);for(const n of byKey.values())if(n.depth===undefined)visit(n.key,false);
    for(let depth=0;depth<levels.length;depth++){
        const desired=n=>{const parents=edges.filter(e=>e.target===n.key&&byKey.get(e.source).depth<depth).map(e=>byKey.get(e.source).y);return parents.length?parents.reduce((a,b)=>a+b,0)/parents.length:PAD;};
        const level=levels[depth];if(depth)level.sort((a,b)=>desired(a)-desired(b));let cursor=PAD;
        for(const n of level){n.x=PAD+depth*(WIDTH+GAP_X);n.y=Math.max(cursor,desired(n));cursor=n.y+n.height+GAP_Y;}
    }
    let positions={};try{const layout=typeof doc.layout_json==='string'?JSON.parse(doc.layout_json):doc.layout_json;positions=layout?.version===1?layout.positions||{}:{};}catch{warnings.push('Use Auto arrange to reset unreadable card positions.');}
    for(const n of order){const p=positions[n.key];if(p&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=0&&p.y>=0&&p.x<=100000&&p.y<=100000){n.x=p.x;n.y=p.y;}}
    for(const e of edges)e.returning=byKey.get(e.target).depth<=byKey.get(e.source).depth;
    return {nodes:order,edges,start,warnings:[...new Set(warnings)],width:Math.max(WIDTH+PAD*2,...order.map(n=>n.x+n.width+PAD)),height:Math.max(BASE+PAD*2,...order.map(n=>n.y+n.height+PAD))};
}

const css=`
.wf-map{min-width:0;color:var(--text-color);border:1px solid var(--border-color);border-radius:14px;background:var(--card-bg);overflow:hidden;position:relative}
.wf-map-header{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border-color);flex-wrap:wrap;background:var(--card-bg)}
.wf-map-heading{font-size:15px;font-weight:600}.wf-map-subtitle{font-size:12px;color:var(--text-muted);margin-top:3px}
.wf-map-tools{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.wf-map-tools button{white-space:nowrap}.wf-map-tools .wf-square{width:32px;height:32px;padding:0;display:inline-flex;align-items:center;justify-content:center}.wf-map-zoom{font-size:12px;min-width:42px;text-align:center;font-variant-numeric:tabular-nums}
.wf-map-viewport{height:580px;max-height:75vh;overflow:auto;position:relative;overscroll-behavior:contain;touch-action:pan-x pan-y;background-color:var(--subtle-fg);background-image:radial-gradient(var(--border-color) 1px,transparent 1px);background-size:20px 20px;cursor:grab}.wf-map-viewport.is-panning{cursor:grabbing;user-select:none}.wf-map-stage{position:relative}.wf-map-board{position:absolute;transform-origin:0 0}
.wf-map-svg{position:absolute;inset:0;overflow:visible;pointer-events:none}.wf-map-edge{fill:none;stroke:var(--gray-400,#9ca3af);stroke-width:1.8}.wf-map-edge.is-return{stroke-dasharray:5 5;stroke:var(--purple-400,#a78bfa);opacity:.6}.wf-map-edge.is-highlighted,.wf-map-ghost{stroke:var(--green-600,#168454);stroke-width:2.8;opacity:1}.wf-map-svg.has-selection .wf-map-edge:not(.is-highlighted){opacity:.18}.wf-map-ghost{fill:none;stroke-dasharray:5 4}
.wf-map-node{position:absolute;width:240px;border:1px solid var(--border-color);border-top:3px solid var(--wf-color);border-radius:12px;background:var(--card-bg);box-shadow:0 2px 6px #0000000a;box-sizing:border-box;cursor:default}.wf-map-node.is-selected{outline:2px solid var(--green-500,#22c55e);outline-offset:3px}.wf-map-node.is-unconnected{border-style:dashed}.wf-map-node.is-dragging{z-index:3;box-shadow:0 8px 24px #0002}
.wf-map-node-main{display:block;border:0;padding:10px 14px;width:100%;height:85px;text-align:left;background:transparent;color:inherit;border-radius:10px;cursor:grab;touch-action:none}.wf-map-node-main:focus-visible,.wf-map-port-row:focus-visible,.wf-map-input:focus-visible{outline:2px solid var(--primary);outline-offset:3px}.wf-map-node-type{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--text-muted);margin-bottom:5px;padding-right:24px}.wf-map-node-type .icon{color:var(--wf-color)}.wf-map-node-title{display:block;font-size:14px;line-height:20px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:16px}.wf-map-node-preview{display:block;font-size:11px;line-height:18px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}.wf-map-start{font-size:9px;color:var(--green-700,#146b46);background:var(--green-50,#f0fdf4);border-radius:4px;padding:1px 4px;margin-left:auto}
.wf-map-edit{position:absolute;right:7px;top:8px;width:26px;height:26px;border:0;background:transparent;color:var(--text-muted);border-radius:5px;display:flex;align-items:center;justify-content:center}.wf-map-edit:hover{background:var(--control-bg)}
.wf-map-input{position:absolute;left:-6px;top:32px;width:12px;height:12px;padding:0;border-radius:50%;border:2px solid var(--wf-color);background:var(--card-bg);z-index:1}.wf-map-port-row{position:relative;display:flex;align-items:center;justify-content:space-between;width:100%;height:28px;border:0;border-top:1px solid var(--border-color);background:transparent;color:var(--text-muted);padding:0 14px;font-size:11px;text-align:left;touch-action:none}.wf-map-port-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wf-map-port-row::after{content:'';position:absolute;right:-6px;top:8px;width:12px;height:12px;border-radius:50%;border:2px solid var(--wf-color);background:var(--card-bg)}.wf-map-port-row:hover{background:var(--control-bg);color:var(--text-color)}.wf-map-port-row:disabled{opacity:1;cursor:default}.wf-map-node.is-drop-target{outline:3px solid var(--green-500,#22c55e);outline-offset:4px}
.wf-map-footer{padding:10px 16px;display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--text-muted);border-top:1px solid var(--border-color)}.wf-map-legend{display:inline-flex;align-items:center;gap:5px}.wf-map-dot{width:7px;height:7px;border-radius:50%;background:var(--wf-color)}
.wf-map-panel{position:absolute;right:14px;width:310px;max-width:calc(100% - 28px);max-height:calc(100% - 145px);overflow:auto;z-index:4;border:1px solid var(--border-color);border-radius:12px;padding:16px;background:var(--card-bg);box-shadow:0 8px 30px #0002;cursor:default}.wf-map-panel[hidden]{display:none}.wf-map-panel h4{font-size:15px;margin:0 28px 10px 0}.wf-map-panel p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.6}.wf-map-panel label{font-size:12px;display:block;margin:12px 0 6px}.wf-map-panel .wf-close{position:absolute;right:10px;top:10px}.wf-map-panel .wf-map-relation{display:block;white-space:normal;text-align:left;max-width:100%;margin:6px 0}.wf-map-panel small{display:block;color:var(--text-muted);margin:10px 0}.wf-map-picker-types{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.wf-map-picker-types button{display:flex;align-items:center;gap:8px;white-space:normal;text-align:left;min-height:48px;padding:8px}.wf-map-picker-types .icon{flex-shrink:0}
.wf-map-warning{padding:10px 14px;background:var(--yellow-50,#fffbeb);font-size:12px;border-bottom:1px solid var(--border-color)}.wf-map.is-expanded{position:fixed;inset:12px;z-index:1035;display:flex;flex-direction:column;box-shadow:0 12px 60px #0003}.wf-map.is-expanded .wf-map-viewport{height:auto;max-height:none;flex:1;min-height:0}
@media(max-width:600px){.wf-map-header{padding:12px}.wf-map-viewport{height:500px}.wf-map.is-expanded{inset:4px}}
`;
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const drawflowOverrides=`
.wf-map-viewport.parent-drawflow{display:block;overflow:hidden;touch-action:none}
.wf-map .drawflow{transform-origin:0 0}.wf-map .drawflow-node.wf-map-node{display:block;width:240px;padding:0;min-height:0;border:1px solid var(--border-color);border-top:3px solid var(--wf-color);border-radius:12px;background:var(--card-bg);color:var(--text-color);z-index:2}
.wf-map .drawflow-node.selected{background:var(--card-bg)}.wf-map .drawflow-node.is-selected{z-index:3}.wf-map .drawflow-node .inputs,.wf-map .drawflow-node .outputs{position:absolute;inset:0;width:auto;pointer-events:none}
.wf-map .drawflow-node .input,.wf-map .drawflow-node .output{position:absolute;margin:0;width:12px;height:12px;border:2px solid var(--wf-color);background:var(--card-bg);pointer-events:auto;z-index:3}
.wf-map .drawflow-node .input{left:-7px}.wf-map .drawflow-node .output{right:-7px}.wf-map .drawflow-node .output:hover,.wf-map .drawflow-node .output:focus-visible{background:var(--wf-color);outline:2px solid var(--primary);outline-offset:3px}
.wf-map .wf-map-port-row:after{display:none}.wf-map .drawflow .connection .main-path{stroke:var(--gray-400,#9ca3af);stroke-width:2}.wf-map .drawflow .connection .main-path:hover,.wf-map .drawflow .connection .main-path.selected{stroke:var(--green-600,#168454);stroke-width:3}
.wf-map .drawflow-delete{display:none}.wf-map .drawflow-node .drawflow_content_node{pointer-events:auto}.wf-map .wf-map-node-preview{user-select:none}
`;
export class FlowMap {
    constructor(root, options) {
        this.options=options;this.graph=layoutFlow(options.doc);this.byKey=new Map(this.graph.nodes.map(n=>[n.key,n]));this.elements=new Map();this.ids=new Map();this.keys=new Map();
        if(!document.getElementById('wf-map-style')){const style=el('style',drawflowCss+'\n'+css+'\n'+drawflowOverrides);style.id='wf-map-style';document.head.append(style);}
        this.root=el('div',undefined,'wf-map');root.append(this.root);
        this.header=el('div',undefined,'wf-map-header');const heading=el('div');heading.append(el('div','Workflow editor','wf-map-heading'),el('div',this.graph.nodes.length+' steps · '+this.graph.edges.length+' connections','wf-map-subtitle'));
        const tools=el('div',undefined,'wf-map-tools');
        if(options.canEdit){tools.append(this.button('Add a step',()=>this.picker()));this.undo=this.iconButton('Undo','undo-2',()=>options.onUndo());this.redo=this.iconButton('Redo','redo-2',()=>options.onRedo());this.undo.disabled=!options.canUndo;this.redo.disabled=!options.canRedo;tools.append(this.undo,this.redo);}
        tools.append(this.button('Auto arrange',()=>options.onArrange()));this.zoomLabel=el('span','','wf-map-zoom');this.expandButton=this.button('Expand map',()=>this.expand());
        tools.append(this.iconButton('Zoom out','minus',()=>this.zoom(this.editor.zoom-.15)),this.zoomLabel,this.iconButton('Zoom in','plus',()=>this.zoom(this.editor.zoom+.15)),this.button('Fit map',()=>this.fit()),this.button('100%',()=>this.zoom(1)),this.expandButton);
        this.header.append(heading,tools);this.root.append(this.header);
        if(this.graph.warnings.length)this.root.append(el('div',this.graph.warnings.join(' '),'wf-map-warning'));
        this.viewport=el('div',undefined,'wf-map-viewport');this.viewport.setAttribute('role','region');this.viewport.setAttribute('aria-label','Workflow canvas');this.root.append(this.viewport);
        this.inspector=el('aside',undefined,'wf-map-panel');this.inspector.hidden=true;this.inspector.setAttribute('aria-label','Step settings');this.root.append(this.inspector);
        // Drawflow owns interaction; only canonical step keys/ports and positions are persisted.
        this.editor=new Drawflow(this.viewport);this.editor.editor_mode=options.canEdit?'edit':'view';this.editor.force_first_input=true;this.editor.draggable_inputs=false;this.editor.zoom_min=.05;this.editor.zoom_max=1.75;this.editor.zoom_value=.15;
        this.viewport.addEventListener('contextmenu',e=>{e.preventDefault();e.stopImmediatePropagation();},{capture:true});
        this.viewport.addEventListener('keydown',e=>{
            if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;
            if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();e.stopImmediatePropagation();if(options.canEdit&&this.selected)this.options.onRemove(this.byKey.get(this.selected).row);}
        },{capture:true});
        this.editor.start();this.draw();this.bind();
        const footer=el('div',undefined,'wf-map-footer');footer.append(el('span',options.canEdit?'Drag dots to connect · Click a branch to choose a step · Save keeps your draft':'Select a card to read its message'));
        for(const[kind,label]of Object.entries(kinds).filter(([k])=>k!=='Missing')){const item=el('span',undefined,'wf-map-legend'),dot=el('span',undefined,'wf-map-dot');dot.style.setProperty('--wf-color',colors[kind]);item.append(dot,el('span',label));footer.append(item);}this.root.append(footer);
        this.root.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&options.canEdit){e.preventDefault();e.shiftKey?options.onRedo():options.onUndo();}if(e.key==='Escape'){if(!this.inspector.hidden)this.closeDetails();else if(this.expanded)this.expand(false);e.stopPropagation();}});
        this.observer=new ResizeObserver(()=>this.refreshConnections());this.observer.observe(this.viewport);
        if(options.view?.expanded)this.expand(true);
        requestAnimationFrame(()=>{if(!this.root.isConnected)return;const view=options.view;this.editor.zoom=view?.scale||.9;this.editor.zoom_last_value=this.editor.zoom;this.editor.canvas_x=view?.x??30-(this.byKey.get(this.graph.start)?.x||0)*this.editor.zoom;this.editor.canvas_y=view?.y??30-(this.byKey.get(this.graph.start)?.y||0)*this.editor.zoom;this.transform();this.refreshConnections();});
    }
    button(label,action){const b=el('button',label,'btn btn-default btn-sm');b.type='button';b.onclick=action;return b;}
    iconButton(label,icon,action){const b=this.button('',action);b.classList.add('wf-square');b.title=label;b.setAttribute('aria-label',label);b.innerHTML=frappe.utils.icon(icon,'sm');b.querySelector('svg')?.setAttribute('aria-hidden','true');return b;}
    draw(){
        for(const n of this.graph.nodes){
            const content=el('div');
            const main=this.button('',()=>{if(!this.justDragged)this.select(n.key);});main.className='wf-map-node-main';main.setAttribute('aria-label',n.title+' · '+(kinds[n.kind]||n.kind)+(n.isStart?' · Start':''));main.setAttribute('aria-pressed','false');
            const type=el('span',undefined,'wf-map-node-type'),icon=el('span');icon.innerHTML=frappe.utils.icon(icons[n.kind]||'message-circle','sm');icon.setAttribute('aria-hidden','true');type.append(icon,el('span',kinds[n.kind]||n.kind));if(n.isStart)type.append(el('span','START','wf-map-start'));if(!n.connected)type.append(el('span','Not connected'));
            main.append(type,el('span',n.title,'wf-map-node-title'),el('span',n.kind==='Template'?(n.row?.message_template||'Choose a template'):n.row?.prompt||'Choose an existing step.','wf-map-node-preview'));content.append(main);
            if(this.options.canEdit&&n.row){const edit=this.iconButton('Edit '+n.title,'pencil',()=>this.options.onEdit(n.row));edit.className='wf-map-edit';this.stopDrag(edit);content.append(edit);}
            for(const port of n.ports){const row=this.button(port.label,()=>this.picker({source:n.key,port:port.key,target:port.target}));row.className='wf-map-port-row';row.setAttribute('aria-label','Connect '+n.title+': '+port.label);row.disabled=!this.options.canEdit;this.stopDrag(row);content.append(row);}
            const id=this.editor.addNode(n.key,1,n.ports.length,n.x,n.y,'wf-map-node'+(!n.connected?' is-unconnected':''),{},content.outerHTML);
            this.ids.set(n.key,id);this.keys.set(String(id),n.key);
            const card=this.viewport.querySelector('#node-'+id);card.dataset.step=n.key;card.dataset.kind=n.kind;card.style.setProperty('--wf-color',colors[n.kind]||colors.Missing);card.style.height=n.height+'px';
            // addNode creates the DOM from HTML; attach handlers to those actual elements.
            const actualMain=card.querySelector('.wf-map-node-main');actualMain.onclick=()=>{if(!this.justDragged)this.select(n.key);};
            const edit=card.querySelector('.wf-map-edit');if(edit){edit.onclick=()=>this.options.onEdit(n.row);this.stopDrag(edit);}
            card.querySelectorAll('.wf-map-port-row').forEach((row,i)=>{row.onclick=()=>this.picker({source:n.key,port:n.ports[i].key,target:n.ports[i].target});this.stopDrag(row);});
            const input=card.querySelector('.input');input.setAttribute('aria-label','Input to '+n.title);input.style.top='32px';
            card.querySelectorAll('.output').forEach((port,i)=>{port.style.top=(BASE+i*PORT+PORT/2-6)+'px';port.setAttribute('aria-label','Connect '+n.title+': '+n.ports[i].label);port.tabIndex=this.options.canEdit?0:-1;port.setAttribute('role','button');port.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();this.picker({source:n.key,port:n.ports[i].key,target:n.ports[i].target});}};});
            this.elements.set(n.key,{card,main:actualMain});
        }
        for(const edge of this.graph.edges){const source=this.byKey.get(edge.source),port=source.ports.findIndex(p=>p.key===edge.port);this.editor.addConnection(this.ids.get(edge.source),this.ids.get(edge.target),'output_'+(port+1),'input_1');}
        this.refreshConnections();
    }
    stopDrag(element){for(const event of ['mousedown','touchstart'])element.addEventListener(event,e=>e.stopPropagation());}
    connection(change){const source=this.keys.get(String(change.output_id)),n=this.byKey.get(source),port=n?.ports[Number(change.output_class.split('_')[1])-1];return port?{source,port:port.key,target:port.target}:null;}
    bind(){
        this.editor.on('nodeMoved',id=>{const n=this.byKey.get(this.keys.get(String(id))),data=this.editor.getNodeFromId(id);if(!n?.row)return;n.x=Math.max(0,Math.min(100000,Math.round(data.pos_x/10)*10));n.y=Math.max(0,Math.min(100000,Math.round(data.pos_y/10)*10));const card=this.elements.get(n.key).card;card.style.left=n.x+'px';card.style.top=n.y+'px';Object.assign(this.editor.drawflow.drawflow.Home.data[id],{pos_x:n.x,pos_y:n.y});this.refreshConnections();this.justDragged=true;setTimeout(()=>this.justDragged=false,60);this.options.onLayout(Object.fromEntries(this.graph.nodes.filter(n=>n.row).map(n=>[n.key,{x:n.x,y:n.y}])));this.undo.disabled=false;this.redo.disabled=true;});
        this.editor.on('connectionCreated',change=>{const connection=this.connection(change),target=this.keys.get(String(change.input_id));this.connecting=null;if(connection&&this.byKey.get(target)?.row&&connection.target!==target)queueMicrotask(()=>this.options.onConnect({...connection,target}));});
        this.editor.on('connectionRemoved',change=>{const connection=this.connection(change);if(connection)queueMicrotask(()=>this.options.onConnect({...connection,target:''}));});
        this.editor.on('connectionStart',change=>{this.connecting=this.connection(change);});
        this.editor.on('connectionCancel',()=>{const connection=this.connecting;this.connecting=null;if(connection)queueMicrotask(()=>{if(this.root.isConnected)this.picker(connection);});});
        this.editor.on('zoom',value=>{this.zoomLabel.textContent=Math.round(value*100)+'%';});
        this.editor.on('nodeSelected',id=>{const key=this.keys.get(String(id));if(key)this.selected=key;});
    }
    refreshConnections(){if(!this.editor?.precanvas||!this.viewport.clientWidth)return;this.graph.width=Math.max(WIDTH+PAD*2,...this.graph.nodes.map(n=>n.x+n.width+PAD));this.graph.height=Math.max(BASE+PAD*2,...this.graph.nodes.map(n=>n.y+n.height+PAD));for(const id of this.ids.values())this.editor.updateConnectionNodes('node-'+id);}
    panel(title){this.inspector.replaceChildren();this.inspector.hidden=false;this.inspector.style.top=(this.header.offsetHeight+14)+'px';this.inspector.style.maxHeight='calc(100% - '+(this.header.offsetHeight+75)+'px)';const close=this.iconButton('Close step settings','x',()=>this.closeDetails());close.classList.add('wf-close');this.inspector.append(close,el('h4',title));return close;}
    picker(connection){
        if(!this.options.canEdit)return;const close=this.panel(connection?'Connect this branch':'Add a step');
        if(connection){const source=this.byKey.get(connection.source),port=source.ports.find(p=>p.key===connection.port);this.inspector.append(el('p',source.title+' → '+port.label));const label=el('label','Connect to an existing step'),select=el('select');select.className='form-control';select.setAttribute('aria-label','Destination step');for(const n of this.graph.nodes.filter(n=>n.row)){const o=el('option',n.title);o.value=n.key;select.append(o);}select.value=connection.target||'';this.inspector.append(label,select,this.button('Connect step',()=>{if(select.value)this.options.onConnect({...connection,target:select.value});}));}
        this.inspector.append(el('small',connection?'Or add a new connected step':'Choose what this step should do'));const types=el('div',undefined,'wf-map-picker-types');for(const[kind,label]of Object.entries(kinds).filter(([k])=>k!=='Missing')){const b=this.button('',()=>{this.inspector.hidden=true;this.options.onAdd(kind,connection);});const icon=el('span');icon.innerHTML=frappe.utils.icon(icons[kind],'sm');icon.setAttribute('aria-hidden','true');b.append(icon,el('span',label));b.setAttribute('aria-label','Add '+label.toLowerCase());types.append(b);}this.inspector.append(types);close.focus({preventScroll:true});
    }
    select(key){
        const n=this.byKey.get(key);if(!n)return;this.selected=key;for(const[id,{card,main}]of this.elements){card.classList.toggle('is-selected',id===key);main.setAttribute('aria-pressed',String(id===key));}
        this.panel(n.title);this.inspector.append(el('small',(kinds[n.kind]||n.kind)+' · '+n.key),el('p',n.kind==='Template'?'Template: '+(n.row?.message_template||'Choose a template'):n.row?.prompt||'Edit the previous step and choose an existing destination.'));if(n.row?.answer_key)this.inspector.append(el('small','Saves answer as: '+n.row.answer_key));
        if(n.ports.length){this.inspector.append(el('strong','Next steps'));for(const port of n.ports){const b=this.button(port.label+' → '+labelFor(port.target),()=>this.focusNode(port.target));b.classList.add('wf-map-relation');this.inspector.append(b);if(this.options.canEdit)this.inspector.append(this.button('Change '+port.label,()=>this.picker({source:key,port:port.key,target:port.target})));}}
        else this.inspector.append(el('small',n.kind==='Handoff'?'Automatic replies stop here. Reception takes over.':n.kind==='End'?'This finishes the conversation flow.':'Add a next step to continue.'));
        if(this.options.canEdit&&n.row){const tools=el('div',undefined,'wf-map-tools');tools.append(this.button('Edit step',()=>this.options.onEdit(n.row)),this.button('Remove step',()=>this.options.onRemove(n.row)));this.inspector.append(tools);}
    }
    closeDetails(){this.inspector.hidden=true;for(const {card,main}of this.elements.values()){card.classList.remove('is-selected');main.setAttribute('aria-pressed','false');}if(this.selected)this.elements.get(this.selected)?.main.focus({preventScroll:true});this.selected=null;}
    transform(){this.editor.precanvas.style.transform=`translate(${this.editor.canvas_x}px, ${this.editor.canvas_y}px) scale(${this.editor.zoom})`;this.zoomLabel.textContent=Math.round(this.editor.zoom*100)+'%';}
    zoom(value){const old=this.editor.zoom,x=this.viewport.clientWidth/2,y=this.viewport.clientHeight/2;this.editor.zoom=Math.max(.05,Math.min(1.75,value));const ratio=this.editor.zoom/old;this.editor.canvas_x=x-(x-this.editor.canvas_x)*ratio;this.editor.canvas_y=y-(y-this.editor.canvas_y)*ratio;this.editor.zoom_last_value=this.editor.zoom;this.transform();}
    fit(){this.closeDetails();const minX=Math.min(0,...this.graph.nodes.map(n=>n.x)),minY=Math.min(0,...this.graph.nodes.map(n=>n.y));this.editor.zoom=Math.max(.05,Math.min(1,(this.viewport.clientWidth-40)/(this.graph.width-minX),(this.viewport.clientHeight-40)/(this.graph.height-minY)));this.editor.zoom_last_value=this.editor.zoom;this.editor.canvas_x=20-minX*this.editor.zoom;this.editor.canvas_y=20-minY*this.editor.zoom;this.transform();}
    focusNode(key){const n=this.byKey.get(key);if(!n)return;this.editor.zoom=Math.max(.9,this.editor.zoom);this.editor.zoom_last_value=this.editor.zoom;this.editor.canvas_x=this.viewport.clientWidth/2-(n.x+WIDTH/2)*this.editor.zoom;this.editor.canvas_y=this.viewport.clientHeight/2-(n.y+n.height/2)*this.editor.zoom;this.transform();this.select(key);this.elements.get(key).main.focus({preventScroll:true});}
    expand(value=!this.expanded){this.expanded=value;this.root.classList.toggle('is-expanded',value);this.expandButton.textContent=value?'Close expanded map':'Expand map';this.expandButton.setAttribute('aria-expanded',String(value));if(value){this.placeholder=document.createComment('workflow map');this.root.before(this.placeholder);document.body.append(this.root);this.savedOverflow=document.body.style.overflow;document.body.style.overflow='hidden';}else{this.placeholder?.replaceWith(this.root);this.placeholder=null;document.body.style.overflow=this.savedOverflow||'';this.expandButton.focus();}requestAnimationFrame(()=>this.refreshConnections());}
    captureView(){return {scale:this.editor.zoom,x:this.editor.canvas_x,y:this.editor.canvas_y,expanded:!!this.expanded};}
    dispose(){this.observer?.disconnect();if(this.expanded)document.body.style.overflow=this.savedOverflow||'';this.placeholder?.remove();this.root.remove();}
}
if(typeof frappe!=='undefined'){frappe.provide('whatsapp_messaging');whatsapp_messaging.FlowMap=FlowMap;}
