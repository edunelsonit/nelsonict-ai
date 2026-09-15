"""Local installation diagnostics. Estimates are guidance, not compatibility guarantees."""
import importlib.util
import os
import platform
import shutil
import struct
import subprocess
from pathlib import Path
import psutil
from .config import settings


def inspect_gguf(path):
    path = Path(path)
    size = path.stat().st_size
    metadata = {}
    with path.open('rb') as handle:
        def read(n):
            value = handle.read(n)
            if len(value) != n:
                raise ValueError('Truncated GGUF metadata.')
            return value
        def number(fmt):
            return struct.unpack('<' + fmt, read(struct.calcsize('<' + fmt)))[0]
        def string(keep=True):
            n = number('Q')
            if n > 16 * 1024**2 or handle.tell() + n > size:
                raise ValueError('Invalid GGUF string length.')
            if keep:
                return read(n).decode('utf-8', errors='replace')
            handle.seek(n, 1)
        numeric = {0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
        def value(kind, keep=False, depth=0):
            if depth > 2:
                raise ValueError('Unsupported nested GGUF arrays.')
            if kind in numeric:
                return number(numeric[kind])
            if kind == 8:
                return string(keep)
            if kind == 9:
                subtype, count = number('I'), number('Q')
                if count > 2_000_000:
                    raise ValueError('GGUF metadata array too large.')
                if subtype in numeric:
                    amount = count * struct.calcsize('<' + numeric[subtype])
                    if handle.tell() + amount > size:
                        raise ValueError('Truncated GGUF array.')
                    handle.seek(amount, 1)
                else:
                    for _ in range(count):
                        value(subtype, False, depth+1)
                return None
            raise ValueError('Unknown GGUF metadata type.')
        if read(4) != b'GGUF':
            raise ValueError('Invalid GGUF header.')
        version, tensors, entries = number('I'), number('Q'), number('Q')
        if version not in (2, 3) or entries > 100000 or tensors == 0:
            raise ValueError('Unsupported GGUF version or empty model.')
        for _ in range(entries):
            key = string()
            wanted = key in ('general.name','general.architecture','general.file_type') or key.endswith('.context_length')
            item = value(number('I'), wanted)
            if wanted:
                metadata[key] = item
        return {'version':version,'tensors':tensors,'bytes':size,'metadata':metadata,
                'note':'Metadata validated. Architecture support and actual RAM/GPU use require a successful load.'}


def system_report():
    memory = psutil.virtual_memory()
    gpu = []
    binary = shutil.which('nvidia-smi')
    if binary:
        try:
            result = subprocess.run([binary,'--query-gpu=name,memory.total','--format=csv,noheader,nounits'],
                                    capture_output=True,text=True,timeout=4,check=True)
            gpu = result.stdout.strip().splitlines()
        except (OSError, subprocess.SubprocessError):
            pass
    dependencies = {name: bool(importlib.util.find_spec(module)) for name,module in
                    [('inference','llama_cpp'),('PDF','pypdf'),('Word','docx'),('Excel','openpyxl'),
                     ('semantic','sentence_transformers'),('PDF preview/OCR renderer','pypdfium2')]}
    dependencies['Tesseract'] = bool(shutil.which('tesseract'))
    backend = {'gpu_offload':False,'error':None}
    if dependencies['inference']:
        try:
            import llama_cpp
            backend['gpu_offload'] = bool(llama_cpp.llama_supports_gpu_offload())
        except Exception as exc:
            backend['error'] = str(exc)[:300]
    total,available = memory.total,memory.available
    # Honour cgroup v2 limits when running the CPU Docker image.
    try:
        limit = int(Path('/sys/fs/cgroup/memory.max').read_text().strip())
        usage = int(Path('/sys/fs/cgroup/memory.current').read_text().strip())
        total,available = min(total,limit),min(available,max(0,limit-usage))
    except (OSError,ValueError):
        pass
    return {'os':platform.system(), 'machine':platform.machine(), 'python':platform.python_version(),
            'cpu':platform.processor() or platform.machine(), 'cores':os.cpu_count(),
            'ram_total':total,'ram_available':available,
            'disk_free':shutil.disk_usage(settings.models_dir).free,
            'models_writable':os.access(settings.models_dir,os.W_OK),
            'nvidia_devices':gpu, 'apple_silicon':platform.system()=='Darwin' and platform.machine()=='arm64',
            'dependencies':dependencies,'inference_backend':backend,
            'installation_help':{'inference':'pip install -r requirements-inference.txt',
              'documents':'pip install -r requirements.txt', 'OCR':'pip install -r requirements-ocr.txt; install Tesseract and the language pack',
              'semantic':'Optional: install requirements-semantic.txt and configure a local embedding folder'},
            'recommended':{'threads':max(1,min(psutil.cpu_count(logical=False) or 2,8)),
                           'context':4096 if available>8*1024**3 else 2048,'gpu_layers':0},
            'model_guidance':'Start with model weights below half of available RAM. Context cache and other services need additional memory. Detected GPU hardware does not establish backend support.'}
