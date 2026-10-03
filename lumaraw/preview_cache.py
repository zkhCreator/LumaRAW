"""Completed, bounded preview receipts reusable without an image worker.

Inputs: captured render requests, engine/backend identity and disposable artifacts.
Outputs: atomically published receipts or fully validated cached preview replies.
The broker hashes bounded files in chunks; it never imports image/pixel libraries.
Keys include source/asset stat identities and every render option, never client IDs
or catalog revisions. Callers must recheck revisions and cancellation on return.
Cache loss/corruption is a miss, not a catalog failure. No original writes or SQL.
Cached replies report unused filter stages and zero new work, never old timings.
"""
import hashlib
from contextlib import nullcontext
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import time

from .source_identity import fingerprint

VERSION = 1
MAX_RECEIPT = 128 * 1024
MAX_PIXELS = 2048 * 1536
MAX_ARTIFACT_BYTES = 320 * 1024**2
NAME = re.compile(r'[0-9a-f]{64}(?:-before)?\.(?:png|tones|mixer|readouts)')
MAPS = {'curve_tones': (b'LRTONE1\0', 4),
        'mixer_target': (b'LRMIX1\0\0', 16),
        'color_readouts': (b'LRCOL1\0\0', 24),
        'before_color_readouts': (b'LRCOL1\0\0', 24)}
FIELDS = {'preview', 'before', 'metadata', 'histogram', 'clipped_percent',
          'width', 'height', 'full_width', 'full_height', 'detail', 'roi',
          'geometry', 'image_width', 'image_height', 'before_cache_hit', *MAPS}


class ArtifactChanged(Exception):
    """A concurrent atomic replacement is a miss, not evidence of corruption."""


def key(request, engine, backend):
    """None means an external input is missing and ordinary rendering must fail."""
    try:
        recipe = request.get('recipe', {})
        before = request.get('before_recipe') if request.get('include_before', True) else None
        display = request.get('display') or {}
        assets = [fingerprint(r['lut']['path']) for r in (recipe, before)
                  if r and r.get('lut')]
        if display.get('proof_path'):
            assets.append(fingerprint(display['proof_path']))
        options = {name: request.get(name, default) for name, default in (
            ('orientation', 0), ('detail', None), ('max_edge', None),
            ('include_before', True), ('include_color_readouts', False),
            ('include_curve_tones', False), ('mixer_target', None))}
        payload = [VERSION, engine, backend, fingerprint(request['path']),
                   recipe, before, display, options, assets]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    except (OSError, ValueError):
        return None


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _validate(result, request):
    width, height = result['width'], result['height']
    if not (_integer(width, 1, 2048) and _integer(height, 1, 2048) and width*height <= MAX_PIXELS):
        raise ValueError('Invalid cached preview dimensions')
    fw, fh = result['full_width'], result['full_height']
    if not (_integer(fw, width, 250000000) and _integer(fh, height, 250000000) and fw*fh <= 250000000):
        raise ValueError('Invalid cached image dimensions')
    histogram = result['histogram']
    if not (isinstance(histogram, list) and len(histogram) == 3 and
            all(isinstance(row, list) and len(row) == 64 and
                all(_integer(n, 0, width*height) for n in row) and sum(row) == width*height for row in histogram)):
        raise ValueError('Invalid cached histogram')
    clipped = result['clipped_percent']
    if type(clipped) not in (int, float) or not math.isfinite(clipped) or not 0 <= clipped <= 100:
        raise ValueError('Invalid cached gamut value')
    if not isinstance(result['metadata'], dict):
        raise ValueError('Invalid cached metadata')
    detail = bool(request.get('detail'))
    if result['detail'] is not detail:
        raise ValueError('Invalid cached viewport mode')
    roi = result['roi']
    if detail:
        if not (isinstance(roi, list) and len(roi) == 4 and roi[2:] == [width, height]
                and _integer(roi[0], 0, fw-width) and _integer(roi[1], 0, fh-height)):
            raise ValueError('Invalid cached viewport')
    elif roi is not None:
        raise ValueError('Unexpected cached viewport')
    geometry = result['geometry']
    crop = geometry['crop_box']
    if geometry['orientation'] != request.get('orientation', 0) or not (
            isinstance(crop, list) and len(crop) == 4 and
            all(type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1 for n in crop)):
        raise ValueError('Invalid cached geometry')
    expected = {'before': request.get('include_before', True),
                'color_readouts': request.get('include_color_readouts', False),
                'before_color_readouts': request.get('include_before', True) and request.get('include_color_readouts', False),
                'curve_tones': request.get('include_curve_tones', False),
                'mixer_target': bool(request.get('mixer_target'))}
    for name, required in expected.items():
        if (name in result) != bool(required):
            raise ValueError('Cached preview lacks requested output')
    if expected['color_readouts']:
        iw, ih = result['image_width'], result['image_height']
        if not (_integer(iw, 1, 250000000) and _integer(ih, 1, 250000000) and iw*ih <= 250000000):
            raise ValueError('Invalid cached full image dimensions')
    for name in MAPS:
        if name in result and (result[name]['width'], result[name]['height']) != (width, height):
            raise ValueError('Invalid cached map dimensions')


