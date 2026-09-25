# SPDX-License-Identifier: MPL-2.0
"""Obtain the deck's key from the source package the manufacturer publishes.

The player runs a maintenance image only if it decrypts with a key the player
holds, and that key ships inside the root filesystem archive that sits in the
XDJ-RX3 GPL source package on the manufacturer's own site. This module fetches
that package from there, reads the one file it needs, and keeps nothing else.
No key, and nothing from which one can be derived, is part of the toolkit.

Every input is pinned by SHA-256: both archives, the root filesystem archive
inside them, and the key read from it. A package that differs in any byte is
refused rather than trusted, because a key that is merely plausible builds an
image the deck ignores in silence. The hashes identify files; none of them can
be turned back into the key.

The package is 252 MB for 90 bytes of use, so it is streamed rather than laid
out on disk: the two archives are downloaded (resumable, since a dropped
connection at 200 MB should not cost the first 200 MB again), then read in one
pass. Neither the source tree nor the filesystem is ever written anywhere.
"""

from __future__ import annotations

import bz2
import dataclasses
import hashlib
import io
import json
import os
import pathlib
import ssl
import struct
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from typing import Callable, Iterable, Iterator

from app.localization import LocalizedError


SOURCE_NAME = "key_source.json"


@dataclasses.dataclass(frozen=True)
class Part:
    """One archive of the published package, as the manufacturer serves it."""

    url: str
    name: str
    size: int
    sha256: str
    # The single member each archive holds: consecutive pieces of one tar.bz2.
    member: str


@dataclasses.dataclass(frozen=True)
class Source:
    """Where the package is and what every piece of it must hash to.

    Kept in `key_source.json` beside this file rather than in the code, so a
    moved link is a data change. The hashes travel with the links on purpose: a
    new link to different bytes is a new package, and has to be checked as one.
    """

    page: str
    # Order matters: the second archive continues the first.
    parts: tuple[Part, ...]
    filesystem_member: str
    filesystem_sha256: str
    key_member: str
    # Of the 32 bytes the player actually uses (`firmware_image.load_key`), not
    # of the file, so a key is checked by what it does rather than how it looks.
    key_sha256: str


def source_path() -> pathlib.Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return pathlib.Path(bundled) / "firmware" / SOURCE_NAME
    return pathlib.Path(__file__).with_name(SOURCE_NAME)


def load_source(path: pathlib.Path | None = None) -> Source:
    data = json.loads((path or source_path()).read_text(encoding="utf-8"))
    return Source(
        page=data["page"],
        parts=tuple(Part(**part) for part in data["parts"]),
        filesystem_member=data["filesystem"]["member"],
        filesystem_sha256=data["filesystem"]["sha256"],
        key_member=data["key"]["member"],
        key_sha256=data["key"]["sha256"],
    )


KEY_NAME = "aes256.key"

# The archives say Deflate64, which `zipfile` lists but cannot read.
DEFLATE64 = 9
CHUNK = 1 << 16
TIMEOUT = 60

Progress = Callable[[int, int, int], None]


class Cancelled(Exception):
    """The operator stopped the download; nothing half-written is kept."""


def directory() -> pathlib.Path:
    """The per-user folder that holds the key, outside every repository."""
    override = os.environ.get("RX3_TOOLKIT_HOME")
    if override:
        return pathlib.Path(override).expanduser()
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library/Application Support/XDJ-RX3 Toolkit"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData/Local")
        return pathlib.Path(base) / "XDJ-RX3 Toolkit"
    base = os.environ.get("XDG_DATA_HOME") or str(pathlib.Path.home() / ".local/share")
    return pathlib.Path(base) / "xdj-rx3-toolkit"


def effective(raw: bytes) -> bytes:
    """The 32 bytes the player derives from a key file (first line, 31 bytes, NUL)."""
    lines = raw.splitlines()
    return (lines[0] if lines else b"")[:31].ljust(32, b"\0")


def stored(folder: pathlib.Path | None = None, source: Source | None = None) -> pathlib.Path | None:
    """The kept key, if there is one and it is the right one."""
    source = source or load_source()
    path = (folder or directory()) / KEY_NAME
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return path if hashlib.sha256(effective(raw)).hexdigest() == source.key_sha256 else None


def _context() -> ssl.SSLContext:
    # A frozen interpreter does not always find the system's certificates;
    # certifi carries its own, and the payloads are pinned regardless.
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    part: Part,
    folder: pathlib.Path,
    progress: Progress = lambda done, total, index: None,
    stopped: Callable[[], bool] = lambda: False,
    index: int = 0,
    opener: Callable[..., object] | None = None,
) -> pathlib.Path:
    """Fetch one archive into `folder`, resuming a partial one, and verify it."""
    target = folder / part.name
    if target.is_file() and target.stat().st_size == part.size and _sha256(target) == part.sha256:
        progress(part.size, part.size, index)
        return target
    partial = target.with_name(target.name + ".partial")
    have = partial.stat().st_size if partial.is_file() else 0
    if have > part.size:
        partial.unlink()
        have = 0
    if have < part.size:
        request = urllib.request.Request(part.url, headers={"User-Agent": "xdj-rx3-toolkit"})
        if have:
            request.add_header("Range", f"bytes={have}-")
        open_url = opener or (lambda req: urllib.request.urlopen(req, timeout=TIMEOUT, context=_context()))
        try:
            response = open_url(request)
        except (urllib.error.URLError, OSError) as error:
            raise LocalizedError("error.keyNetwork", name=part.name,
                                 reason=str(getattr(error, "reason", error))) from error
        with response:
            # A server that ignores the range starts over from byte zero.
            if have and getattr(response, "status", 200) != 206:
                have = 0
            with partial.open("ab" if have else "wb") as handle:
                while True:
                    if stopped():
                        raise Cancelled()
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    have += len(chunk)
                    if have > part.size:
                        break
                    progress(have, part.size, index)
    if have != part.size or _sha256(partial) != part.sha256:
        partial.unlink(missing_ok=True)
        raise LocalizedError("error.keyPackage", name=part.name)
    partial.replace(target)
    return target


