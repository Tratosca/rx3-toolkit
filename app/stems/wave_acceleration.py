# SPDX-License-Identifier: MPL-2.0
"""Optional NumPy worker; the application remains independent of NumPy."""
import array
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
from app.stems import processes


class Worker:
    def __init__(self, process):
        self.memory = False
        self.process = process
        self.lock = threading.Lock()

    def call(self, action, progress=lambda value: None, **values):
        with self.lock:
            processes.checkpoint()
            try:
                self.process.stdin.write(json.dumps(dict(action=action, **values)) + '\n')
                self.process.stdin.flush()
                while True:
                    response = self.process.stdout.readline()
                    processes.checkpoint()
                    if not response or 'progress' not in json.loads(response):
                        break
                    progress(json.loads(response)['progress'])
            except (OSError, ValueError):
                processes.checkpoint()
                raise
            processes.checkpoint()
            if not response:
                raise RuntimeError('Waveform worker stopped before completing its request')
            result = json.loads(response)
            if not result.get('ok'):
                raise RuntimeError(result.get('error', 'Waveform worker failed'))
            return result.get('result')

    def mix(self, source, files, gains, frames, outputs):
        roles = [{'path': str(path.path), 'offset': path.offset + 64} if hasattr(path, 'offset')
                 else {'path': str(path), 'offset': 64} for path in files]
        self.call('mix', source=str(source), roles=roles, gains=gains,
                  frames=frames, outputs={str(k): str(v) for k, v in outputs.items()})

    def build(self, source, files, frames, ffmpeg, workspace, progress):
        from app.stems import audition
        output = workspace / 'wave-columns.bin'
        roles = [{'path': str(path.path), 'offset': path.offset + 64} if hasattr(path, 'offset')
                 else {'path': str(path), 'offset': 64} for path in files]
        try:
            result = self.call('build', source=str(source), roles=roles, frames=frames,
                               gains=[audition.gain(path) for path in files], ffmpeg=str(ffmpeg),
                               output=str(output), progress=progress)
            size = ((frames + 293) // 294) * 6
            masks = 3 if len(files) == 1 else 7
            if output.stat().st_size != masks * size or len(result['digests']) != masks:
                raise ValueError('Waveform worker output size')
            with output.open('rb') as stream:
                return {mask: (stream.read(size), result['digests'][mask - 1]) for mask in range(1, masks + 1)}
        except BaseException:
            self.close()
            raise
        finally:
            output.unlink(missing_ok=True)

    def peaks(self, path, boundaries, integer=False, scale=1):
        with tempfile.TemporaryDirectory(prefix='rx3-wave-peaks-') as temp:
            output = pathlib.Path(temp) / 'peaks.f64'
            bounds = pathlib.Path(temp) / 'boundaries.i64'
            offsets = array.array('q', boundaries)
            if sys.byteorder != 'little': offsets.byteswap()
            bounds.write_bytes(offsets.tobytes())
            self.call('peaks', source=str(path), boundaries=str(bounds), integer=integer,
                      scale=scale, output=str(output))
            values = array.array('d')
            values.frombytes(output.read_bytes())
            if sys.byteorder != 'little': values.byteswap()
            if len(values) != len(boundaries) - 1:
                raise ValueError('Waveform worker peak count')
            return [int(v) for v in values] if integer else list(values)

    def envelopes(self, bands, count):
        with tempfile.TemporaryDirectory(prefix='rx3-wave-envelope-') as temp:
            source, output = pathlib.Path(temp) / 'bands.i32', pathlib.Path(temp) / 'envelopes.f64'
            values = array.array('i', (v for band in bands for v in band))
            if sys.byteorder != 'little': values.byteswap()
            source.write_bytes(values.tobytes())
            self.call('envelopes', source=str(source), output=str(output), count=count)
            result = array.array('d'); result.frombytes(output.read_bytes())
            if sys.byteorder != 'little': result.byteswap()
            if len(result) != 3 * count: raise ValueError('Waveform worker envelope count')
            return [result[j * count:(j + 1) * count] for j in range(3)]

    def close(self):
        process = self.process
        try:
            if process.poll() is None:
                try:
                    process.stdin.write('{"action":"close"}\n'); process.stdin.flush()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    processes.stop(process)
        finally:
            process.stdin.close(); process.stdout.close()


def open_worker():
    from app.stems import provisioning, engine
    runtime = provisioning.detect()
    if not runtime.ready:
        return None
    try:
        python = engine.interpreter(runtime)
    except RuntimeError:
        return None
    script = (pathlib.Path(sys._MEIPASS) / 'wave_worker.py' if getattr(sys, 'frozen', False)
              else pathlib.Path(__file__).with_name('wave_worker.py'))
    process = processes.start([str(python), '-u', str(script)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, bufsize=1, env=runtime.subprocess_environment())
    worker = Worker(process)
    try:
        response = process.stdout.readline()
        processes.checkpoint()
        if response and json.loads(response).get('available'):
            worker.memory = bool(json.loads(response).get('memory'))
            return worker
    except BaseException:
        worker.close()
        raise
    worker.close()
    return None
