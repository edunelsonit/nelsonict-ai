"""Memory admission must apply beyond the browser and preserve a running model."""
import struct
import sys
import threading
from types import SimpleNamespace

import pytest

from app import db, model_resources
from app.config import settings
from app.inference import ModelRuntime, runtime
from app.schemas import ModelConfig
from conftest import sign_in

GIB = 1024**3


def write_model(name, *, large_cache=False, padding=0):
    metadata = {
        'general.architecture': 'llama',
        'llama.context_length': 32768,
        'llama.block_count': 80 if large_cache else 4,
        'llama.embedding_length': 8192 if large_cache else 128,
        'llama.attention.head_count': 64 if large_cache else 4,
        'llama.attention.head_count_kv': 64 if large_cache else 2,
    }
    def string(value):
        encoded = value.encode()
        return struct.pack('<Q', len(encoded)) + encoded
    content = b'GGUF' + struct.pack('<IQQ', 3, 1, len(metadata))
    for key, value in metadata.items():
        content += string(key)
        content += (struct.pack('<I', 8) + string(value) if isinstance(value, str)
                    else struct.pack('<II', 4, value))
    path = settings.models_dir / name
    path.write_bytes(content + b'\0' * (64 + padding))
    return path


@pytest.fixture
def memory(monkeypatch):
    report = {'ram_total': 8*GIB, 'ram_available': 4*GIB,
              'reserve_bytes': GIB, 'budget_bytes': 3*GIB,
              'recommended': {'context': 4096, 'threads': 2, 'gpu_layers': 0},
              'note': 'Test memory snapshot.'}
    monkeypatch.setattr(model_resources, 'memory_snapshot', lambda: dict(report))
    monkeypatch.setattr('app.main.memory_snapshot', lambda: dict(report))
    return report


@pytest.fixture
def fake_inference(monkeypatch):
    calls = []
    class FakeLlama:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.closed = False
        def close(self):
            self.closed = True
    monkeypatch.setitem(sys.modules, 'llama_cpp', SimpleNamespace(Llama=FakeLlama))
    return calls


def test_resource_report_recommends_fitting_local_model(admin, memory):
    write_model('small.gguf')
    write_model('medium.gguf', padding=200)
    write_model('too-large.gguf', large_cache=True)
    (settings.models_dir / 'broken.gguf').write_bytes(b'GGUF')
    result = admin.get('/api/models/resources?context=4096')
    assert result.status_code == 200, result.text
    report = result.json()
    by_name = {item['filename']: item for item in report['models']}
    assert by_name['small.gguf']['allowed']
    assert not by_name['too-large.gguf']['allowed']
    assert not by_name['broken.gguf']['allowed']
    assert report['recommended']['filename'] == 'medium.gguf'
    assert report['recommended']['gpu_layers'] == 0
    assert report['budget_bytes'] == 3*GIB


def test_resource_report_no_files_and_no_fitting_model(admin, memory):
    assert admin.get('/api/models/resources').json()['recommended']['filename'] is None
    write_model('small.gguf')
    memory.update(ram_available=GIB, budget_bytes=0)
    report = admin.get('/api/models/resources').json()
    assert report['recommended']['filename'] is None
    assert not report['models'][0]['allowed']


def test_recommendation_reduces_context_only_if_needed(admin, memory):
    write_model('large-cache.gguf', large_cache=True)
    memory.update(ram_total=16*GIB, ram_available=5*GIB, budget_bytes=4*GIB)
    report = admin.get('/api/models/resources?context=4096').json()
    assert not report['models'][0]['allowed']
    assert report['recommended']['filename'] == 'large-cache.gguf'
    assert report['recommended']['context'] == 1024
    write_model('small.gguf')
    report = admin.get('/api/models/resources?context=4096').json()
    assert report['recommended']['filename'] == 'small.gguf'
    assert report['recommended']['context'] == 4096


def test_resources_admin_only_and_context_validated(admin, memory):
    assert admin.get('/api/models/resources?context=0').status_code == 422
    assert admin.get('/api/models/resources?context=32769').status_code == 422
    admin.post('/api/users', json={'username': 'member', 'password': 'member-password-123'})
    sign_in(admin, 'member', 'member-password-123')
    assert admin.get('/api/models/resources').status_code == 403
    assert admin.post('/api/models/load', json={'filename': 'small.gguf'}).status_code == 403


def test_large_api_load_preserves_active_model_and_saved_config(admin, memory, fake_inference):
    write_model('small.gguf')
    write_model('large.gguf', large_cache=True)
    assert admin.post('/api/models/load', json={'filename': 'small.gguf'}).status_code == 200
    active = runtime.model
    previous = db.get_setting('model_config')
    result = admin.post('/api/models/load', json={'filename': 'large.gguf', 'gpu_layers': -1})
    assert result.status_code == 409, result.text
    assert len(fake_inference) == 1
    assert runtime.model is active and not active.closed
    assert db.get_setting('model_config') == previous
    assert not runtime.loading and not runtime.gate.locked()


def test_load_rechecks_ram_after_browser_report(admin, memory, fake_inference):
    write_model('small.gguf')
    assert admin.get('/api/models/resources').json()['models'][0]['allowed']
    memory.update(ram_available=GIB, budget_bytes=0)
    result = admin.post('/api/models/load', json={'filename': 'small.gguf'})
    assert result.status_code == 409
    assert not fake_inference
    assert db.get_setting('model_config') is None


def test_saved_profile_cannot_bypass_memory_guard(admin, memory, fake_inference):
    write_model('large.gguf', large_cache=True)
    assert admin.post('/api/model-profiles', json={
        'name': 'Large GPU', 'config': {'filename': 'large.gguf', 'gpu_layers': -1}
    }).status_code == 201
    saved = admin.get('/api/model-profiles').json()[0]['config']
    assert admin.post('/api/models/load', json=saved).status_code == 409
    assert not fake_inference


def test_direct_runtime_load_used_by_startup_is_guarded(admin, memory, fake_inference):
    write_model('large.gguf', large_cache=True)
    instance = ModelRuntime()
    saved = ModelConfig(filename='large.gguf').model_dump()
    with pytest.raises(ValueError):
        instance.load(saved)
    assert instance.model is None and instance.error
    assert not instance.gate.locked() and not instance.loading
    assert not fake_inference


def test_chat_stream_uses_supported_chat_completion_arguments():
    class ChatModel:
        def create_chat_completion(self, *, messages, stream, max_tokens, temperature):
            self.arguments = {"messages": messages, "stream": stream, "max_tokens": max_tokens,
                              "temperature": temperature}
            return iter([{"choices": [{"delta": {"content": "Hello"}}]}])

    instance = ModelRuntime()
    instance.model = ChatModel()
    instance.config = {"max_tokens": 128, "temperature": 0.4}
    assert list(instance.stream([{"role": "user", "content": "Hi"}], threading.Event())) == ["Hello"]
    assert instance.model.arguments == {"messages": [{"role": "user", "content": "Hi"}], "stream": True,
                                        "max_tokens": 128, "temperature": 0.4}


def test_eligible_switch_closes_old_model_only_after_admission(admin, memory, fake_inference):
    write_model('first.gguf')
    write_model('second.gguf')
    assert admin.post('/api/models/load', json={'filename': 'first.gguf'}).status_code == 200
    old = runtime.model
    assert admin.post('/api/models/load', json={'filename': 'second.gguf'}).status_code == 200
    assert old.closed and runtime.model is not old
    assert len(fake_inference) == 2
    assert db.get_setting('model_config')['filename'] == 'second.gguf'
