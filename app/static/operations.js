'use strict';
let evaluationQuestions=[], publicSites=[], selectedRun=null, migrationStage=null, migrationConfig=null, queuePaused=false;
function addFeedbackControls(article,id){
  const row=node('div',undefined,'row');
  for(const [label,rating] of [['Helpful','helpful'],['Flag incorrect','incorrect']]) row.append(button(label,async()=>{
    if(!confirm('Share this answer, cited excerpts, and your feedback with administrators?'))return;
    const note=prompt('Optional feedback note','');if(note===null)return;
    await api('/messages/'+id+'/feedback',{method:'POST',body:{rating,note}});notify('Feedback saved.');
  }));
  row.append(button('Remove feedback',async()=>{await api('/messages/'+id+'/feedback',{method:'DELETE'});notify('Feedback removed.');}));article.append(row);
}
async function refreshQuality(){
  selectOptions('eval-kb',state.knowledge,'Select knowledge');
  evaluationQuestions=await api('/evaluation/questions');$('eval-questions').replaceChildren();
  evaluationQuestions.forEach(q=>{
    const row=node('div',undefined,'card');const label=node('label',q.question);const check=node('input');check.type='checkbox';check.value=q.id;check.className='eval-select';label.prepend(check);
    row.append(label,button('Edit',()=>{$('eval-question-id').value=q.id;$('eval-kb').value=q.kb_id;$('eval-question').value=q.question;$('eval-expected').value=q.expected;}),button('Delete',async()=>{if(!confirm('Delete this saved question?'))return;await api('/evaluation/questions/'+q.id,{method:'DELETE'});await refreshQuality();}));$('eval-questions').append(row);
  });
  const runs=await api('/evaluation/runs');$('eval-runs').replaceChildren();
  runs.forEach(r=>{$('eval-runs').append(button('#'+r.id+' · '+new Date(r.created*1000).toLocaleString()+' · '+r.status,()=>showEvaluation(r.id)));});
  if(state.user.role==='admin'){
    const feedback=await api('/feedback');$('feedback-list').replaceChildren();
    feedback.forEach(f=>{const item=node('details');item.append(node('summary',f.username+' · '+f.rating),node('p',f.note),node('pre',f.content,'message-text'));$('feedback-list').append(item);});
  }
}
async function showEvaluation(id){
  selectedRun=id;const r=await api('/evaluation/runs/'+id),box=$('eval-results');box.replaceChildren(node('h3','Run #'+id+' · '+r.status));
  const config=node('details');config.append(node('summary','Model configuration & fingerprint'),node('pre',JSON.stringify(r.config,null,2),'message-text'));box.append(config);
  if(['queued','running'].includes(r.status))box.append(button('Cancel run',async()=>{await api('/evaluation/runs/'+id+'/cancel',{method:'POST'});await showEvaluation(id);}));
  box.append(button('Export run JSON',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='evaluation-'+id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
  r.results.forEach(result=>{
    const card=node('div',undefined,'card');if(result.error){card.append(node('p',result.error));box.append(card);return;}
    card.append(node('h3',result.question),node('p','Expected: '+result.expected),node('pre',result.answer,'message-text'),node('p','Expected-term coverage: '+Math.round(result.expected_term_coverage*100)+'% · Review: '+result.review),node('p',result.note||''));
    renderSources(card,result.sources||[]);
    if(!['queued','running'].includes(r.status))for(const verdict of ['pass','fail'])card.append(button('Mark '+verdict,async()=>{const note=prompt('Review note','');if(note===null)return;await api('/evaluation/runs/'+id+'/review',{method:'POST',body:{question_id:result.question_id,verdict,note}});await showEvaluation(id);}));box.append(card);
  });
}
on('quality-refresh','click',async()=>{await refreshQuality();if(selectedRun)await showEvaluation(selectedRun);});
on('eval-clear','click',()=>{$('eval-question-form').reset();$('eval-question-id').value='';});
on('eval-question-form','submit',async e=>{e.preventDefault();const id=$('eval-question-id').value;await api('/evaluation/questions'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{kb_id:Number($('eval-kb').value),question:$('eval-question').value,expected:$('eval-expected').value}});$('eval-question-form').reset();$('eval-question-id').value='';await refreshQuality();});
on('eval-run','click',async()=>{const question_ids=Array.from(document.querySelectorAll('.eval-select:checked')).map(x=>Number(x.value));if(!question_ids.length||question_ids.length>20)throw new Error('Select between 1 and 20 questions.');const r=await api('/evaluation/runs',{method:'POST',body:{question_ids}});await refreshQuality();await showEvaluation(r.id);});
async function refreshQueue(){
  const q=await api('/queue');queuePaused=q.paused;$('queue-pause').textContent=q.paused?'Resume queue':'Pause queue';$('queue-list').replaceChildren();
  if(!q.requests.length)$('queue-list').append(node('p','No requests waiting or running.'));
  q.requests.forEach(r=>{const row=node('div',undefined,'user-row');row.append(node('span',r.kind+' · user '+r.user_id+' · '+(r.position?'position '+r.position:r.status)),button('Cancel',async()=>{await api('/queue/cancel',{method:'POST',body:{key:r.key}});await refreshQueue();}));$('queue-list').append(row);});
}
on('queue-pause','click',async()=>{await api('/queue/pause',{method:'POST',body:{paused:!queuePaused}});await refreshQueue();});
async function refreshSites(){publicSites=await api('/public-sites');selectOptions('site-select',publicSites,'Select public assistant');await showSite();}
async function showSite(){
  const site=publicSites.find(x=>x.id===Number($('site-select').value));$('site-documents').replaceChildren();$('site-approved').checked=false;$('site-snippet').value='';if(!site)return;
  $('site-edit-origins').value=site.origins.join('\n');$('site-enabled').checked=Boolean(site.enabled);
  const docs=await api('/knowledge/'+site.kb_id+'/documents');
  docs.forEach(d=>{const label=node('label',d.name+' · '+d.status),check=node('input');check.type='checkbox';check.value=d.id;check.className='public-document';check.disabled=d.status!=='ready';check.checked=site.approved.some(p=>p.document_id===d.id);label.prepend(check);$('site-documents').append(label);});
  $('site-snippet').value='<iframe src="'+location.origin+'/widget/'+site.id+'" title="Nelsonict AI" width="100%" height="620" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>';
}
on('site-select','change',showSite);
on('site-create','submit',async e=>{e.preventDefault();const r=await api('/public-sites',{method:'POST',body:{name:$('site-name').value,origins:$('site-origins').value.split('\n').map(x=>x.trim()).filter(Boolean)}});await refreshLists();await refreshSites();$('site-select').value=r.id;await showSite();notify('Separate public collection created. Upload documents before approving publication.');});
on('site-library','click',async()=>{const s=publicSites.find(x=>x.id===Number($('site-select').value));if(!s)return;await chooseKnowledge(s.kb_id);showView('knowledge');});
on('site-publish','submit',async e=>{e.preventDefault();const id=Number($('site-select').value);if(!id)throw new Error('Select a public assistant.');await api('/public-sites/'+id,{method:'PUT',body:{enabled:$('site-enabled').checked,confirm_public:$('site-approved').checked,origins:$('site-edit-origins').value.split('\n').map(x=>x.trim()).filter(Boolean),document_ids:Array.from(document.querySelectorAll('.public-document:checked')).map(x=>Number(x.value))}});await refreshSites();notify('Public assistant settings saved.');});
on('site-delete','click',async()=>{const id=$('site-select').value;if(!id||!confirm('Remove the public assistant? Its collection stays private in Knowledge.'))return;await api('/public-sites/'+id,{method:'DELETE'});await refreshSites();});
on('operations-refresh','click',async()=>{await refreshQueue();await refreshSites();});
document.querySelector('[data-view="quality"]').addEventListener('click',()=>refreshQuality().catch(e=>notify(e.message)));
document.querySelector('[data-view="operations"]').addEventListener('click',()=>Promise.all([refreshQueue(),refreshSites()]).catch(e=>notify(e.message)));
setInterval(async()=>{if(!state.user)return;try{if(!$('view-operations').hidden)await refreshQueue();if(!$('view-quality').hidden && selectedRun)await showEvaluation(selectedRun);}catch{}},4000);
on('open-migration','click',async()=>{
  migrationConfig=await api('/migration/settings');$('migration-dialog').showModal();
  const c=migrationConfig;for(const [id,key] of [['models','models_dir'],['embedding','embedding_model'],['hosts','allowed_hosts'],['bind','bind_host'],['port','bind_port']])$('migration-'+id).value=c[key];
  $('migration-secure').checked=c.cookie_secure;$('migration-threads').value=c.hardware.recommended.threads;$('migration-context').value=c.hardware.recommended.context;
  $('migration-review').textContent='Current data: '+c.data_dir+'\nAvailable RAM: '+(c.hardware.ram_available/1073741824).toFixed(1)+' GiB\nUpload a trusted Nelsonict backup to review its contents.';
});
on('migration-close','click',()=>$('migration-dialog').close());
on('migration-upload','submit',async e=>{
  e.preventDefault();if(migrationStage)throw new Error('Discard the current staged restore before uploading another.');const file=$('migration-file').files[0];if(!file)return;
  $('migration-stage').disabled=true;$('migration-result').textContent='Uploading and validating backup…';
  try{
    const result=await new Promise((resolve,reject)=>{const x=new XMLHttpRequest();x.open('POST','/api/migration/stage');x.setRequestHeader('X-Nelson-Client','web');x.setRequestHeader('X-CSRF-Token',state.csrf);x.setRequestHeader('Content-Type','application/zip');x.upload.onprogress=e=>{if(e.lengthComputable)$('migration-progress').value=e.loaded/e.total*100;};x.onerror=()=>reject(new Error('Backup upload failed.'));x.onload=()=>{try{const data=JSON.parse(x.responseText);if(x.status>=200&&x.status<300)resolve(data);else reject(new Error(errorText(data)));}catch{reject(new Error('Backup rejected. Check the server and proxy upload limits.'));}};x.send(file);});
    migrationStage=result.id;$('migration-review').textContent=JSON.stringify(result.counts,null,2);$('migration-data').value=result.data_dir;$('migration-activate').hidden=false;$('migration-result').textContent='Backup validated. Review paths, network and hardware below.';
  }finally{$('migration-stage').disabled=false;}
});
on('migration-activate','submit',async e=>{e.preventDefault();const body={models_dir:$('migration-models').value,embedding_model:$('migration-embedding').value,allowed_hosts:$('migration-hosts').value,bind_host:$('migration-bind').value,bind_port:Number($('migration-port').value),cookie_secure:$('migration-secure').checked,threads:Number($('migration-threads').value),context:Number($('migration-context').value),gpu_layers:Number($('migration-gpu').value),confirm:$('migration-confirm').value};const r=await api('/migration/'+migrationStage+'/activate',{method:'POST',body});$('migration-result').textContent=r.message;$('migration-restart').hidden=!migrationConfig.managed_restart;});
on('migration-discard','click',async()=>{if(!migrationStage)return;await api('/migration/'+migrationStage,{method:'DELETE'});migrationStage=null;$('migration-activate').hidden=true;$('migration-review').textContent='Staged restore removed.';});
on('migration-restart','click',async()=>{if(!confirm('Restart the application and worker now? Active replies will be interrupted.'))return;const r=await api('/migration/restart',{method:'POST'});$('migration-result').textContent=r.message;});
