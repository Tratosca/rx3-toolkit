"""Read-only RX3 USB-B metadata client for the isolated on-deck file service.

Rekordbox export and analysis files are requested by the gateway. A separately
bounded audio range interface can read selected tracks for explicit tests.
The deck reads USB files in a separate process; Python parses on the computer.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import PurePosixPath
import socket
import threading
import time

from pre_gig import decode_analysis, load_tracks

MAX_PDB = 16 * 1024 * 1024
MAX_ANALYSIS = 4 * 1024 * 1024
MAX_AUDIO_RANGE = 256 * 1024


def validate_analysis_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/PIONEER/USBANLZ/"):
        raise ValueError("analysis path outside USBANLZ")
    parts = PurePosixPath(path).parts
    if (".." in parts or len(path) > 228 or
            any(not part.replace(".", "").isalnum() for part in parts[1:]) or
            parts[-1] != "ANLZ0000.DAT"):
        raise ValueError("unsafe analysis path")
    return path


def fetch(host: str, request: str, limit: int, port: int = 50131) -> bytes:
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.settimeout(5)
        sock.sendall((request + "\n").encode("ascii"))
        with sock.makefile("rb") as stream:
            if stream.readline(8) != b"OK\n":
                raise OSError("RX3 metadata service refused the request")
            data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("RX3 metadata response exceeds limit")
    return data


def validate_audio_path(path: str) -> str:
    if (not isinstance(path, str) or not path.startswith("/Contents/") or
            len(path.encode("utf-8")) > 480 or
            any(part in ("", ".", "..") for part in path.split("/")[1:]) or
            not path.lower().endswith((".wav", ".aif", ".aiff", ".flac", ".mp3",
                                       ".m4a", ".aac")) or
            any(ord(character) < 32 or character == "\\" for character in path)):
        raise ValueError("unsafe or unsupported audio path")
    return path


def audio_stat(host: str, path: str, port: int = 50131) -> int:
    encoded = validate_audio_path(path).lstrip("/").encode("utf-8").hex()
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.settimeout(5)
        sock.sendall(f"STAT {encoded}\n".encode("ascii"))
        with sock.makefile("rb") as stream:
            header = stream.readline(40)
    if not header.startswith(b"SIZE ") or not header.endswith(b"\n"):
        raise OSError("RX3 refused audio size request")
    size = int(header[5:-1])
    if not 0 <= size <= 512 * 1024 * 1024:
        raise ValueError("RX3 returned invalid audio size")
    return size


def audio_range(host: str, path: str, offset: int, count: int,
                port: int = 50131) -> tuple[bytes, int]:
    if not isinstance(offset, int) or offset < 0 or not 1 <= count <= MAX_AUDIO_RANGE:
        raise ValueError("audio range must be nonnegative and at most 256 KiB")
    encoded = validate_audio_path(path).lstrip("/").encode("utf-8").hex()
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.settimeout(5)
        sock.sendall(f"RANGE {encoded} {offset} {count}\n".encode("ascii"))
        with sock.makefile("rb") as stream:
            header = stream.readline(48)
            if not header.startswith(b"DATA ") or not header.endswith(b"\n"):
                raise OSError("RX3 refused audio range request")
            fields = header[5:-1].split(b" ")
            if len(fields) != 2 or int(fields[0]) != count:
                raise ValueError("RX3 returned unexpected audio range header")
            size = int(fields[1])
            if not 0 <= size <= 512 * 1024 * 1024 or offset + count > size:
                raise ValueError("RX3 returned invalid audio size")
            data = stream.read(count + 1)
    if len(data) != count:
        raise OSError("RX3 returned truncated or oversized audio range")
    return data, size


class RemoteCatalog:
    def __init__(self, host: str, port: int = 50131):
        self.host, self.port = host, port
        raw = fetch(host, "PDB", MAX_PDB, port)
        # The existing defensive parser accepts a Path. Keep the copy in
        # private host temp storage only long enough to parse it.
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="rx3-remote-pdb-") as directory:
            source = Path(directory) / "export.pdb"
            source.write_bytes(raw)
            rows = load_tracks(source)
        if not rows:
            raise ValueError("remote export contains no tracks")
        self.manifest = {"schema": "rx3-remote/1",
                         "export_pdb_sha256": hashlib.sha256(raw).hexdigest()}
        self.tracks = {str(track_id): {"metadata": meta, "asset": None,
                                       "analysis_error": None}
                       for track_id, meta in rows.items()}
        self._pending: set[str] = set()
        self._last_attempt: dict[str, float] = {}
        self._lock = threading.Lock()
        self._identity_lock = threading.Lock()
        self._verified_at = 0.0
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rx3-analysis")

    def request(self, track_id: int | None) -> None:
        key = str(track_id)
        item = self.tracks.get(key)
        if item is None or item.get("asset") is not None:
            return
        with self._lock:
            if (key in self._pending or len(self._pending) >= 2 or
                    time.monotonic()-self._last_attempt.get(key, -1e9) < 30):
                return
            self._pending.add(key)
            self._last_attempt[key] = time.monotonic()
        self._pool.submit(self._download, key)

    def _download(self, key: str) -> None:
        try:
            path = validate_analysis_path(self.tracks[key]["metadata"]["anlz_path"])
            dat = fetch(self.host, "ANLZ " + path, MAX_ANALYSIS, self.port)
            try:
                ext = fetch(self.host, "ANLZ " + path[:-4] + ".EXT",
                            MAX_ANALYSIS, self.port)
            except OSError:
                ext = None
            if hashlib.sha256(fetch(self.host, "PDB", MAX_PDB, self.port)).hexdigest() != \
                    self.manifest["export_pdb_sha256"]:
                raise ValueError("mounted export changed during analysis fetch")
            decoded = decode_analysis(dat, ext)
            asset = {**decoded, "schema": "rx3-analysis/1", "track_id": int(key),
                     "export_pdb_sha256": self.manifest["export_pdb_sha256"],
                     "dat_sha256": hashlib.sha256(dat).hexdigest(),
                     "ext_sha256": hashlib.sha256(ext).hexdigest() if ext else None}
            self.tracks[key] = {**self.tracks[key], "asset": asset,
                                "analysis_error": None}
        except (OSError, ValueError) as exc:
            # Retain the track's PDB identity, but do not assert beat/phrase.
            self.tracks[key] = {**self.tracks[key], "analysis_error": str(exc)[:160]}
        finally:
            with self._lock:
                self._pending.discard(key)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def verify_export(self, max_age_s: float = 2.0) -> None:
        with self._identity_lock:
            if time.monotonic() - self._verified_at < max_age_s:
                return
            actual = hashlib.sha256(fetch(self.host, "PDB", MAX_PDB,
                                          self.port)).hexdigest()
            if actual != self.manifest["export_pdb_sha256"]:
                raise ValueError("RX3 USB export changed; restart the gateway")
            self._verified_at = time.monotonic()

    def audio_stat(self, track_id: int) -> int:
        self.verify_export()
        item = self.tracks.get(str(track_id))
        if item is None:
            raise KeyError(track_id)
        return audio_stat(self.host, item["metadata"]["file_path"], self.port)

    def audio_range(self, track_id: int, offset: int, count: int) -> tuple[bytes, int]:
        self.verify_export()
        item = self.tracks.get(str(track_id))
        if item is None:
            raise KeyError(track_id)
        return audio_range(self.host, item["metadata"]["file_path"], offset, count,
                           self.port)
