# SPDX-License-Identifier: MPL-2.0
"""Shared scalar 3Band packing, usable by the standalone waveform worker."""
import math
import struct

_FLOAT = struct.Struct("<f")
def f32(value):
    return _FLOAT.unpack(_FLOAT.pack(value))[0]


def three_band(bands, count, checkpoint=lambda: None, progress=lambda value: None, accelerator=None):
    """PWV7 low/mid/high bytes from integer millisecond peaks.

    The release envelope is restarted for each pixel's bounded look-back.
    Gains use 1200 time windows, then are limited by band peaks and quantized
    to hundredths. High frequencies use a cosine transfer before packing.
    """
    length = len(bands[0])
    if not length or any(len(b) != length for b in bands):
        raise ValueError("three-band envelope length")
    bands = [list(b) for b in bands]
    for band in bands:
        band[-1] = 0
    overview = []
    for band, back in zip(bands, (length // 1000, (length // 1000) * 2 // 3, length // 3000)):
        prefix = [0]
        for value in band:
            prefix.append(prefix[-1] + value)
        values = []
        for i in range(1200):
            start = (length * i + 1199) // 1200 - back
            stop = (length * (i + 1) + 1199) // 1200
            values.append((prefix[stop] - prefix[max(0, start)]) / (stop - start)
                          if stop > start else 0)
        overview.append(values)
    totals = list(map(sum, overview))
    gains = [max(totals) / value if value else 1 for value in totals]
    maximum = max(sum(cell[i] * gains[i] for i in range(3)) for cell in zip(*overview))
    if maximum:
        gains = [gain * 32768 / maximum for gain in gains]
    peaks = list(map(max, bands))
    peaks[2] = (1 - math.cos(peaks[2] * math.pi / 32768)) * 16384
    gains = [int(min(cap, max(.8, min(gain, 32768 / peak if peak else math.inf))) * 100)
             for gain, peak, cap in zip(gains, peaks, (3, 3, 5))]
    envelopes = accelerator.envelopes(bands, count) if accelerator else None
    output = bytearray(count * 3)
    for j, (band, back, decay) in enumerate(zip(bands, (300, 200, 100), (.99, .98, .97))):
        gain = f32(f32(gains[j]) * f32(.01))
        for i in range(count):
            if i % 128 == 0:
                checkpoint()
                progress((j + i / count) / 3)
            start = max(0, (length * i + count - 1) // count - back)
            stop = (length * (i + 1) + count - 1) // count
            envelope = envelopes[j][i] if envelopes is not None else 0.0
            if envelopes is None:
                for value in band[start:stop]:
                    envelope = value + (envelope - value) * decay if value < envelope else value
            value = f32(envelope)
            value = ((1 - math.cos(value * math.pi / 32768)) * 64 * gain if j == 2
                     else value * gain / 256)
            output[i * 3 + j] = min(255, max(0, int(value)))
    progress(1)
    return bytes(output)


def required_memory(frames, masks):
    # Int32 peak tables + one role's Python packing workspace + bounded PCM/filter blocks.
    seconds = frames / 44100
    return int(seconds * (masks * (7 * 1000 + 2 * 150) * 4 + 7 * 1000 * 40) + 96 * 1024**2)
