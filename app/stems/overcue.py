# SPDX-License-Identifier: MPL-2.0
"""Experimental OverCue export. Separation stays in the existing engine.

The USB holds the public seven-role 96 kHz format, never RX3-rate PGZ files.
The standalone CLI deliberately does not change the app's default export.
"""
from __future__ import annotations

import argparse
import array
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from app.stems import processes

ROLES = ('vocal', 'instrumental', 'drums', 'harmonics',
         'vocals-drums', 'vocals-harmonics', 'full-mix')
MASKS = (2, 5, 4, 1, 6, 3, 7)
PAGE_BYTES = 131072
MAX_FRAMES = 4096 * PAGE_BYTES // 4


def _safe(root, relative):
    parts = Path(relative).parts
    if not relative.startswith('/') or any(p in ('.', '..') for p in relative.split('/')[1:]):
        raise ValueError('Expected an absolute USB-relative path without dot components')
    path = root
    for part in parts[1:]:
        path /= part
        if path.is_symlink():
            raise ValueError('Symbolic links are not accepted')
    if not path.is_relative_to(root):
        raise ValueError('Path escapes USB')
    return path


def _hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_role(raw, output):
    """Page and hash already prepared stereo s16le at 96 kHz."""
    size = raw.stat().st_size
    if not size or size % 4 or size // 4 > MAX_FRAMES:
        raise ValueError('Invalid OverCue PCM length')
    count = (size + PAGE_BYTES - 1) // PAGE_BYTES
    header = b'OVPGZ001' + struct.pack('>IIQ', PAGE_BYTES, count, size)
    table = bytearray(count * 48)
    pcm_hash = hashlib.sha256()
    with raw.open('rb') as source, output.open('w+b') as target:
        target.write(header + table)
        for page in range(count):
            processes.checkpoint()
            data = source.read(PAGE_BYTES)
            compressed = zlib.compress(data)
            struct.pack_into('>QII32s', table, page * 48, target.tell(),
                             len(compressed), len(data), hashlib.sha256(data).digest())
            target.write(compressed)
            pcm_hash.update(data)
        target.seek(24)
        target.write(table)
        target.flush()
        os.fsync(target.fileno())
    return pcm_hash.hexdigest(), hashlib.sha256(header + table).hexdigest()


