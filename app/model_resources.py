"""Conservative CPU memory admission estimates, not runtime/architecture guarantees.

Count all file bytes as resident weights. Runtime buffers use the largest of
512 MiB, 20% of weights, or a non-flash attention work-buffer estimate:
2 * context * min(context, 512) * maximum attention heads * 4 (FP32 bytes).
Standard attention metadata supplies FP16 K/V cache size with
25% headroom. Unknown/partial architectures use at least 1 MiB per context token
(scaled up for files over 8 GiB) or the larger metadata estimate. Reserve at
least 1 GiB / 10% of effective total RAM for other services. No swap or GPU credit
is granted. Only GGUF metadata is read; tensor payloads are never scanned.
"""
import math
import os
import platform
import re
from pathlib import Path

import psutil

from .machine import inspect_gguf

MIB = 1024**2
GIB = 1024**3
_STANDARD_ATTENTION = {
    'llama', 'qwen2', 'qwen2moe', 'qwen3', 'qwen3moe', 'phi2', 'phi3',
    'mistral', 'gemma', 'gemma2', 'gemma3', 'starcoder2',
}


def _read_text(path):
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        # None means absent; an empty value makes an unreadable cap fail closed.
        return ''


def _cgroup_directories():
    """Find current process groups and their parents, including nested limits."""
    groups = {('', Path('/sys/fs/cgroup')), ('memory', Path('/sys/fs/cgroup/memory'))}
    membership = _read_text('/proc/self/cgroup')
    mounts = _read_text('/proc/self/mountinfo')
    if membership == '' or mounts == '':
        raise OSError('Cannot establish current process cgroup limits.')
    membership, mounts = membership or '', mounts or ''
    for entry in membership.splitlines():
        parts = entry.split(':', 2)
        if len(parts) != 3:
            continue
        controllers, group = parts[1:]
        kind = '' if not controllers else 'memory' if 'memory' in controllers.split(',') else None
        if kind is None:
            continue
        for mount in mounts.splitlines():
            fields, separator, filesystem = mount.partition(' - ')
            fields, filesystem = fields.split(), filesystem.split()
            if not separator or len(fields) < 5 or len(filesystem) < 3:
                continue
            if not ((kind == '' and filesystem[0] == 'cgroup2') or
                    (kind == 'memory' and filesystem[0] == 'cgroup' and 'memory' in filesystem[2].split(','))):
                continue
            # mountinfo escapes whitespace; decode only its documented octal escapes.
            root, point = [re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), field)
                           for field in fields[3:5]]
            try:
                relative = Path(group).relative_to(root)
            except ValueError:
                # Namespaced cgroups may expose "/" as the process membership.
                if group != '/':
                    continue
                relative = Path('.')
            if '..' in relative.parts:
                continue
            boundary = Path(point)
            current = boundary / relative
            while True:
                groups.add((kind, current))
                if current == boundary:
                    break
                current = current.parent
    return groups


def _cgroup_limits():
    """Yield (hard limit, current usage or None); ignore unlimited sentinels."""
    if platform.system() != 'Linux':
        return
    try:
        directories = _cgroup_directories()
    except OSError:
        yield 0, None
        return
    for kind, directory in directories:
        limit_name, usage_name = ('memory.max', 'memory.current') if not kind else (
            'memory.limit_in_bytes', 'memory.usage_in_bytes')
        raw = _read_text(directory / limit_name)
        if raw is None or raw == 'max':
            continue
        try:
            limit = int(raw)
        except ValueError:
            # An existing, unreadable limit cannot establish an available budget.
            yield 0, None
            continue
        if limit >= 1 << 60:  # cgroup v1 uses a huge page-aligned unlimited value.
            continue
        try:
            usage = int(_read_text(directory / usage_name))
            if usage < 0:
                usage = None
        except (ValueError, TypeError):
            usage = None
        yield max(0, limit), usage


