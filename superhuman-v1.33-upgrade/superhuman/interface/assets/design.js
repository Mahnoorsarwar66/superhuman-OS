'use strict';
(() => {
  const mobile=window.matchMedia('(max-width:800px)');
  document.querySelectorAll('.shell-menu,.ui-accounts').forEach(menu=>{if(mobile.matches)menu.open=false;});
  document.querySelectorAll('[data-history-back]').forEach(button=>button.addEventListener('click',()=>{if(history.length>1)history.back();else location.assign('/');}));
  const states={'working':['In progress','info'],'running':['Working','info'],'paused':['Paused','neutral'],'blocked':['Blocked','warning'],'idle':['No active assignment','neutral'],'needs review':['Needs review','warning'],'awaiting review':['Needs review','warning'],'offline':['Offline','warning']};
  document.querySelectorAll('[data-team-status] [data-state]').forEach(node=>{
    const refresh=()=>{const value=states[node.textContent.toLowerCase().replaceAll('_',' ')];if(!value)return;if(node.textContent!==value[0])node.textContent=value[0];node.className='badge ui-status ui-'+value[1];};
    new MutationObserver(refresh).observe(node,{childList:true,subtree:true,characterData:true});refresh();
  });
  // Browser validation and named submit-button values remain native.
  // Prevent repeat submission without disabling controls before form serialization.
  const busy=new WeakSet();
  document.addEventListener('submit',event=>{
    const form=event.target;
    if(!(form instanceof HTMLFormElement)||(form.method||'get').toLowerCase()!=='post')return;
    if(busy.has(form)){event.preventDefault();return;}
    busy.add(form);form.setAttribute('aria-busy','true');
    setTimeout(()=>{busy.delete(form);form.removeAttribute('aria-busy');},12000);
  });
  window.addEventListener('pageshow',()=>document.querySelectorAll('form[aria-busy]').forEach(form=>{busy.delete(form);form.removeAttribute('aria-busy');}));
})();
