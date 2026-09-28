# SPDX-License-Identifier: MPL-2.0
"""Source-bound waveform sections, embedded in v2 packages for the player."""
from __future__ import annotations

import array
import contextlib
import pathlib
import struct
import subprocess
import sys
import tempfile

from app.localization import LocalizedError
from app.stems import analysis, audition, importing, mixing, safety, wave_dsp
from app.stems.rekordbox import export_stem

MAGIC = b"RX3WAV1\0"
HEADER = struct.Struct("<8s8I32s32sQ16s")
ROLE = struct.Struct("<IIQQ32s8s")
ROLE_IDS = {"vocals": 1, "instrumental": 2, "drums": 3, "bass": 4}
TAGS = {1: b"PWV3", 2: b"PWV5"}


def write(path, template, frames, source_hash, roles):
    if (frames + wave_dsp.STEP - 1) // wave_dsp.STEP != template.count:
        raise ValueError("waveform axis")
    stride = analysis.STRIDES[template.tag]
    if not 2 <= len(roles) <= 4 or list(roles) != list(ROLE_IDS)[:len(roles)]:
        raise ValueError("waveform roles")
    if any(len(data) != template.count * stride for data, _ in roles.values()):
        raise ValueError("waveform length")
    first = HEADER.size + ROLE.size * len(roles)
    with path.open("wb") as output:
        output.write(HEADER.pack(MAGIC, 1, HEADER.size, 44100, 150, template.count,
                                 stride, len(roles), ROLE.size, bytes.fromhex(source_hash),
                                 bytes.fromhex(template.sha256), frames, b"\0" * 16))
        offset = first
        for role, (data, digest) in roles.items():
            output.write(ROLE.pack(ROLE_IDS[role], stride, offset, len(data),
                                   bytes.fromhex(digest), b"\0" * 8))
            offset += len(data)
        for data, _ in roles.values():
            output.write(data)


MULTI_MAGIC = b"RX3WAV3\0"
MULTI_STRIDE = 6  # BLUE byte, RGB big-endian word, PWV7 low/mid/high envelopes.


def write_combinations(path, template, frames, source_hash, combinations, format=None):
    stride = {b"PWV3":1, b"PWV5":2, b"PWV7":3, None:MULTI_STRIDE}[format]
    masks = list(combinations)
    if masks not in (list(range(1, 4)), list(range(1, 8))):
        raise ValueError("waveform combinations")
    if (frames + wave_dsp.STEP - 1) // wave_dsp.STEP != template.count:
        raise ValueError("waveform axis")
    if any(len(data) != template.count * stride for data, _ in combinations.values()):
        raise ValueError("waveform length")
    offset = HEADER.size + ROLE.size * len(masks)
    with path.open("wb") as output:
        output.write(HEADER.pack(b"RX3WAV4\0" if format else MULTI_MAGIC, 4 if format else 3, HEADER.size, 44100, 150, template.count,
                                 stride, len(masks), ROLE.size, bytes.fromhex(source_hash),
                                 bytes.fromhex(template.sha256), frames, b"\0" * 16))
        for mask, (data, digest) in combinations.items():
            output.write(ROLE.pack(mask, stride, offset, len(data), bytes.fromhex(digest), b"\0" * 8))
            offset += len(data)
        for data, _ in combinations.values():
            output.write(data)


def read(path, expected_count=None):
    try:
        if path.stat().st_size > HEADER.size + 7 * ROLE.size + analysis.MAX_COLUMNS * 42:
            return None
        with path.open("rb") as source:
            magic, version, size, rate, cadence, count, fmt, roles, table_size, sha, anlz, frames, reserved = HEADER.unpack(source.read(HEADER.size))
            multi = (magic, version) in ((b"RX3WAV2\0", 2), (MULTI_MAGIC, 3), (b"RX3WAV4\0", 4))
            if ((magic, version) not in ((MAGIC, 1), (b"RX3WAV2\0", 2), (MULTI_MAGIC, 3), (b"RX3WAV4\0", 4)) or
                    (size, rate, cadence, table_size, reserved) !=
                    (HEADER.size, 44100, 150, ROLE.size, b"\0" * 16) or
                    not 0 < count <= analysis.MAX_COLUMNS or fmt not in ((1, 2, 3) if version == 4 else (MULTI_STRIDE,) if multi else TAGS) or
                    (frames + wave_dsp.STEP - 1) // wave_dsp.STEP != count or frames < 4410 or
                    (roles not in (3, 7) if multi else not 2 <= roles <= 4) or expected_count is not None and count != expected_count):
                return None
            offset = HEADER.size + roles * ROLE.size
            entries = []
            for role in range(1, roles + 1):
                role_id, stride, start, length, digest, zero = ROLE.unpack(source.read(ROLE.size))
                if (role_id, stride, start, length, zero) != (role, fmt, offset, count * fmt, b"\0" * 8):
                    return None
                entries.append((role, start, length, digest.hex()))
                offset += length
            if path.stat().st_size != offset:
                return None
            if version == 2:
                for _, start, length, _ in entries:
                    source.seek(start)
                    data = source.read(length)
                    if any(sum(data[i+3:i+6]) > 31 for i in range(0, length, 6)):
                        return None
            return {"count": count, "frames": frames, "format": {1:b"PWV3", 2:b"PWV5", 3:b"PWV7"}[fmt] if version == 4 else b"MULTI" if multi else TAGS[fmt], "version": version,
                    "available": roles if multi else (1 << roles) - 1, "source_sha256": sha.hex(),
                    "analysis_sha256": anlz.hex(), "roles": entries}
    except (OSError, ValueError, struct.error):
        return None


