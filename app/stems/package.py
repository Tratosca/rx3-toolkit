# SPDX-License-Identifier: MPL-2.0
"""Versioned, indexed .rx3stem packages. Only complete packages are published."""
from __future__ import annotations

import io
import json
import pathlib
import shutil
import struct
import tempfile
import zlib
from dataclasses import dataclass

from app.stems import limits, safety, stem

MAGIC = b'RX3PKG2\0'
HEADER = struct.Struct('<8sIIIIQQ24s')
ENTRY = struct.Struct('<IIQQII32s')
PCM, WAVE, MANIFEST = 1, 2, 3
ROLE_BITS = {'vocals': 2, 'drums': 4, 'bass': 8}
MAX_BYTES = limits.RESIDENT_BYTES


class Slice(io.BufferedIOBase):
    def __init__(self, path, offset, length):
        self.source = path.open('rb')
        self.offset, self.length, self.position = offset, length, 0
        self.source.seek(offset)

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def read(self, size=-1):
        size = self.length - self.position if size < 0 else min(size, self.length - self.position)
        data = self.source.read(max(0, size))
        self.position += len(data)
        return data
    def seek(self, offset, whence=0):
        position = offset + (self.position if whence == 1 else self.length if whence == 2 else 0)
        if whence not in (0, 1, 2) or not 0 <= position <= self.length:
            raise ValueError('package seek')
        self.source.seek(self.offset + position)
        self.position = position
        return position
    def close(self):
        self.source.close()
        super().close()


@dataclass(frozen=True)
class Member:
    path: pathlib.Path
    kind: int
    role: int
    offset: int
    length: int
    crc: int
    name: str

    @property
    def parent(self): return self.path.parent
    def is_symlink(self): return self.path.is_symlink()
    def open(self, mode='rb'):
        if mode != 'rb': raise ValueError('read-only package member')
        return Slice(self.path, self.offset, self.length)
    def stat(self):
        from types import SimpleNamespace
        return SimpleNamespace(st_size=self.length, st_mtime_ns=self.path.stat().st_mtime_ns)


def is_package(path):
    with path.open('rb') as source:
        return source.read(8) == MAGIC


def checksum(path):
    crc = 0
    with path.open('rb') as source:
        while block := source.read(1024 * 1024):
            crc = zlib.crc32(block, crc)
    return crc


def read(path, *, verify=True):
    """Reject unknown, overlapping, truncated, duplicated or inconsistent entries."""
    from app.stems import audition, waveform
    safety.check_target(path)
    size = path.stat().st_size
    with path.open('rb') as source:
        magic, version, hs, count, es, total, frames, zero = HEADER.unpack(source.read(64))
        if (magic, version, hs, es, total, zero) != (MAGIC, version, 64, 64, size, b'\0' * 24) or version not in (2, 3):
            raise ValueError('package header')
        if not 3 <= count <= 5 or not limits.MIN_FRAMES <= frames <= limits.MAX_FRAMES or size > MAX_BYTES:
            raise ValueError('package limits')
        members, offset = [], 64 + count * 64
        roles = tuple(stem.ROLE_ORDER[:count - 2])
        expected = [(PCM, ROLE_BITS[r], r) for r in roles] + [(WAVE, 0, 'waveform'), (MANIFEST, 0, 'manifest')]
        for kind, role, name in expected:
            k, r, start, length, crc, reserved, label = ENTRY.unpack(source.read(64))
            if (k, r, start, reserved, label) != (kind, role, offset, 0, name.encode().ljust(32, b'\0')):
                raise ValueError('package directory')
            if (not length and not (version == 3 and kind == WAVE)) or length > size - offset or (kind == MANIFEST and length > limits.MANIFEST_BYTES):
                raise ValueError('package member bounds')
            members.append(Member(path, kind, role, start, length, crc, name))
            offset += length
    if offset != size: raise ValueError('package trailing data')
    if verify and any(checksum(m) != m.crc for m in members):
        raise ValueError('package checksum')
    if any(audition.header(m) != frames for m in members[:-2]):
        raise ValueError('package PCM grid')
    wave = waveform.read(members[-2]) if members[-2].length else None
    if members[-2].length and (not wave or wave['frames'] != frames or (wave['available'] != (3 if len(roles) == 1 else 7) if wave['version'] >= 2 else len(wave['roles']) != len(roles) + 1)):
        raise ValueError('package waveform grid')
    with members[-1].open() as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict):
        raise ValueError("package manifest")
    source_hash = manifest.get('source_sha256')
    if (not isinstance(source_hash, str) or len(source_hash) != 64 or
            any(c not in '0123456789abcdef' for c in source_hash)):
        raise ValueError('package source hash')
    if (wave is None and manifest.get('waveform') is not None):
        raise ValueError('package absent waveform')
    if (manifest.get('version'), manifest.get('roles'), manifest.get('frames'), manifest.get('source_sha256')) != (version, list(roles), frames, wave['source_sha256'] if wave else source_hash):
        raise ValueError('package manifest')
    return {'frames': frames, 'roles': roles, 'members': members, 'manifest': manifest, 'waveform': wave}


