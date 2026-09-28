# SPDX-License-Identifier: MPL-2.0
"""Private bounded NumPy operations, run by the installed separation Python."""
import contextlib
import json
import pathlib
import sys


def mix(request, np):
    frames = request['frames']
    source = np.memmap(request['source'], dtype='<f4', mode='r', shape=(frames, 2))
    roles = [np.memmap(role['path'], dtype='<i2', mode='r', offset=role['offset'], shape=(frames, 2))
             for role in request['roles']]
    with contextlib.ExitStack() as stack:
        outputs = {int(mask): stack.enter_context(open(path, 'wb'))
                   for mask, path in request['outputs'].items()}
        for start in range(0, frames, 32768):
            full = source[start:start + 32768]
            # Match Python double multiplication followed by float32 storage.
            parts = [(role[start:start + 32768].astype(np.float64) * gain).astype(np.float32)
                     for role, gain in zip(roles, request['gains'])]
            silent = np.all(full == 0, axis=1)
            for mask, output in outputs.items():
                if mask == (2 << len(roles)) - 1:
                    values = full
                else:
                    residual = float(bool(mask & 1))
                    values = full * np.float32(residual)
                    for i, part in enumerate(parts):
                        gain = np.float32((float(bool(mask & (1 << (i + 1)))) - residual) / 32768.)
                        values = np.add(values, part * gain)
                    values[silent] = full[silent]
                output.write(values.astype('<f4', copy=False).tobytes())


def peaks(request, np):
    data = np.memmap(request['source'], dtype='<f8', mode='r')
    boundaries = np.fromfile(request['boundaries'], dtype='<i8')
    starts, stops = boundaries[:-1], boundaries[1:]
    valid = stops > starts
    values = np.zeros(len(starts), dtype=np.float64)
    # Empty cells are possible at low sample rates. Reduce only real intervals.
    if valid.any():
        offsets = starts[valid]
        selected = data[:int(stops[valid][-1])]
        values[valid] = np.maximum(np.maximum.reduceat(selected, offsets),
                                  -np.minimum.reduceat(selected, offsets)) * request['scale']
    if request['integer']:
        values = np.minimum(32767, np.trunc(values))
    values.astype('<f8').tofile(request['output'])


def envelopes(request, np):
    bands = np.fromfile(request['source'], dtype='<i4').reshape(3, -1)
    length = bands.shape[1]
    count = request['count']
    positions = np.arange(count, dtype=np.int64)
    stop = (length * (positions + 1) + count - 1) // count
    output = np.zeros((3, count), dtype=np.float64)
    for j, (back, decay) in enumerate(zip((300, 200, 100), (.99, .98, .97))):
        start = np.maximum(0, (length * positions + count - 1) // count - back)
        envelope = output[j]
        for offset in range(int(np.max(stop - start))):
            index = start + offset
            active = index < stop
            value = bands[j, np.minimum(index, length - 1)]
            updated = np.where(value < envelope, value + (envelope - value) * decay, value)
            envelope[active] = updated[active]
    output.astype('<f8').tofile(request['output'])


def main():
    try:
        import numpy as np
    except ImportError:
        print(json.dumps({'available': False}), flush=True)
        return
    try:
        import wave_memory
    except ImportError:
        wave_memory = None
    print(json.dumps({'available': True, 'memory': wave_memory is not None}), flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request['action'] == 'close':
                return
            if request['action'] == 'build':
                if wave_memory is None:
                    raise RuntimeError('In-memory waveform engine unavailable')
                result = wave_memory.build(request, lambda value: print(json.dumps({'progress': value}), flush=True))
            else:
                {'mix': mix, 'peaks': peaks, 'envelopes': envelopes}[request['action']](request, np)
                result = None
            print(json.dumps({'ok': True, 'result': result}), flush=True)
        except Exception as error:
            print(json.dumps({'ok': False, 'error': str(error)}), flush=True)
            return


if __name__ == '__main__':
    main()
