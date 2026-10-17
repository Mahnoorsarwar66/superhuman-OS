'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[2]||'stage-v139/superhuman/workspace/assets/workspace.js','utf8');
test('live reply refresh updates usage and trace without enabling archived send or overwriting draft',async()=>{
 const field={value:'unsent draft',addEventListener(){}},button={disabled:true},status={},counts={};
 const composer={querySelector:s=>s.startsWith('textarea')?field:button,addEventListener(){}};
 const transcript={replaceWith(v){this.replaced=v}},proposals={contains:()=>false,replaceWith(v){this.replaced=v},dataset:{}},context={open:true,contains:()=>false,replaceWith(v){this.replaced=v},dataset:{}};
 const freshTranscript={},freshProposals={},freshContext={open:false};
 const root={dataset:{room:'qa-room',before:'0'},querySelector:s=>({'.ux-composer':composer,'[data-chat-status]':status,'[data-reply-count]':counts,'[data-transcript]':transcript,'[data-proposals]':proposals})[s],addEventListener(){}};
 let requests=[];
 const document={hidden:false,activeElement:{},querySelector:s=>s==='[data-room]'?root:s==='[data-live-context]'?context:null,querySelectorAll:()=>[],importNode:x=>x,addEventListener(){}};
 const doc={querySelector:s=>({'[data-transcript]':freshTranscript,'[data-proposals]':freshProposals,'[data-live-context]':freshContext})[s]};
 const sandbox={document,window:{addEventListener(){}},sessionStorage:{getItem:()=>null,removeItem(){},setItem(){}},setInterval(){return 1},clearInterval(){},DOMParser:class{parseFromString(){return doc}},fetch:async url=>{requests.push(url);return {ok:true,status:200,redirected:false,json:async()=>({can_send:false,pending:false,used:3,maximum:20,signature:'done'}),text:async()=>'<fragment>'}}};
 vm.runInNewContext(source,sandbox);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(button.disabled,true);assert.equal(field.value,'unsent draft');assert.match(counts.textContent,/3 \/ 20/);assert.match(status.textContent,/3 \/ 20/);
 assert.equal(context.replaced,freshContext);assert.equal(freshContext.open,true);assert.equal(transcript.replaced,freshTranscript);assert.equal(proposals.replaced,freshProposals);
 assert.deepEqual(requests,['/room-live/qa-room','/room-fragment/qa-room?before=0']);
});