def _paths(result, cache, saving=False):
    """Rebase only recognized artifact paths; never accept traversal or symlinks."""
    entries = {}
    for role in ('preview', 'before', *MAPS):
        if role not in result:
            continue
        parent, field = (result[role], 'path') if role in MAPS else (result, role)
        original = Path(parent[field])
        name = original.name
        if not NAME.fullmatch(name) or (not saving and str(original) != name):
            raise ValueError('Invalid cached artifact name')
        if saving and original.parent.resolve() != cache.resolve():
            raise ValueError('Artifact is outside preview cache')
        path = cache/name
        parent[field] = name if saving else str(path)
        entries[name] = (path, role)
    return entries


def _digest(path, role, width, height, checkpoint):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Cached artifact is not a regular file')
    expected = 16+width*height*MAPS[role][1] if role in MAPS else None
    if expected is not None and before.st_size != expected:
        raise ValueError('Invalid cached map length')
    if expected is None and not 45 <= before.st_size <= 32*1024**2:
        raise ValueError('Invalid cached PNG length')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        # LRU touches may change mtime during another reader's checksum. Contents
        # are checked in full; atomic replacements change inode, not just mtime.
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size)
        if identity(opened) != identity(before):
            raise ArtifactChanged()
        header = stream.read(24)
        if role in MAPS:
            if header[:16] != MAPS[role][0]+struct.pack('<II', width, height):
                raise ValueError('Invalid cached map header')
        elif header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR' or header[16:24] != struct.pack('>II', width, height):
            raise ValueError('Invalid cached PNG header')
        digest = hashlib.sha256(header)
        total = len(header)
        while chunk := stream.read(1024*1024):
            checkpoint()
            total += len(chunk)
            if total > before.st_size:
                raise ArtifactChanged()
            digest.update(chunk)
        if identity(os.fstat(stream.fileno())) != identity(before) or identity(path.lstat()) != identity(before):
            raise ArtifactChanged()
    return {'bytes': before.st_size, 'sha256': digest.hexdigest()}


