# SPDX-License-Identifier: MPL-2.0
"""Validate manual lossless stems before exposing them to the player."""
from __future__ import annotations

import array
import json
import math
import pathlib
import statistics
import subprocess
import sys
import tempfile
import threading

from app.localization import LocalizedError
from app.rx3_stems import cache, provisioning, safety, stem
from app.rx3_stems.rekordbox import export_stem

# Correlation is evidence of a shared signal, never proof of a source role.
MIN_CORRELATION = 0.55
GAIN_TOLERANCE = 0.05
GAIN_SPREAD = 0.10
MAX_SHIFT = stem.SAMPLE_RATE
ENVELOPE_STEP = 64
MIN_WINDOWS = 4
SETTINGS_LOCK = threading.Lock()


def assignments(library, track_id, values=None):
    path = provisioning.data_directory() / "stem-imports.json"
    key = json.dumps([str(library.source.resolve()), str(track_id)])
    with SETTINGS_LOCK:
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        if values is not None:
            values = {role: str(value) for role, value in values.items()
                      if role in stem.ROLE_ORDER and value}
            data[key] = values
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(".partial")
            partial.write_text(json.dumps(data) + "\n")
            partial.replace(path)
        return data.get(key, {})


def audio_info(path, ffmpeg):
    probe = pathlib.Path(ffmpeg).with_name("ffprobe" + (".exe" if sys.platform == "win32" else ""))
    command = str(probe) if probe.is_file() else "ffprobe"
    result = subprocess.run([command, "-v", "error", "-select_streams", "a:0",
                             "-show_entries", "stream=codec_name,channels", "-of", "json", str(path)],
                            capture_output=True, text=True)
    try:
        info = json.loads(result.stdout)["streams"][0]
        if result.returncode:
            raise ValueError()
        return info
    except (ValueError, KeyError, IndexError, TypeError):
        raise LocalizedError("stems.importUnreadable", name=path.name) from None


def lossless(path, ffmpeg):
    if path.suffix.lower() not in (".wav", ".aif", ".aiff", ".flac"):
        raise LocalizedError("stems.importLossless", name=path.name)
    info = audio_info(path, ffmpeg)
    codec = info.get("codec_name", "")
    if not ((codec == "flac" or codec.startswith("pcm_")) and info.get("channels") in (1, 2)):
        raise LocalizedError("stems.importLossless", name=path.name)


def decode(path, target, ffmpeg, *, untrimmed=False, duplicate_mono=False):
    # The default mono-to-stereo matrix attenuates each channel by sqrt(0.5).
    # A manual mono stem must be duplicated at unity instead.
    mono = duplicate_mono and audio_info(path, ffmpeg).get("channels") == 1
    stem._decode(ffmpeg, [*(stem.UNTRIMMED if untrimmed else ()), "-i", str(path),
                          "-map", "0:a:0", "-vn",
                          *(["-af", "pan=stereo|c0=c0|c1=c0"] if mono else []),
                          "-ar", "44100", "-ac", "2", "-f", "f32le", str(target)])
    size = target.stat().st_size
    if not size or size % 8:
        raise LocalizedError("stems.importUnreadable", name=path.name)
    return size // 8


def samples(path, start, frames):
    with path.open("rb") as source:
        source.seek(start * 8)
        values = array.array("f")
        values.frombytes(source.read(frames * 8))
    if sys.byteorder != "little":
        values.byteswap()
    if any(not math.isfinite(value) for value in values):
        raise LocalizedError("stems.importUnreadable", name=path.name)
    return values


def correlation(reference, candidate, offset, step=1):
    count = len(reference)
    cross = sum(reference[i] * candidate[offset + i] for i in range(0, count, step))
    ref_power = sum(reference[i] ** 2 for i in range(0, count, step))
    power = sum(candidate[offset + i] ** 2 for i in range(0, count, step))
    return cross / math.sqrt(ref_power * power) if ref_power * power > 1e-20 else -1.0


def envelope(values):
    step = ENVELOPE_STEP
    return [sum(abs(v) for v in values[i:i + step]) / step
            for i in range(0, len(values) - step + 1, step)]


