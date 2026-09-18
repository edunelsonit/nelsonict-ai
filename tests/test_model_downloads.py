import hashlib
import io
import socket
import threading
import time
import pytest
from app import db
from app.config import settings
from app.model_downloads import DownloadRequest, DownloadError, Downloads, PinnedHTTPSConnection, normalize_url, public_addresses
from app import model_downloads as module
from conftest import sign_in
from test_v11 import gguf


class Response(io.BytesIO):
    def __init__(self, payload=b'',status=200,headers=None):
        super().__init__(payload);self.status=status;self.headers=headers or {}
    def getheader(self,key,default=None):return self.headers.get(key,default)


class Connection:
    def close(self):pass


def wait(manager,identifier):
    manager.jobs[identifier]['thread'].join(4)
    assert not manager.jobs[identifier]['thread'].is_alive()
    return next(j for j in manager.snapshot() if j['id']==identifier)


def test_hf_blob_link_becomes_resolve():
    assert normalize_url('https://huggingface.co/team/model/blob/main/sub/file.gguf?download=true')=='https://huggingface.co/team/model/resolve/main/sub/file.gguf?download=true'


@pytest.mark.parametrize('url',['http://example.org/x.gguf','https://user:password@example.org/a.gguf','https://example.org:8443/a.gguf','file:///tmp/model.gguf','https://example.org/a.gguf#test','https://example.org/\r\nHost:localhost','https://[fe80::1%25eth0]/a.gguf'])
def test_invalid_source_addresses(url):
    with pytest.raises(DownloadError):normalize_url(url)


@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','169.254.169.254','192.168.0.1','::1','::ffff:127.0.0.1','224.0.0.1','2002:7f00:0001::1','64:ff9b::7f00:1'])
def test_private_and_transition_addresses_are_blocked(monkeypatch,ip):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',(ip,443))])
    with pytest.raises(DownloadError):public_addresses('repository.example')


def test_mixed_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',('8.8.8.8',443)),(0,0,0,'',('127.0.0.1',443))])
    with pytest.raises(DownloadError):public_addresses('repository.example')


def test_connection_pins_ip_but_preserves_tls_hostname(monkeypatch):
    seen={};raw=object()
    monkeypatch.setattr(socket,'create_connection',lambda address,timeout:(seen.update(address=address) or raw))
    class Context:
        def wrap_socket(self,sock,server_hostname):seen.update(host=server_hostname);return sock
    connection=PinnedHTTPSConnection('repository.example','8.8.8.8');connection._context=Context();connection.connect()
    assert seen=={'address':('8.8.8.8',443),'host':'repository.example'}
    connection.sock=None


def test_valid_download_checksum_atomic_install_and_progress(admin,monkeypatch):
    payload=gguf();manager=Downloads()
    monkeypatch.setattr(module,'open_response',lambda *a:(Connection(),Response(payload,headers={'Content-Length':str(len(payload))})))
    identifier=manager.start(DownloadRequest(url='https://example.org/model.gguf',sha256=hashlib.sha256(payload).hexdigest()),1)
    result=wait(manager,identifier)
    assert result['status']=='complete' and result['received']==len(payload)
    assert result['checksum_verified']
    assert (settings.models_dir/'model.gguf').read_bytes()==payload
    assert not list(settings.models_dir.glob('.download-*.part'))
    with pytest.raises(RuntimeError,match='already exists'):manager.start(DownloadRequest(url='https://example.org/model.gguf'),1)


@pytest.mark.parametrize('payload,headers,expected',[(b'<html>Page</html>',{},''),(gguf(),{},'0'*64),(gguf(),{'Content-Length':'99999999999999'},''),(gguf(),{'Content-Length':'9999'},''),(gguf(),{'Content-Encoding':'gzip'},'')])
def test_invalid_or_incomplete_download_never_installs(admin,monkeypatch,payload,headers,expected):
    manager=Downloads();monkeypatch.setattr(module,'open_response',lambda *a:(Connection(),Response(payload,headers=headers)))
    identifier=manager.start(DownloadRequest(url='https://example.org/model.gguf',sha256=expected),1)
    assert wait(manager,identifier)['status']=='failed'
    assert not (settings.models_dir/'model.gguf').exists()
    assert not list(settings.models_dir.glob('.download-*.part'))


