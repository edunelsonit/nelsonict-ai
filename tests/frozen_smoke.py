"""Exercise the actual frozen API, worker and indexing subprocess without GGUF weights."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx

binary=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as folder:
    base=Path(folder)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=dict(os.environ,NELSON_DATA_DIR=str(base/'data'),NELSON_MODELS_DIR=str(base/'models'),
             NELSON_BIND_PORT=str(port),NELSON_EMBEDDING_MODEL='',NELSON_ALLOWED_HOSTS='127.0.0.1,localhost',NELSON_COOKIE_SECURE='false')
    with (base/'log').open('wb') as log:
        process=subprocess.Popen([str(binary),'--service'],env=env,stdout=log,stderr=log)
        def wait_for(fn):
            for _ in range(150):
                assert process.poll() is None,(base/'log').read_text(errors='replace')
                try:
                    value=fn()
                    if value:return value
                except (httpx.HTTPError,KeyError):pass
                time.sleep(.1)
            raise AssertionError((base/'log').read_text(errors='replace'))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=3,trust_env=False,headers={'X-Nelson-Client':'web'}) as client:
                wait_for(lambda:client.get('/api/health').status_code==200)
                assert 'operations.js' in client.get('/').text
                token=(base/'data'/'setup-token.txt').read_text()
                credentials={'username':'smoke-owner','password':'smoke-password-123'}
                assert client.post('/api/setup',json={**credentials,'setup_token':token}).status_code==201
                r=client.post('/api/login',json=credentials);assert r.status_code==200,r.text
                client.headers['X-CSRF-Token']=r.json()['csrf']
                kid=client.post('/api/knowledge',json={'name':'Smoke'}).json()['id']
                r=client.post(f'/api/knowledge/{kid}/documents',content=b'Nelsonict provides practical MikroTik training.',headers={'X-Filename':'training.txt'})
                assert r.status_code==202,r.text
                docs=wait_for(lambda:(rows if (rows:=client.get(f'/api/knowledge/{kid}/documents').json()) and rows[0]['status'] in ('ready','failed') else None))
                assert docs[0]['status']=='ready',docs
                check=client.get('/api/system/check').json()
                assert check['dependencies']['inference'],check
                assert client.get('/api/status').json()['worker_online']
                print('Frozen smoke passed: HTTP, frontend, setup/login, native inference import, document worker and indexing subprocess.')
        finally:
            (base/'data').mkdir(exist_ok=True)
            (base/'data'/'stop.request').touch()
            try:process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                process.kill();process.wait();raise
