// DOM behaviour tests; these do not replace browser layout or real-model tests.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const errors=[];
const console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(fs.readFileSync('app/static/index.html','utf8'),{url:'http://localhost',runScripts:'outside-only',virtualConsole:console});
const w=dom.window,d=w.document,calls=[];
const knowledge=[{id:1,name:'Shared training',documents:1,permission:'owner'}];
const fixtures={
 '/setup':{required:false},'/me':{id:1,username:'test-owner',role:'admin',csrf:'fixture'},
 '/conversations':[], '/knowledge':knowledge, '/assistants':[],
 '/status':{model:{loaded:false},worker_online:true,search:'keyword',upload_limit_mb:25,storage_limit_mb:250},
 '/system/check':{os:'Linux',cpu:'Test CPU',cores:4,ram_total:16*1073741824,ram_available:8*1073741824,disk_free:100*1073741824,models_writable:true,nvidia_devices:[],dependencies:{inference:false},inference_backend:{gpu_offload:false,error:null},installation_help:{inference:'Install inference'},recommended:{context:2048,threads:2},worker_online:true,wizard_complete:false},
 '/models/downloads':[],
 '/models':{models:[{filename:'local.gguf',bytes:2*1073741824},{filename:'large.gguf',bytes:12*1073741824}],loaded:false},
 '/models/load':{loaded:true},
 '/model-profiles':[{id:1,name:'Laptop',config:{filename:'local.gguf',context:2048,threads:2,gpu_layers:0,max_tokens:256,temperature:0.2}},{id:2,name:'Large model',config:{filename:'large.gguf',context:2048,threads:2,gpu_layers:0,max_tokens:256,temperature:0.2}}],
 '/knowledge/1/documents':[{id:5,name:'training.txt',size:100,status:'ready',progress:100,pages:0,format:'txt'}],
 '/knowledge/1/members':[], '/users':[],
 '/evaluation/questions':[{id:3,kb_id:1,question:'What training?',expected:'MikroTik'}],
 '/evaluation/runs':[], '/feedback':[],
 '/queue':{paused:false,requests:[{key:'chat:1',kind:'chat',user_id:1,position:2,status:'waiting'}]},
 '/public-sites':[{id:1,kb_id:1,name:'Public website',origins:['https://nelsonict.com.ng'],enabled:0,approved:[]}]
};
const resourceReport=context=>({ram_total:16*1073741824,ram_available:8*1073741824,reserve_bytes:2*1073741824,budget_bytes:6*1073741824,note:'Conservative CPU RAM estimate; GPU memory does not increase this budget.',recommended:{filename:'local.gguf',context:2048,threads:2,gpu_layers:0},models:[
 {filename:'local.gguf',bytes:2*1073741824,allowed:context<=4096,reason:context<=4096?'Sufficient RAM.':'Context needs more RAM; reduce context tokens.',estimated_bytes:(context<=4096?3:9)*1073741824,context},
 {filename:'large.gguf',bytes:12*1073741824,allowed:false,reason:'Choose a smaller GGUF; this model exceeds the RAM budget.',estimated_bytes:15*1073741824,context}
]});
let resourceResponse=resourceReport;
w.fetch=async(url,options={})=>{const path=String(url).replace(/^\/api/,'');calls.push({path,options});let result;
 if(path.startsWith('/models/resources?context='))result=await resourceResponse(Number(path.split('=')[1]));
 else {if(!(path in fixtures))throw Error('Unexpected request '+path);result=fixtures[path];}
 return new Response(JSON.stringify(result),{headers:{'content-type':'application/json'}});};
