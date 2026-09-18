"""Administrator-triggered public HTTPS GGUF downloads with pinned public addresses."""
import hashlib
import http.client
import ipaddress
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import tempfile
import threading
import time
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from . import db
from .config import settings
from .machine import inspect_gguf
from .security import administrator

router = APIRouter(prefix='/api/models/downloads')
REDIRECTS = {301, 302, 303, 307, 308}


class DownloadError(ValueError):
    pass


class Cancelled(DownloadError):
    pass


class DownloadRequest(BaseModel):
    url: str = Field(min_length=8, max_length=8192)
    filename: str = Field(default='', max_length=185)
    sha256: str = Field(default='', max_length=64)


def parse_url(value):
    if any(ord(c) <= 32 or ord(c) == 127 for c in value) or '\\' in value:
        raise DownloadError('Use a valid HTTPS download URL without spaces or control characters.')
    try:
        p = urlsplit(value)
        port = p.port
    except ValueError:
        raise DownloadError('Invalid download address.')
    if p.scheme != 'https' or not p.hostname or port not in (None, 443) or p.username is not None or p.password is not None or p.fragment:
        raise DownloadError('Use a public HTTPS URL on port 443 without credentials or a fragment.')
    try:
        host = p.hostname.encode('idna').decode('ascii')
    except UnicodeError:
        raise DownloadError('Invalid repository hostname.')
    if '%' in host:
        raise DownloadError('Scoped network addresses are not supported.')
    return p, host


def normalize_url(value):
    p, host = parse_url(value)
    path = p.path
    if host.lower() in ('huggingface.co', 'www.huggingface.co', 'hf.co'):
        parts = path.split('/')
        if len(parts) >= 6 and parts[3] == 'blob':
            parts[3] = 'resolve'
            path = '/'.join(parts)
    return urlunsplit((p.scheme, p.netloc, quote(path, safe='/%:@!$&\'()*+,;=-._~'), p.query, ''))


def public_addresses(host):
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise DownloadError('Repository hostname could not be resolved.')
    addresses = []
    for answer in answers:
        ip = ipaddress.ip_address(answer[4][0])
        # Reject mixed public/private DNS answers as well as literal private addresses.
        if not ip.is_global or ip.is_multicast or ip.is_unspecified or getattr(ip, 'ipv4_mapped', None) or getattr(ip, 'sixtofour', None) or getattr(ip, 'teredo', None) or (ip.version == 6 and ip in ipaddress.ip_network('64:ff9b::/96')):
            raise DownloadError('Downloads must use public Internet addresses; local and reserved networks are blocked.')
        if str(ip) not in addresses:
            addresses.append(str(ip))
    if not addresses:
        raise DownloadError('Repository has no usable public address.')
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, port=443, timeout=30, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Never re-resolve the hostname after validation. TLS/Host still use the original name.
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def open_response(url, stop):
    p, host = parse_url(url)
    addresses = public_addresses(host)
    target = p.path or '/'
    if p.query:
        target += '?' + p.query
    for address in addresses[:4]:
        if stop.is_set():
            raise Cancelled('Download cancelled.')
        connection = PinnedHTTPSConnection(host, address)
        try:
            connection.request('GET', target, headers={'Accept-Encoding':'identity', 'User-Agent':'Nelsonict-AI/1.2', 'Connection':'close'})
            return connection, connection.getresponse()
        except (OSError, http.client.HTTPException):
            connection.close()
    raise DownloadError('Could not connect securely to the repository. Check server Internet access and the HTTPS URL.')


