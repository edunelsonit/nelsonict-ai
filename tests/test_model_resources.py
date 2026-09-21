import os
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import model_resources as resources
from app.machine import inspect_gguf

GIB = resources.GIB
MIB = resources.MIB


def memory(budget=6 * GIB):
    return {'ram_total': 8 * GIB, 'ram_available': 7 * GIB,
            'reserve_bytes': GIB, 'budget_bytes': budget}


def gguf_file(tmp_path, changes=None, filename='model.gguf'):
    metadata = {
        'general.architecture': 'llama', 'llama.block_count': 32,
        'llama.embedding_length': 4096, 'llama.attention.head_count': 32,
        'llama.attention.head_count_kv': 8, 'llama.context_length': 32768,
    }
    metadata.update(changes or {})

    def string(text):
        value = text.encode()
        return struct.pack('<Q', len(value)) + value

    payload = b'GGUF' + struct.pack('<IQQ', 3, 1, len(metadata))
    for key, value in metadata.items():
        payload += string(key)
        if isinstance(value, str):
            payload += struct.pack('<I', 8) + string(value)
        elif isinstance(value, list):
            payload += struct.pack('<IIQ', 9, 4, len(value))
            payload += b''.join(struct.pack('<I', item) for item in value)
        else:
            payload += struct.pack('<Iq', 11, value)
    path = tmp_path / filename
    path.write_bytes(payload + b'\0' * 64)
    return path


def test_small_model_fits_and_large_weights_are_blocked(tmp_path, monkeypatch):
    path = gguf_file(tmp_path)
    assert resources.assess_model(path, 2048, memory())['allowed']
    actual_stat = Path.stat

    def sized_stat(self, *args, **kwargs):
        stat = actual_stat(self, *args, **kwargs)
        if self == path:
            values = list(stat)
            values[6] = 7 * GIB
            return os.stat_result(values)
        return stat

    monkeypatch.setattr(Path, 'stat', sized_stat)
    result = resources.assess_model(path, 2048, memory())
    assert not result['allowed']
    assert result['model_bytes'] == 7 * GIB
    assert result['estimated_bytes'] > 8 * GIB
    assert 'Choose a smaller model' in result['reason']


def test_context_growth_can_make_previously_fitting_model_unsafe(tmp_path):
    path = gguf_file(tmp_path)
    low = resources.assess_model(path, 1024, memory(900 * MIB))
    high = resources.assess_model(path, 4096, memory(900 * MIB))
    assert low['allowed']
    assert not high['allowed']
    assert high['kv_cache_bytes'] == 4 * low['kv_cache_bytes']
    # 32 layers, 8 KV heads, two 128-dimension FP16 K/V vectors, 25% margin.
    assert low['kv_cache_bytes'] == 32 * 8 * (128 + 128) * 2 * 1024 * 1.25
    assert high['estimation'] == 'metadata'


def test_context_cannot_exceed_trained_limit(tmp_path):
    path = gguf_file(tmp_path, {'llama.context_length': 1024})
    result = resources.assess_model(path, 2048, memory())
    assert not result['allowed'] and result['trained_context'] == 1024
    assert 'trained context' in result['reason']


def test_long_context_small_kv_cache_still_accounts_for_attention_scratch(tmp_path):
    path = gguf_file(tmp_path, {
        'general.architecture': 'qwen2', 'qwen2.block_count': 24,
        'qwen2.embedding_length': 1536, 'qwen2.attention.head_count': 12,
        'qwen2.attention.head_count_kv': 2, 'qwen2.context_length': 32768,
    })
    short = resources.assess_model(path, 2048, memory(2 * GIB))
    long = resources.assess_model(path, 32768, memory(2 * GIB))
    assert short['allowed']
    # The old fixed buffer plus small GQA cache fits; non-flash scratch does not.
    assert long['model_bytes'] + long['kv_cache_bytes'] + 512 * MIB < 2 * GIB
    assert long['attention_work_bytes'] == 2 * 32768 * 512 * 12 * 4
    assert long['runtime_bytes'] >= long['attention_work_bytes']
    assert not long['allowed']


def test_fallback_uses_available_head_counts_for_attention_scratch(tmp_path):
    path = gguf_file(tmp_path, {'general.architecture': 'future_arch',
                                'future_arch.attention.head_count': [256, 512]})
    result = resources.assess_model(path, 1024, memory())
    assert result['estimation'] == 'conservative_fallback'
    assert result['runtime_bytes'] >= 2 * 1024 * 512 * 512 * 4


