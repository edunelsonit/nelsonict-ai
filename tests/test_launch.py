"""Real subprocess regression for GUI activation and managed API/worker restart."""
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx


def test_managed_restart_switches_both_processes(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    bootstrap=tmp_path/'data';models=tmp_path/'models';models.mkdir()
    env=dict(os.environ,NELSON_DATA_DIR=str(bootstrap),NELSON_MODELS_DIR=str(models),
             NELSON_EMBEDDING_MODEL='',NELSON_BIND_PORT=str(port),NELSON_ALLOWED_HOSTS='127.0.0.1,localhost',NELSON_COOKIE_SECURE='false')
    log=(tmp_path/'service.log').open('wb')
    process=subprocess.Popen([sys.executable,'-m','app.cli','run'],env=env,stdout=log,stderr=log)
    def wait_for(fn,seconds=20):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                value=fn()
                if value:return value
            except (httpx.HTTPError,FileNotFoundError,KeyError):pass
            assert process.poll() is None,(tmp_path/'service.log').read_text()
            time.sleep(.1)
        raise AssertionError((tmp_path/'service.log').read_text())
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=3,trust_env=False,headers={'X-Nelson-Client':'web'}) as client:
            wait_for(lambda:client.get('/api/health').status_code==200)
            token=(bootstrap/'setup-token.txt').read_text()
            credentials={'username':'owner','password':'correct-password-123'}
            assert client.post('/api/setup',json={**credentials,'setup_token':token}).status_code==201
            def login():
                r=client.post('/api/login',json=credentials)
                if r.status_code!=200:return False
                client.headers['X-CSRF-Token']=r.json()['csrf'];return True
            assert login()
            wait_for(lambda:client.get('/api/status').json().get('worker_online'))
            backup=client.get('/api/backup').content
            stage=client.post('/api/migration/stage',content=backup).json()
            active=client.post('/api/migration/'+stage['id']+'/activate',json={
                'models_dir':str(models),'allowed_hosts':'127.0.0.1,localhost','bind_port':port,'confirm':'RESTORE'})
            assert active.status_code==200,active.text
            assert client.post('/api/migration/restart').status_code==200
            # Wait until old API exits: the new installation rejects the pre-restart session.
            wait_for(lambda:client.get('/api/me').status_code==401)
            wait_for(login)
            current=client.get('/api/migration/settings').json()
            assert Path(current['data_dir'])==Path(stage['data_dir'])
            wait_for(lambda:client.get('/api/status').json().get('worker_online'))
    finally:
        bootstrap.mkdir(exist_ok=True)
        (bootstrap/'stop.request').touch()
        try:process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            process.kill();process.wait();raise
        log.close()
