# SPDX-License-Identifier: MPL-2.0
"""Bounded excerpts from the PCM files the player will actually load."""
from __future__ import annotations

import array
import base64
import math
import pathlib
import struct
import sys
import tempfile

from app.localization import LocalizedError
from app.rx3_stems import importing, mixing, safety, stem
from app.rx3_stems.rekordbox import export_stem

MAX_SECONDS = 30


def header(path):
    safety.check_target(path)
    try:
        with path.open("rb") as source:
            magic, rate, channels, fmt, offset, frames, reserved = stem.HEADER.unpack(source.read(64))
        if ((magic, rate, channels, fmt, offset, reserved) != (stem.MAGIC, 44100, 2, 2, 64, b"\0" * 32)
                or not 0 < frames <= 0x5000000 or path.stat().st_size != 64 + frames * 4):
            raise ValueError()
    except (OSError, ValueError, struct.error):
        raise LocalizedError("stems.auditionInvalid", name=path.name) from None
    return frames


def role_files(directory, base):
    files = []
    frames = None
    rejected = []
    for role in stem.ROLE_ORDER:
        path = directory / (base + stem.ROLE_SUFFIXES[role])
        if not path.exists():
            break
        try:
            length = header(path)
            if frames is not None and length != frames:
                raise LocalizedError("stems.auditionLength")
        except LocalizedError:
            if role == "vocals":
                raise
            rejected.append(role)
            break
        frames = length
        files.append(path)
    return files, frames, rejected


def float_wav(pcm):
    values = array.array("f", pcm)
    if sys.byteorder != "little":
        values.byteswap()
    payload = values.tobytes()
    # IEEE-float WAV preserves the hook's output, including peaks above unity.
    return (b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 3, 2, 44100, 44100 * 8, 8, 32) +
            b"data" + struct.pack("<I", len(payload)) + payload)


def excerpt(source, files, selection, start, seconds, ffmpeg="ffmpeg"):
    try:
        start, seconds = float(start), float(seconds)
        if not math.isfinite(start) or not math.isfinite(seconds) or start < 0 or seconds <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise LocalizedError("stems.auditionRange") from None
    seconds = min(seconds, MAX_SECONDS)
    if not files:
        return {"audio": None, "available": 0, "seconds": 0, "totalSeconds": 0}
    lengths = [header(path) for path in files]
    if len(set(lengths)) != 1:
        raise LocalizedError("stems.auditionLength")
    available = (2 << len(files)) - 1
    options = selection if isinstance(selection, dict) else {"mask": selection}
    mask = options.get("mask", available)
    if mask == "original":
        mask = available
    try:
        mask = int(mask)
        if mask < 0 or mask & ~available:
            raise ValueError()
    except (TypeError, ValueError):
        raise LocalizedError("stems.auditionSelection") from None
    state = mixing.MixState.read(options.get("state"))
    initial = state.as_dict()
    with tempfile.TemporaryDirectory(prefix="rx3-listen-") as directory:
        raw = pathlib.Path(directory) / "mix.f32"
        frames = importing.decode(source, raw, ffmpeg, untrimmed=True)
        if frames != lengths[0]:
            raise LocalizedError("stems.auditionLength")
        first = min(frames, round(start * 44100))
        count = min(frames - first, round(seconds * 44100))
        full = importing.samples(raw, first, count)
    roles = []
    for path in files:
        with path.open("rb") as audio:
            audio.seek(64 + first * 4)
            values = array.array("h")
            values.frombytes(audio.read(count * 4))
        if sys.byteorder != "little":
            values.byteswap()
        roles.append(values)
    ramp = []
    mixed = mixing.reconstruct(full, roles, mask, state, timeline=ramp)
    encoded = float_wav(mixed)
    # Display peaks use the same audible output as the WAV, never model output.
    stride = max(1, len(mixed) // 1024)
    peaks = [max((abs(v) for v in mixed[i:i + stride]), default=0) for i in range(0, len(mixed), stride)]
    return {"audio": base64.b64encode(encoded).decode("ascii"), "seconds": count / 44100,
            "start": first / 44100, "totalSeconds": frames / 44100, "available": available,
            "selection": mask, "peaks": peaks, "initialState": initial,
            "ramp": ramp, "finalState": state.as_dict()}


def on_drive(source, drive, selection, start=0, seconds=30, ffmpeg="ffmpeg"):
    files, _, rejected = role_files(drive / "RX3_STEMS", export_stem(source.stem))
    result = excerpt(source, files, selection, start, seconds, ffmpeg)
    result["rejected"] = rejected
    return result


def imported(source, inputs, selection, start=0, seconds=30, ffmpeg="ffmpeg"):
    with tempfile.TemporaryDirectory(prefix="rx3-listen-import-") as directory:
        outputs, report = importing.prepare(source, inputs, pathlib.Path(directory), ffmpeg)
        result = excerpt(source, list(outputs.values()), selection, start, seconds, ffmpeg)
        result["checks"] = report
        return result
