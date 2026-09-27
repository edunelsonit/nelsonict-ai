"use strict";
const $ = (id) => document.getElementById(id);
const state = {user:null, setup:false, recovering:false, conversations:[], knowledge:[], assistants:[], conversation:null, kb:null, busy:false, csrf:""};
let passwordResetUser = null;
const modelSafety = {report:null,context:null,checkedAt:0,pending:false,error:"",version:0,timer:null,expiry:null,loading:false,serverLoading:false,filesRefreshing:false,filesVersion:0,initialized:false};
const MODEL_RESOURCE_MAX_AGE = 30000;
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function notify(message) {
  $("toast").textContent = message; $("toast").hidden = false;
  clearTimeout(notify.timer); notify.timer = setTimeout(() => $("toast").hidden = true, 7000);
}
function errorText(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map(x => x.msg).join("; ");
  return "Request failed. Please try again.";
}
async function api(path, options={}) {
  const headers = {"X-Nelson-Client":"web", "X-CSRF-Token":state.csrf, ...options.headers};
  if (options.body && typeof options.body === "object" && !(options.body instanceof Blob)) {
    options.body = JSON.stringify(options.body);
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch("/api" + path, {...options, headers});
  if (!response.ok) {
    let data; try { data = await response.json(); } catch { data = {detail: await Promise.resolve(response.statusText)}; }
    throw new Error(errorText(data));
  }
  return response.json();
}
function on(id, event, handler) {
  $(id).addEventListener(event, async (e) => {
    try { await handler(e); } catch (err) { notify(err.message); }
  });
}
function button(text, callback, className="quiet") {
  const el = node("button", text, className);
  el.type = "button";
  el.addEventListener("click", () => Promise.resolve().then(callback).catch(e => notify(e.message)));
  return el;
}
function selectOptions(id, items, placeholder) {
  const select = $(id), value = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  items.forEach(item => select.add(new Option(item.name, item.id)));
  if (items.some(x => String(x.id) === value)) select.value = value;
}
let chatStatusTimer;
function setChatStatus(message, linger=0) {
  clearTimeout(chatStatusTimer);
  $("chat-status").hidden=!message;$("chat-status-text").textContent=message||"";
  if(linger)chatStatusTimer=setTimeout(()=>{if(!state.busy)setChatStatus("");},linger);
}
function showView(view) {
  document.querySelectorAll(".view").forEach(el => el.hidden = el.id !== "view-" + view);
  document.querySelectorAll("[data-view]").forEach(el => el.classList.toggle("active", el.dataset.view === view));
  $("view-title").textContent = {chat:"Chat",knowledge:"Knowledge",assistants:"Assistants",models:"Models",settings:"Settings & backup",wizard:"Setup wizard",quality:"Quality & evaluation",operations:"Operations & website"}[view];
}
document.querySelectorAll("[data-view]").forEach(el => el.addEventListener("click", async () => {
  showView(el.dataset.view);
  try {
    if(el.dataset.view === "models") {await refreshModels();await refreshProfiles();}
    if(el.dataset.view === "wizard") await refreshWizard();
    if(el.dataset.view === "settings" && state.user.role === "admin") await refreshUsers();
  } catch(e) { notify(e.message); }
}));
function renderConversations() {
  $("conversation-list").replaceChildren();
  state.conversations.forEach(c => $("conversation-list").append(button(c.title, () => openConversation(c.id),
    "conversation-link" + (state.conversation === c.id ? " selected" : ""))));
}
function renderSources(container, sources) {
  if (!sources.length) return;
  const details = node("details", undefined, "sources");
  details.append(node("summary", sources.length + " source passages"));
  sources.forEach(source => {
    const card = node("div", undefined, "source-card");
    const link = node("a", "[" + source.id + "] " + source.name + " · " + (source.location || "page " + source.page));
    link.href = "/api/documents/" + source.document_id + "/download";
    card.append(button("Preview source", () => openPreview(source)), link, node("p", source.text));
    details.append(card);
  });
  container.append(details);
}
function message(role, content, sources=[], status="complete") {
  const article = node("article", undefined, "message " + role);
  article.append(node("div", role === "user" ? "YOU" : "NELSONICT AI", "message-label"));
  const text = node("div", content, "message-text");
  article.append(text);
  if (sources.length) renderCitedText(text, content, sources);
  renderSources(article, sources);
  if (status !== "complete" && status !== "generating") article.append(node("small", status, "muted"));
  $("messages").append(article);
  return {article,text};
}
async function openConversation(id) {
  if (state.busy) throw new Error("Stop or finish the current response before switching chats.");
  state.conversation = id;
  const convo = state.conversations.find(x => x.id === id);
  $("chat-assistant").value = convo?.assistant_id || "";
  $("chat-assistant").disabled = true;
  const assistant = state.assistants.find(x => x.id === convo?.assistant_id);
  if (assistant?.kb_id) $("chat-kb").value = assistant.kb_id;
  await refreshChatDocuments();
  const rows = await api("/conversations/" + id + "/messages");
  $("messages").replaceChildren();
  rows.forEach(row => {
    const rendered=message(row.role,row.content,row.sources,row.status);
    if(row.role==='assistant' && row.status!=='generating' && typeof addFeedbackControls==='function') addFeedbackControls(rendered.article,row.id);
  });
  renderConversations(); showView("chat");
  $("messages").scrollTop = $("messages").scrollHeight;
}
async function refreshLists() {
  [state.conversations,state.knowledge,state.assistants] = await Promise.all([
    api("/conversations"), api("/knowledge"), api("/assistants")
  ]);
  renderConversations();
  selectOptions("chat-kb",state.knowledge,"Select knowledge");
  selectOptions("assistant-kb",state.knowledge,"No default knowledge");
  selectOptions("chat-assistant",state.assistants,"Nelsonict AI");
  $("knowledge-list").replaceChildren(node("h3","Knowledge bases"));
  if (!state.knowledge.length) $("knowledge-list").append(node("p","Create a knowledge base to get started.","muted"));
  state.knowledge.forEach(k => $("knowledge-list").append(button(k.name + " · " + k.documents + " · " + k.permission, () => chooseKnowledge(k.id),
    "knowledge-link" + (state.kb === k.id ? " selected" : ""))));
  $("assistant-list").replaceChildren();
  state.assistants.forEach(a => {
    const card = node("div",undefined,"card");
    card.append(node("h2",a.name),node("p",a.instructions));
    const kb = state.knowledge.find(k => k.id === a.kb_id);
    card.append(node("small",kb ? kb.name : "No default knowledge","muted"));
    const actions = node("div",undefined,"row");
    actions.append(button("Edit",() => {
      $("assistant-id").value = a.id; $("assistant-name").value = a.name;
      $("assistant-instructions").value = a.instructions; $("assistant-kb").value = a.kb_id || "";
      $("assistant-form-title").textContent = "Edit assistant";
    }),button("Delete",async () => {
      if(!confirm("Delete this assistant? Conversations will remain.")) return;
      await api("/assistants/"+a.id,{method:"DELETE"}); await refreshLists();
    },"quiet danger"));
    card.append(actions); $("assistant-list").append(card);
  });
}
async function chooseKnowledge(id) {
  state.kb=id; $("kb-title").textContent=state.knowledge.find(x=>x.id===id)?.name || "Knowledge base";
  await refreshDocuments();
  await refreshSharing();
}
async function refreshDocuments() {
  if(!state.kb) return;
  const permission=state.knowledge.find(x=>x.id===state.kb)?.permission;
  $("pdf-files").disabled=permission==="reader";
  $("delete-kb").hidden=permission!=="owner";
  const docs=await api("/knowledge/"+state.kb+"/documents");
  $("document-list").replaceChildren();
  if(!docs.length) $("document-list").append(node("p","No documents yet. Choose files above to build this knowledge base.","muted"));
  docs.forEach(d=>{
    const card=node("div",undefined,"card document");
    card.append(node("h3",d.name),node("span",d.status+" · "+d.progress+"%","badge"),
      node("p",(d.format==="pdf" ? d.pages+" pages" : d.format.toUpperCase())+" · "+(d.size/1048576).toFixed(1)+" MB","muted"));
    if(d.error) card.append(node("p",d.error,"error-text"));
    const row=node("div",undefined,"row");
    const download=node("a","Download","button quiet"); download.href="/api/documents/"+d.id+"/download";
    row.append(download,button("Preview",()=>openPreview({document_id:d.id,name:d.name,page:1,format:d.format})));
    if(permission!=="reader") row.append(button("Reindex",async()=>{await api("/documents/"+d.id+"/reindex",{method:"POST"});await refreshDocuments();}));
    if(permission==="owner") row.append(button("Delete",async()=>{
        if(!confirm("Delete this document and its searchable passages?")) return;
        await api("/documents/"+d.id,{method:"DELETE"});await refreshDocuments();await refreshLists();
      },"quiet danger"));
    card.append(row); $("document-list").append(card);
  });
}
async function refreshStatus() {
  const s=await api("/status"), model=s.model;
  modelSafety.serverLoading=Boolean(model.loading);renderModelResources();
  $("model-pill").textContent=model.loading ? "Loading model…" : model.loaded ? model.config.filename : "Model not loaded";
  $("model-pill").classList.toggle("online",model.loaded);
  $("search-pill").textContent=s.search==="hybrid"?"Hybrid search":"Keyword search";
  $("worker-state").textContent=(s.worker_online?"PDF worker online":"PDF worker offline — start the worker")+
    " · "+s.upload_limit_mb+" MB per PDF";
  $("system-status").textContent="Search: "+s.search+". PDF worker: "+(s.worker_online?"online":"offline")+
    ". Document allowance: "+s.storage_limit_mb+" MB per user.";
}
async function refreshModels() {
  const version=++modelSafety.filesVersion;
  modelSafety.filesRefreshing=true;invalidateModelResources();
  try {
    const result=await api("/models");
    if(version!==modelSafety.filesVersion)return;
    const previous=$("model-file").value;
    $("model-file").replaceChildren(new Option("Select a GGUF file",""));
    result.models.forEach(m=>{
      const option=new Option(m.filename+" · "+formatMemory(m.bytes),m.filename);
      option.dataset.label=option.textContent;$("model-file").add(option);
    });
    $("model-file").value=previous || (!modelSafety.initialized ? result.config?.filename || "" : "");
    if(result.config && !modelSafety.initialized) {
      for(const [id,key] of [["context","context"],["threads","threads"],["gpu","gpu_layers"],["tokens","max_tokens"],["temperature","temperature"],["format","chat_format"]]) {
        $("model-"+id).value=result.config[key] ?? "";
      }
    }
    modelSafety.initialized=true;modelSafety.serverLoading=Boolean(result.loading);
    $("model-details").textContent=result.loading?"Loading model…":result.error?"Load error: "+result.error:
      result.loaded?"Loaded: "+result.config.filename+(result.busy?" · responding":" · ready"):"No model loaded.";
  } catch(error) {
    if(version===modelSafety.filesVersion)modelSafety.error="Could not refresh model files: "+error.message;
    throw error;
  } finally {
    if(version===modelSafety.filesVersion){modelSafety.filesRefreshing=false;renderModelResources();}
  }
  if(version===modelSafety.filesVersion)await refreshModelResources();
}
function formatMemory(bytes) {
  return typeof bytes==="number" && Number.isFinite(bytes) ? (bytes/1073741824).toFixed(2)+" GiB" : "unavailable";
}
function freshModelResources() {
  return !modelSafety.pending && !modelSafety.filesRefreshing && modelSafety.report &&
    modelSafety.context===Number($("model-context").value) && Date.now()-modelSafety.checkedAt<MODEL_RESOURCE_MAX_AGE;
}
function selectedModelAssessment() {
  return freshModelResources() ? modelSafety.report.models.find(m=>m.filename===$("model-file").value) : null;
}
function renderModelResources() {
  const fresh=freshModelResources(),report=modelSafety.report,assessment=selectedModelAssessment();
  const working=modelSafety.loading || modelSafety.serverLoading;
  $("load-model").disabled=working || !assessment?.allowed;
  $("recommend-model").disabled=working || !fresh || !report.recommended?.filename;
  $("refresh-model-resources").disabled=modelSafety.pending || modelSafety.filesRefreshing || working;
  for(const option of $("model-file").options) {
    if(!option.value)continue;
    const fit=fresh ? report.models.find(m=>m.filename===option.value) : null;
    option.disabled=false;
    option.textContent=(option.dataset.label || option.value)+(fit && !fit.allowed ? " · exceeds current budget" : "");
  }
  $("model-resource-memory").textContent=report ? "RAM: "+formatMemory(report.ram_available)+" available / "+formatMemory(report.ram_total)+" total. Reserved for other work: "+formatMemory(report.reserve_bytes)+". Model budget: "+formatMemory(report.budget_bytes)+"." : "Available RAM has not been checked for these settings.";
  let text="Select a GGUF file to see its estimated memory use.";
  if(modelSafety.pending || modelSafety.filesRefreshing)text="Checking this computer and model memory requirements…";
  else if(modelSafety.error)text=modelSafety.error+" Loading is blocked until a resource check succeeds.";
  else if(!fresh)text="Resource check required. Recheck resources before loading.";
  else if(assessment)text="Estimated memory: "+formatMemory(assessment.estimated_bytes)+" at "+assessment.context+" context tokens. "+(assessment.allowed ? "Fits the current RAM budget. " : "Cannot load this model. ")+(assessment.reason || "");
  else if($("model-file").value)text="This file has no current resource assessment. Refresh files before loading.";
  $("model-resource-assessment").textContent=text;
  $("model-resource-assessment").classList.toggle("error-text",Boolean(modelSafety.error || (fresh && assessment && !assessment.allowed)));
  $("model-resource-guidance").textContent=fresh && !report.recommended?.filename ?
    (report.models.length ? "No local model fits the current RAM budget. " : "No local GGUF models found. ")+"Import or download a smaller GGUF, close other apps, or unload the current model and recheck resources." :
    report?.note || "Memory checks include context and keep RAM available for other work. The server checks again before loading.";
  $("model-resource-list").replaceChildren();
  if(fresh)report.models.forEach(model=>$("model-resource-list").append(node("p",model.filename+" · "+formatMemory(model.estimated_bytes)+" estimated · "+(model.allowed ? "Fits. " : "Unavailable. ")+(model.reason || ""))));
  else $("model-resource-list").append(node("p","A current resource check is required to assess local models."));
}
function invalidateModelResources() {
  ++modelSafety.version;clearTimeout(modelSafety.timer);clearTimeout(modelSafety.expiry);
  modelSafety.report=null;modelSafety.checkedAt=0;modelSafety.error="";modelSafety.pending=false;
  renderModelResources();
}
async function refreshModelResources() {
  invalidateModelResources();
  const context=Number($("model-context").value),version=modelSafety.version;
  if(!$("model-context").checkValidity() || !Number.isInteger(context)) {
    modelSafety.error="Enter a whole context value between 1024 and 32768 tokens.";renderModelResources();return null;
  }
  if(modelSafety.filesRefreshing)return null;
  modelSafety.pending=true;renderModelResources();
  try {
    const report=await api("/models/resources?context="+context);
    if(version!==modelSafety.version || context!==Number($("model-context").value))return null;
    if(!Array.isArray(report.models))throw new Error("Resource information is unavailable.");
    modelSafety.report=report;modelSafety.context=context;modelSafety.checkedAt=Date.now();
    modelSafety.expiry=setTimeout(()=>{
      renderModelResources();
      if(state.user?.role==="admin" && !$("view-models").hidden)refreshModelResources();
    },MODEL_RESOURCE_MAX_AGE);
    return report;
  } catch(error) {
    if(version===modelSafety.version)modelSafety.error="Could not check system resources: "+error.message;
    return null;
  } finally {
    if(version===modelSafety.version){modelSafety.pending=false;renderModelResources();}
  }
}
async function refreshUsers() {
  const users=await api("/users"); $("user-list").replaceChildren();
  users.forEach(u=>{
    const row=node("div",undefined,"user-row");
    row.append(node("span",u.username+" · "+u.role+(u.disabled?" · disabled":"")));
    row.append(button("Reset password",()=>{
      passwordResetUser=u;$("reset-password-user").textContent="Set a new password for "+u.username+". Existing sessions will be signed out.";
      $("reset-password-form").reset();$("reset-password-dialog").showModal();$("reset-password").focus();
    }));
    if(u.id!==state.user.id) row.append(button(u.disabled?"Enable":"Disable",async()=>{
      await api("/users/"+u.id+(u.disabled?"/enable":"/disable"),{method:"POST"});await refreshUsers();
    }));
    $("user-list").append(row);
  });
}
async function enter(user) {
  state.user=user; state.csrf=user.csrf;
  $("auth").hidden=true; $("workspace").hidden=false; $("account").textContent=user.username+" · "+user.role;
  document.querySelectorAll("[data-admin]").forEach(el=>el.hidden=user.role!=="admin");
  await refreshLists(); await refreshStatus();
  if (user.role === "admin") { const report=await refreshWizard(); if(!report.wizard_complete) showView("wizard"); }
}
on("auth-form","submit",async e=>{
  e.preventDefault(); $("sign-in").disabled=true;
  try {
    const credentials={username:$("username").value,password:$("password").value};
    if(state.setup) {await api("/setup",{method:"POST",body:{...credentials,setup_token:$("setup-token").value}});state.setup=false;}
    if(state.recovering) {
      await api("/recover",{method:"POST",body:{...credentials,recovery_token:$("recovery-token").value}});
      state.recovering=false;$("recovery-token").value="";$("recovery-token-label").hidden=true;
      $("auth-title").textContent="Sign in";$("auth-description").textContent="Continue to your private AI workspace.";
      $("sign-in").textContent="Sign in →";$("recovery-toggle").textContent="Use recovery token";
      $("password").value="";notify("Password reset. Sign in with your new password.");return;
    }
    const user=await api("/login",{method:"POST",body:credentials});
    $("password").value=""; await enter(user);
  } finally { $("sign-in").disabled=false; }
});
on("recovery-toggle","click",()=>{
  if(state.setup)return;
  state.recovering=!state.recovering;$("recovery-token-label").hidden=!state.recovering;
  $("recovery-token").required=state.recovering;
  $("auth-title").textContent=state.recovering?"Recover administrator":"Sign in";
  $("auth-description").textContent=state.recovering?"Reset an administrator password with a local recovery token.":"Continue to your private AI workspace.";
  $("sign-in").textContent=state.recovering?"Reset password →":"Sign in →";
  $("recovery-toggle").textContent=state.recovering?"Use password sign in":"Use recovery token";
  if(state.recovering)$("recovery-token").focus();
});
on("logout","click",async()=>{await api("/logout",{method:"POST"});location.reload();});
on("new-chat","click",()=>{
  if(state.busy) throw new Error("Stop the active response before starting another chat.");
  state.conversation=null; $("chat-assistant").disabled=false; $("messages").replaceChildren();
  $("messages").append(node("div","Start a new conversation. Select an assistant and answer mode above.","empty-chat"));
  renderConversations();showView("chat");$("question").focus();
});
document.querySelectorAll("[data-prompt]").forEach(el=>el.addEventListener("click",()=>{
  $("question").value=el.dataset.prompt;$("question").focus();
}));
on("chat-mode","change",()=>{
  $("chat-kb").disabled=$("chat-mode").value==="general";
  $("chat-hint").textContent=$("chat-mode").value==="general"?"Answers use the model’s general knowledge.":"Answers use passages from the selected knowledge base.";
});
on("chat-form","submit",async e=>{
  e.preventDefault(); if(state.busy) return;
  const content=$("question").value.trim(); if(!content) return;
  const mode=$("chat-mode").value, kb_id=Number($("chat-kb").value)||null;
  const assistant=state.assistants.find(x=>x.id===Number($("chat-assistant").value));
  if(mode==="documents" && !kb_id && !assistant?.kb_id) throw new Error("Select a knowledge base first.");
  state.busy=true; $("chat-form").setAttribute("aria-busy","true");$("send").disabled=true;$("send").textContent="Working…";$("stop").hidden=false;setChatStatus("Sending your request…");
  let finalStatus="";
  try {
    if(!state.conversation) {
      setChatStatus("Creating conversation…");
      const created=await api("/conversations",{method:"POST",body:{title:content.slice(0,80),assistant_id:assistant?.id||null}});
      state.conversation=created.id; $("messages").replaceChildren(); $("chat-assistant").disabled=true;
      await refreshLists();
    }
    setChatStatus("Request received. Waiting for the model…");
    const response=await fetch("/api/conversations/"+state.conversation+"/chat",{
      method:"POST",headers:{"Content-Type":"application/json","X-Nelson-Client":"web","X-CSRF-Token":state.csrf},
      body:JSON.stringify({content,mode,kb_id,task:$("chat-task").value,document_ids:Array.from($("chat-documents").selectedOptions).map(x=>Number(x.value))})
    });
    if(!response.ok) throw new Error(errorText(await response.json()));
    setChatStatus("Preparing response…");
    $("question").value=""; message("user",content);
    const output=message("assistant",""); const reader=response.body.getReader(), decoder=new TextDecoder();
    let buffer="";
    while(true) {
      const {value,done}=await reader.read();
      if(done) break;
      buffer+=decoder.decode(value,{stream:true});
      let end;
      while((end=buffer.indexOf("\n\n"))>=0) {
        const line=buffer.slice(0,end);buffer=buffer.slice(end+2);
        if(!line.startsWith("data: ")) continue;
        const event=JSON.parse(line.slice(6));
        if(event.type==="token") {output.text.textContent+=event.text;setChatStatus("Writing response…");}
        if(event.type==="sources") renderSources(output.article,event.sources);
        if(event.type==="error") {notify(event.message);finalStatus="Response interrupted.";setChatStatus(finalStatus);}
        if(event.type==="queue" || event.type==="progress") {$("chat-hint").textContent=event.message;setChatStatus(event.message);}
        if(event.type==="done") finalStatus=event.status==="complete"?"Response complete.":event.status==="cancelled"?"Response stopped.":"Response interrupted.";
      }
      $("messages").scrollTop=$("messages").scrollHeight;
    }
  } catch(error) {
    finalStatus="Request failed: "+error.message;setChatStatus(finalStatus);throw error;
  } finally {
    state.busy=false;$("chat-form").setAttribute("aria-busy","false");$("send").disabled=false;$("send").textContent="Send ↑";$("stop").hidden=true;
    $("chat-hint").textContent=mode==="general"?"Answers use the model’s general knowledge.":"Answers use passages from the selected knowledge base.";
    setChatStatus(finalStatus||"Response complete.",3500);
    if(state.conversation) await openConversation(state.conversation);
  }
});
on("stop","click",async()=>{
  if(state.conversation) {setChatStatus("Stopping response…");await api("/conversations/"+state.conversation+"/stop",{method:"POST"});}
});
on("rename-chat","click",async()=>{
  if(!state.conversation) return;
  const name=prompt("Conversation name"); if(!name?.trim()) return;
  await api("/conversations/"+state.conversation,{method:"PUT",body:{name:name.trim()}});await refreshLists();
});
on("export-chat","click",()=>{if(state.conversation) location.href="/api/conversations/"+state.conversation+"/export";});
on("delete-chat","click",async()=>{
  if(!state.conversation||!confirm("Delete this conversation permanently?")) return;
  await api("/conversations/"+state.conversation,{method:"DELETE"});state.conversation=null;
  $("messages").replaceChildren();$("chat-assistant").disabled=false;await refreshLists();
});
on("new-kb","click",()=>{
  $("knowledge-base-form").reset();$("knowledge-base-dialog").showModal();$("knowledge-base-name").focus();
});
on("knowledge-base-close","click",()=>$("knowledge-base-dialog").close());
on("knowledge-base-form","submit",async e=>{
  e.preventDefault();
  const k=await api("/knowledge",{method:"POST",body:{name:$("knowledge-base-name").value.trim()}});
  $("knowledge-base-dialog").close();await refreshLists();await chooseKnowledge(k.id);notify("Knowledge base created.");
});
on("delete-kb","click",async()=>{
  if(!state.kb||!confirm("Delete this knowledge base and all its PDFs?")) return;
  await api("/knowledge/"+state.kb,{method:"DELETE"});state.kb=null;
  $("kb-title").textContent="Select a knowledge base";$("document-list").replaceChildren();await refreshLists();
});
on("upload-format","change",()=>{
  const formats={
    all:[".pdf,.docx,.txt,.md,.csv,.xlsx","documents","Choose Word, CSV, PDF, text, Markdown, or Excel files. Wait for Ready before asking questions."],
    docx:[".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document","Word documents","Upload .docx files. Main paragraphs and top-level tables are indexed; convert older .doc files to .docx first."],
    csv:[".csv,text/csv","CSV tables","Upload UTF-8 CSV files with a header row. Each row is indexed with its column labels; sources identify CSV row numbers."],
    pdf:[".pdf,application/pdf","PDF documents","Upload unlocked PDFs. Scanned pages need OCR configured by your administrator."],
    text:[".txt,.md,text/plain,text/markdown","text documents","Save text and Markdown as UTF-8. Sources identify line ranges."],
    xlsx:[".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","Excel workbooks","Save a recalculated .xlsx workbook first. Formula results use cached values; sources identify sheets and rows."]
  };
  const [accept,label,help]=formats[$("upload-format").value]||formats.all;
  $("pdf-files").accept=accept;$("pdf-files").value="";
  $("upload-label").textContent="＋ Choose "+label;$("upload-help").textContent=help;
});
on("pdf-files","change",async()=>{
  if(!state.kb) {$("pdf-files").value="";throw new Error("Create or select a knowledge base first.");}
  const files=Array.from($("pdf-files").files);$("pdf-files").disabled=true;
  try {
    for(const file of files) {
      notify("Uploading "+file.name+"…");
      await api("/knowledge/"+state.kb+"/documents",{method:"POST",headers:{"Content-Type":file.type||"application/octet-stream","X-Filename":encodeURIComponent(file.name)},body:file});
    }
    notify("Documents queued for indexing.");await refreshDocuments();await refreshLists();
  } finally {$("pdf-files").disabled=false;$("pdf-files").value="";}
});
on("assistant-form","submit",async e=>{
  e.preventDefault();const id=$("assistant-id").value;
  await api("/assistants"+(id?"/"+id:""),{method:id?"PUT":"POST",body:{
    name:$("assistant-name").value,instructions:$("assistant-instructions").value,kb_id:Number($("assistant-kb").value)||null
  }});
  $("assistant-form").reset();$("assistant-id").value="";$("assistant-form-title").textContent="Create assistant";
  await refreshLists();notify("Assistant saved.");
});
on("assistant-reset","click",()=>{$("assistant-form").reset();$("assistant-id").value="";$("assistant-form-title").textContent="Create assistant";});
on("refresh-models","click",refreshModels);
on("refresh-model-resources","click",refreshModelResources);
on("model-file","change",refreshModelResources);
on("model-context","input",()=>{
  invalidateModelResources();modelSafety.pending=true;renderModelResources();
  modelSafety.timer=setTimeout(refreshModelResources,300);
});
on("model-context","change",refreshModelResources);
on("recommend-model","click",async()=>{
  const report=await refreshModelResources(),recommended=report?.recommended;
  if(!recommended?.filename)return;
  if(!Array.from($("model-file").options).some(option=>option.value===recommended.filename)) {
    await refreshModels();notify("Model files changed. Choose a model for this system again.");return;
  }
  $("model-file").value=recommended.filename;applySuggestedCpuSettings(recommended);
  await refreshModelResources();
  notify(selectedModelAssessment()?.allowed ? "Suitable model and CPU settings selected. Review the form, then click Load model to switch." : "Available resources changed. Review the memory check before loading.");
});
on("model-form","submit",async e=>{
  e.preventDefault();
  if(modelSafety.loading || modelSafety.serverLoading)return;
  if(!selectedModelAssessment()?.allowed)throw new Error("Select a model that fits a current resource check before loading.");
  modelSafety.loading=true;renderModelResources();
  try {
    await refreshModelResources();
    if(!selectedModelAssessment()?.allowed)throw new Error("This model cannot load with the current resources. Review the memory check.");
    notify("Loading model. Large files can take a few minutes.");
    await api("/models/load",{method:"POST",body:modelFormConfig()});
    notify("Model loaded.");await refreshModels();await refreshStatus();await refreshWizard();
  } finally {modelSafety.loading=false;renderModelResources();}
});
on("unload-model","click",async()=>{await api("/models/unload",{method:"POST"});await refreshModels();await refreshStatus();});
on("user-form","submit",async e=>{
  e.preventDefault();await api("/users",{method:"POST",body:{username:$("new-username").value,password:$("new-password").value,role:$("new-role").value}});
  $("user-form").reset();await refreshUsers();notify("User created.");
});
on("reset-password-close","click",()=>$("reset-password-dialog").close());
on("reset-password-form","submit",async e=>{
  e.preventDefault();
  if(!passwordResetUser)throw new Error("Choose a user first.");
  const password=$("reset-password").value;
  if(password!==$("reset-password-confirm").value)throw new Error("Passwords do not match.");
  const resetSelf=passwordResetUser.id===state.user.id;
  await api("/users/"+passwordResetUser.id+"/reset-password",{method:"POST",body:{password}});
  $("reset-password-dialog").close();passwordResetUser=null;
  if(resetSelf){location.reload();return;}
  await refreshUsers();notify("Password reset and existing sessions signed out.");
});
on("theme-toggle","click",()=>{
  document.body.classList.toggle("dark");localStorage.setItem("nelson-theme",document.body.classList.contains("dark")?"dark":"light");
});
if(localStorage.getItem("nelson-theme")==="dark") document.body.classList.add("dark");
$("recovery-token").required=false;
(async()=>{
  try {
    state.setup=(await api("/setup")).required;
    if(state.setup) {
      $("setup-label").hidden=false;$("setup-token").required=true;
      $("recovery-toggle").hidden=true;
      $("auth-title").textContent="Create your administrator";
      $("auth-description").textContent="Use the server’s setup token to claim this installation.";
      $("sign-in").textContent="Create administrator →";
    } else {
      try {await enter(await api("/me"));} catch { /* Sign-in form remains available. */ }
    }
  } catch(e) {notify("Unable to reach Nelsonict AI: "+e.message);}
})();
setInterval(async()=>{
  if(!state.user) return;
  try {await refreshStatus();if(!$("view-knowledge").hidden) await refreshDocuments();} catch { /* Retry next interval. */ }
},5000);

// Nelsonict AI 1.1: guided setup, model imports, profiles and team collections.
let modelProfiles=[], machineReport=null, modelUpload=null, previewSource=null, previewURL=null;
function modelFormConfig() {
  return {filename:$("model-file").value,context:Number($("model-context").value),threads:Number($("model-threads").value),
    gpu_layers:Number($("model-gpu").value),max_tokens:Number($("model-tokens").value),
    temperature:Number($("model-temperature").value),chat_format:$("model-format").value||null};
}
function applySuggestedCpuSettings(recommended) {
  $("model-context").value=recommended.context;$("model-threads").value=recommended.threads;$("model-gpu").value=0;
  const responseLimit=Math.max(64,Math.floor(recommended.context/2));
  const current=Number($("model-tokens").value);
  $("model-tokens").value=Math.min(Number.isInteger(current) && current>=64 ? current : 512,responseLimit);
}
async function refreshProfiles() {
  modelProfiles=await api('/model-profiles');
  $("profile-list").replaceChildren(new Option('Select a saved profile',''));
  modelProfiles.forEach(p=>$("profile-list").add(new Option(p.name,p.id)));
}
async function refreshWizard() {
  machineReport=await api('/system/check');
  const r=machineReport, box=$("machine-report");box.replaceChildren();
  box.append(node('p',r.os+' · '+r.cpu+' · '+r.cores+' logical cores'));
  box.append(node('p',(r.ram_available/1073741824).toFixed(1)+' GB available / '+(r.ram_total/1073741824).toFixed(1)+' GB RAM'));
  box.append(node('p',(r.disk_free/1073741824).toFixed(1)+' GB free model storage · '+(r.models_writable?'writable':'folder needs write permission')));
  box.append(node('p',r.nvidia_devices.length?'NVIDIA: '+r.nvidia_devices.join('; '):r.apple_silicon?'Apple Silicon detected; Metal requires a compatible inference build.':'No NVIDIA device reported. CPU mode is the starting option.'));
  const list=node('ul');
  Object.entries(r.dependencies).forEach(([name,available])=>list.append(node('li',(available?'✓ ':'○ ')+name+(available?' installed':' missing / optional'))));
  box.append(node('p','Inference GPU backend: '+(r.inference_backend.gpu_offload?'available':'not detected')+(r.inference_backend.error?' · '+r.inference_backend.error:'')));
  const help=node('details');help.append(node('summary','Dependency installation guidance'));
  Object.entries(r.installation_help).forEach(([name,command])=>help.append(node('p',name+': '+command)));box.append(help);
  box.append(list,node('p','Document worker: '+(r.worker_online?'online':'offline — start the worker')),node('p',r.model_guidance));
  return r;
}
on('wizard-refresh','click',refreshWizard);
on('wizard-models','click',async()=>{showView('models');await refreshModels();await refreshProfiles();});
on('wizard-knowledge','click',()=>showView('knowledge'));
on('apply-recommendations','click',async()=>{
  if(!machineReport)return;
  await refreshModels();
  applySuggestedCpuSettings(machineReport.recommended);
  await refreshModelResources();
  showView('models');notify('Suggested CPU settings applied. Select a model, then load it.');
});
on('wizard-test','click',async()=>{
  $("wizard-test").disabled=true;$("wizard-test-result").textContent='Generating locally…';
  try { const result=await api('/system/model-test',{method:'POST'});$("wizard-test-result").textContent=result.response+'\n\n'+result.note; }
  finally {$("wizard-test").disabled=false;}
});
on('wizard-complete','click',async()=>{await api('/system/complete',{method:'POST'});notify('Setup complete.');showView('chat');});
on('save-profile','click',async()=>{
  await api('/model-profiles',{method:'POST',body:{name:$("profile-name").value,config:modelFormConfig()}});
  await refreshProfiles();notify('Profile saved.');
});
on('use-profile','click',async()=>{
  const p=modelProfiles.find(x=>x.id===Number($("profile-list").value));if(!p)return;
  $("model-file").value=p.config.filename;
  for(const [id,key] of [['context','context'],['threads','threads'],['gpu','gpu_layers'],['tokens','max_tokens'],['temperature','temperature'],['format','chat_format']]) $("model-"+id).value=p.config[key]??'';
  await refreshModelResources();
  notify('Profile applied to the form. Click Load model to activate it.');
});
on('delete-profile','click',async()=>{
  const id=$("profile-list").value;if(!id||!confirm('Delete this saved profile?'))return;
  await api('/model-profiles/'+id,{method:'DELETE'});await refreshProfiles();
});
on('inspect-model','click',async()=>{
  $("model-inspection").textContent='Reading GGUF metadata and calculating SHA-256…';
  const r=await api('/models/inspect?filename='+encodeURIComponent($("model-file").value));
  $("model-inspection").textContent=JSON.stringify(r,null,2);
});
on('model-import-form','submit',async e=>{
  e.preventDefault();if(modelUpload)return;
  const file=$("model-import-file").files[0];if(!file)return;
  $("import-model").disabled=true;$("model-upload-progress").value=0;$("import-status").textContent='Preparing import…';
  try {
    const result=await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();modelUpload=xhr;
      xhr.open('POST','/api/models/import');
      xhr.setRequestHeader('X-Nelson-Client','web');xhr.setRequestHeader('X-CSRF-Token',state.csrf);
      xhr.setRequestHeader('X-Filename',encodeURIComponent(file.name));xhr.setRequestHeader('Content-Type','application/octet-stream');
      if($("model-sha").value)xhr.setRequestHeader('X-SHA256',$("model-sha").value.trim());
      xhr.upload.onprogress=event=>{if(event.lengthComputable){const value=Math.round(event.loaded/event.total*100);$("model-upload-progress").value=value;$("import-status").textContent=value===100?'Upload sent. Validating file…':'Uploading '+value+'%';}};
      xhr.upload.onload=()=>{$("model-upload-progress").value=100;$("import-status").textContent='Upload complete. Saving, checking the checksum, and reading GGUF metadata…';};
      xhr.onerror=()=>reject(new Error('Upload failed. Check the connection and proxy upload limit.'));
      xhr.onabort=()=>reject(new Error('Upload cancelled.'));
      xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch{reject(new Error('Server rejected upload; check proxy limits.'));return;}if(xhr.status>=200&&xhr.status<300)resolve(data);else reject(new Error(errorText(data)));};
      xhr.send(file);
    });
    await refreshModels();$("model-file").value=result.filename;await refreshModelResources();
    const assessment=selectedModelAssessment();
    const guidance=assessment?.allowed?'Selected in the model form. Review the settings, then click Load model.':
      'Installed but cannot load with the current settings. '+(assessment?.reason||'Recheck available RAM.');
    $("import-status").textContent='Imported '+result.filename+'. SHA-256: '+result.sha256+(result.checksum_verified?' · matches expected checksum. ':' · no expected checksum supplied. ')+guidance;
    notify('Model imported. '+guidance);await refreshWizard();
  } catch(error) {
    $("import-status").textContent='Import failed: '+error.message;
    throw error;
  } finally {modelUpload=null;$("import-model").disabled=false;}
});
on('cancel-import','click',()=>{if(modelUpload)modelUpload.abort();});
async function refreshSharing() {
  const kb=state.knowledge.find(x=>x.id===state.kb);
  $("sharing-card").hidden=!kb||kb.permission!=='owner';
  if($("sharing-card").hidden)return;
  const members=await api('/knowledge/'+state.kb+'/members');$("member-list").replaceChildren();
  members.forEach(m=>{
    const row=node('div',undefined,'user-row');row.append(node('span',m.username+' · '+m.permission),button('Revoke',async()=>{
      if(!confirm('Revoke access for '+m.username+'? Their historical chat excerpts remain.'))return;
      await api('/knowledge/'+state.kb+'/members/'+m.id,{method:'DELETE'});await refreshSharing();
    }));$("member-list").append(row);
  });
}
on('share-form','submit',async e=>{
  e.preventDefault();await api('/knowledge/'+state.kb+'/members',{method:'POST',body:{username:$("share-username").value,permission:$("share-permission").value}});
  await refreshSharing();notify('Collection access updated.');
});
async function refreshChatDocuments() {
  const kb=Number($("chat-kb").value)||state.assistants.find(x=>x.id===Number($("chat-assistant").value))?.kb_id;
  const selected=new Set(Array.from($("chat-documents").selectedOptions).map(x=>x.value));
  $("chat-documents").replaceChildren();if(!kb)return;
  const docs=await api('/knowledge/'+kb+'/documents');
  docs.filter(x=>x.status==='ready').forEach(d=>{const option=new Option(d.name,d.id);option.selected=selected.has(String(d.id));$("chat-documents").add(option);});
}
on('chat-kb','change',refreshChatDocuments);
on('chat-assistant','change',refreshChatDocuments);
on('chat-task','change',()=>{
  if($("chat-task").value!=='question'){$("chat-mode").value='documents';$("chat-kb").disabled=false;}
  $("chat-hint").textContent=$("chat-task").value==='question'?'Follow-up questions use earlier questions for context; sources are retrieved again.':'Select documents above. All indexed passages are processed; large analyses can take several minutes.';
});
function renderCitedText(element,text,sources) {
  const pattern=/\[(S\d+)\]/g;let cursor=0;let match;element.replaceChildren();
  while((match=pattern.exec(text))){element.append(document.createTextNode(text.slice(cursor,match.index)));
    const source=sources.find(x=>x.id===match[1]);
    element.append(source?button(match[0],()=>openPreview(source),'citation'):document.createTextNode(match[0]));cursor=pattern.lastIndex;}
  element.append(document.createTextNode(text.slice(cursor)));
}
async function openPreview(source) {
  previewSource=source;$("preview-title").textContent=source.name;$("preview-page").value=source.page||1;
  $("preview-download").href='/api/documents/'+source.document_id+'/download';
  if(!$("source-preview").open)$("source-preview").showModal();await loadPreview();
}
async function loadPreview() {
  if(!previewSource)return;const box=$("preview-content");box.replaceChildren(node('p','Loading source…'));
  if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null;}
  const r=await fetch('/api/documents/'+previewSource.document_id+'/preview?page='+Number($("preview-page").value));
  if(!r.ok){const error=await r.json();box.replaceChildren(node('p',errorText(error)));return;}
  box.replaceChildren();
  if(r.headers.get('content-type').includes('image/')){previewURL=URL.createObjectURL(await r.blob());const img=node('img');img.src=previewURL;img.alt=previewSource.name+' page '+$("preview-page").value;box.append(img);}
  else {const data=await r.json();box.append(node('h3',data.location),node('pre',data.text,'message-text'));}
}
on('preview-go','click',loadPreview);
on('close-preview','click',()=>$("source-preview").close());
on('source-preview','close',()=>{if(previewURL)URL.revokeObjectURL(previewURL);previewURL=null;});