def test_private_redirect_is_revalidated_before_connect(admin,monkeypatch):
    calls=[];manager=Downloads()
    class PublicConnection(Connection):
        def __init__(self,host,address):calls.append((host,address))
        def request(self,*a,**k):pass
        def getresponse(self):return Response(status=302,headers={'Location':'https://127.0.0.1/model.gguf'})
    monkeypatch.setattr(socket,'getaddrinfo',lambda host,*a,**k:[(0,0,0,'',('127.0.0.1' if host=='127.0.0.1' else '8.8.8.8',443))])
    monkeypatch.setattr(module,'PinnedHTTPSConnection',PublicConnection)
    identifier=manager.start(DownloadRequest(url='https://example.org/model.gguf'),1)
    assert wait(manager,identifier)['status']=='failed'
    assert calls==[('example.org','8.8.8.8')]


def test_allowed_redirects_and_query_not_exposed(admin,monkeypatch):
    manager=Downloads();calls=[]
    def opened(url,stop):
        calls.append(url)
        return (Connection(),Response(status=302,headers={'Location':'https://cdn.example/file?signature=secret'})) if len(calls)==1 else (Connection(),Response(gguf()))
    monkeypatch.setattr(module,'open_response',opened)
    identifier=manager.start(DownloadRequest(url='https://example.org/model.gguf'),1)
    result=wait(manager,identifier)
    assert result['status']=='complete' and len(calls)==2
    assert 'secret' not in str(result)


def test_cancel_download_keeps_controls_responsive_and_cleans_file(admin,monkeypatch):
    manager=Downloads();monkeypatch.setattr(module,'downloads',manager)
    began=threading.Event();release=threading.Event()
    def opened(url,stop):
        began.set();release.wait(3);return Connection(),Response(gguf())
    monkeypatch.setattr(module,'open_response',opened)
    result=admin.post('/api/models/downloads',json={'url':'https://example.org/model.gguf'})
    assert result.status_code==202;identifier=result.json()['id'];assert began.wait(1)
    try:
        assert admin.post('/api/models/downloads',json={'url':'https://example.org/second.gguf'}).status_code==409
        assert admin.get('/api/knowledge').status_code==200
        assert admin.get('/api/models/downloads').status_code==200
        assert admin.post(f'/api/models/downloads/{identifier}/cancel').json()['status']=='cancelling'
    finally:release.set()
    assert wait(manager,identifier)['status']=='cancelled'
    assert not (settings.models_dir/'model.gguf').exists()
    assert not list(settings.models_dir.glob('.download-*.part'))


def test_member_cannot_control_downloads(admin):
    admin.post('/api/users',json={'username':'member','password':'member-password-123'})
    sign_in(admin,'member','member-password-123')
    assert admin.get('/api/models/downloads').status_code==403
    assert admin.post('/api/models/downloads',json={'url':'https://example.org/file.gguf'}).status_code==403
    assert admin.post('/api/models/downloads/unknown/cancel').status_code==403


def test_account_revocation_blocks_installation(admin,monkeypatch):
    manager=Downloads();db.execute('UPDATE users SET disabled=1 WHERE id=1')
    monkeypatch.setattr(module,'open_response',lambda *a:(_ for _ in ()).throw(AssertionError('must not connect')))
    identifier=manager.start(DownloadRequest(url='https://example.org/model.gguf'),1)
    assert wait(manager,identifier)['status']=='cancelled'
    assert not (settings.models_dir/'model.gguf').exists()


def test_unknown_length_still_enforces_limit(admin,monkeypatch):
    manager=Downloads();monkeypatch.setattr(settings,'max_model_mb',0)
    monkeypatch.setattr(module,'open_response',lambda *a:(Connection(),Response(gguf())))
    identifier=manager.start(DownloadRequest(url='https://example.org/model.gguf'),1)
    assert wait(manager,identifier)['status']=='failed'
    assert not (settings.models_dir/'model.gguf').exists()