def locate(reference, candidate, centre):
    # A centred amplitude envelope supplies a coarse location without a full
    # 88,201 by 4,096 correlation in Python. Fine passes return to real samples.
    ref_env = envelope(reference)
    mean = statistics.fmean(ref_env)
    ref_env = [v - mean for v in ref_env]
    env = envelope(candidate)
    length = len(ref_env)
    power = sum(v * v for v in ref_env)
    scores = []
    for offset in range(len(env) - length + 1):
        part = env[offset:offset + length]
        avg = statistics.fmean(part)
        variance = sum((v - avg) ** 2 for v in part)
        score = sum(a * b for a, b in zip(ref_env, part)) / math.sqrt(power * variance) if power * variance > 1e-20 else -1
        scores.append((score, offset * ENVELOPE_STEP))
    # More than one coarse candidate protects against a transient masked by
    # another instrument. Final sample correlation decides, not the envelope.
    peaks = []
    for _, offset in sorted(scores, reverse=True):
        if all(abs(offset - old) > 2 * ENVELOPE_STEP for old in peaks):
            peaks.append(offset)
        if len(peaks) == 3:
            break
    peaks.append(centre)
    candidates = set()
    last = len(candidate) - len(reference)
    for peak in peaks:
        candidates.update(range(max(0, peak - 96), min(last, peak + 96) + 1, 4))
    rough = sorted(((correlation(reference, candidate, offset, 16), offset)
                    for offset in candidates), reverse=True)[:3]
    refined = {offset for _, peak in rough for offset in range(max(0, peak - 4), min(last, peak + 4) + 1)}
    score, offset = max((correlation(reference, candidate, offset), offset) for offset in refined)
    return offset - centre, score


def inspect_role(mix, imported, frames, imported_frames, checkpoint=lambda: None):
    if imported_frames < frames:
        raise LocalizedError("stems.importShort")
    if imported_frames - frames > stem.SAMPLE_RATE:
        raise LocalizedError("stems.importLong")
    results = []
    for fraction in stem.PROBE_POSITIONS:
        checkpoint()
        position = int(frames * fraction)
        if position < MAX_SHIFT or position + stem.PROBE_FRAMES + MAX_SHIFT > min(frames, imported_frames):
            continue
        full = samples(mix, position, stem.PROBE_FRAMES)
        region = samples(imported, position - MAX_SHIFT, stem.PROBE_FRAMES + 2 * MAX_SHIFT)
        # Taking the stronger stereo channel avoids cancelling anti-phase audio.
        channel = max((0, 1), key=lambda c: sum(v * v for v in full[c::2]))
        reference = full[channel::2]
        candidate = region[channel::2]
        shift, score = locate(reference, candidate, MAX_SHIFT)
        if score < MIN_CORRELATION:
            raise LocalizedError("stems.importAlignment", correlation=round(score, 3))
        aligned = candidate[MAX_SHIFT + shift:MAX_SHIFT + shift + stem.PROBE_FRAMES]
        energy = sum(v * v for v in aligned)
        gain = sum(a * b for a, b in zip(reference, aligned)) / energy if energy else 0
        results.append({"shift": shift, "correlation": score, "gain": gain, "position": position})
    if len(results) < MIN_WINDOWS or max(r["shift"] for r in results) - min(r["shift"] for r in results) > 2:
        raise LocalizedError("stems.importDrift")
    shift = round(statistics.median(r["shift"] for r in results))
    if any(abs(r["shift"] - shift) > 1 for r in results):
        raise LocalizedError("stems.importDrift")
    gains = [r["gain"] for r in results]
    gain = statistics.median(gains)
    spread = max(gains) - min(gains)
    if gain <= 0 or abs(gain - 1.0) > GAIN_TOLERANCE:
        raise LocalizedError("stems.importGain", gain=round(gain, 4))
    # A wide spread can be genuine mix correlation; report uncertainty rather
    # than asserting that a dynamics processor has definitely been used.
    extra = imported_frames - frames
    if extra and (shift < 0 or shift > extra):
        raise LocalizedError("stems.importTrim")
    return {"shift": shift, "milliseconds": shift * 1000 / stem.SAMPLE_RATE,
            "trimStart": max(0, shift), "trimEnd": max(0, extra - shift),
            "gainEstimate": gain, "gainSpread": spread, "gainUncertain": spread > GAIN_SPREAD,
            "gainCertified": False, "windows": results}