w.confirm=()=>false;
w.eval(fs.readFileSync('app/static/app.js','utf8')+'\n'+fs.readFileSync('app/static/operations.js','utf8')+'\n'+fs.readFileSync('app/static/model-downloads.js','utf8')+'\nwindow.resourceTestUI={renderModelResources,refreshDownloads};');
const flush=()=>new Promise(r=>setTimeout(r,30));
(async()=>{
 await flush();
 assert.equal(d.getElementById('workspace').hidden,false);
 assert.equal(d.getElementById('view-wizard').hidden,false);
 assert.match(d.getElementById('machine-report').textContent,/Test CPU/);
 d.getElementById('wizard-models').click();await flush();
 assert.equal(d.getElementById('view-models').hidden,false);
 assert.equal(d.getElementById('load-model').disabled,true);
 assert.match(d.getElementById('model-resource-memory').textContent,/8.00 GiB available.*Reserved.*2.00 GiB/);
 assert.equal(d.querySelector('#model-file option[value="large.gguf"]').disabled,true);
 assert.match(d.getElementById('model-resource-list').textContent,/large.gguf.*15.00 GiB.*Choose a smaller GGUF/);
 d.getElementById('download-source').value='url';
 d.getElementById('download-source').dispatchEvent(new w.Event('change'));
 assert.equal(d.getElementById('download-url').required,true);
 assert.equal(d.getElementById('download-repo').required,false);
 d.getElementById('download-source').value='huggingface';
 d.getElementById('download-source').dispatchEvent(new w.Event('change'));
 assert.equal(d.getElementById('download-repo').required,true);
 assert.equal(d.getElementById('download-url-label').hidden,true);
 d.getElementById('profile-list').value='1';d.getElementById('use-profile').click();await flush();
 assert.equal(d.getElementById('model-threads').value,'2');
 assert.equal(d.getElementById('model-file').value,'local.gguf');
 assert.equal(d.getElementById('load-model').disabled,false);
 const loadCount=()=>calls.filter(call=>call.path==='/models/load').length;
 const submitModel=()=>d.getElementById('model-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 const setContext=(context,event='change')=>{d.getElementById('model-context').value=context;d.getElementById('model-context').dispatchEvent(new w.Event(event));};
 d.getElementById('profile-list').value='2';d.getElementById('use-profile').click();await flush();
 assert.equal(d.getElementById('load-model').disabled,true);
 assert.match(d.getElementById('model-resource-assessment').textContent,/Cannot load.*Choose a smaller GGUF/);
 submitModel();await flush();assert.equal(loadCount(),0);
 d.getElementById('model-tokens').value='2048';d.getElementById('recommend-model').click();await flush();
 assert.equal(d.getElementById('model-file').value,'local.gguf');
 assert.equal(d.getElementById('model-context').value,'2048');
 assert.equal(d.getElementById('model-gpu').value,'0');
 assert.equal(d.getElementById('model-tokens').value,'1024','Suggested context must leave room for the prompt');
 assert.equal(d.getElementById('load-model').disabled,false);
 assert.equal(loadCount(),0,'Choosing a suitable model must leave loading to the user');
 fixtures['/models'].config={filename:'large.gguf',context:4096,threads:4,max_tokens:512,temperature:0.3,gpu_layers:0};
 d.getElementById('model-threads').value='7';d.getElementById('model-tokens').value='256';
 d.getElementById('refresh-models').click();await flush();
 assert.equal(d.getElementById('model-file').value,'local.gguf','Refreshing files must preserve the selected replacement model');
 assert.equal(d.getElementById('model-context').value,'2048');assert.equal(d.getElementById('model-threads').value,'7');assert.equal(d.getElementById('model-tokens').value,'256');
 setContext(8192,'input');assert.equal(d.getElementById('load-model').disabled,true);
 submitModel();await new Promise(resolve=>setTimeout(resolve,360));assert.equal(loadCount(),0);
 assert.match(d.getElementById('model-resource-assessment').textContent,/8192.*Cannot load/);
 assert.ok(calls.some(call=>call.path==='/models/resources?context=8192'));
 const pending=[];resourceResponse=context=>new Promise(resolve=>pending.push({context,resolve}));
 setContext(2048);setContext(8192);assert.equal(d.getElementById('load-model').disabled,true);
 pending[1].resolve(resourceReport(8192));await flush();pending[0].resolve(resourceReport(2048));await flush();
 assert.equal(d.getElementById('load-model').disabled,true,'An older context response cannot enable loading');
 assert.match(d.getElementById('model-resource-assessment').textContent,/8192.*Cannot load/);
 resourceResponse=()=>{throw Error('RAM probe unavailable');};d.getElementById('refresh-model-resources').click();await flush();
 assert.equal(d.getElementById('load-model').disabled,true);assert.match(d.getElementById('model-resource-assessment').textContent,/RAM probe unavailable.*blocked/);
 submitModel();await flush();assert.equal(loadCount(),0);
 resourceResponse=resourceReport;setContext(2048);await flush();
 const now=w.Date.now;w.Date.now=()=>now()+31000;w.resourceTestUI.renderModelResources();
 assert.equal(d.getElementById('load-model').disabled,true,'Expired checks cannot permit loading');
 submitModel();await flush();assert.equal(loadCount(),0);w.Date.now=now;
 d.getElementById('refresh-model-resources').click();await flush();
 resourceResponse=context=>({...resourceReport(context),recommended:{filename:null},models:resourceReport(context).models.map(model=>({...model,allowed:false,reason:'RAM use increased.'}))});
 submitModel();await flush();assert.equal(loadCount(),0,'A fresh pre-load check must catch reduced available RAM');
 assert.match(d.getElementById('model-resource-guidance').textContent,/No local model fits.*smaller GGUF/);
 resourceResponse=resourceReport;d.getElementById('refresh-model-resources').click();await flush();
 submitModel();await flush();assert.equal(loadCount(),1);
 assert.equal(JSON.parse(calls.find(call=>call.path==='/models/load').options.body).filename,'local.gguf');
 resourceResponse=context=>({...resourceReport(context),models:[],recommended:{filename:null}});
 d.getElementById('refresh-model-resources').click();await flush();
 assert.equal(d.getElementById('load-model').disabled,true);assert.match(d.getElementById('model-resource-guidance').textContent,/No local GGUF models found.*smaller GGUF/);
 resourceResponse=resourceReport;d.getElementById('apply-recommendations').click();await flush();
 assert.equal(d.getElementById('model-context').value,'2048');assert.equal(d.getElementById('load-model').disabled,false);
 fixtures['/models/downloads']=[{id:1,filename:'large.gguf',status:'complete',host:'example.com',sha256:'fixture'}];await w.resourceTestUI.refreshDownloads();
 Array.from(d.querySelectorAll('#download-jobs button')).find(button=>button.textContent==='Select in model form').click();await flush();
 assert.equal(d.getElementById('model-file').value,'large.gguf');assert.equal(d.getElementById('load-model').disabled,true,'Downloaded model selection must refresh its safety check');
 assert.match(d.getElementById('model-resource-assessment').textContent,/Cannot load.*Choose a smaller GGUF/);
 d.querySelector('[data-view="knowledge"]').click();await flush();
 d.querySelector('.knowledge-link').click();await flush();
 assert.equal(d.getElementById('sharing-card').hidden,false);
 assert.match(d.getElementById('document-list').textContent,/training.txt/);
 assert.match(d.getElementById('document-list').textContent,/Preview/);
 d.getElementById('chat-kb').value='1';d.getElementById('chat-kb').dispatchEvent(new w.Event('change'));await flush();
 assert.equal(d.getElementById('chat-documents').options[0].value,'5');
 d.getElementById('chat-task').value='summary';d.getElementById('chat-task').dispatchEvent(new w.Event('change'));await flush();
 assert.equal(d.getElementById('chat-mode').value,'documents');
 d.querySelector('[data-view="quality"]').click();await flush();
 assert.equal(d.getElementById('view-quality').hidden,false);
 assert.match(d.getElementById('eval-questions').textContent,/What training/);
 d.querySelector('[data-view="operations"]').click();await flush();
 assert.match(d.getElementById('queue-list').textContent,/position 2/);
 d.getElementById('site-select').value='1';d.getElementById('site-select').dispatchEvent(new w.Event('change'));await flush();
 assert.match(d.getElementById('site-snippet').value,/\/widget\/1/);
 assert.equal(d.querySelector('.public-document').checked,false);
 assert.equal(d.getElementById('site-approved').checked,false);
 assert.deepEqual(errors,[]);
 assert.ok(!d.getElementById('toast').textContent.includes('undefined'));
 process.stdout.write('DOM smoke checks passed: resource-aware selection, blocked/unknown/stale model guards, recommendations, context races, switching, wizard, profiles, documents, sharing, evaluation, queue and public approval.\n');
 dom.window.close();
})().catch(e=>{dom.window.close();process.stderr.write(e.stack+'\n');process.exitCode=1;});