def invalidate(track, drive):
    target = drive / "RX3_STEMS" / (export_stem(track.location.stem) + ".rx3wave")
    safety.check_target(target)
    target.unlink(missing_ok=True)
    if target.parent.is_dir():
        safety.sync_directory(target.parent)
    return target


def accelerated_combinations(raw, files, frames, available, template, format, ffmpeg,
                             workspace, checkpoint, progress, worker):
    """Two mixes at a time: bounded scratch space and shared PCM/gain reads."""
    import contextvars
    from concurrent.futures import ThreadPoolExecutor
    import shutil
    # Full-format filtering has nine float64 outputs per concurrent mix.
    # Keep the serial route when two sets would exceed available scratch space.
    workers = 2 if format or shutil.disk_usage(workspace).free >= frames * 176 else 1
    gains = [audition.gain(path) for path in files]
    results = {}

    def analyze(mask, pcm):
        checkpoint()
        formats = wave_dsp.columns(pcm, frames, format, template.count, ffmpeg, checkpoint,
                                   accelerator=worker)
        if format:
            packed = formats
        else:
            packed = bytearray(template.count * MULTI_STRIDE)
            for i in range(template.count):
                packed[i*6:i*6+6] = (formats[b"PWV3"][i:i+1] + formats[b"PWV5"][i*2:i*2+2]
                                    + formats[b"PWV7"][i*3:i*3+3])
        digest = safety.digest(pcm)
        pcm.unlink()
        return packed, digest

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='rx3-wave') as pool:
        for first in range(1, available + 1, workers):
            checkpoint()
            paths = {mask: workspace / f'combination-{mask}.f32'
                     for mask in range(first, min(available + 1, first + workers))}
            try:
                worker.mix(raw, files, gains, frames, paths)
                futures = {mask: pool.submit(contextvars.copy_context().run, analyze, mask, pcm)
                           for mask, pcm in paths.items()}
                try:
                    for mask, future in futures.items():
                        results[mask] = future.result()
                        progress(.05 + .9 * len(results) / available)
                finally:
                    # Complete owned readers before deleting their files, including Windows.
                    for future in futures.values():
                        if not future.cancelled():
                            try: future.result()
                            except Exception: pass
            finally:
                for pcm in paths.values(): pcm.unlink(missing_ok=True)
    return results


