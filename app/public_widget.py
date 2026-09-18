"""Anonymous widget restricted to explicitly approved public-document snapshots."""
import asyncio
import json
import secrets
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from . import db
from .inference import runtime
from .request_queue import scheduler
from .retrieval import search
from .security import administrator, rate_limit
from .quality import RULES

router=APIRouter()


class Site(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    origins: list[str] = Field(min_length=1,max_length=10)
    @field_validator('origins')
    @classmethod
    def validate_origins(cls, values):
        result=[]
        for value in values:
            p=urlsplit(value)
            if p.scheme!='https' or not p.hostname or p.username or p.password or p.path not in ('','/') or p.query or p.fragment or '*' in value:
                raise ValueError('Use exact HTTPS origins, for example https://nelsonict.com.ng.')
            if any(ch.isspace() or ch in "'\";\\" for ch in value):
                raise ValueError('Invalid origin.')
            result.append(p.scheme+'://'+p.netloc)
        return sorted(set(result))


def owner_site(identifier,user):
    row=db.one('SELECT * FROM public_sites WHERE id=? AND owner_id=?',(identifier,user['id']))
    if not row:
        raise HTTPException(404,'Public site not found.')
    return row


def live_site(identifier):
    row=db.one('SELECT s.* FROM public_sites s JOIN users u ON u.id=s.owner_id WHERE s.id=? AND s.enabled=1 AND u.disabled=0',(identifier,))
    if not row:
        raise HTTPException(404,'Public assistant unavailable.')
    return row


@router.get('/api/public-sites')
def sites(user=Depends(administrator)):
    rows=db.rows('SELECT * FROM public_sites WHERE owner_id=?',(user['id'],))
    for row in rows:
        row['origins']=json.loads(row['origins'])
        row['approved']=db.rows('SELECT document_id,sha256 FROM public_documents WHERE site_id=?',(row['id'],))
    return rows


@router.post('/api/public-sites',status_code=201)
def create(body: Site,user=Depends(administrator)):
    with db.connect() as conn:
        kb=conn.execute('INSERT INTO knowledge_bases(user_id,name) VALUES(?,?)',(user['id'],'Public · '+body.name)).lastrowid
        identifier=conn.execute('INSERT INTO public_sites(owner_id,kb_id,name,origins) VALUES(?,?,?,?)',(user['id'],kb,body.name,json.dumps(body.origins))).lastrowid
    return {'id':identifier,'kb_id':kb}


class Publish(BaseModel):
    enabled: bool
    document_ids: list[int] = Field(default_factory=list,max_length=100)
    origins: list[str] = Field(min_length=1,max_length=10)
    confirm_public: bool = False


@router.put('/api/public-sites/{identifier}')
def publish(identifier: int,body: Publish,user=Depends(administrator)):
    site=owner_site(identifier,user)
    try:
        origins=Site(name=site['name'],origins=body.origins).origins
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    if body.enabled and (not body.confirm_public or not body.document_ids):
        raise HTTPException(400,'Select ready documents and explicitly approve them for anonymous public access.')
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        documents=[]
        for did in dict.fromkeys(body.document_ids):
            row=conn.execute("SELECT id,sha256 FROM documents WHERE id=? AND kb_id=? AND status='ready'",(did,site['kb_id'])).fetchone()
            if not row:
                raise HTTPException(400,'Only ready documents in this separate public collection can be approved.')
            documents.append(row)
        conn.execute('DELETE FROM public_documents WHERE site_id=?',(identifier,))
        for d in documents:
            conn.execute('INSERT INTO public_documents VALUES(?,?,?)',(identifier,d['id'],d['sha256']))
        conn.execute('UPDATE public_sites SET enabled=?,origins=? WHERE id=?',(int(body.enabled),json.dumps(origins),identifier))
    for entry in scheduler.snapshot()['requests']:
        if entry['key'].startswith(f'public:{identifier}:'):
            scheduler.cancel(entry['key'])
    return {'ok':True}


@router.delete('/api/public-sites/{identifier}')
def delete_site(identifier: int,user=Depends(administrator)):
    owner_site(identifier,user)
    db.execute('DELETE FROM public_sites WHERE id=?',(identifier,))
    for entry in scheduler.snapshot()['requests']:
        if entry['key'].startswith(f'public:{identifier}:'):
            scheduler.cancel(entry['key'])
    return {'ok':True}


@router.get('/widget/{identifier}',response_class=HTMLResponse)
def widget(identifier: int):
    live_site(identifier)
    return HTMLResponse('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nelsonict AI</title><link rel="stylesheet" href="/widget.css"><script defer src="/widget.js"></script></head><body><main><h1>Ask Nelsonict AI</h1><p>Answers from approved public information. Do not enter private information. AI can make mistakes.</p><div id="answers" aria-live="polite"></div><form id="ask"><label for="question">Your question</label><textarea id="question" maxlength="2000" required></textarea><button id="send">Ask</button><button id="stop" type="button" hidden>Cancel</button></form><p id="status" role="status"></p></main></body></html>''')


class PublicQuestion(BaseModel):
    question: str = Field(min_length=1,max_length=2000)


@router.post('/api/public/{identifier}/chat')
async def chat(identifier: int,body: PublicQuestion,request: Request):
    site=live_site(identifier)
    ip=request.client.host if request.client else 'unknown'
    rate_limit(f'public:{identifier}:{ip}',limit=10,window=300)
    token=secrets.token_hex(16)
    try:
        ticket=scheduler.submit(f'public:{identifier}:{token}',0,'public')
    except RuntimeError as exc:
        raise HTTPException(429,str(exc))
    def produce():
        try:
            yield {'type':'request','token':token}
            # Waiting occurs off the event loop. Poll state so the browser receives positions.
            import queue, threading
            notifications=queue.Queue()
            def wait():
                try:
                    scheduler.wait(ticket,notifications.put)
                    notifications.put({'type':'ready'})
                except Exception as exc:
                    notifications.put({'type':'error','message':str(exc)[:300]})
            waiter=threading.Thread(target=wait,daemon=True);waiter.start()
            while True:
                try:
                    item=notifications.get(timeout=1)
                except queue.Empty:
                    yield {'type':'heartbeat'}
                    continue
                if item['type']=='ready': break
                yield item
                if item['type']=='error': return
            site_now=live_site(identifier)
            docs=db.rows("SELECT d.id FROM public_documents p JOIN documents d ON d.id=p.document_id WHERE p.site_id=? AND d.kb_id=? AND d.sha256=p.sha256 AND d.status='ready'",(identifier,site_now['kb_id']))
            ids=[d['id'] for d in docs]
            evidence=search(site_now['owner_id'],site_now['kb_id'],body.question,document_ids=ids) if ids else []
            prompt,evidence=runtime.fit(RULES,body.question,[],evidence)
            # Public sources expose approved excerpts only; no private file download links.
            sources=[{k:s[k] for k in ('id','name','location','text')} for s in evidence]
            yield {'type':'sources','sources':sources}
            if not evidence:
                yield {'type':'token','text':'No supporting information was found in the approved public documents. Please contact Nelsonict Services Limited.'}
            else:
                for text in runtime.stream(prompt,ticket.stop):
                    if ticket.stop.is_set(): break
                    yield {'type':'token','text':text}
        except Exception as exc:
            yield {'type':'error','message':str(exc)[:300]}
        finally:
            ticket.stop.set()
            if 'waiter' in locals(): waiter.join(timeout=2)
            scheduler.finish(ticket)
    import queue, threading
    events=queue.Queue(maxsize=64)
    def pump():
        iterator=produce()
        try:
            for event in iterator:
                while not ticket.stop.is_set():
                    try:
                        events.put(event,timeout=0.2)
                        break
                    except queue.Full:
                        pass
                if ticket.stop.is_set(): break
        finally:
            iterator.close()
            while True:
                try:
                    events.put({'type':'done'},timeout=0.2)
                    break
                except queue.Full:
                    try: events.get_nowait()
                    except queue.Empty: pass
    threading.Thread(target=pump,daemon=True).start()
    async def stream():
        try:
            while True:
                try:
                    event=await asyncio.to_thread(events.get,True,1)
                except queue.Empty:
                    if await request.is_disconnected(): break
                    yield ': heartbeat\n\n'
                    continue
                yield 'data: '+json.dumps(event)+'\n\n'
                if event['type']=='done': break
        finally:
            ticket.stop.set()
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})


@router.post('/api/public/{identifier}/cancel/{token}')
def cancel(identifier: int,token: str):
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):
        raise HTTPException(400,'Invalid request token.')
    return {'cancelled':scheduler.cancel(f'public:{identifier}:{token}',0)}
