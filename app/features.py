"""Setup wizard, local model imports/profiles, sharing and source preview APIs."""
import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import time
import threading
from functools import wraps
from pathlib import Path
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import db
from .config import settings
from .inference import runtime
from .request_queue import scheduler
from .security import administrator, current_user, owned, owned_document, knowledge_access
from .schemas import Share, Profile
from .machine import inspect_gguf, system_report

router = APIRouter(prefix='/api')
_preview_lock = threading.Lock()

def serial_preview(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _preview_lock:
            return fn(*args, **kwargs)
    return wrapped



@router.get('/system/check')
def check_system(user=Depends(administrator)):
    report = system_report()
    report['model'] = runtime.status()
    report['worker_online'] = time.time()-db.get_setting('worker_heartbeat',0) < 20
    report['wizard_complete'] = db.get_setting('wizard_complete',False)
    reviewed = db.get_setting('migration_hardware')
    if reviewed:
        report['recommended'].update(reviewed)
    return report


@router.post('/system/complete')
def complete_setup(user=Depends(administrator)):
    if not runtime.model:
        raise HTTPException(409,'Load and test a model before completing setup.')
    if not db.get_setting('model_test_passed',False):
        raise HTTPException(409,'Run the model test first.')
    db.set_setting('wizard_complete',True)
    return {'ok':True}


@router.post('/system/model-test')
def test_model(user=Depends(administrator)):
    try:
        stop = runtime.reserve(-1,user['id'])
    except RuntimeError as exc:
        raise HTTPException(409,str(exc))
    try:
        prompt,_ = runtime.fit('You are a helpful assistant.', 'Reply briefly to confirm that you can respond.',[],[])
        answer = ''.join(runtime.stream(prompt,stop))
        if not answer.strip():
            raise HTTPException(400,'Model returned no visible response. Review chat format and model compatibility.')
        db.set_setting('model_test_passed',True)
        return {'response':answer, 'note':'Successful generation confirms basic loading, not answer accuracy.'}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400,str(exc)[:400])
    finally:
        runtime.release(-1)


@router.post('/models/import',status_code=201)
async def import_model(request: Request,user=Depends(administrator)):
    filename = unquote(request.headers.get('X-Filename',''))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,179}\.gguf',filename,re.IGNORECASE):
        raise HTTPException(400,'Use a simple .gguf filename without directories.')
    expected = request.headers.get('X-SHA256','').lower()
    if expected and not re.fullmatch('[a-f0-9]{64}',expected):
        raise HTTPException(400,'Expected SHA-256 must contain 64 hexadecimal characters.')
    root = settings.models_dir.resolve()
    destination = root / filename
    if destination.exists() or destination.is_symlink():
        raise HTTPException(409,'A file with this name already exists. Existing models are never overwritten.')
    limit = settings.max_model_mb * 1024**2
    try:
        descriptor,temporary = tempfile.mkstemp(prefix='.import-',suffix='.part',dir=root)
    except OSError:
        raise HTTPException(400,'Models directory is not writable. Check host/container folder permissions.')
    digest,total = hashlib.sha256(),0
    try:
        with os.fdopen(descriptor,'wb') as handle:
            async for part in request.stream():
                total += len(part)
                if total > limit:
                    raise HTTPException(413,'Model exceeds the configured import limit.')
                if shutil.disk_usage(root).free < len(part) + 64*1024**2:
                    raise HTTPException(507,'Not enough disk space to import the model.')
                digest.update(part)
                await asyncio.to_thread(handle.write,part)
            await asyncio.to_thread(handle.flush)
            os.fsync(handle.fileno())
        actual = digest.hexdigest()
        if expected and actual != expected:
            raise HTTPException(400,'Checksum mismatch. Import rejected; no model was installed.')
        try:
            info = await asyncio.to_thread(inspect_gguf,temporary)
        except (ValueError,OSError) as exc:
            raise HTTPException(400,str(exc))
        # Hard-link creation is atomic and fails if a concurrent import won the name.
        try:
            os.link(temporary,destination)
            destination.chmod(0o644)
        except FileExistsError:
            raise HTTPException(409,'Another import already installed this filename.')
        db.audit('model_import',user['id'])
        return {'filename':filename,'sha256':actual,'checksum_verified':bool(expected),'inspection':info}
    finally:
        Path(temporary).unlink(missing_ok=True)