def _inflated(path: pathlib.Path, part: Part) -> Iterator[bytes]:
    """The single member of one archive, decompressed as it is read."""
    import inflate64

    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
    if len(entries) != 1 or entries[0].filename != part.member or entries[0].compress_type != DEFLATE64:
        raise LocalizedError("error.keyPackage", name=part.name)
    entry = entries[0]
    inflater = inflate64.Inflater()
    with path.open("rb") as handle:
        handle.seek(entry.header_offset)
        header = handle.read(30)
        if len(header) != 30 or struct.unpack_from("<I", header)[0] != 0x04034B50:
            raise LocalizedError("error.keyPackage", name=part.name)
        name_length, extra_length = struct.unpack_from("<HH", header, 26)
        handle.seek(name_length + extra_length, io.SEEK_CUR)
        remaining = entry.compress_size
        while remaining:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                raise LocalizedError("error.keyPackage", name=part.name)
            remaining -= len(chunk)
            data = inflater.inflate(chunk)
            if data:
                yield data


def _bunzipped(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """bzip2 across the seam between the two pieces, and across stream ends."""
    decompressor = bz2.BZ2Decompressor()
    for chunk in chunks:
        while chunk:
            if decompressor.eof:
                chunk = decompressor.unused_data + chunk
                decompressor = bz2.BZ2Decompressor()
            data = decompressor.decompress(chunk)
            chunk = b""
            if data:
                yield data


class _Stream(io.RawIOBase):
    """A generator of bytes, as the file object `tarfile` wants to read."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._pending = b""

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        while not self._pending:
            self._pending = next(self._chunks, b"")
            if not self._pending:
                return 0
        count = min(len(buffer), len(self._pending))
        buffer[:count] = self._pending[:count]
        self._pending = self._pending[count:]
        return count


def key_from_parts(paths: Iterable[pathlib.Path], source: Source | None = None) -> bytes:
    """Read the key out of the downloaded archives, without laying them out."""
    source = source or load_source()
    pieces = list(zip(paths, source.parts))

    def chunks() -> Iterator[bytes]:
        for path, part in pieces:
            yield from _inflated(path, part)

    stream = io.BufferedReader(_Stream(_bunzipped(chunks())), 1 << 20)
    filesystem = None
    try:
        with tarfile.open(fileobj=stream, mode="r|") as package:
            for member in package:
                if member.name == source.filesystem_member and member.isfile():
                    handle = package.extractfile(member)
                    filesystem = handle.read() if handle else None
                    break
    except (tarfile.TarError, OSError, EOFError) as error:
        raise LocalizedError("error.keyPackage", name=source.filesystem_member) from error
    if filesystem is None or hashlib.sha256(filesystem).hexdigest() != source.filesystem_sha256:
        raise LocalizedError("error.keyPackage", name=source.filesystem_member)
    with tarfile.open(fileobj=io.BytesIO(filesystem), mode="r:gz") as tree:
        try:
            handle = tree.extractfile(source.key_member)
        except KeyError:
            handle = None
        raw = handle.read() if handle else b""
    if hashlib.sha256(effective(raw)).hexdigest() != source.key_sha256:
        raise LocalizedError("error.keyPackage", name=source.key_member)
    return raw


def keep(raw: bytes, folder: pathlib.Path) -> pathlib.Path:
    """Write the key where only this account can read it, atomically."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / KEY_NAME
    temporary = path.with_name(path.name + ".partial")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return path


def forget(folder: pathlib.Path | None = None) -> tuple[str, ...]:
    """Delete the kept key and any download in progress, and nothing else.

    Only names this module writes are touched, so a folder the operator pointed
    `RX3_TOOLKIT_HOME` at keeps whatever else they put there. The folder itself
    goes only if that leaves it empty.
    """
    folder = folder or directory()
    removed = []
    for name in (KEY_NAME, KEY_NAME + ".partial"):
        path = folder / name
        if path.is_file():
            path.unlink()
            removed.append(name)
    downloads = folder / "download"
    if downloads.is_dir():
        for item in downloads.iterdir():
            if item.is_file() and item.name.endswith((".zip", ".zip.partial")):
                item.unlink()
                removed.append(f"download/{item.name}")
        if not any(downloads.iterdir()):
            downloads.rmdir()
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    return tuple(removed)


def total_size(source: Source | None = None) -> int:
    return sum(part.size for part in (source or load_source()).parts)


def obtain(
    progress: Progress = lambda done, total, index: None,
    stopped: Callable[[], bool] = lambda: False,
    folder: pathlib.Path | None = None,
    opener: Callable[..., object] | None = None,
    source: Source | None = None,
) -> pathlib.Path:
    """Download, verify, keep the key, and delete everything else.

    Verified archives are kept across a cancelled or failed run and reused, so
    only a finished run removes them.
    """
    source = source or load_source()
    folder = folder or directory()
    existing = stored(folder, source)
    if existing:
        return existing
    downloads = folder / "download"
    downloads.mkdir(parents=True, exist_ok=True)
    paths = [download(part, downloads, progress, stopped, index, opener)
             for index, part in enumerate(source.parts)]
    if stopped():
        raise Cancelled()
    path = keep(key_from_parts(paths, source), folder)
    for item in downloads.iterdir():
        item.unlink(missing_ok=True)
    downloads.rmdir()
    return path
