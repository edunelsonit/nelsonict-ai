'use strict';
const site=location.pathname.split('/').pop();
const get=id=>document.getElementById(id);
let token=null, controller=null;
get('ask').addEventListener('submit',async event=>{
  event.preventDefault(); if(controller)return;
  controller=new AbortController();get('send').disabled=true;get('stop').hidden=false;
  const question=document.createElement('p');question.textContent=get('question').value;
  const answer=document.createElement('p');get('answers').append(question,answer);
  try {
    const response=await fetch('/api/public/'+site+'/chat',{method:'POST',credentials:'omit',signal:controller.signal,
      headers:{'Content-Type':'application/json','X-Nelson-Client':'web'},body:JSON.stringify({question:get('question').value})});
    if(!response.ok){const e=await response.json();throw new Error(typeof e.detail==='string'?e.detail:'Request rejected.');}
    get('question').value='';const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let end;
      while((end=buffer.indexOf('\n\n'))>=0){const line=buffer.slice(0,end);buffer=buffer.slice(end+2);if(!line.startsWith('data: '))continue;
        const e=JSON.parse(line.slice(6));if(e.type==='request')token=e.token;
        if(e.type==='token'){answer.textContent+=e.text;get('status').textContent='Answering…';}
        if(e.type==='queue')get('status').textContent=e.message;
        if(e.type==='error')get('status').textContent=e.message;
        if(e.type==='sources' && e.sources.length){const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Approved sources';details.append(summary);
          e.sources.forEach(s=>{const p=document.createElement('p');p.textContent='['+s.id+'] '+s.name+' · '+s.location+'\n'+s.text;details.append(p);});get('answers').append(details);}
      }
    }
  } catch(e){get('status').textContent=e.name==='AbortError'?'Cancelled.':e.message;}
  finally {controller=null;token=null;get('send').disabled=false;get('stop').hidden=true;}
});
get('stop').addEventListener('click',async()=>{
  if(token)await fetch('/api/public/'+site+'/cancel/'+token,{method:'POST',credentials:'omit',headers:{'X-Nelson-Client':'web'}});
  if(controller)controller.abort();
});