def build(track, drive, template, source_hash, ffmpeg, workspace, checkpoint, *, files=None, progress=lambda value: None, format=None):
    if files is None:
        files, frames, rejected = audition.role_files(drive / "RX3_STEMS", export_stem(track.location.stem))
    else:
        frames, rejected = audition.header(files[0]), []
    if not files or rejected or (frames + wave_dsp.STEP - 1) // wave_dsp.STEP != template.count:
        raise ValueError("waveform stems")
    source_stamp = safety.source_stamp(track.location)
    if source_stamp[2] != source_hash:
        raise ValueError("waveform source")
    stamps = [(path, safety.source_stamp(path)) for path in files]
    progress(0)
    checkpoint()
    from app.stems import wave_acceleration
    from app.stems.wave_encoding import required_memory
    available = 3 if len(files) == 1 else 7
    local_pcm = workspace / "combination.f32"
    worker = wave_acceleration.open_worker() if len(files) <= 2 else None
    results = {}
    streaming = worker and worker.memory and required_memory(frames, available) <= 512 * 1024**2
    if streaming:
        try:
            def update(value):
                checkpoint()
                progress(.95 * value)
            results = worker.build(track.location, files, frames, ffmpeg, workspace, update)
            if format:
                offset, stride = {b"PWV3": (0, 1), b"PWV5": (1, 2), b"PWV7": (3, 3)}[format]
                for mask, (data, digest) in results.items():
                    packed = bytearray(template.count * stride)
                    for j in range(stride): packed[j::stride] = data[offset+j::MULTI_STRIDE]
                    results[mask] = packed, digest
        finally:
            worker.close()
    else:
        raw = workspace / "mix.f32"
        try:
            if importing.decode(track.location, raw, ffmpeg, untrimmed=True) != frames:
                raise ValueError("waveform source frames")
            checkpoint()
        except BaseException:
            if worker: worker.close()
            raise
        progress(.05)
    if worker and not streaming:
        try:
            results = accelerated_combinations(raw, files, frames, available, template, format,
                                               ffmpeg, workspace, checkpoint, progress, worker)
        finally:
            worker.close()
    elif not streaming:
        for mask in range(1, available + 1):
            checkpoint()
            # Analyze the audible PCM of this exact selection, not summed envelopes.
            levels = [float(bool(mask & (1 << (0 if i == 3 else i)))) for i in range(4)]
            state = mixing.MixState(gain=levels[:], start=levels[:], target=levels[:])
            with contextlib.ExitStack() as stack:
                full = stack.enter_context(raw.open("rb"))
                inputs = [stack.enter_context(path.open("rb")) for path in files]
                scales = [audition.gain(path) for path in files]
                for stream in inputs:
                    stream.seek(64)
                output = stack.enter_context(local_pcm.open("wb"))
                remaining = frames
                while remaining:
                    checkpoint()
                    count = min(remaining, 32768)
                    mix = array.array("f")
                    mix.frombytes(full.read(count * 8))
                    components = []
                    for stream, scale in zip(inputs, scales):
                        components.append(audition.read_pcm(stream, count, scale))
                    if sys.byteorder != "little": mix.byteswap()
                    values = (mixing.reconstruct_static(mix, components, mask) if len(components) < 3
                              else mixing.reconstruct(mix, components, mask, state))
                    if sys.byteorder != "little": values.byteswap()
                    output.write(values.tobytes())
                    remaining -= count
                    progress(.05 + .9 * ((mask - 1) + .3 * (1 - remaining / frames)) / available)
            formats = wave_dsp.columns(local_pcm, frames, format, template.count, ffmpeg, checkpoint,
                                       progress=lambda value: progress(.05 + .9 * ((mask - 1) + .3 + .7 * value) / available))
            if format:
                packed = formats
            else:
                packed = bytearray(template.count * MULTI_STRIDE)
                for i in range(template.count):
                    packed[i*6:i*6+6] = (formats[b"PWV3"][i:i+1] + formats[b"PWV5"][i*2:i*2+2]
                                        + formats[b"PWV7"][i*3:i*3+3])
            results[mask] = (packed, safety.digest(local_pcm))
    local_pcm.unlink(missing_ok=True)
    safety.check_source(track.location, source_stamp)
    for path, before in stamps + list(template.files):
        safety.check_source(path, before)
    local = workspace / "track.rx3wave"
    write_combinations(local, template, frames, source_hash, results, format)
    if read(local, template.count) is None:
        raise ValueError("waveform verification")
    progress(1)
    return local


def prepare(track, drive, source_hash=None, ffmpeg="ffmpeg", checkpoint=lambda: None):
    """An unavailable analysis disables only this optional file, never the stems."""
    target = None
    try:
        target = invalidate(track, drive)
        safety.require_library_closed()
        source_hash = source_hash or safety.digest(track.location)
        template = analysis.locate(track, drive, source_hash)
        if template is None:
            return False
        # Bound temporary storage before decoding/filtering a complete track.
        with tempfile.TemporaryDirectory(prefix="rx3-wave-") as directory:
            workspace = pathlib.Path(directory)
            safety.require_space(workspace, template.count * wave_dsp.STEP * 96)
            checkpoint()
            local = build(track, drive, template, source_hash, ffmpeg, workspace, checkpoint)
            checkpoint()
            safety.require_space(target.parent, local.stat().st_size)
            safety.publish(local, target)
            safety.clean_metadata(target.parent)
        return True
    except (OSError, ValueError, OverflowError, LocalizedError, subprocess.SubprocessError):
        # Do not catch cancellation or programming errors in the optional path.
        return False
