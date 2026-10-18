'use strict';
(() => {
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  document.querySelectorAll('.practice-sheet textarea').forEach((field,index)=>{
    if (!Speech) return;
    const button=document.createElement('button');button.type='button';button.className='secondary practice-mic';button.textContent='Use microphone';
    if(!field.id)field.id='practice-answer-'+index;
    button.setAttribute('aria-controls',field.id);button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','Dictate answer '+(index+1));
    const notice=document.createElement('small');notice.className='practice-mic-status';notice.setAttribute('role','status');notice.textContent='Optional: your browser may use an online speech service. Starts only when tapped.';
    field.insertAdjacentElement('afterend',notice);field.insertAdjacentElement('afterend',button);
    let active=false,recognition;
    const stop=()=>{if(recognition)recognition.stop();};
    button.addEventListener('click',()=>{
      if(active){stop();return;}
      recognition=new Speech();recognition.lang=document.documentElement.lang||'en';recognition.interimResults=false;recognition.continuous=false;
      recognition.onstart=()=>{active=true;button.textContent='Stop microphone';button.setAttribute('aria-pressed','true');notice.textContent='Listening. Your words will be added to this answer; nothing is submitted.';};
      recognition.onresult=event=>{
        const spoken=Array.from(event.results).map(row=>row[0].transcript).join(' ');const combined=field.value+(field.value?' ':'')+spoken;
        if(field.maxLength>0 && combined.length>field.maxLength){notice.textContent='Answer limit reached. Edit or shorten it before dictating more.';return;}
        field.value=combined;field.dispatchEvent(new Event('input',{bubbles:true}));notice.textContent='Text added. Review it and save this step.';
      };
      recognition.onerror=()=>{notice.textContent='Microphone unavailable or permission denied. You can type your answer.';};
      recognition.onend=()=>{active=false;button.textContent='Use microphone';button.setAttribute('aria-pressed','false');};
      try{recognition.start();}catch(error){notice.textContent='Microphone could not start. You can type your answer.';}
    });
    field.form?.addEventListener('submit',stop);window.addEventListener('pagehide',stop);
  });
})();
