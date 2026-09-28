# SPDX-License-Identifier: MPL-2.0
"""Full-mix ceiling prototype derived from OverCue Desktop 2.1.9.

Measurements use FFmpeg EBU R128, not OverCue's Rust implementation. Metadata
rounding is covered by conservative margins. Numerical equivalence to Desktop
is a separate acceptance test; see docs/overcue-prototype.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import array
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class Measurement:
    windows: tuple[tuple[float, float], ...]
    peak: float
    full_windows: int | None = None

    def integrated(self, gain_db=0.):
        # OverCue skips the first three 100 ms windows for integration.
        blocks = [10 ** ((m + gain_db + .691) / 10)
                  for m, _ in self.windows[3:self.full_windows] if m + gain_db > -70]
        if not blocks:
            return -math.inf
        threshold = sum(blocks) / len(blocks) * .1
        gated = [e for e in blocks if e > threshold]
        return -.691 + 10 * math.log10(sum(gated) / len(gated))


def measure(path: Path, *, ffmpeg='ffmpeg'):
    """Measure aligned stereo f32le/96k, including a partial last window.

    Three seconds of analysis-only silence initialize both windows. Padding the
    last block is analysis-only too: the writer never changes the PCM timeline.
    """
    frames, remainder = divmod(path.stat().st_size, 8)
    if remainder or not frames:
        raise ValueError('Expected nonempty stereo f32le')
    count = (frames + 9599) // 9600
    filters = (f'adelay=3000:all=1,apad=whole_len={288000+count*9600},'
               'ebur128=metadata=1:peak=true,ametadata=print:file=-')
    result = subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-f', 'f32le',
                             '-ar', '96000', '-ac', '2', '-i', str(path),
                             '-af', filters, '-f', 'null', '-'],
                            capture_output=True, text=True, check=True)
    records, record = [], {}
    for line in result.stdout.splitlines():
        if line.startswith('frame:'):
            if record:
                records.append(record)
            record = {}
        elif line.startswith('lavfi.r128.'):
            key, value = line.split('=', 1)
            record[key.removeprefix('lavfi.r128.')] = float(value)
    if record:
        records.append(record)
    records = records[30:]
    if len(records) != count or any(not {'M', 'S', 'true_peak'} <= r.keys() for r in records):
        raise ValueError('Incomplete FFmpeg EBU R128 measurements')
    # FFmpeg's rolling energy subtraction can become slightly negative after
    # a signal falls to digital silence, printing NaN. Accept that case only
    # after verifying the entire corresponding PCM window is exactly zero.
    with path.open('rb') as pcm:
        for number, record in enumerate(records):
            for key, blocks in (('M', 4), ('S', 30)):
                if math.isnan(record[key]):
                    first = max(0, (number + 1 - blocks) * 9600)
                    end = min(frames, (number + 1) * 9600)
                    pcm.seek(first * 8)
                    values = array.array('f', pcm.read((end-first)*8))
                    if any(values):
                        raise ValueError('Undefined loudness on a nonsilent window')
                    record[key] = -math.inf
    if any(not math.isfinite(r['true_peak']) or
           any(math.isnan(r[k]) or r[k] == math.inf for k in ('M', 'S')) for r in records):
        raise ValueError('Nonfinite FFmpeg EBU R128 measurement')
    # FFmpeg prints peaks with three decimal places. Upper bound the rounding.
    peak = max(r['true_peak'] for r in records)
    return Measurement(tuple((r['M'], r['S']) for r in records), peak + .0005 if peak else 0.)


def gains(measurements, headroom, *, rounded_metadata=True):
    """Downward gains against full mix: true peak, M/S and gated integrated.

    A negative trim receives 0.1 dB margin. An additional 0.002 dB covers two
    rounded FFmpeg loudness values. Silence remains silence, with unity gain.
    """
    if not 0 < headroom <= 1 or not math.isfinite(headroom):
        raise ValueError('Invalid common headroom')
    full = measurements['full-mix']
    if any(len(m.windows) != len(full.windows) for m in measurements.values()):
        raise ValueError('Selections have different measurement timelines')
    db = 20 * math.log10(headroom)
    guard = .002 if rounded_metadata else 0.
    ceiling = max(-70., full.integrated(db))
    result = {'full-mix': 1.}
    for role, value in measurements.items():
        if role == 'full-mix':
            continue
        if value.peak == 0:
            result[role] = 1.
            continue
        if full.peak == 0:
            result[role] = 0.
            continue
        limit = -db - 20 * math.log10(value.peak)
        for reference, candidate in zip(full.windows, value.windows):
            for ref, val in zip(reference, candidate):
                if not math.isfinite(val):
                    continue
                limit = min(limit, max(-70., ref + db) - (val + db) - guard)
        limit = min(limit, ceiling - value.integrated(db) - guard)
        if limit >= 0:
            result[role] = 1.
            continue
        limit -= .1
        if value.integrated(db + limit) > ceiling - .1:
            lower, upper = limit - 200, limit
            for _ in range(32):
                middle = (lower + upper) / 2
                if value.integrated(db + middle) > ceiling - .1:
                    upper = middle
                else:
                    lower = middle
            limit = lower
        result[role] = min(1., 10 ** (limit / 20))
    return result
