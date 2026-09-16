"""Guided restore: validate a snapshot, review target settings, activate at restart."""
import asyncio
import json
import os
import re
import secrets
import shutil
import sqlite3
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from .config import settings
from .security import administrator
from .maintenance import restore_backup
from .machine import system_report

router = APIRouter(prefix='/api/migration')


def root():
    return settings.launch_root or settings.data_dir.resolve()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as f:
            json.dump(value, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def stage_path(identifier):
    if not re.fullmatch('[a-f0-9]{32}', identifier):
        raise HTTPException(404, 'Restore not found.')
    path = root() / 'restores' / identifier
    if not (path / 'review.json').is_file():
        raise HTTPException(404, 'Restore not found.')
    return path


class MigrationSettings(BaseModel):
    models_dir: str = Field(min_length=1, max_length=1000)
    embedding_model: str = Field(default='', max_length=1000)
    allowed_hosts: str = Field(min_length=1, max_length=500)
    cookie_secure: bool = False
    bind_host: str = '127.0.0.1'
    bind_port: int = Field(default=8000, ge=1024, le=65535)
    threads: int = Field(default=4, ge=1, le=128)
    context: int = Field(default=4096, ge=1024, le=32768)
    gpu_layers: int = Field(default=0, ge=-1, le=200)
    confirm: str

    @field_validator('allowed_hosts')
    @classmethod
    def hosts(cls, value):
        if any(not re.fullmatch(r'[A-Za-z0-9.\-]+', x.strip()) for x in value.split(',')):
            raise ValueError('Enter comma-separated hostnames/IP addresses without schemes, ports, or wildcards.')
        return ','.join(x.strip() for x in value.split(','))

    @field_validator('bind_host')
    @classmethod
    def address(cls, value):
        import ipaddress
        ipaddress.ip_address(value)
        return value


@router.get('/settings')
def current(user=Depends(administrator)):
    return {'data_dir':str(settings.data_dir.resolve()),'models_dir':str(settings.models_dir.resolve()),
            'embedding_model':settings.embedding_model,'allowed_hosts':settings.allowed_hosts,
            'cookie_secure':settings.cookie_secure,'bind_host':settings.bind_host,'bind_port':settings.bind_port,
            'managed_restart':os.environ.get('NELSON_MANAGED_LAUNCH') == '1',
            'pending_restart':(root()/'runtime-settings.json').exists() and json.loads((root()/'runtime-settings.json').read_text()).get('data_dir') != str(settings.data_dir.resolve()),
            'hardware':system_report()}


@router.post('/stage', status_code=201)
async def stage(request: Request, user=Depends(administrator)):
    identifier = secrets.token_hex(16)
    path = root() / 'restores' / identifier
    path.mkdir(parents=True)
    archive = path / 'upload.zip'
    total = 0
    try:
        with archive.open('xb') as f:
            async for part in request.stream():
                total += len(part)
                if total > settings.max_backup_mb * 1024**2:
                    raise HTTPException(413, 'Backup upload exceeds the configured limit.')
                if shutil.disk_usage(path).free < len(part) + 64 * 1024**2:
                    raise HTTPException(507, 'Insufficient space for backup staging.')
                await asyncio.to_thread(f.write, part)
        await asyncio.to_thread(restore_backup, archive, path/'data')
        def inspect():
            conn = sqlite3.connect(path/'data'/'nelsonict.sqlite3')
            try:
                if not conn.execute("SELECT 1 FROM users WHERE role='admin' AND disabled=0").fetchone():
                    raise ValueError('Backup has no enabled administrator. Recover the source account first.')
                return {name:conn.execute('SELECT count(*) FROM '+name).fetchone()[0]
                        for name in ('users','knowledge_bases','documents','conversations')}
            finally:
                conn.close()
        counts = await asyncio.to_thread(inspect)
        review = {'id':identifier,'counts':counts,'data_dir':str((path/'data').resolve())}
        atomic_json(path/'review.json',review)
        return review
    except HTTPException:
        shutil.rmtree(path, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(path, ignore_errors=True)
        raise HTTPException(400, 'Backup could not be restored: '+str(exc)[:300])
    finally:
        archive.unlink(missing_ok=True)


@router.post('/{identifier}/activate')
def activate(identifier: str, body: MigrationSettings, user=Depends(administrator)):
    path = stage_path(identifier)
    if body.confirm != 'RESTORE':
        raise HTTPException(400, 'Type RESTORE to confirm switching to this restored installation.')
    model_path = Path(body.models_dir).expanduser()
    embed_path = Path(body.embedding_model).expanduser() if body.embedding_model else None
    if not model_path.is_absolute() or not model_path.is_dir():
        raise HTTPException(400, 'Model directory must be an existing absolute server path.')
    if embed_path and (not embed_path.is_absolute() or not embed_path.is_dir()):
        raise HTTPException(400, 'Embedding directory must be an existing absolute server path, or blank.')
    if settings.data_dir.resolve() == (path/'data').resolve():
        raise HTTPException(409, 'This restore is already active.')
    config = {k:getattr(body,k) for k in ('allowed_hosts','cookie_secure','bind_host','bind_port')}
    config.update(data_dir=str((path/'data').resolve()),models_dir=str(model_path.resolve()),
                  embedding_model=str(embed_path.resolve()) if embed_path else '')
    conn = sqlite3.connect(path/'data'/'nelsonict.sqlite3')
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('migration_hardware',?)",
                         (json.dumps({k:getattr(body,k) for k in ('threads','context','gpu_layers')}),))
    finally:
        conn.close()
    previous = {k:str(getattr(settings,k)) if k.endswith('_dir') else getattr(settings,k) for k in config}
    atomic_json(root()/'previous-runtime-settings.json', previous)
    atomic_json(root()/'runtime-settings.json', config)
    return {'ok':True,'data_dir':config['data_dir'],
            'message':'Restore prepared. Restart both API and worker. Sign in with an account from the backup and load/test your model. Docker port mappings must be changed in Compose separately.'}


@router.delete('/{identifier}')
def discard(identifier: str, user=Depends(administrator)):
    path = stage_path(identifier)
    config_path = root()/'runtime-settings.json'
    pending = json.loads(config_path.read_text()) if config_path.exists() else {}
    if settings.data_dir.resolve() == (path/'data').resolve() or pending.get('data_dir') == str((path/'data').resolve()):
        raise HTTPException(409, 'Cannot delete an active or pending restore.')
    shutil.rmtree(path)
    return {'ok':True}


@router.post('/restart')
def restart(user=Depends(administrator)):
    if os.environ.get('NELSON_MANAGED_LAUNCH') != '1':
        raise HTTPException(409, 'Restart both services with Docker Compose or your service manager.')
    (root()/'restart.request').touch()
    return {'ok':True,'message':'Restart requested. Reopen the application at the reviewed address.'}
