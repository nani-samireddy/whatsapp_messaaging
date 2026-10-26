import {test} from 'node:test';
import assert from 'node:assert/strict';
import {layoutFlow} from '../whatsapp_messaging/public/js/flow_map.js';
const step=(step_key,step_type='Menu',next_step='')=>({step_key,step_type,next_step,prompt:'Fictional text'});
let choiceId=0;
const choice=(from_step,next_step,label='Choose')=>({from_step,next_step,label,choice_key:'port_'+(++choiceId)});

test('a branching flow has connected nodes and never duplicates a shared destination',()=>{
    const doc={start_step:'main',steps:[step('main'),step('a'),step('b'),step('shared','End')],choices:[choice('main','a','A'),choice('main','b','B'),choice('a','shared'),choice('b','shared')]};
    const before=JSON.stringify(doc),graph=layoutFlow(doc);
    assert.equal(graph.nodes.length,4);assert.equal(graph.edges.length,4);assert.equal(graph.nodes.filter(n=>n.key==='shared').length,1);
    assert.ok(graph.nodes.every(n=>n.connected));assert.equal(JSON.stringify(doc),before);
    for(const n of graph.nodes)assert.ok(n.x>=0&&n.y>=0&&n.x+n.width<=graph.width&&n.y+n.height<=graph.height);
});

test('menu loops and self links terminate and are represented as return edges',()=>{
    const graph=layoutFlow({start_step:'main',steps:[step('main'),step('info'),step('hours','Message','info')],choices:[choice('main','info'),choice('info','hours'),choice('info','main'),choice('main','main')]});
    assert.equal(graph.nodes.length,3);assert.equal(graph.edges.filter(e=>e.returning).length,3);
});

test('choices sharing a destination retain independent editable output ports',()=>{
    const g=layoutFlow({start_step:'department',steps:[step('department'),step('name','Question','end'),step('end','End')],choices:[choice('department','name','General'),choice('department','name','Ortho'),choice('department','name','Paediatrics')]});
    const edges=g.edges.filter(e=>e.source==='department');assert.equal(edges.length,3);assert.equal(new Set(edges.map(e=>e.port)).size,3);assert.equal(g.nodes.filter(n=>n.key==='name').length,1);assert.equal(g.nodes.find(n=>n.key==='name').depth,1);
});

test('disconnected draft steps and missing destinations stay visible for repair',()=>{
    const g=layoutFlow({start_step:'main',steps:[step('main'),step('unlinked','End')],choices:[choice('main','not_created')]});
    assert.ok(g.nodes.find(n=>n.key==='not_created').kind==='Missing');assert.equal(g.nodes.find(n=>n.key==='unlinked').connected,false);assert.ok(g.warnings.some(w=>w.includes('does not exist')));
});

test('empty, incomplete and duplicate drafts do not crash the map',()=>{
    assert.equal(layoutFlow({}).nodes.length,0);
    const g=layoutFlow({start_step:'missing',steps:[step('q','Question'),step('q','End'),step('')],choices:[]});
    assert.equal(g.nodes.length,1);assert.ok(g.warnings.length>=3);assert.equal(g.start,null);
});

test('nodes never overlap across a dense, merging graph with return links',()=>{
    const steps=[step('root')],choices=[];
    for(let i=0;i<10;i++){steps.push(step('branch_'+i));choices.push(choice('root','branch_'+i,'Branch '+i));for(let j=0;j<3;j++){const key='leaf_'+i+'_'+j;steps.push(step(key,'Message','root'));choices.push(choice('branch_'+i,key,'Choice '+j));}}
    const g=layoutFlow({start_step:'root',steps,choices});
    assert.equal(g.nodes.length,41);
    for(let i=0;i<g.nodes.length;i++)for(let j=i+1;j<g.nodes.length;j++){
        const a=g.nodes[i],b=g.nodes[j];assert.ok(a.x+a.width<=b.x||b.x+b.width<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y,`Overlapping ${a.key} and ${b.key}`);
    }
});


test('saved positions survive reload without changing step content',()=>{
    const doc={start_step:'main',steps:[step('main'),step('end','End')],choices:[choice('main','end')],layout_json:JSON.stringify({version:1,positions:{main:{x:800,y:400},end:{x:40,y:20},removed:{x:100,y:100}}})};
    const before=JSON.stringify(doc),g=layoutFlow(doc);
    assert.equal(g.nodes.find(n=>n.key==='main').x,800);assert.equal(g.nodes.find(n=>n.key==='end').y,20);assert.equal(g.nodes.length,2);assert.equal(JSON.stringify(doc),before);
    for(const n of g.nodes)assert.ok(n.x+n.width<=g.width&&n.y+n.height<=g.height);
});

test('invalid saved positions cannot create an unbounded canvas',()=>{
    const doc={start_step:'end',steps:[step('end','End')],layout_json:{version:1,positions:{end:{x:Infinity,y:-5}}}};
    const g=layoutFlow(doc);assert.ok(Number.isFinite(g.width));assert.ok(g.nodes[0].y>=0);
    assert.ok(layoutFlow({...doc,layout_json:'broken'}).warnings.some(w=>w.includes('unreadable')));
});

test('a phone question exposes matching and verification paths',()=>{
    const graph=layoutFlow({start_step:'phone',steps:[{...step('phone','Question','done'),answer_type:'Phone',phone_mismatch_step:'verify'},step('done','End'),step('verify','Handoff')],choices:[]});
    assert.deepEqual(graph.nodes.find(n=>n.key==='phone').ports.map(p=>p.key),['next','phone_mismatch']);
    assert.equal(graph.edges.length,2);assert.ok(graph.nodes.every(n=>n.connected));
});
