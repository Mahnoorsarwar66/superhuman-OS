'use strict';
(() => {
  const rail=document.querySelector('.hub-rail');
  if(rail&&matchMedia('(max-width:850px)').matches)rail.open=false;
  document.querySelectorAll('.hub-direct').forEach(form=>{const name=form.querySelector('span')?.textContent;const button=form.querySelector('button');if(name&&button)button.setAttribute('aria-label','Open direct conversation with '+name);});
  const draft=document.querySelector('[data-hub-draft]');
  if(draft){
    const field=draft.querySelector('textarea[name="message"]'),key='superhuman-draft-topic-'+draft.dataset.hubDraft,sent=key+'-sent';
    try{const value=sessionStorage.getItem(key);if(value)field.value=value;}catch(e){}
    field.addEventListener('input',()=>{try{sessionStorage.setItem(key,field.value);}catch(e){}});
    draft.addEventListener('submit',()=>{try{sessionStorage.setItem(key,field.value);sessionStorage.setItem(sent,field.value.trim());}catch(e){}});
    try{const previous=sessionStorage.getItem(sent);const messages=[...document.querySelectorAll('.hub-owner')];if(previous&&messages.some(node=>node.textContent.includes(previous))){sessionStorage.removeItem(key);sessionStorage.removeItem(sent);field.value='';}}catch(e){}
    const transcript=document.querySelector('[data-channel-topic]');
    let position=0,stick=transcript?.dataset.history==='1',busy=false;
    transcript?.addEventListener('scroll',()=>{position=transcript.scrollTop;stick=transcript.scrollHeight-transcript.clientHeight-position<70;},{passive:true});
    if(transcript&&stick)transcript.scrollTop=transcript.scrollHeight;
    const refresh=async()=>{
      if(document.hidden||busy)return;busy=true;
      try{
        const response=await fetch(location.href,{credentials:'same-origin'});if(!response.ok||response.redirected)throw Error('refresh');
        const doc=new DOMParser().parseFromString(await response.text(),'text/html');
        const fresh=doc.querySelector('[data-channel-topic]');if(fresh&&transcript&&fresh.innerHTML!==transcript.innerHTML){transcript.innerHTML=fresh.innerHTML;transcript.scrollTop=stick?transcript.scrollHeight:position;}
        const send=draft.querySelector('button:not([type="button"])'),freshSend=doc.querySelector('[data-hub-draft] button');if(send&&freshSend)send.disabled=freshSend.disabled;
        const work=document.querySelector('.hub-work'),freshWork=doc.querySelector('.hub-work');if(work&&freshWork)work.replaceWith(document.importNode(freshWork,true));
        const note=document.querySelector('.hub-refresh');if(note&&!doc.querySelector('.hub-refresh'))note.textContent='Saved discussion updated.';
      }catch(e){const note=document.querySelector('.hub-refresh');if(note)note.textContent='Live refresh unavailable. Your draft is preserved; use Refresh to reload saved replies.';}
      finally{busy=false;}
    };
    const timer=setInterval(refresh,6000);window.addEventListener('pagehide',()=>clearInterval(timer));
  }
  const anchor=location.hash;
  if(anchor&&/^#(?:turn|message)-[a-f0-9]+$/.test(anchor))requestAnimationFrame(()=>document.getElementById(anchor.slice(1))?.scrollIntoView({block:'center'}));
})();