def publish(root, media_path, track_id, pcm, *, provenance=None, waveforms=None):
    """Publish immutable bundle files first and the complete index last.

    A failed export can leave an unreferenced bundle, never a referenced
    partially written one. Existing music, databases and analyses are untouched.
    """
    root = Path(root).resolve()
    source = _safe(root, media_path)
    if not str(track_id).isdecimal() or not source.is_file() or set(pcm) != set(ROLES):
        raise ValueError('Exact exported track, library ID and all seven roles required')
    sizes = {Path(p).stat().st_size for p in pcm.values()}
    if len(sizes) != 1:
        raise ValueError('Selections must have the same frame count')
    size = sizes.pop()
    mods = _safe(root, '/CDJMODS')
    stems = _safe(root, '/CDJMODS/stems')
    index = _safe(root, '/CDJMODS/index.json')
    stems.mkdir(parents=True, exist_ok=True)
    # A lock prevents this writer from losing concurrent index updates.
    lock = mods / '.rx3-export.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if index.exists() and index.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('OverCue index exceeds 4 MiB')
        data = json.loads(index.read_text()) if index.exists() else {
            'schema': 'overcue-index/1', 'keyed_by': 'export.pdb',
            'tracks': {}, 'tracks_onelibrary': {}}
        if data.get('schema') != 'overcue-index/1' or not all(
                isinstance(data.get(k, {}), dict) for k in ('tracks', 'tracks_onelibrary')):
            raise ValueError('Unsupported existing index')
        previous = data.setdefault('tracks', {}).get(str(track_id))
        if previous and previous.get('file_path') != media_path:
            raise ValueError('Library ID already belongs to another track')
        with tempfile.TemporaryDirectory(prefix='.rx3-export-', dir=stems) as temporary:
            stage = Path(temporary)
            entry = {'file_path': media_path, 'frames': size // 4, 'three_part': 1,
                     'page_bytes': PAGE_BYTES, 'source_sha256': _hash(source),
                     'separation': 'manual/rx3-toolkit/prepared-stems/1',
                     'loudness_policy': ('full-mix-ceiling/2'
                                         if provenance and provenance.get('loudness_implementation') in
                                         ('rx3-toolkit/ffmpeg-ceiling/1', 'rx3-toolkit/native-ceiling/1')
                                         else 'precomputed/1')}
            for role in ROLES:
                digest, table = write_role(Path(pcm[role]), stage / f'stems-sidecar-{role}.s16le.pgz')
                name = role.replace('-', '_')
                entry[f'{name}_sha256'] = digest
                entry[f'{name}_page_table_sha256'] = table
            identity = 'three-part/1:' + ':'.join(entry[f'{r.replace("-", "_")}_sha256'] for r in ROLES)
            entry['bundle'] = hashlib.sha256(identity.encode()).hexdigest()[:16]
            for role, waveform in (waveforms or {}).items():
                if role not in ROLES[:-1]:
                    raise ValueError('Unexpected preview waveform role')
                shutil.copyfile(waveform, stage / f'stems-{role}-waveform.EXT')
            manifest = {'schema': 'overcue-stems/4',
                        'created': datetime.now(timezone.utc).isoformat(),
                        'runtime': {'sample_rate': 96000, 'channels': 2, 'format': 's16le',
                                    'frames': size // 4, 'page_bytes': PAGE_BYTES,
                                    'latency_pad_frames': 0},
                        'source': {'name': source.name, 'sha256': entry['source_sha256']},
                        'roles': {r: {'bytes': size, 'loudness_gain': (provenance or {}).get('role_gains', {}).get(r, 1.),
                                     'sha256': entry[f'{r.replace("-", "_")}_sha256'],
                                     'page_table_sha256': entry[f'{r.replace("-", "_")}_page_table_sha256']}
                                  for r in ROLES},
                        'waveforms': [f'stems-{r}-waveform.EXT' for r in (waveforms or {})], 'bundle': entry['bundle'],
                        'loudness_policy': entry['loudness_policy'],
                        'track_ids': [int(track_id)], 'writer': 'rx3-toolkit-prototype',
                        'processing': provenance or {},
                        'headroom': (provenance or {}).get('common_gain', 1.)}
            (stage / 'overcue-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            target = _safe(root, '/CDJMODS/stems/' + entry['bundle'])
            if target.exists():
                if any(_hash(target / p.name) != _hash(p) for p in stage.glob('*.pgz')):
                    raise ValueError('Existing bundle differs')
                for derived in [*stage.glob('*.EXT'), stage / 'overcue-manifest.json']:
                    descriptor, name = tempfile.mkstemp(prefix='.rx3-derived-', dir=target)
                    temporary_derived = Path(name)
                    try:
                        with os.fdopen(descriptor, 'wb') as stream:
                            stream.write(derived.read_bytes())
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary_derived, target / derived.name)
                    finally:
                        temporary_derived.unlink(missing_ok=True)
            else:
                os.rename(stage, target)
                stage.mkdir()  # TemporaryDirectory still owns its original path.
            for table in ('tracks', 'tracks_onelibrary'):
                for key, old in data.get(table, {}).items():
                    if old.get('file_path') == media_path:
                        data[table][key] = dict(old, **entry)
            data['tracks'][str(track_id)] = dict(previous or {}, **entry)
            encoded = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
            if len(encoded) > 4 * 1024 * 1024:
                raise ValueError('OverCue index exceeds 4 MiB')
            descriptor, name = tempfile.mkstemp(prefix='.rx3-index-', dir=mods)
            tmp = Path(name)
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                processes.checkpoint()
                os.replace(tmp, index)
            finally:
                tmp.unlink(missing_ok=True)
            return entry
    finally:
        lock.unlink(missing_ok=True)


def write_preview(pcm, output, *, ffmpeg='ffmpeg'):
    """Write RGB analysis for Desktop from the exact final role PCM.

    Only the PWV5 detail block is included. This does not claim full CDJ
    analysis support (overview, three-band, beat grid and cue blocks).
    """
    from app.stems import wave_dsp
    with tempfile.TemporaryDirectory(prefix='rx3-overcue-wave-') as directory:
        floating = Path(directory) / 'wave.f32'
        processes.run([ffmpeg, '-v', 'error', '-nostdin', '-y', '-f', 's16le',
                        '-ar', '96000', '-ac', '2', '-i', str(pcm), '-ar', '44100',
                        '-f', 'f32le', str(floating)], check=True)
        frames = floating.stat().st_size // 8
        count = (frames + 293) // 294
        columns = wave_dsp.columns(floating, frames, b'PWV5', count, ffmpeg)
        chunk = struct.pack('>4sIIIII', b'PWV5', 24, 24+len(columns), 2, count, 0x00960305) + columns
        header = struct.pack('>4sIIIIII', b'PMAI', 28, 28+len(chunk), 1, 0x10000, 0x10000, 0)
        output.write_bytes(header+chunk)
    return output