def memory_snapshot():
    """Read current physical memory and cgroup caps without probing GPU hardware."""
    note = 'RAM budget excludes a reserve for other services; GPU memory and swap are not counted.'
    try:
        memory = psutil.virtual_memory()
        total, available = int(memory.total), int(memory.available)
        if total <= 0 or not 0 <= available <= total:
            raise ValueError('Invalid memory readings')
    except (OSError, ValueError, TypeError, AttributeError, psutil.Error):
        total = available = 0
        note = 'Reliable available RAM could not be detected. Model loading is blocked.'
    if total:
        capped = False
        for limit, usage in _cgroup_limits():
            total = min(total, limit)
            available = min(available, max(0, limit - usage) if usage is not None else 0)
            capped = True
        if capped:
            note += ' Linux container hard limits are included.'
    reserve = max(GIB, math.ceil(total * 0.1)) if total else 0
    budget = max(0, available - reserve)
    try:
        cores = psutil.cpu_count(logical=False) or os.cpu_count() or 2
    except (OSError, ValueError, psutil.Error):
        cores = 2
    return {
        'ram_total': total, 'ram_available': available,
        'reserve_bytes': reserve, 'budget_bytes': budget,
        'recommended': {'context': 4096 if budget >= 8 * GIB else 2048,
                        'threads': max(1, min(cores, 8)), 'gpu_layers': 0},
        'note': note,
    }


def _positive_integer(value, name, maximum=1_000_000_000):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise ValueError(f'Invalid GGUF {name} metadata.')
    return value


def _cache_estimate(metadata, architecture, context):
    """Return standard full-attention FP16 cache bytes, or None for missing keys."""
    prefix = architecture + '.'
    fields = {}
    suffixes = ('block_count', 'embedding_length', 'attention.head_count',
                'attention.head_count_kv', 'attention.key_length', 'attention.value_length')
    for suffix in suffixes:
        if prefix + suffix in metadata:
            value = metadata[prefix + suffix]
            if suffix.startswith('attention.') and isinstance(value, list):
                if not value:
                    raise ValueError(f'Invalid GGUF {suffix} metadata.')
                fields[suffix] = [_positive_integer(item, suffix) for item in value]
            else:
                fields[suffix] = _positive_integer(value, suffix)
    if 'block_count' in fields:
        if fields['block_count'] > 4096:
            raise ValueError('Invalid GGUF block_count metadata.')
        for name, value in fields.items():
            if isinstance(value, list) and len(value) != fields['block_count']:
                raise ValueError(f'Invalid GGUF {name} layer count.')
    if not all(name in fields for name in ('block_count', 'embedding_length', 'attention.head_count')):
        return None
    layers = fields['block_count']
    embedding = fields['embedding_length']

    def per_layer(name, default):
        value = fields.get(name, default)
        if isinstance(value, list):
            if len(value) != layers:
                raise ValueError(f'Invalid GGUF {name} layer count.')
            return value
        return [value] * layers

    heads = per_layer('attention.head_count', None)
    kv_heads = per_layer('attention.head_count_kv', heads)
    keys = per_layer('attention.key_length', None)
    values = per_layer('attention.value_length', None)
    total = 0
    for head, kv, key, value in zip(heads, kv_heads, keys, values):
        if kv > head or head % kv:
            raise ValueError('Invalid GGUF attention head proportions.')
        if (key is None or value is None) and embedding % head:
            raise ValueError('Invalid GGUF attention dimensions.')
        key = embedding // head if key is None else key
        value = embedding // head if value is None else value
        total += 2 * kv * (key + value) * context  # Two bytes per FP16 scalar.
    return math.ceil(total * 1.25)


def _attention_work_buffer(metadata, architecture, context):
    """Allow two FP32 attention workspaces for the runtime's default 512 batch.

    Called only after _cache_estimate has validated any supplied head counts.
    Use the largest layer's head count because scratch is reused across layers.
    """
    heads = metadata.get(architecture + '.attention.head_count')
    if heads is None:
        return 0
    heads = max(heads) if isinstance(heads, list) else heads
    return 2 * context * min(context, 512) * heads * 4