@router.get('/models/inspect')
def inspect_model(filename: str, user=Depends(administrator)):
    try:
        path = runtime.path(filename)
        info = inspect_gguf(path)
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            while part := handle.read(1024**2):
                digest.update(part)
        info['sha256'] = digest.hexdigest()
        return info
    except (ValueError,OSError) as exc:
        raise HTTPException(400,str(exc))


@router.get('/model-profiles')
def profiles(user=Depends(administrator)):
    return [{**r,'config':json.loads(r['config'])} for r in db.rows('SELECT * FROM model_profiles ORDER BY name')]


@router.post('/model-profiles',status_code=201)
def save_profile(body: Profile,user=Depends(administrator)):
    try:
        runtime.path(body.config.filename)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    db.execute('INSERT INTO model_profiles(name,config) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET config=excluded.config',
               (body.name,json.dumps(body.config.model_dump())))
    return {'ok':True}


@router.delete('/model-profiles/{identifier}')
def delete_profile(identifier: int,user=Depends(administrator)):
    db.execute('DELETE FROM model_profiles WHERE id=?',(identifier,))
    return {'ok':True}


@router.get('/knowledge/{identifier}/members')
def members(identifier: int,user=Depends(current_user)):
    owned('knowledge_bases',identifier,user['id'])
    return db.rows('SELECT u.id,u.username,m.permission FROM knowledge_members m JOIN users u ON u.id=m.user_id WHERE m.kb_id=?', (identifier,))


@router.post('/knowledge/{identifier}/members')
def share(identifier: int,body: Share,user=Depends(current_user)):
    owned('knowledge_bases',identifier,user['id'])
    target = db.one('SELECT id FROM users WHERE username=? AND disabled=0',(body.username.lower(),))
    if not target:
        raise HTTPException(404,'Active user not found. Ask an administrator to create the account first.')
    if target['id']==user['id']:
        raise HTTPException(400,'You already own this knowledge base.')
    db.execute('INSERT INTO knowledge_members VALUES(?,?,?) ON CONFLICT(kb_id,user_id) DO UPDATE SET permission=excluded.permission',
               (identifier,target['id'],body.permission))
    return {'ok':True}


@router.delete('/knowledge/{identifier}/members/{member_id}')
def revoke(identifier: int,member_id: int,user=Depends(current_user)):
    owned('knowledge_bases',identifier,user['id'])
    db.execute('DELETE FROM knowledge_members WHERE kb_id=? AND user_id=?',(identifier,member_id))
    scheduler.cancel_user(member_id)
    # Stop outstanding generations for this user; later requests recheck access.
    for _,(owner,stop) in list(runtime.active.items()):
        if owner==member_id:
            stop.set()
    return {'ok':True}


@router.get('/documents/{identifier}/preview')
@serial_preview
def preview(identifier: int,page: int=1,user=Depends(current_user)):
    doc = owned_document(identifier,user['id'])
    if page < 1:
        raise HTTPException(400,'Page/unit number must be positive.')
    if doc['format'] != 'pdf':
        rows = db.rows('SELECT text,location FROM chunks WHERE document_id=? AND page=? ORDER BY id',(identifier,page))
        if not rows:
            raise HTTPException(404,'Source unit not found.')
        return {'format':doc['format'],'location':rows[0]['location'],'text':'\n'.join(r['text'] for r in rows)}
    payload = db.one('SELECT pdf FROM documents WHERE id=?',(identifier,))
    if not payload:
        raise HTTPException(404)
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise HTTPException(503,'PDF preview needs pypdfium2 (included in requirements-ocr.txt and Docker).')
    try:
        with pdfium.PdfDocument(payload['pdf']) as pdf:
            if page > len(pdf):
                raise HTTPException(404,'Page not found.')
            p = pdf[page-1]
            try:
                width,height = p.get_size()
                bitmap = p.render(scale=min(1.5,1600/max(width,height)))
                try:
                    image = bitmap.to_pil()
                    try:
                        output = io.BytesIO()
                        image.save(output,format='PNG')
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                p.close()
        return Response(output.getvalue(),media_type='image/png')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400,'This PDF page could not be rendered.')