def write(output, inputs, wave, metadata):
    from app.stems import audition, waveform
    roles = tuple(inputs)
    if not roles or roles != stem.ROLE_ORDER[:len(roles)]:
        raise ValueError('unsupported stem selection')
    frames = audition.header(inputs[roles[0]])
    if any(audition.header(p) != frames for p in inputs.values()):
        raise ValueError('package PCM grid')
    limits.require(frames, len(roles), waveforms=wave is not None)
    info = waveform.read(wave) if wave is not None else None
    if wave is not None and (not info or info['frames'] != frames or (info['available'] != (3 if len(roles) == 1 else 7) if info['version'] >= 2 else len(info['roles']) != len(roles) + 1)):
        raise ValueError('package waveform required')
    version = 2 if info else 3
    manifest = dict(metadata, version=version, roles=list(roles), frames=frames,
                    source_sha256=info['source_sha256'] if info else metadata.get('source_sha256'), sample_rate=44100, channels=2,
                    waveform={'cadence':150, 'format':info['format'].decode(),
                              'residual':'instrumental' if len(roles) == 1 else 'other'} if info else None)
    with tempfile.TemporaryDirectory(prefix='rx3-package-') as directory:
        if wave is None:
            wave = pathlib.Path(directory) / 'absent-waveform'
            wave.touch()
        description = pathlib.Path(directory) / 'manifest.json'
        description.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
        parts = [(PCM, ROLE_BITS[r], r, p) for r, p in inputs.items()] + [(WAVE, 0, 'waveform', wave), (MANIFEST, 0, 'manifest', description)]
        offset = 64 + len(parts) * 64
        directory = bytearray()
        for kind, role, name, path in parts:
            length = path.stat().st_size
            directory.extend(ENTRY.pack(kind, role, offset, length, checksum(path), 0, name.encode().ljust(32,b'\0')))
            offset += length
        if offset > MAX_BYTES:
            raise limits.LimitError(limits.Verdict('refused', 'size', frames, offset).message(len(roles)))
        with output.open('wb') as target:
            target.write(HEADER.pack(MAGIC, version, 64, len(parts), 64, offset, frames, b'\0'*24))
            target.write(directory)
            for _, _, _, path in parts:
                with path.open('rb') as source:
                    shutil.copyfileobj(source, target)
    read(output)
    return output


def build(track, drive, inputs, workspace, source_hash, ffmpeg='ffmpeg', checkpoint=lambda: None, metadata=None, *, waveforms=True, progress=None, wave_format=None):
    """Build privately; a failed requested waveform never replaces a valid package."""
    if not waveforms:
        checkpoint()
        return write(workspace / "package.rx3stem", inputs, None,
                     dict(metadata or {}, source_sha256=source_hash, title=track.title,
                          artist=track.artist, track_id=track.track_id))
    from app.stems import analysis, audition, waveform, wave_dsp, wave_settings
    frames = audition.header(next(iter(inputs.values())))
    count = (frames + wave_dsp.STEP - 1) // wave_dsp.STEP
    template = analysis.locate(track, drive, source_hash)
    if template is None or template.count != count:
        # Own 150 Hz axis, explicitly distinguished from an exported analysis.
        template = analysis.Template(b'PWV5', b'', count, (), '00'*32)
    safety.require_space(workspace, count * wave_dsp.STEP * 96)
    wave = waveform.build(track, drive, template, source_hash, ffmpeg, workspace, checkpoint, files=list(inputs.values()),
                          format=wave_settings.FORMATS[wave_format] if wave_format else None, **({"progress": progress} if progress else {}))
    checkpoint()
    return write(workspace / 'package.rx3stem', inputs, wave,
                 dict(metadata or {}, title=track.title, artist=track.artist, track_id=track.track_id,
                      waveform_formats="all" if wave_format is None else wave_format))


def publish(local, target):
    """One atomic replacement, then retire obsolete v1 sidecars."""
    read(local)
    safety.publish(local, target)
    for suffix in ('.rx3drums', '.rx3bass', '.rx3wave'):
        old = target.with_suffix(suffix)
        safety.check_target(old)
        old.unlink(missing_ok=True)
    safety.sync_directory(target.parent)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="verify and describe a package")
    inspect.add_argument("path", type=pathlib.Path)
    migrate = sub.add_parser("migrate", help="package legacy stems on a working copy of an export")
    migrate.add_argument("--drive", type=pathlib.Path, required=True)
    migrate.add_argument("--track", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(read(args.path)["manifest"], ensure_ascii=False, indent=2))
        return
    from app.stems import audition
    from app.stems.rekordbox import Track, export_stem
    drive, audio = args.drive.resolve(), args.track.resolve()
    if not audio.is_relative_to(drive):
        parser.error("--track must be inside the working export")
    safety.require_library_closed()
    base = export_stem(audio.stem)
    target = drive / 'RX3_STEMS' / (base + '.rx3stem')
    if is_package(target):
        read(target)
        print(target)
        return
    files, frames, rejected = audition.role_files(target.parent, base)
    if not files or rejected:
        parser.error("legacy stems missing or inconsistent")
    track = Track('migration', audio.stem, '', round(frames / 44100), audio, True)
    stamp = safety.source_stamp(audio)
    with tempfile.TemporaryDirectory(prefix='rx3-migrate-') as directory:
        local = build(track, drive, dict(zip(stem.ROLE_ORDER, files)), pathlib.Path(directory), stamp[2],
                      metadata={"origin":"migrated-v1", "separation_provenance":"unverified"})
        safety.check_source(audio, stamp)
        publish(local, target)
    print(target)


if __name__ == '__main__':
    main()