def save(cache, cache_key, request, result):
    """Receipt failure cannot turn a successfully rendered preview into failure."""
    if cache_key is None:
        return None
    cache = Path(cache)
    try:
        receipt = json.loads(json.dumps({k: v for k, v in result.items() if k in FIELDS}, allow_nan=False))
        _validate(receipt, request)
        entries = _paths(receipt, cache, saving=True)
        assets = {name: _digest(path, role, receipt['width'], receipt['height'], lambda: None)
                  for name, (path, role) in entries.items()}
        if sum(a['bytes'] for a in assets.values()) > MAX_ARTIFACT_BYTES:
            return None
        data = json.dumps({'version': VERSION, 'key': cache_key, 'result': receipt, 'assets': assets}, allow_nan=False).encode()
        if len(data) > MAX_RECEIPT:
            return None
        target = cache/(cache_key+'.preview.json')
        fd, name = tempfile.mkstemp(dir=cache, prefix='.preview-receipt-', suffix='.part')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
        return str(target)
    except (OSError, ValueError, KeyError, TypeError, RecursionError, ArtifactChanged):
        return None


def load(cache, cache_key, request, backend, checkpoint=lambda: None, repair_lock=None):
    if cache_key is None:
        return None
    started = time.perf_counter()
    cache = Path(cache)
    target = cache/(cache_key+'.preview.json')
    try:
        checkpoint()
        if target.is_symlink() or not 0 < target.stat().st_size <= MAX_RECEIPT:
            return None
        with target.open('rb') as stream:
            data = stream.read(MAX_RECEIPT+1)
        if len(data) > MAX_RECEIPT:
            return None
        saved = json.loads(data)
        if saved['version'] != VERSION or saved['key'] != cache_key:
            return None
        result = saved['result']
        if not isinstance(result, dict) or set(result)-FIELDS:
            return None
        _validate(result, request)
        entries = _paths(result, cache)
        assets = saved['assets']
        if set(assets) != set(entries) or sum(a['bytes'] for a in assets.values()) > MAX_ARTIFACT_BYTES:
            return None
        for name, (path, role) in entries.items():
            try:
                valid = _digest(path, role, result['width'], result['height'], checkpoint) == assets[name]
            except InterruptedError:
                raise
            except (OSError, ValueError):
                valid = False
            if not valid:
                # Worker map caches predate full checksums and inspect headers.
                # Remove this receipt's disposable maps so a miss cannot bless
                # a damaged body as new data. Never unlink images or originals.
                # Repairs serialize with writers, but successful reads never
                # wait for an active export/preview. No catalog lock is held.
                with repair_lock if repair_lock is not None else nullcontext():
                    checkpoint()
                    for map_path, map_role in entries.values():
                        if map_role in MAPS:
                            try:map_path.unlink(missing_ok=True)
                            except OSError as error:
                                raise RuntimeError('Cannot repair preview maps; check catalog cache permissions') from error
                return None
        checkpoint()
        for path, _ in entries.values():
            os.utime(path, None)
        os.utime(target, None)
        result.update(cache_keep=[str(target), *[str(p) for p, _ in entries.values()]],
                      ok=True, preview_cache_hit=True, worker_spawned=False, peak_mb=0)
        if 'before' in result:
            result['before_cache_hit'] = True
        for role in MAPS:
            if role in result:
                result[role]['cache_hit'] = True
        result['processing'] = {'backend': 'cache', 'requested': backend, 'device': None,
            'metal_grade_tiles': 0, 'metal_output_tiles': 0, 'metal_readout_tiles': 0,
            'cpu_tiles': 0, 'cpu_readout_tiles': 0, 'cpu_readout_output_tiles': 0,
            'worker_seconds': 0, 'shared_buffer_peak_mb': 0, 'fallback_reasons': [],
            'gpu_seconds': 0, 'dispatch_seconds': 0, 'initialization_seconds': 0,
            'presence_metal_gaussian_filters': 0, 'presence_metal_gaussian_passes': 0,
            'presence_cpu_gaussian_filters': 0, 'presence_gaussian_gpu_seconds': 0,
            'presence_gaussian_dispatch_seconds': 0, 'presence_gaussian_backend': 'unused',
            'presence_other_operations_backend': 'unused',
            'cache_lookup_seconds': round(time.perf_counter()-started, 6)}
        return result
    except InterruptedError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError, ArtifactChanged):
        return None
