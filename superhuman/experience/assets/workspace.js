'use strict';
(() => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let active = null;
  const stop = () => {if (active) {active.abort(); active = null;}};
  window.addEventListener('pagehide', stop);
  document.querySelectorAll('form').forEach(form => {
    const action = new URL(form.action, location.href).pathname;
    if (!(form.hasAttribute('data-voice') || /^\/talk\/[^/]+(?:\/(?:messages|send))?$/.test(action) || action === '/team/twin/messages' || /^\/team-room\/[^/]+\/send$/.test(action))) return;
    const field = form.querySelector('textarea[name="message"],textarea[name="content"],textarea[data-voice]');
    if (!field) return;
    const box = document.createElement('div'); box.className = 'voice-controls';
    const language = document.createElement('select'); language.setAttribute('aria-label','Speech language');
    [['en-US','English'],['ur-PK','Urdu']].forEach(([value,text])=>{const o=document.createElement('option');o.value=value;o.textContent=text;language.append(o);});
    const mic = document.createElement('button'); mic.type = 'button'; mic.className='secondary';mic.textContent='🎙 Dictate';mic.setAttribute('aria-label','Start speech to text');
    const status = document.createElement('span');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    const note = document.createElement('small');note.textContent='Speech may be processed online by your browser. Review the transcript, then press Send. Availability depends on your browser and language.';
    box.append(language,mic,status,note);field.after(box);
    if (!Recognition) {mic.disabled=true;status.textContent='Speech unavailable in this browser. You can type here.';return;}
    let recording=false,recognizer=null;
    mic.addEventListener('click',()=>{
      if (recording) {recognizer.stop();return;}
      stop();recognizer=new Recognition();recognizer.lang=language.value;recognizer.continuous=true;recognizer.interimResults=false;
      recognizer.onstart=()=>{recording=true;mic.textContent='■ Stop dictation';mic.setAttribute('aria-pressed','true');status.textContent='Listening…';};
      recognizer.onresult=event=>{
        let addition='';for(let i=event.resultIndex;i<event.results.length;i++){if(event.results[i].isFinal)addition+=event.results[i][0].transcript+' ';}
        const proposed=(field.value+(field.value ? ' ' : '')+addition).trimEnd();
        const maximum=field.maxLength>0?field.maxLength:6000;
        field.value=proposed.slice(0,maximum);field.dispatchEvent(new Event('input',{bubbles:true}));
        status.textContent=proposed.length>maximum?'Text limit reached. Review before sending.':'Transcript added. Review before sending.';
      };
      recognizer.onerror=event=>{status.textContent=event.error==='not-allowed'?'Microphone access denied. Allow it in your browser or type.':'Dictation stopped. You can type or try again.';};
      recognizer.onend=()=>{recording=false;mic.textContent='🎙 Dictate';mic.setAttribute('aria-pressed','false');if(active===recognizer)active=null;};
      active=recognizer;try{recognizer.start();}catch(e){stop();status.textContent='Microphone could not start. You can type.';}
    });
    form.addEventListener('submit',stop);
    language.addEventListener('change',stop);
  });
  const board=document.querySelector('[data-team-status]');
  if(board){
    let timer;
    const refresh=async()=>{
      if(document.hidden)return;
      try{const r=await fetch('/team-room/status',{credentials:'same-origin',headers:{Accept:'application/json'}});if(!r.ok||r.redirected)throw new Error('Status unavailable');const data=await r.json();
        data.forEach(e=>{const node=document.querySelector('[data-employee="'+e.id+'"]');if(!node)return;node.querySelector('[data-state]').textContent=e.state;node.querySelector('[data-reason]').textContent=e.reason;node.querySelector('[data-assignment]').textContent=e.task?e.task.title:e.assignment||'No active assignment';
        const actions=node.querySelector('.ux-actions');
        let task=actions.querySelector('[data-task-link]');
        if(e.task){if(!task){task=document.createElement('a');task.setAttribute('data-task-link','');actions.append(task);}task.href='/team/tasks/'+encodeURIComponent(e.task.id);task.textContent='Open task';}else if(task)task.remove();
        const project=node.querySelector('[data-project]');if(project){project.textContent=e.project?e.project.title:'';if(e.project)project.href='/team/projects/'+encodeURIComponent(e.project.id);else project.removeAttribute('href');}
        const last=node.querySelector('[data-last-action]');if(last)last.textContent='Last recorded action: '+(e.last?e.last.action.replaceAll('_',' ')+' · '+new Date(e.last.created_at).toLocaleString():'No action recorded');});
        const stamp=document.querySelector('[data-refreshed]');if(stamp)stamp.textContent='Updated '+new Date().toLocaleTimeString();
      }catch(e){const stamp=document.querySelector('[data-refreshed]');if(stamp)stamp.textContent='Status refresh unavailable. Reload for saved state.';}
    };
    timer=setInterval(refresh,15000);window.addEventListener('pagehide',()=>clearInterval(timer));
  }
})();
