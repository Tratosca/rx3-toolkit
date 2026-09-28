# SPDX-License-Identifier: MPL-2.0
"""Compute compact detailed columns from PCM, independently of mix colours."""
from __future__ import annotations

import math
import mmap
import pathlib
import struct
import subprocess
from app.stems import processes
import tempfile

from app.stems.mixing import f32

RATE = 44100
CADENCE = 150
STEP = RATE // CADENCE
HEIGHT_SCALE = 2.9327451233027466e-08


def biquad(frequency, high=False, rate=RATE):
    angle = 2 * math.pi * frequency / rate
    cosine = math.cos(angle)
    alpha = math.sin(angle) / math.sqrt(2)
    b0 = (1 + cosine if high else 1 - cosine) / 2
    b1 = -(1 + cosine) if high else 1 - cosine
    values = (1 + alpha, -2 * cosine, 1 - alpha, b0, b1, b0)
    return "biquad=" + ":".join(f"{key}={value:.17g}" for key, value in
                                zip(("a0", "a1", "a2", "b0", "b1", "b2"), values)) + ":r=f64:a=di"


def peaks(path, boundaries, integer=False, scale=1):
    result = []
    with path.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for start, stop in zip(boundaries, boundaries[1:]):
            values = struct.unpack_from("<" + "d" * (stop - start), data, start * 8)
            peak = max(max(values, default=0), -min(values, default=0)) * scale
            result.append(min(32767, int(peak)) if integer else peak)
    return result


