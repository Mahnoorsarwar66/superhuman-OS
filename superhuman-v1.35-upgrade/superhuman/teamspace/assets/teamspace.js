'use strict';
(() => {
  const narrow=window.matchMedia('(max-width:900px)');
  document.querySelectorAll('.teamspace-rail').forEach(rail=>{if(narrow.matches)rail.open=false;});
  // Native anchored disclosure also works without JavaScript.
  if(location.hash==='#new-conversation')document.querySelector('#new-conversation')?.setAttribute('open','');
  document.querySelectorAll('a[href="#new-conversation"]').forEach(a=>a.addEventListener('click',()=>document.querySelector('#new-conversation')?.setAttribute('open','')));
  const chat=document.querySelector('.teamspace-chat[data-room]');
  if(!chat)return;
  const latest=chat.dataset.before==='0';
  let stick=latest,position=0,scroller;
  const watch=()=>{
    const fresh=chat.querySelector('[data-transcript]');if(!fresh)return;
    if(fresh!==scroller){scroller=fresh;if(!stick)scroller.scrollTop=position;scroller.addEventListener('scroll',()=>{position=scroller.scrollTop;stick=latest&&scroller.scrollHeight-scroller.clientHeight-scroller.scrollTop<65;},{passive:true});}
    if(stick)scroller.scrollTop=scroller.scrollHeight;
  };
  new MutationObserver(watch).observe(chat,{childList:true,subtree:true});watch();
})();
