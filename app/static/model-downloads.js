'use strict';
let downloadRefreshing=false, lastDownloadStates=new Map();
on('download-source','change',()=>{
  const hf=$('download-source').value==='huggingface';
  $('download-hf-fields').hidden=!hf;$('download-url-label').hidden=hf;$('download-url').required=!hf;
  for(const id of ['download-repo','download-hf-file','download-revision'])$(id).required=hf;
});
on('model-download-form','submit',async e=>{
  e.preventDefault();let url=$('download-url').value.trim();
  if($('download-source').value==='huggingface'){
    const repo=$('download-repo').value.trim(),file=$('download-hf-file').value.trim(),revision=$('download-revision').value.trim();
    if(!/^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/.test(repo))throw new Error('Enter a Hugging Face repository as owner/model.');
    if(!file.toLowerCase().endsWith('.gguf') || file.split('/').some(x=>!x||x==='.'||x==='..'))throw new Error('Enter the GGUF file path shown in the repository.');
    url='https://huggingface.co/'+repo+'/resolve/'+encodeURIComponent(revision)+'/'+file.split('/').map(encodeURIComponent).join('/');
  }
  $('download-start').disabled=true;
  try{await api('/models/downloads',{method:'POST',body:{url,filename:$('download-filename').value.trim(),sha256:$('download-sha').value.trim()}});notify('Model download started on the server.');await refreshDownloads();}
  finally{$('download-start').disabled=false;}
});
async function refreshDownloads(){
  if(downloadRefreshing||!state.user||state.user.role!=='admin')return;
  downloadRefreshing=true;
  try{
    const jobs=await api('/models/downloads');$('download-jobs').replaceChildren();let completed=false;
    for(const job of jobs){
      const card=node('div',undefined,'card');card.append(node('h3',job.filename),node('p',job.host+' · '+job.status));
      if(['downloading','validating','cancelling'].includes(job.status)){
        const progress=node('progress');progress.max=100;if(job.total)progress.value=Math.min(100,job.received/job.total*100);
        card.append(progress,node('p',(job.received/1048576).toFixed(1)+' MiB'+(job.total?' of '+(job.total/1048576).toFixed(1)+' MiB':'')));
        const cancel=button(job.status==='cancelling'?'Cancelling…':'Cancel download',async()=>{await api('/models/downloads/'+job.id+'/cancel',{method:'POST'});await refreshDownloads();});cancel.disabled=job.status==='cancelling';card.append(cancel);
      }
      if(job.error)card.append(node('p',job.error));
      if(job.status==='complete'){
        card.append(node('p','SHA-256: '+job.sha256+(job.checksum_verified?' · matches expected checksum':' · no expected checksum supplied'),'message-text'));
        card.append(button('Select in model form',async()=>{await refreshModels();$('model-file').value=job.filename;$('model-form').scrollIntoView?.({behavior:'smooth'});notify('Model selected. Review settings, then click Load model.');}));
        if(lastDownloadStates.get(job.id)!=='complete')completed=true;
      }
      lastDownloadStates.set(job.id,job.status);$('download-jobs').append(card);
    }
    if(completed)await refreshModels();
  }finally{downloadRefreshing=false;}
}
document.querySelector('[data-view="models"]').addEventListener('click',()=>refreshDownloads().catch(e=>notify(e.message)));
on('refresh-models','click',refreshDownloads);
setInterval(()=>{if(state.user && !$('view-models').hidden)refreshDownloads().catch(()=>{});},2000);