def export_package(root, media_path, track_id, container, *, ffmpeg='ffmpeg', native=None, checkpoint=processes.checkpoint):
    """Export a verified current vocal+drums package without separating again."""
    from app.stems import audition, package, stem, safety
    checkpoint()
    root = Path(root).resolve()
    source = _safe(root, media_path)
    info = package.read(Path(container))
    if tuple(info['roles']) != ('vocals', 'drums'):
        raise ValueError('This prototype requires a vocal+drums package')
    before = safety.source_stamp(source)
    if before[2] != info['manifest']['source_sha256']:
        raise ValueError('The package belongs to a different source')
    # Lossy encoder delay needs a measured cross-player contract. Keep initial
    # physical acceptance on PCM sources instead of silently guessing a pad.
    if source.suffix.lower() not in ('.wav', '.aif', '.aiff', '.flac'):
        raise ValueError('Prototype export requires a lossless source; lossy timing is not validated')
    def run(*args):
        checkpoint()
        processes.run([ffmpeg, '-v', 'error', '-nostdin', '-y', *map(str, args)], check=True)
    with tempfile.TemporaryDirectory(prefix='rx3-overcue-') as directory:
        work = Path(directory)
        original = work / 'original.f32'
        run(*stem.UNTRIMMED, '-i', source, '-map', '0:a:0', '-vn', '-ar', 44100,
            '-ac', 2, '-f', 'f32le', original)
        if original.stat().st_size != info['frames'] * 8:
            raise ValueError('Source and package timelines differ')
        gains = []
        for number, member in enumerate(info['members'][:2]):
            with member.open() as incoming, (work / f'{number}.s16').open('wb') as outgoing:
                header = stem.HEADER.unpack(incoming.read(64))
                gains.append(audition.pcm_gain(header[3], header[6]))
                shutil.copyfileobj(incoming, outgoing)
        floating = {}
        peak = 0.
        for role, mask in zip(ROLES, MASKS):
            checkpoint()
            residual = int(bool(mask & 1))
            weights = (residual, (int(bool(mask & 2)) - residual) * gains[0],
                       (int(bool(mask & 4)) - residual) * gains[1])
            output = work / (role + '.f32')
            filters = ';'.join(f'[{i}:a]volume={w:.17g}:precision=float[a{i}]'
                               for i, w in enumerate(weights))
            filters += ';[a0][a1][a2]amix=inputs=3:normalize=0:duration=first'
            if not native:
                filters += ',aresample=96000'
            mixed = work / (role + '-44.f32') if native else output
            run('-f', 'f32le', '-ar', 44100, '-ac', 2, '-i', original,
                '-f', 's16le', '-ar', 44100, '-ac', 2, '-i', work / '0.s16',
                '-f', 's16le', '-ar', 44100, '-ac', 2, '-i', work / '1.s16',
                '-filter_complex', filters, '-f', 'f32le', mixed)
            if native:
                peak = max(peak, native.resample(mixed, output))
                mixed.unlink()
            with output.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    checkpoint()
                    values = array.array('f', block)
                    if os.sys.byteorder != 'little': values.byteswap()
                    if not all(map(math.isfinite, values)):
                        raise ValueError('Nonfinite prepared PCM')
                    peak = max(peak, max(map(abs, values), default=0))
            floating[role] = output
        from app.stems import overcue_loudness
        if native:
            common_gain, role_gains = native.gains(floating, peak)
        else:
            measurements = {r: overcue_loudness.measure(p, ffmpeg=ffmpeg) for r, p in floating.items()}
            peak = max(peak, *(m.peak for m in measurements.values()))
            common_gain = min(1., .95 / peak) if peak else 1.
            role_gains = overcue_loudness.gains(measurements, common_gain)
        pcm = {}
        for role, incoming in floating.items():
            checkpoint()
            pcm[role] = work / (role + '.s16')
            if native:
                native.quantize(incoming, pcm[role], common_gain, role_gains[role])
            else:
                run('-f', 'f32le', '-ar', 96000, '-ac', 2, '-i', incoming,
                    '-af', f'volume={common_gain * role_gains[role]:.17g}:precision=double', '-f', 's16le', pcm[role])
        waveforms = {}
        for role in ROLES[:-1]:
            checkpoint()
            waveforms[role] = write_preview(pcm[role], work / (role + '.EXT'), ffmpeg=ffmpeg)
        checkpoint()
        safety.check_source(source, before)
        return publish(root, media_path, track_id, pcm, waveforms=waveforms, provenance={
            'source_package_sha256': _hash(Path(container)),
            'common_gain': common_gain, 'role_gains': role_gains,
            'loudness_implementation': ('rx3-toolkit/native-ceiling/1' if native
                                        else 'rx3-toolkit/ffmpeg-ceiling/1'),
            **({'resampler_coefficients_sha256': _hash(native.coefficients)} if native else {}),
            'measurement_rate': 96000, 'measurement_step_frames': 9600,
            'separation_reused': True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drive', type=Path, required=True)
    parser.add_argument('--track', required=True, help='Exact USB-relative path, starting with /')
    parser.add_argument('--track-id', required=True, help='Matching export.pdb ID')
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--native-helper', type=Path, help='Experimental rx3-overcue-audio executable')
    parser.add_argument('--coefficients', type=Path, help='Validated local 44.1 to 96 kHz profile')
    args = parser.parse_args()
    if args.coefficients and not args.native_helper:
        parser.error('--coefficients requires --native-helper')
    native = None
    if args.native_helper:
        from app.stems.overcue_exact import NativePreparation
        native = NativePreparation(args.native_helper, args.coefficients)
    print(json.dumps(export_package(args.drive, args.track, args.track_id, args.package,
                                    native=native), indent=2))


if __name__ == '__main__':
    main()
