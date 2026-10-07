"""Decode a bounded source-file excerpt and derive labelled motion features.

These are pre-fader file features at the requested source time, never live mixer
meters. They do not replace a rekordbox beat grid or phrase analysis.
"""
from __future__ import annotations

from array import array
import math
import subprocess
import sys


RATE = 8000
WINDOW = 2000  # quarter-second motion windows


def _dbfs(rms):
    return 20 * math.log10(max(rms, 1e-8))


def analyze_pcm16_mono(data: bytes, start_s: float) -> dict:
    if len(data) % 2 or not data:
        raise ValueError("empty or incomplete PCM excerpt")
    pcm = array("h")
    pcm.frombytes(data)
    if sys.byteorder != "little":
        pcm.byteswap()
    if len(pcm) > RATE * 5:
        raise ValueError("excerpt exceeds five-second limit")
    low_state = mid_state = 0.0
    low_alpha = 1 - math.exp(-2 * math.pi * 200 / RATE)
    mid_alpha = 1 - math.exp(-2 * math.pi * 2000 / RATE)
    windows = []
    previous_rms = 0.0
    for begin in range(0, len(pcm), WINDOW):
        chunk = pcm[begin:begin + WINDOW]
        if len(chunk) < WINDOW // 2:
            break
        total = bands_low = bands_mid = bands_high = 0.0
        peak = 0.0
        for integer in chunk:
            sample = integer / 32768.0
            low_state += low_alpha * (sample - low_state)
            mid_state += mid_alpha * (sample - mid_state)
            low = low_state
            mid = mid_state - low_state
            high = sample - mid_state
            total += sample * sample
            bands_low += low * low
            bands_mid += mid * mid
            bands_high += high * high
            peak = max(peak, abs(sample))
        count = len(chunk)
        rms = math.sqrt(total / count)
        low = math.sqrt(bands_low / count)
        mid = math.sqrt(bands_mid / count)
        high = math.sqrt(bands_high / count)
        summed = low + mid + high
        windows.append({"start_s": start_s + begin / RATE,
                        "end_s": start_s + (begin + count) / RATE,
                        "rms_dbfs": _dbfs(rms), "peak_dbfs": _dbfs(peak),
                        "low": min(1.0, low * 3),
                        "mid": min(1.0, mid * 3),
                        "high": min(1.0, high * 3),
                        "onset": min(1.0, max(0.0, rms - previous_rms) * 6),
                        "centroid_hz": ((100 * low + 800 * mid + 3500 * high) / summed
                                        if summed else 0.0)})
        previous_rms = rms
    return {"schema": "rx3-source-excerpt/1", "source": "sampled_source_file_pre_fader",
            "tap_location": "source_file", "live_audio": False,
            "start_s": start_s, "duration_s": len(pcm) / RATE,
            "sample_rate_hz": RATE, "window_s": WINDOW / RATE,
            "windows": windows,
            "limitations": ["Only the sampled interval is measured",
                            "Band values are coarse motion features, not calibrated EQ or VU",
                            "Rekordbox beat and phrase analysis remains authoritative"]}


def decode_url(url: str, start_s: float, duration_s: float) -> dict:
    if not url.startswith("http://127.0.0.1:") or not 0 <= start_s or not 0 < duration_s <= 5:
        raise ValueError("invalid local excerpt request")
    command = ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(start_s),
               "-i", url, "-t", str(duration_s), "-vn", "-ac", "1",
               "-ar", str(RATE), "-f", "s16le", "pipe:1"]
    result = subprocess.run(command, capture_output=True, timeout=35)
    if result.returncode or not result.stdout or len(result.stdout) > RATE * 5 * 2:
        raise OSError("bounded audio excerpt decode failed: " +
                      result.stderr.decode("utf-8", "replace")[-240:])
    return analyze_pcm16_mono(result.stdout, start_s)