def test_key_value_lengths_are_respected(tmp_path):
    path = gguf_file(tmp_path, {'llama.attention.key_length': 256, 'llama.attention.value_length': 64})
    result = resources.assess_model(path, 2048, memory())
    assert result['kv_cache_bytes'] == 32 * 8 * (256 + 64) * 2 * 2048 * 1.25


def test_per_layer_attention_head_arrays_are_read(tmp_path):
    path = gguf_file(tmp_path, {'llama.block_count': 2, 'llama.attention.head_count': [32, 32],
                                'llama.attention.head_count_kv': [8, 4]})
    result = resources.assess_model(path, 2048, memory())
    assert result['allowed']
    assert result['kv_cache_bytes'] == (8 + 4) * 256 * 2 * 2048 * 1.25


def test_unknown_architecture_gets_explicit_conservative_fallback(tmp_path):
    path = gguf_file(tmp_path, {'general.architecture': 'future_arch'})
    result = resources.assess_model(path, 2048, memory())
    assert result['allowed']
    assert result['estimation'] == 'conservative_fallback'
    assert result['kv_cache_bytes'] >= 2048 * MIB
    assert 'fallback' in result['note']


@pytest.mark.parametrize('changes', [
    {'llama.block_count': -1}, {'llama.embedding_length': 0},
    {'llama.attention.head_count': 3}, {'llama.attention.head_count_kv': 64},
    {'llama.attention.key_length': '128'}, {'llama.context_length': -100},
    {'llama.attention.head_count_kv': []}, {'llama.attention.head_count_kv': [8]},
    {'general.architecture': 123},
])
def test_invalid_metadata_fails_closed(tmp_path, changes):
    result = resources.assess_model(gguf_file(tmp_path, changes), 2048, memory())
    assert not result['allowed']
    assert result['estimated_bytes'] is None
    assert 'failed' in result['reason']


@pytest.mark.parametrize('payload', [b'not a model', b'GGUF', b'GGUF' + struct.pack('<IQQ', 3, 1, 1)])
def test_invalid_and_truncated_headers_fail_closed(tmp_path, payload):
    path = tmp_path / 'bad.gguf'
    path.write_bytes(payload)
    result = resources.assess_model(path, 2048, memory())
    assert not result['allowed'] and result['estimated_bytes'] is None


def test_truncated_metadata_and_missing_tensor_directory_fail_closed(tmp_path):
    path = gguf_file(tmp_path)
    data = path.read_bytes()
    for removed in (64, 70):
        path.write_bytes(data[:-removed])
        result = resources.assess_model(path, 2048, memory())
        assert not result['allowed'] and 'Truncated' in result['reason']


@pytest.mark.parametrize('changes,filename', [
    ({'split.count': 2}, 'model.gguf'), ({}, 'model-00001-of-00003.gguf'),
    ({'general.architecture': 'clip'}, 'projector.gguf'), ({}, 'mmproj-model.gguf'),
    ({}, 'mtp-model.gguf'), ({'general.type': 'adapter'}, 'model.gguf'),
])
def test_auxiliary_and_split_models_cannot_bypass_file_weight_check(tmp_path, changes, filename):
    result = resources.assess_model(gguf_file(tmp_path, changes, filename), 2048, memory())
    assert not result['allowed'] and result['estimated_bytes'] is None


def test_unknown_ram_blocks_loading(tmp_path, monkeypatch):
    def unavailable():
        raise OSError('No memory data')
    monkeypatch.setattr(resources.psutil, 'virtual_memory', unavailable)
    snapshot = resources.memory_snapshot()
    assert snapshot['budget_bytes'] == 0
    assert 'blocked' in snapshot['note']
    assert not resources.assess_model(gguf_file(tmp_path), 2048, snapshot)['allowed']


def test_current_available_ram_is_used_and_system_reserve_preserved(monkeypatch):
    monkeypatch.setattr(resources.psutil, 'virtual_memory', lambda: SimpleNamespace(total=8 * GIB, available=3 * GIB))
    monkeypatch.setattr(resources, '_cgroup_limits', lambda: iter(()))
    snapshot = resources.memory_snapshot()
    assert snapshot['reserve_bytes'] == GIB
    assert snapshot['budget_bytes'] == 2 * GIB
    assert snapshot['recommended']['gpu_layers'] == 0