class Downloads:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = {}

    def snapshot(self):
        with self.lock:
            return [{k:v for k,v in job.items() if k not in ('stop','thread')} for job in reversed(list(self.jobs.values()))]

    def update(self, job, **values):
        with self.lock:
            job.update(values)

    def start(self, body, user_id):
        url = normalize_url(body.url.strip())
        filename = body.filename.strip() or unquote(urlsplit(url).path.rsplit('/',1)[-1])
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,179}\.gguf', filename, re.IGNORECASE):
            raise DownloadError('Choose a simple .gguf filename without directories.')
        expected = body.sha256.strip().lower()
        if expected and not re.fullmatch('[a-f0-9]{64}', expected):
            raise DownloadError('Expected SHA-256 must contain 64 hexadecimal characters.')
        root = settings.models_dir.resolve()
        destination = root / filename
        with self.lock:
            if any(j['status'] in ('downloading','validating','cancelling') for j in self.jobs.values()):
                raise RuntimeError('A model download is already running. Finish or cancel it first.')
            if destination.exists() or destination.is_symlink():
                raise RuntimeError('This model filename already exists. Choose another name; models are never overwritten.')
            # Check write access before accepting the job; do not retain the URL or query tokens in status.
            fd, path = tempfile.mkstemp(prefix='.download-',suffix='.part',dir=root)
            os.close(fd)
            while len(self.jobs) >= 20:
                del self.jobs[next(iter(self.jobs))]
            identifier = secrets.token_hex(16)
            job = {'id':identifier,'filename':filename,'host':urlsplit(url).hostname,'status':'downloading',
                   'received':0,'total':None,'sha256':None,'checksum_verified':False,'error':None,
                   'created':time.time(),'stop':threading.Event()}
            self.jobs[identifier] = job
            thread = threading.Thread(target=self.run,args=(job,url,expected,user_id,Path(path),destination,settings.max_model_mb*1024**2),daemon=True)
            job['thread'] = thread
            try:
                thread.start()
            except BaseException:
                Path(path).unlink(missing_ok=True)
                del self.jobs[identifier]
                raise
            return identifier

    def check(self, job, user_id, deadline):
        if job['stop'].is_set():
            raise Cancelled('Download cancelled.')
        if time.monotonic() > deadline:
            raise DownloadError('Download exceeded its six-hour time limit. Retry with a faster connection.')
        if not db.one("SELECT id FROM users WHERE id=? AND role='admin' AND disabled=0",(user_id,)):
            raise Cancelled('Download stopped because its administrator account is no longer active.')

    def run(self, job, url, expected, user_id, temporary, destination, limit):
        connection = response = None
        deadline = time.monotonic()+6*3600
        received = 0
        try:
            for redirect in range(9):
                self.check(job,user_id,deadline)
                connection,response = open_response(url,job['stop'])
                if response.status not in REDIRECTS:
                    break
                location = response.getheader('Location')
                response.close(); connection.close(); response = connection = None
                if not location or redirect == 8:
                    raise DownloadError('Missing redirect destination or too many redirects.')
                url = normalize_url(urljoin(url,location))
            if response.status != 200:
                if response.status in (401,403):
                    raise DownloadError('Repository requires access or rejected the link. Use a public file link, or download gated/private files manually and import them.')
                raise DownloadError(f'Repository returned HTTP {response.status}. Check the file link.')
            if response.getheader('Content-Encoding','identity').lower() not in ('identity',''):
                raise DownloadError('Repository sent encoded content; use a direct uncompressed GGUF file URL.')
            length = response.getheader('Content-Length')
            if length is not None and (not length.isdigit() or len(length)>20):
                raise DownloadError('Repository returned an invalid file size.')
            total = int(length) if length is not None else None
            if total is not None and total > limit:
                raise DownloadError('Model exceeds NELSON_MAX_MODEL_MB.')
            if total is not None and shutil.disk_usage(temporary.parent).free < total + 64*1024**2:
                raise DownloadError('Not enough free model storage for this download.')
            self.update(job,total=total)
            digest = hashlib.sha256()
            last_account_check = time.monotonic()
            with temporary.open('wb') as handle:
                while True:
                    if job['stop'].is_set():
                        raise Cancelled('Download cancelled.')
                    if time.monotonic()-last_account_check>2:
                        self.check(job,user_id,deadline); last_account_check=time.monotonic()
                    part=response.read(64*1024)
                    if not part: break
                    received+=len(part)
                    if received>limit:
                        raise DownloadError('Model exceeds NELSON_MAX_MODEL_MB.')
                    if shutil.disk_usage(temporary.parent).free<len(part)+64*1024**2:
                        raise DownloadError('Not enough free model storage; partial download removed.')
                    digest.update(part);handle.write(part)
                    self.update(job,received=received)
                handle.flush();os.fsync(handle.fileno())
            if total is not None and received != total:
                raise DownloadError('Incomplete download; retry the file.')
            self.check(job,user_id,deadline)
            self.update(job,status='validating')
            actual = digest.hexdigest()
            if expected and actual != expected:
                raise DownloadError('SHA-256 mismatch. Download rejected.')
            try:
                inspection = inspect_gguf(temporary)
            except (ValueError,OSError):
                raise DownloadError('Downloaded file is not a supported GGUF. Use a raw/download link, not an HTML page or Git LFS pointer.')
            self.check(job,user_id,deadline)
            # Serialize final installation with cancellation, and never overwrite another upload.
            with self.lock:
                if job['stop'].is_set(): raise Cancelled('Download cancelled.')
                temporary.chmod(0o644)
                try:
                    os.link(temporary,destination)
                except FileExistsError:
                    raise DownloadError('Another operation installed this filename. Existing model preserved.')
                job.update(status='complete',sha256=actual,checksum_verified=bool(expected),inspection=inspection)
        except Cancelled as exc:
            self.update(job,status='cancelled',error=str(exc))
        except DownloadError as exc:
            self.update(job,status='failed',error=str(exc))
        except Exception:
            # Do not expose signed redirect URLs, network internals, or server paths in diagnostics.
            self.update(job,status='cancelled' if job['stop'].is_set() else 'failed',
                        error='Download cancelled.' if job['stop'].is_set() else 'Download failed. Check connectivity, free disk space and model-folder permissions, then retry.')
        finally:
            if response is not None: response.close()
            if connection is not None: connection.close()
            temporary.unlink(missing_ok=True)

    def cancel(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if not job:
                raise KeyError(identifier)
            if job['status'] in ('downloading','validating','cancelling'):
                job['stop'].set()
                job['status']='cancelling'
            return job['status']

    def shutdown(self):
        with self.lock:
            for job in self.jobs.values(): job['stop'].set()


downloads = Downloads()


@router.post('',status_code=202)
def start_download(body: DownloadRequest,user=Depends(administrator)):
    try:
        return {'id':downloads.start(body,user['id'])}
    except DownloadError as exc:
        raise HTTPException(400,str(exc))
    except RuntimeError as exc:
        raise HTTPException(409,str(exc))
    except OSError:
        raise HTTPException(400,'Models directory is not writable or lacks free space.')


@router.get('')
def list_downloads(user=Depends(administrator)):
    return downloads.snapshot()


@router.post('/{identifier}/cancel')
def cancel_download(identifier: str,user=Depends(administrator)):
    try:
        return {'status':downloads.cancel(identifier)}
    except KeyError:
        raise HTTPException(404,'Download not found.')