def reduce_max(values, count):
    starts = [(len(values) * i + count - 1) // count for i in range(count)]
    return [max(values[start:max(start + 1, stop)], default=0)
            for start, stop in zip(starts, starts[1:] + [len(values)])]


def rolling(values, radius):
    return [max(values[max(0, i - radius):i + radius + 1], default=0) for i in range(len(values))]


def rgb_bits(low, middle, high):
    r, g, b = map(f32, (low, middle, high))
    peak = max(r, g, b)
    if not peak:
        return 7, 7, 7
    scale = f32(1 / peak)
    r, g, b = (f32(f32(v * 255) * scale) for v in (r, g, b))
    cut = f32(f32(r * g) * f32(0.0013071897))
    cut = f32(f32(f32(b * -0.015625) * cut) + cut) if b < 64 else 0
    r, g = f32(r - cut), f32(g - cut)
    g = f32(f32(f32(g * f32(-0.00234375)) * min(max(r, b), 128)) + g)
    b = f32(b * f32(1.3))
    return tuple(min(255, max(0, int(v))) >> 5 for v in (r, g, b))


def encode(blue, low_blue, full_ms, low_ms, mid_ms, high_ms, count, tag):
    if tag == b"PWV3":
        peak = max(blue, default=0)
        gain = 32767 / peak if peak else 0
        return bytes(((7 - min(7, max(0, int(lo / value * 8))) if value else 7) << 5) |
                     min(31, int(int(value * gain) ** 2 * HEIGHT_SCALE))
                     for value, lo in zip(blue, low_blue))
    if tag != b"PWV5":
        raise ValueError("unsupported column format")
    low = reduce_max(rolling(low_ms, 12), count)
    mid = reduce_max(rolling(mid_ms, 1), count)
    high = reduce_max(high_ms, count)
    full = reduce_max(full_ms, count)
    # The normalizer excludes the last millisecond of each output cell.
    excluded = {(len(full_ms) * i + count - 1) // count - 1 for i in range(1, count)}
    excluded.add(len(full_ms) - 1)
    maximum = max((v for i, v in enumerate(full_ms) if i not in excluded), default=0)
    out = bytearray()
    for value, lo, mi, hi in zip(full, low, mid, high):
        # A column can peak in a millisecond excluded by the normalizer.
        # Saturate the five-bit height: masking would turn 32 into silence.
        height = min(31, int(int(value * 32767 / maximum) ** 2 * HEIGHT_SCALE)) if maximum else 0
        r, g, b = rgb_bits(lo, mi, hi)
        out.extend(struct.pack(">H", r << 13 | g << 10 | b << 7 | height << 2))
    return bytes(out)



from app.stems.wave_encoding import three_band


def columns(pcm, frames, tag, count, ffmpeg="ffmpeg", checkpoint=lambda: None, *, rate=RATE, progress=lambda value: None, accelerator=None):
    peak_reader = accelerator.peaks if accelerator else peaks
    if tag not in (None, b"PWV3", b"PWV5", b"PWV7"):
        raise ValueError("unsupported column format")
    if not 8000 <= rate <= 192000:
        raise ValueError("waveform sample rate")
    if frames < rate // 10 or (frames * CADENCE + rate - 1) // rate != count:
        raise ValueError("waveform column count")
    if pcm.stat().st_size != frames * 8:
        raise ValueError("waveform PCM length")
    total = (count * rate + CADENCE - 1) // CADENCE
    left, right = "trunc(val(0)*32768)", "trunc(val(1)*32768)"
    blue = f"trunc(({left}+{right})/2)"
    left, right = f"({left}/32767)", f"({right}/32767)"
    mono = f"if(lt(abs(abs({left})-abs({right})),0.001),if(gt(abs({left}),abs({right})),{left},{right}),({left}+{right})/2)"
    graph = [f"[0:a]apad=whole_len={total},asplit=2[a][b]",
             f"[a]aeval='{blue}':c=mono,aformat=channel_layouts=mono,asplit=2[o0][bl]", f"[bl]{biquad(150, rate=rate)}[o1]",
             f"[b]aeval='{mono}':c=mono,aformat=channel_layouts=mono,asplit=7[o2][lo][mi][hi][blow][bmid][bhigh]",
             f"[lo]{biquad(100, rate=rate)}[o3]", f"[mi]{biquad(300, True, rate)},{biquad(3000, rate=rate)}[o4]",
             f"[hi]{biquad(1500, True, rate)}[o5]",
             f"[blow]{biquad(300, rate=rate)}[o6]",
             f"[bmid]{biquad(250, True, rate)},{biquad(1200, rate=rate)}[o7]",
             f"[bhigh]{biquad(3000, True, rate)},{biquad(9000, rate=rate)}[o8]"]
    # A single requested format creates only its own filter outputs.
    indices = list(range(9))
    if tag == b"PWV3":
        indices = [0, 1]
        graph = [f"[0:a]apad=whole_len={total},aeval='{blue}':c=mono,aformat=channel_layouts=mono,asplit=2[o0][bl]",
                 f"[bl]{biquad(150, rate=rate)}[o1]"]
    elif tag == b"PWV5":
        indices = [2, 3, 4, 5]
        graph = [f"[0:a]apad=whole_len={total},aeval='{mono}':c=mono,aformat=channel_layouts=mono,asplit=4[o2][lo][mi][hi]",
                 f"[lo]{biquad(100, rate=rate)}[o3]", f"[mi]{biquad(300, True, rate)},{biquad(3000, rate=rate)}[o4]",
                 f"[hi]{biquad(1500, True, rate)}[o5]"]
    elif tag == b"PWV7":
        indices = [6, 7, 8]
        graph = [f"[0:a]apad=whole_len={total},aeval='{mono}':c=mono,aformat=channel_layouts=mono,asplit=3[blow][bmid][bhigh]",
                 f"[blow]{biquad(300, rate=rate)}[o6]",
                 f"[bmid]{biquad(250, True, rate)},{biquad(1200, rate=rate)}[o7]",
                 f"[bhigh]{biquad(3000, True, rate)},{biquad(9000, rate=rate)}[o8]"]
    with tempfile.TemporaryDirectory(prefix="rx3-wave-dsp-") as directory:
        files = {i: pathlib.Path(directory) / f"channel-{i}.f64" for i in indices}
        command = [str(ffmpeg), "-v", "error", "-nostdin", "-y", "-f", "f32le", "-ar", str(rate),
                   "-ac", "2", "-i", str(pcm), "-filter_complex", ";".join(graph)]
        for i, path in files.items():
            command.extend(["-map", f"[o{i}]", "-f", "f64le", str(path)])
        checkpoint()
        progress(0)
        result = processes.run(command, capture_output=True, timeout=600)
        if result.returncode or any(p.stat().st_size != total * 8 for p in files.values()):
            raise ValueError("waveform filtering")
        checkpoint()
        progress(.25)
        cells = [(i * rate + CADENCE - 1) // CADENCE for i in range(count + 1)]
        blue_peaks, blue_low = ([peak_reader(files[i], cells, integer=True) for i in (0, 1)]
                                if tag in (None, b"PWV3") else ([], []))
        if tag == b"PWV3":
            return encode(blue_peaks, blue_low, [], [], [], [], count, tag)
        # Padding the final column must not stretch the RGB envelope axis.
        milliseconds = (frames * 1000 + rate - 1) // rate
        bounds = [(i * rate + 999) // 1000 for i in range(milliseconds)] + [frames]
        full, low, mid, high = ([peak_reader(files[i], bounds, integer=True, scale=32768) for i in range(2, 6)]
                                if tag in (None, b"PWV5") else ([], [], [], []))
        if tag in (b"PWV3", b"PWV5"):
            return encode(blue_peaks, blue_low, full, low, mid, high, count, tag)
        bands = [peak_reader(path, bounds, integer=True, scale=32768) for path in (files[i] for i in range(6, 9))]
        checkpoint()
        progress(.4)
        band_data = three_band(bands, count, checkpoint, lambda value: progress(.4 + .6 * value), accelerator=accelerator)
        if tag == b"PWV7":
            return band_data
        if tag is not None:
            raise ValueError("unsupported column format")
        return {b"PWV3": encode(blue_peaks, blue_low, full, low, mid, high, count, b"PWV3"),
                b"PWV5": encode(blue_peaks, blue_low, full, low, mid, high, count, b"PWV5"),
                b"PWV7": band_data}
