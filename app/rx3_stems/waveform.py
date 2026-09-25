# SPDX-License-Identifier: MPL-2.0
"""Optional, source-bound host waveform files; no player renderer consumes these."""
from __future__ import annotations

import array
import contextlib
import pathlib
import struct
import subprocess
import sys
import tempfile

from app.localization import LocalizedError
from app.rx3_stems import analysis, audition, importing, mixing, safety, wave_dsp
from app.rx3_stems.rekordbox import export_stem

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


def read(path, expected_count=None):
    try:
        if path.stat().st_size > HEADER.size + 4 * ROLE.size + analysis.MAX_COLUMNS * 8:
            return None
        with path.open("rb") as source:
            magic, version, size, rate, cadence, count, fmt, roles, table_size, sha, anlz, frames, reserved = HEADER.unpack(source.read(HEADER.size))
            if ((magic, version, size, rate, cadence, table_size, reserved) !=
                    (MAGIC, 1, HEADER.size, 44100, 150, ROLE.size, b"\0" * 16) or
                    not 0 < count <= analysis.MAX_COLUMNS or fmt not in TAGS or
                    (frames + wave_dsp.STEP - 1) // wave_dsp.STEP != count or frames < 4410 or
                    not 2 <= roles <= 4 or expected_count is not None and count != expected_count):
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
            return {"count": count, "frames": frames, "format": TAGS[fmt], "source_sha256": sha.hex(),
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


def build(track, drive, template, source_hash, ffmpeg, workspace, checkpoint):
    files, frames, rejected = audition.role_files(drive / "RX3_STEMS", export_stem(track.location.stem))
    if not files or rejected or (frames + wave_dsp.STEP - 1) // wave_dsp.STEP != template.count:
        raise ValueError("waveform stems")
    source_stamp = safety.source_stamp(track.location)
    if source_stamp[2] != source_hash:
        raise ValueError("waveform source")
    stamps = [(path, safety.source_stamp(path)) for path in files]
    raw = workspace / "mix.f32"
    if importing.decode(track.location, raw, ffmpeg, untrimmed=True) != frames:
        raise ValueError("waveform source frames")
    # Only the terminal incomplete cell receives zeros in the DSP stage.
    # No source or stem is resized to disguise a different column count.
    results = {}
    with contextlib.ExitStack() as stack:
        full = stack.enter_context(raw.open("rb"))
        inputs = [stack.enter_context(path.open("rb")) for path in files]
        for stream in inputs:
            stream.seek(64)
        paths = {role: workspace / f"{role}.f32" for role in list(ROLE_IDS)[:len(files) + 1]}
        outputs = {role: stack.enter_context(path.open("wb")) for role, path in paths.items()}
        state = mixing.MixState(gain=[1, 0, 0, 0], start=[1, 0, 0, 0], target=[1, 0, 0, 0])
        remaining = frames
        while remaining:
            checkpoint()
            count = min(remaining, 32768)
            mix = array.array("f")
            mix.frombytes(full.read(count * 8))
            vocal = None
            for index, stream in enumerate(inputs):
                data = array.array("h")
                data.frombytes(stream.read(count * 4))
                if sys.byteorder != "little":
                    data.byteswap()
                if index == 0:
                    vocal = data
                values = array.array("f", (value / 32768 for value in data))
                if sys.byteorder != "little":
                    values.byteswap()
                outputs[("vocals", "drums", "bass")[index]].write(values.tobytes())
            if sys.byteorder != "little":
                mix.byteswap()
            values = mixing.reconstruct(mix, [vocal], 1, state)
            if sys.byteorder != "little":
                values.byteswap()
            outputs["instrumental"].write(values.tobytes())
            remaining -= count
    for role, path in paths.items():
        checkpoint()
        data = wave_dsp.columns(path, frames, template.tag, template.count, ffmpeg, checkpoint)
        # Hash the exact PCM projected to columns, including reconstructed roles.
        results[role] = (data, safety.digest(path))
    safety.check_source(track.location, source_stamp)
    for path, before in stamps + list(template.files):
        safety.check_source(path, before)
    local = workspace / "track.rx3wave"
    write(local, template, frames, source_hash, results)
    if read(local, template.count) is None:
        raise ValueError("waveform verification")
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
