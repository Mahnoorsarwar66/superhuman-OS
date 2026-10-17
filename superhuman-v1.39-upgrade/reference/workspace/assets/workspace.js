'use strict';
(() => {
 const root=document.querySelector('[data-room]');
 if(root){
  const ident=root.dataset.room,before=root.dataset.before||'0',composer=root.querySelector('.ux-composer'),field=composer.querySelector('textarea[name="message"]'),button=composer.querySelector('button'),status=root.querySelector('[data-chat-status]');
  const key='superhuman-draft-'+ident,pendingKey=key+'-sent';
  try{
   const saved=sessionStorage.getItem(key);const sent=sessionStorage.getItem(pendingKey);
   if(sent && sent===root.dataset.lastUser){sessionStorage.removeItem(key);sessionStorage.removeItem(pendingKey);}
   else if(saved)field.value=saved;
  }catch(e){status.textContent='Browser draft storage unavailable. Keep this page open while composing.';}
  field.addEventListener('input',()=>{try{sessionStorage.setItem(key,field.value);}catch(e){}});
  composer.addEventListener('submit',()=>{
   try{sessionStorage.setItem(key,field.value);}catch(e){}
   try{sessionStorage.setItem(pendingKey,field.value.trim());}catch(e){}
  });
  let signature=null,busy=false;
  const refresh=async()=>{
   if(document.hidden||busy)return;busy=true;
   try{
    const response=await fetch('/room-live/'+encodeURIComponent(ident),{credentials:'same-origin'});
    if(response.status===401||response.status===403||response.redirected){status.textContent='Session needs attention. Your unsent draft remains in this browser tab.';return;}
    if(!response.ok)throw Error('status');const data=await response.json();
    button.disabled=!data.can_send;status.textContent=data.pending?'Reply queued or being prepared…':'Saved replies updated · '+data.used+' / '+data.maximum+' used';
    if(signature!==data.signature){
     const html=await fetch('/room-fragment/'+encodeURIComponent(ident)+'?before='+before,{credentials:'same-origin'});if(!html.ok)throw Error('fragment');
     const doc=new DOMParser().parseFromString(await html.text(),'text/html');
     const current=root.querySelector('[data-transcript]'),fresh=doc.querySelector('[data-transcript]');if(current&&fresh)current.replaceWith(document.importNode(fresh,true));
     const proposals=root.querySelector('[data-proposals]'),freshProposals=doc.querySelector('[data-proposals]');
     if(proposals&&freshProposals&&!proposals.contains(document.activeElement)&&!proposals.dataset.edited){proposals.replaceWith(document.importNode(freshProposals,true));signature=data.signature;}
     else if(proposals&&proposals.dataset.edited){status.textContent+=' · A saved proposal changed; finish your edits or reload to review the latest state.';}
    }
   }catch(e){status.textContent='Live refresh unavailable. Your draft is preserved; refresh when the connection returns.';}
   finally{busy=false;}
  };
  root.addEventListener('input',event=>{const panel=event.target.closest('[data-proposals]');if(panel)panel.dataset.edited='true';});
  const timer=setInterval(refresh,4000);refresh();window.addEventListener('pagehide',()=>clearInterval(timer));
 }
 document.querySelectorAll('form[action="/logout"]').forEach(form=>form.addEventListener('submit',()=>{try{Object.keys(sessionStorage).filter(k=>k.startsWith('superhuman-draft-')).forEach(k=>sessionStorage.removeItem(k));}catch(e){}}));
 // Explain disabled actions instead of submitting forms that cannot succeed.
 document.querySelectorAll('button[disabled]').forEach(button=>{if(!button.title)button.title='Finish pending work or review the explanation above before using this action.';});
})();