def assess_model(path, context, snapshot=None):
    """Fail closed on unreadable GGUF, malformed dimensions or unknown RAM.

    A positive result is a conservative admission estimate. It does not validate
    backend architecture support or guarantee a load after memory use changes.
    """
    snapshot = memory_snapshot() if snapshot is None else snapshot
    budget = snapshot.get('budget_bytes', 0)
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        budget = 0
    total, available = snapshot.get('ram_total', 0), snapshot.get('ram_available', 0)
    if (isinstance(total, bool) or not isinstance(total, int) or total <= 0 or
            isinstance(available, bool) or not isinstance(available, int) or not 0 <= available <= total):
        budget = 0
    else:
        budget = min(budget, available)
    result = {'allowed': False, 'reason': '', 'estimated_bytes': None, 'model_bytes': 0,
              'budget_bytes': budget, 'context': context, 'estimation': None,
              'note': 'Memory estimate only; backend compatibility and actual allocations may differ.'}
    try:
        if isinstance(context, bool) or not isinstance(context, int) or context < 1 or context > 1_000_000_000:
            raise ValueError('Choose a valid positive context length.')
        path = Path(path)
        result['model_bytes'] = path.stat().st_size
        info = inspect_gguf(path)
        metadata = info['metadata']
        architecture = metadata.get('general.architecture')
        if not isinstance(architecture, str) or not architecture.strip():
            raise ValueError('Missing or invalid GGUF architecture metadata.')
        model_type = metadata.get('general.type', 'model')
        if not isinstance(model_type, str) or model_type not in ('model',):
            raise ValueError('This GGUF is an auxiliary component, not a standalone chat model.')
        if architecture in ('clip', 'mmproj', 'mtp') or re.match(r'^(mmproj|mtp)[-_.]', path.name, re.I):
            raise ValueError('Choose a standalone chat model; projector and MTP files cannot be loaded alone.')
        split_count = _positive_integer(metadata.get('split.count', 1), 'split.count')
        if split_count > 1 or re.search(r'-\d{5}-of-\d{5}\.gguf$', path.name, re.I):
            raise ValueError('Split GGUF models are not supported by this RAM check. Choose a single-file GGUF.')
        trained = metadata.get(architecture + '.context_length')
        if architecture + '.context_length' in metadata:
            trained = _positive_integer(trained, 'context_length')
        result['trained_context'] = trained
        cache = _cache_estimate(metadata, architecture, context)
        fallback = architecture not in _STANDARD_ATTENTION or cache is None
        if fallback:
            per_token = max(MIB, math.ceil(result['model_bytes'] / (8 * GIB)) * MIB)
            cache = max(cache or 0, per_token * context)
            result['estimation'] = 'conservative_fallback'
            result['note'] += ' Unknown or incomplete attention metadata: conservative context-memory fallback used.'
        else:
            result['estimation'] = 'metadata'
        attention_work = _attention_work_buffer(metadata, architecture, context)
        runtime = max(512 * MIB, math.ceil(result['model_bytes'] * 0.2), attention_work)
        result.update(kv_cache_bytes=cache, runtime_bytes=runtime, attention_work_bytes=attention_work,
                      estimated_bytes=result['model_bytes'] + runtime + cache)
        if trained is not None and context > trained:
            result['reason'] = f'Context {context:,} exceeds this model\'s trained context of {trained:,}. Reduce context.'
        elif budget <= 0:
            result['reason'] = 'No reliable RAM budget is available. Close other applications or check system memory detection.'
        elif result['estimated_bytes'] > budget:
            result['reason'] = (f'Estimated RAM needed is {result["estimated_bytes"] / GIB:.2f} GiB; '
                                f'{budget / GIB:.2f} GiB is available after the system reserve. '
                                'Choose a smaller model, reduce context, or free memory.')
        else:
            result['allowed'] = True
            result['reason'] = 'Fits the current RAM budget at this context; actual runtime memory may vary.'
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        result['reason'] = f'Model resource check failed: {exc}'
    return result
