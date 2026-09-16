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
 '/models':{models:[{filename:'local.gguf',bytes:10000}],loaded:false},
 '/model-profiles':[{id:1,name:'Laptop',config:{filename:'local.gguf',context:2048,threads:2,gpu_layers:0,max_tokens:256,temperature:0.2}}],
 '/knowledge/1/documents':[{id:5,name:'training.txt',size:100,status:'ready',progress:100,pages:0,format:'txt'}],
 '/knowledge/1/members':[], '/users':[],
 '/evaluation/questions':[{id:3,kb_id:1,question:'What training?',expected:'MikroTik'}],
 '/evaluation/runs':[], '/feedback':[],
 '/queue':{paused:false,requests:[{key:'chat:1',kind:'chat',user_id:1,position:2,status:'waiting'}]},
 '/public-sites':[{id:1,kb_id:1,name:'Public website',origins:['https://nelsonict.com.ng'],enabled:0,approved:[]}]
};
w.fetch=async(url,options={})=>{const path=String(url).replace(/^\/api/,'');calls.push({path,options});if(!(path in fixtures))throw Error('Unexpected request '+path);return new Response(JSON.stringify(fixtures[path]),{headers:{'content-type':'application/json'}});};
w.confirm=()=>false;
w.eval(fs.readFileSync('app/static/app.js','utf8')+'\n'+fs.readFileSync('app/static/operations.js','utf8'));
const flush=()=>new Promise(r=>setTimeout(r,30));
(async()=>{
 await flush();
 assert.equal(d.getElementById('workspace').hidden,false);
 assert.equal(d.getElementById('view-wizard').hidden,false);
 assert.match(d.getElementById('machine-report').textContent,/Test CPU/);
 d.getElementById('wizard-models').click();await flush();
 assert.equal(d.getElementById('view-models').hidden,false);
 d.getElementById('profile-list').value='1';d.getElementById('use-profile').click();await flush();
 assert.equal(d.getElementById('model-threads').value,'2');
 assert.equal(d.getElementById('model-file').value,'local.gguf');
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
 process.stdout.write('DOM smoke checks passed: wizard, navigation, profiles, documents, sharing, summary selection, evaluation, queue and public approval.\n');
 dom.window.close();
})().catch(e=>{dom.window.close();process.stderr.write(e.stack+'\n');process.exitCode=1;});
