# SPDX-License-Identifier: MPL-2.0
"""Prepared previews stream local binary PCM; legacy analysis keeps its fallback."""
from __future__ import annotations

import array
import base64
import math
import pathlib
import sys
import tempfile
import uuid
import subprocess
import threading
import time
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from app.localization import LocalizedError
from app.stems import audition, importing, processes

STREAM_FRAMES = 44100 * 2
CHUNK_FRAMES = 44100 * 10
# AudioBuffers contain float32 stereo for the source and each stored role.
MAX_BUFFER_BYTES = 1024 * 1024 * 1024


class Preview:
    def __init__(self, source, files=None, inputs=None, ffmpeg="ffmpeg", *, streaming=False, verified=False):
        self.directory = tempfile.TemporaryDirectory(prefix="rx3-preview-")
        self.token = uuid.uuid4().hex
        self.closed = threading.Event()
        self.process = None
        self.server = None
        self.server_thread = None
        self.io_lock = threading.Lock()
        self.streaming = False
        self.frames = 0
        self.files = []
        self.peaks = []
        self.waveforms = None
        self.waveform_format = None
        try:
            workspace = pathlib.Path(self.directory.name)
            if inputs is not None:
                outputs, _ = importing.prepare(source, inputs, workspace, ffmpeg, waveforms=False)
                files = list(outputs.values())
            self.files = list(files or [])
            self.stamps = [(path.stat().st_size, path.stat().st_mtime_ns) for path in self.files]
            if not self.files:
                return
            lengths = [audition.header(path) for path in self.files]
            if len(set(lengths)) != 1:
                raise LocalizedError("stems.auditionLength")
            self.frames = lengths[0]
            if self.frames * 8 * (1 + len(self.files)) > MAX_BUFFER_BYTES:
                raise LocalizedError("stems.previewMemory")
            self.raw = workspace / "original.f32"
            # Packages already contain every audible selection, at 150 columns/s.
            # Reuse validated bytes instead of re-analyzing all PCM in the webview.
            from app.stems import package, safety
            if isinstance(self.files[0], package.Member):
                parsed = package.read(self.files[0].path, verify=not verified)
                wave = parsed["waveform"]
                if (wave and wave["version"] in (3, 4) and
                        wave["source_sha256"] == safety.digest(source)):
                    with parsed["members"][-2].open() as stream:
                        self.waveforms = {}
                        self.waveform_format = wave["format"].decode()
                        for mask, offset, length, _ in wave["roles"]:
                            stream.seek(offset)
                            self.waveforms[str(mask)] = base64.b64encode(stream.read(length)).decode("ascii")
            self.source = pathlib.Path(source)
            self.source_stamp = (self.source.stat().st_size, self.source.stat().st_mtime_ns)
            self.scales = [audition.gain(path) for path in self.files]
            if streaming and self.waveforms:
                self.streaming = True
                self._start_stream(ffmpeg)
                return
            if importing.decode(source, self.raw, ffmpeg, untrimmed=True) != self.frames:
                raise LocalizedError("stems.auditionLength")
            if self.waveforms:
                return
            # Fixed overview for legacy files without embedded waveforms.
            step = max(1, math.ceil(self.frames / 1600))
            with self.raw.open("rb") as stream:
                while block := stream.read(step * 8):
                    values = array.array("f", block)
                    if sys.byteorder != "little":
                        values.byteswap()
                    self.peaks.append(max(map(abs, values), default=0))
        except BaseException:
            self.close()
            raise

    def close(self):
        self.closed.set()
        if self.process and self.process.poll() is None:
            processes.stop(self.process)
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.server_thread:
            self.server_thread.join(timeout=2)
            self.server_thread = None
        with self.io_lock:
            self.directory.cleanup()

    def _start_stream(self, ffmpeg):
        # FFmpeg writes directly to a local file; no Python sample conversion.
        with self.raw.open("wb") as output:
            self.process = processes.start(
                [str(ffmpeg), "-v", "error", "-flags2", "+skip_manual", "-i", str(self.source),
                 "-map", "0:a:0", "-vn", "-ar", "44100", "-ac", "2", "-f", "f32le", "pipe:1"],
                stdout=output, stderr=subprocess.DEVNULL)
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                # A random per-preview capability exposes only bounded PCM,
                # never a filesystem path or a general file server.
                expected = f"127.0.0.1:{self.server.server_port}"
                origin = self.headers.get("Origin", "null")
                parsed = urlsplit(origin)
                allowed = origin in ("null", "file://") or (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost"))
                parts = self.path.split("/")
                if self.headers.get("Host") != expected or not allowed or len(parts) != 3 or parts[1] != owner.token or not parts[2].isdigit():
                    self.send_error(404); return
                try:
                    payload = owner.binary_chunk(int(parts[2]))
                except (OSError, ValueError, LocalizedError):
                    self.send_error(410); return
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers(); self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError): pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.server_thread.start()

    def binary_chunk(self, first):
        if isinstance(first, bool) or not isinstance(first, int) or first < 0 or first >= self.frames or first % STREAM_FRAMES:
            raise LocalizedError("stems.auditionRange")
        count = min(STREAM_FRAMES, self.frames - first)
        needed = (first + count) * 8
        deadline = time.monotonic() + 30
        while not self.closed.is_set():
            code = self.process.poll()
            size = self.raw.stat().st_size
            if code is not None and (code or size != self.frames * 8):
                raise LocalizedError("stems.auditionLength")
            if size >= needed and (first + count < self.frames or code is not None): break
            if time.monotonic() >= deadline: raise LocalizedError("stems.listenDecode")
            self.closed.wait(.01)
        with self.io_lock:
            if self.closed.is_set(): raise LocalizedError("stems.previewExpired")
            for path, stamp in [(self.source, self.source_stamp), *zip(self.files, self.stamps)]:
                if (path.stat().st_size, path.stat().st_mtime_ns) != stamp:
                    raise LocalizedError("stems.previewExpired")
            with self.raw.open("rb") as source:
                source.seek(first * 8); pcm = source.read(count * 8)
            if len(pcm) != count * 8: raise LocalizedError("stems.auditionLength")
            parts = [struct.pack("<II", first, count), pcm]
            for path in self.files:
                with path.open("rb") as role:
                    role.seek(64 + first * 4); data = role.read(count * 4)
                if len(data) != count * 4: raise LocalizedError("stems.auditionLength")
                parts.append(data)
            return b"".join(parts)

    def describe(self):
        return {"token": self.token, "frames": self.frames, "sampleRate": 44100,
                "available": ((2 << len(self.files)) - 1) if self.files else 0,
                "channels": len(self.files) + 1, "peaks": self.peaks,
                "waveforms": self.waveforms, "waveformFormat": self.waveform_format,
                "chunkFrames": STREAM_FRAMES if self.streaming else CHUNK_FRAMES,
                **({"binaryURL": f"http://127.0.0.1:{self.server.server_port}/{self.token}/",
                    "scales": self.scales, "pcmLayout": "f32-source-s16-roles-v1"} if self.streaming else {})}

    def chunk(self, first):
        if isinstance(first, bool) or not isinstance(first, int) or not 0 <= first < self.frames:
            raise LocalizedError("stems.auditionRange")
        count = min(CHUNK_FRAMES, self.frames - first)
        full = importing.samples(self.raw, first, count)
        streams = [full]
        for path, stamp in zip(self.files, self.stamps):
            if (path.stat().st_size, path.stat().st_mtime_ns) != stamp:
                raise LocalizedError("stems.previewExpired")
            with path.open("rb") as audio:
                audio.seek(64 + first * 4)
                values = audition.read_pcm(audio, count, audition.gain(path))
            if len(values) != count * 2:
                raise LocalizedError("stems.auditionLength")
            role = array.array("f", (value / 32768 for value in values))
            # The RX3 gates every role when both source channels are silent.
            for i in range(0, len(full), 2):
                if full[i] == 0 and full[i + 1] == 0:
                    role[i] = role[i + 1] = 0
            streams.append(role)
        encoded = []
        for values in streams:
            if sys.byteorder != "little":
                values.byteswap()
            encoded.append(base64.b64encode(values.tobytes()).decode("ascii"))
        return {"first": first, "frames": count, "pcm": encoded}
