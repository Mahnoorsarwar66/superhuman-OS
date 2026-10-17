// Optional local browser-API contract checks; no Node dependency on the server.
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(require('node:path').join(__dirname,'../reference/experience/assets/workspace.js'),'utf8');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.events={};this.attributes={};this.value='';this.maxLength=6000;}
 setAttribute(k,v){this.attributes[k]=v;}
 append(...nodes){this.children.push(...nodes);}
 addEventListener(k,fn){this.events[k]=fn;}
 dispatchEvent(e){this.lastEvent=e;}
 after(node){this.afterNode=node;}
}
function harness(supported=true){
 const forms=['/talk/legacy/send','/team/twin/messages','/team-room/room/send'].map(action=>{const f=new Element('form');f.action='https://example.test'+action;f.field=new Element('textarea');f.hasAttribute=()=>false;f.querySelector=()=>f.field;return f;});
 const all=[];class Recognition {
  constructor(){all.push(this);this.aborts=0;}
  start(){this.onstart();}
  stop(){this.onend();}
  abort(){this.aborts++;this.onend();}
 }
 const win={events:{},addEventListener(k,fn){this.events[k]=fn;}};if(supported)win.SpeechRecognition=Recognition;
 const doc={querySelectorAll:()=>forms,querySelector:()=>null,createElement:tag=>new Element(tag)};
 vm.runInNewContext(code,{window:win,document:doc,URL,location:{href:'https://example.test'},Event:class {constructor(type){this.type=type;}},setInterval,clearInterval});
 return {forms,all,win};
}
const h=harness();assert.equal(h.forms.length,3);
for(const form of h.forms){assert.ok(form.field.afterNode,'every conversation gets dictation');const [lang,mic,status]=form.field.afterNode.children;assert.equal(mic.type,'button');assert.deepEqual(lang.children.map(x=>x.value),['en-US','ur-PK']);}
const f=h.forms[0],controls=f.field.afterNode.children;controls[0].value='ur-PK';f.field.value='Typed first';controls[1].events.click();assert.equal(h.all[0].lang,'ur-PK');
h.all[0].onresult({resultIndex:0,results:[Object.assign([{transcript:'اردو الفاظ'}],{isFinal:true})]});assert.equal(f.field.value,'Typed first اردو الفاظ');
f.field.value='Edited';h.all[0].onresult({resultIndex:0,results:[Object.assign([{transcript:'new words'}],{isFinal:true})]});assert.equal(f.field.value,'Edited new words');
f.field.maxLength=5;h.all[0].onresult({resultIndex:0,results:[Object.assign([{transcript:'long transcript'}],{isFinal:true})]});assert.equal(f.field.value.length,5);assert.match(controls[2].textContent,/limit/);
const other=h.forms[1];other.field.afterNode.children[1].events.click();assert.equal(h.all[0].aborts,1);other.events.submit();assert.equal(h.all[1].aborts,1);
const unsupported=harness(false);assert.ok(unsupported.forms[0].field.afterNode.children[1].disabled);assert.match(unsupported.forms[0].field.afterNode.children[2].textContent,/type/);
assert.ok(!code.includes('.submit('));console.log('Browser dictation contract checks passed: 3 composers, English/Urdu, editing, limits, single recorder, manual send, unsupported browser.');