def prepare(source, inputs, workspace, ffmpeg="ffmpeg", checkpoint=lambda: None):
    roles = tuple(role for role in stem.ROLE_ORDER if inputs.get(role))
    if "vocals" not in roles or ("bass" in roles and "drums" not in roles):
        raise LocalizedError("stems.importRoles")
    for role in roles:
        lossless(pathlib.Path(inputs[role]), ffmpeg)
    mix = workspace / "mix.f32"
    frames = decode(source, mix, ffmpeg, untrimmed=True)
    raw = {}
    lengths = {}
    for role in roles:
        checkpoint()
        raw[role] = workspace / (role + ".f32")
        lengths[role] = decode(pathlib.Path(inputs[role]), raw[role], ffmpeg, duplicate_mono=True)
    # All duration checks precede correlation or gain checks.
    if any(lengths[role] < frames for role in roles):
        raise LocalizedError("stems.importShort")
    if any(lengths[role] - frames > stem.SAMPLE_RATE for role in roles):
        raise LocalizedError("stems.importLong")
    reports = {role: inspect_role(mix, raw[role], frames, lengths[role], checkpoint) for role in roles}
    residual_ratio = None
    if len(roles) == 3:
        residual_energy, mix_energy = 0.0, 0.0
        for fraction in stem.PROBE_POSITIONS:
            position = int(frames * fraction)
            if position < MAX_SHIFT or position + stem.PROBE_FRAMES + MAX_SHIFT > frames:
                continue
            full = samples(mix, position, stem.PROBE_FRAMES)
            parts = [samples(raw[role], position + reports[role]["shift"], stem.PROBE_FRAMES) for role in roles]
            residual_energy += sum((value - sum(part[i] for part in parts)) ** 2 for i, value in enumerate(full))
            mix_energy += sum(value * value for value in full)
        residual_ratio = residual_energy / mix_energy if mix_energy else None
    outputs = {}
    for role in roles:
        checkpoint()
        report = reports[role]
        corrected = workspace / (role + ".wav")
        shift = report["shift"]
        filters = [f"atrim=start_sample={shift}"] if shift > 0 else ([f"adelay={-shift}S:all=1"] if shift else [])
        filters.extend(["apad", f"atrim=end_sample={frames}"])
        stem._decode(ffmpeg, ["-f", "f32le", "-ar", "44100", "-ac", "2", "-i", str(raw[role]),
                              "-af", ",".join(filters), "-c:a", "pcm_f32le", str(corrected)])
        target = workspace / (role + stem.ROLE_SUFFIXES[role])
        # The verified file already occupies the deck grid. match_full would
        # add the container's encoder padding a second time.
        result = stem.write_stem(corrected, target, ffmpeg=ffmpeg, sample_format="s16")
        if result.frames != frames:
            raise LocalizedError("stems.importShort")
        report["peak"] = result.peak
        report["clippedSamples"] = result.clipped
        outputs[role] = target
    return outputs, {"roles": reports, "residualEnergyRatio": residual_ratio,
                     "residualCertified": False, "frames": frames}


def publish(track, inputs, drive, ffmpeg="ffmpeg", checkpoint=lambda: None):
    safety.require_library_closed()
    output = drive / "RX3_STEMS"
    safety.check_target(output / safety.MANIFEST_NAME)
    output.mkdir(exist_ok=True)
    base = export_stem(track.location.stem)
    for suffix in stem.ROLE_SUFFIXES.values():
        safety.check_target(output / (base + suffix))
    stamps = {path: safety.source_stamp(path) for path in {track.location, *(pathlib.Path(p) for p in inputs.values() if p)}}
    safety.require_space(output, safety.estimated_bytes(track, len(inputs), ffmpeg))
    with tempfile.TemporaryDirectory(prefix="rx3-import-") as directory:
        workspace = pathlib.Path(directory)
        outputs, report = prepare(track.location, inputs, workspace, ffmpeg, checkpoint)
        checkpoint()
        for path, before in stamps.items():
            safety.check_source(path, before)
        safety.require_space(output, sum(path.stat().st_size for path in outputs.values()))
        for role in reversed(stem.ROLE_ORDER[1:]):
            old = output / (base + stem.ROLE_SUFFIXES[role])
            safety.check_target(old)
            old.unlink(missing_ok=True)
        safety.sync_directory(output)
        entries = []
        for role, local in outputs.items():
            checkpoint()
            for path, before in stamps.items():
                safety.check_source(path, before)
            target = output / (base + stem.ROLE_SUFFIXES[role])
            safety.publish(local, target)
            entries.append({"role": role, "file": target.name, "bytes": target.stat().st_size,
                            "sha256": safety.digest(target), "clippedSamples": report["roles"][role]["clippedSamples"]})
        manifest, _ = cache.read_manifest(drive)
        name = base + stem.ROLE_SUFFIXES["vocals"]
        entry = {"trackId": track.track_id, "artist": track.artist, "title": track.title,
                 "stem": name, "origin": "imported", "source_sha256": stamps[track.location][2],
                 "source_bytes": stamps[track.location][0], "processing": {"origin": "imported", "version": 1, "sample_format": "s16", "stem_version": 1},
                 "import_sha256": {role: stamps[pathlib.Path(path)][2] for role, path in inputs.items() if path},
                 "gainCorrection": 1.0, "encoderDelayFrames": 0, "checks": report, "stems": entries}
        manifest = [old for old in manifest if old.get("stem") != name] + [entry]
        local = workspace / safety.MANIFEST_NAME
        local.write_text(json.dumps({"format": 2, "tracks": manifest}, indent=2) + "\n")
        safety.publish(local, output / safety.MANIFEST_NAME)
    return entry