@pytest.mark.parametrize('version', [1, 2])
def test_cgroup_limit_and_usage_cap_host_memory(monkeypatch, version):
    directory = '/sys/fs/cgroup' if version == 2 else '/sys/fs/cgroup/memory'
    limit = 'memory.max' if version == 2 else 'memory.limit_in_bytes'
    usage = 'memory.current' if version == 2 else 'memory.usage_in_bytes'
    files = {f'{directory}/{limit}': str(4 * GIB), f'{directory}/{usage}': str(GIB)}
    monkeypatch.setattr(resources.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(resources, '_read_text', lambda path: files.get(Path(path).as_posix()))
    monkeypatch.setattr(resources.psutil, 'virtual_memory', lambda: SimpleNamespace(total=32 * GIB, available=20 * GIB))
    snapshot = resources.memory_snapshot()
    assert snapshot['ram_total'] == 4 * GIB
    assert snapshot['ram_available'] == 3 * GIB
    assert snapshot['budget_bytes'] == 2 * GIB
    assert 'container' in snapshot['note']


def test_nested_cgroup_parent_limit_is_honoured(monkeypatch):
    files = {
        '/proc/self/cgroup': '0::/tenant/service',
        '/proc/self/mountinfo': '21 20 0:20 / /sys/fs/cgroup rw - cgroup2 cgroup rw',
        '/sys/fs/cgroup/memory.max': 'max',
        '/sys/fs/cgroup/tenant/memory.max': str(4 * GIB),
        '/sys/fs/cgroup/tenant/memory.current': str(2 * GIB),
        '/sys/fs/cgroup/tenant/service/memory.max': str(8 * GIB),
        '/sys/fs/cgroup/tenant/service/memory.current': str(GIB),
    }
    monkeypatch.setattr(resources.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(resources, '_read_text', lambda path: files.get(Path(path).as_posix()))
    monkeypatch.setattr(resources.psutil, 'virtual_memory', lambda: SimpleNamespace(total=32 * GIB, available=20 * GIB))
    snapshot = resources.memory_snapshot()
    assert snapshot['ram_total'] == 4 * GIB
    assert snapshot['ram_available'] == 2 * GIB
    assert snapshot['budget_bytes'] == GIB


def test_known_cgroup_limit_without_usage_fails_closed(monkeypatch):
    monkeypatch.setattr(resources.psutil, 'virtual_memory', lambda: SimpleNamespace(total=32 * GIB, available=20 * GIB))
    monkeypatch.setattr(resources, '_cgroup_limits', lambda: iter([(4 * GIB, None)]))
    assert resources.memory_snapshot()['budget_bytes'] == 0


def test_unreadable_cgroup_cap_does_not_fall_back_to_host_memory(monkeypatch):
    def denied(self, *args, **kwargs):
        if self.as_posix() == '/sys/fs/cgroup/memory.max':
            raise PermissionError('Cannot read container limit')
        raise FileNotFoundError(str(self))

    monkeypatch.setattr(Path, 'read_text', denied)
    monkeypatch.setattr(resources.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(resources.psutil, 'virtual_memory', lambda: SimpleNamespace(total=32 * GIB, available=20 * GIB))
    assert resources.memory_snapshot()['budget_bytes'] == 0


@pytest.mark.parametrize('unreadable', ['/proc/self/cgroup', '/proc/self/mountinfo'])
def test_unreadable_cgroup_discovery_does_not_ignore_nested_caps(monkeypatch, unreadable):
    files = {'/proc/self/cgroup': '0::/tenant/service',
             '/proc/self/mountinfo': '21 20 0:20 / /sys/fs/cgroup rw - cgroup2 cgroup rw',
             '/sys/fs/cgroup/memory.max': 'max'}

    def read(self, *args, **kwargs):
        name = self.as_posix()
        if name == unreadable:
            raise PermissionError('Cannot discover process cgroup')
        if name in files:
            return files[name]
        raise FileNotFoundError(name)

    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(resources.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(resources.psutil, 'virtual_memory', lambda: SimpleNamespace(total=32 * GIB, available=20 * GIB))
    assert resources.memory_snapshot()['budget_bytes'] == 0


def test_inspection_retains_resource_metadata(tmp_path):
    metadata = inspect_gguf(gguf_file(tmp_path, {'split.count': 1}))['metadata']
    assert metadata['llama.attention.head_count_kv'] == 8
    assert metadata['llama.block_count'] == 32
    assert metadata['split.count'] == 1
