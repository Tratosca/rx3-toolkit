# SPDX-License-Identifier: MPL-2.0
"""Experimental native preparation against the Desktop 2.1.9 reference.

The helper uses the bundled reference coefficients by default. Neither starts
Desktop or accesses the deck. Explicit profiles must match the pinned hash.
"""
import hashlib
import math
from pathlib import Path
import struct
import sys

from app.stems.overcue_loudness import Measurement, gains
from app.stems import processes

COEFFICIENT_SHA256 = 'df98a625978e21767f978986565ab5a6f6b345bf0a0a576f57b64d14e0006713'


def bundled_coefficients():
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / 'stems/overcue-44100-96000.f32'
    return Path(__file__).with_name('data') / 'overcue-44100-96000.f32'


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class NativePreparation:
    def __init__(self, helper, coefficients=None):
        self.helper = Path(helper).resolve(strict=True)
        self.coefficients = Path(coefficients if coefficients is not None else bundled_coefficients()).resolve(strict=True)
        if hashlib.sha256(self.coefficients.read_bytes()).hexdigest() != COEFFICIENT_SHA256:
            raise ValueError('Unrecognized 44.1 to 96 kHz coefficient profile')

    def run(self, *args):
        return processes.run([str(self.helper), *map(str, args)],
                              check=True, capture_output=True, text=True).stdout

    def resample(self, incoming, output):
        result = self.run('resample', incoming, output, self.coefficients).split()
        expected = (incoming.stat().st_size // 8 * 320 // 147) * 8
        if len(result) != 2 or result[0] != 'peak' or output.stat().st_size != expected:
            raise ValueError('Invalid native resampler response')
        peak = f32(float(result[1]))
        if not math.isfinite(peak) or peak < 0:
            raise ValueError('Invalid native peak')
        return peak

    def measure(self, path):
        rows = [line.split() for line in self.run('measure', path).splitlines()]
        frames = path.stat().st_size // 8
        count = (frames + 9599) // 9600
        if (len(rows) != count + 1 or rows[-1][0] != 'peak' or
                any(len(row) != 4 or row[0] != 'window' or row[3] !=
                    ('true' if i < frames // 9600 else 'false')
                    for i, row in enumerate(rows[:-1]))):
            raise ValueError('Invalid native measurement timeline')
        windows = tuple((float(row[1]), float(row[2])) for row in rows[:-1])
        peak = float(rows[-1][1])
        if (not math.isfinite(peak) or peak < 0 or
                any(math.isnan(v) or v == math.inf for window in windows for v in window)):
            raise ValueError('Invalid native loudness')
        return Measurement(windows, peak, frames // 9600)

    def gains(self, floating, peak):
        common = f32(f32(32766 / 32768) / peak) if f32(peak * 32768) > 32766 else 1.
        measurements = {r: self.measure(p) for r, p in floating.items()}
        return common, {r: f32(g) for r, g in
                        gains(measurements, common, rounded_metadata=False).items()}

    def quantize(self, incoming, output, common, gain):
        self.run('quantize', incoming, output, repr(f32(common * gain)))
        if output.stat().st_size * 2 != incoming.stat().st_size:
            raise ValueError('Native quantizer changed the timeline')
