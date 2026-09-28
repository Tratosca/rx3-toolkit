# SPDX-License-Identifier: MPL-2.0
"""Reuse verified final PCM by source content and processing settings."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys
import struct
import tempfile
import threading

from app.stems import provisioning, safety, stem

DEFAULT_LIMIT = 4 * 1024 ** 3
MAX_MANIFEST_BYTES = 4 * 1024 ** 2
LOCK = threading.RLock()


def signature(settings, architecture, roles):
    return {"model": settings.model, "architecture": architecture,
            "preset": settings.mode, "arguments": settings.arguments(architecture),
            "sample_format": "s16_gain", "stem_version": 3, "encoder_version": 2,
            "roles": list(roles)}


def key(source_hash, processing):
    return hashlib.sha256(json.dumps([source_hash, processing], sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def read_manifest(root):
    for path in (root / "RX3_STEMS" / safety.MANIFEST_NAME, root / safety.MANIFEST_NAME):
        if path.is_file():
            try:
                if path.stat().st_size > MAX_MANIFEST_BYTES:
                    return [], True
                value = json.loads(path.read_text(encoding="utf-8"))
                if value.get("format") not in (1, 2) or not isinstance(value.get("tracks"), list):
                    return [], True
                return [entry for entry in value["tracks"] if isinstance(entry, dict)], True
            except (OSError, ValueError, AttributeError):
                return [], True
    return [], False


def verified_files(directory, entry, roles):
    from app.stems import package
    found = {}
    lengths = set()
    # A package is validated once and then exposed as bounded PCM members.
    try:
        name = entry.get("stem", "")
        if not name or pathlib.Path(name).name != name or "\\" in name:
            return None
        container = directory / name
        if container.is_file() and package.is_package(container):
            parsed = package.read(container)
            if tuple(roles) != parsed["roles"]:
                return None
            digest = safety.digest(container)
            for role in roles:
                item = next(i for i in entry["stems"] if i["role"] == role)
                if (item["file"], item["bytes"], item["sha256"]) != (name, container.stat().st_size, digest):
                    return None
            return dict(zip(roles, parsed["members"][:-2]))
    except (OSError, ValueError, KeyError, TypeError, StopIteration, struct.error):
        return None
    try:
        for role in roles:
            item = next(item for item in entry["stems"] if item["role"] == role)
            name = item["file"]
            if not isinstance(name, str) or pathlib.Path(name).name != name or "\\" in name:
                return None
            path = directory / name
            safety.check_target(path)
            size = path.stat().st_size
            with path.open("rb") as source:
                magic, rate, channels, fmt, header, frames, reserved = stem.HEADER.unpack(source.read(64))
            from app.stems.audition import pcm_gain
            pcm_gain(fmt, reserved)
            if (magic, rate, channels, header) != (stem.MAGIC, 44100, 2, 64):
                return None
            if not frames or size != 64 + frames * 4 or size != item["bytes"]:
                return None
            if safety.digest(path) != item["sha256"]:
                return None
            lengths.add(frames)
            found[role] = path
    except (OSError, ValueError, KeyError, TypeError, StopIteration, struct.error):
        return None
    return found if len(lengths) == 1 else None


def mounted_roots():
    if sys.platform == "darwin":
        base = pathlib.Path("/Volumes")
        return tuple(path for path in base.iterdir() if path.is_mount()) if base.is_dir() else ()
    if sys.platform == "win32":
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return tuple(pathlib.Path(f"{chr(65 + i)}:/") for i in range(26) if mask & (1 << i))
    try:
        return tuple(pathlib.Path(line.split()[1].replace("\\040", " ").replace("\\134", "\\"))
                     for line in pathlib.Path("/proc/self/mounts").read_text().splitlines())
    except (OSError, IndexError):
        return ()


def root():
    return provisioning.data_directory() / "stem-cache"


def limit():
    try:
        value = json.loads((provisioning.data_directory() / "stem-cache.json").read_text())["limit"]
        return max(0, int(value))
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_LIMIT


def directories():
    path = root()
    if not path.is_dir() or path.is_symlink():
        return []
    return [p for p in path.iterdir() if p.is_dir() and not p.is_symlink()
            and len(p.name) == 64 and all(c in "0123456789abcdef" for c in p.name)]


def size(path):
    return sum(p.stat().st_size for p in path.iterdir() if p.is_file() and not p.is_symlink())


def prune(maximum=None):
    with LOCK:
        maximum = limit() if maximum is None else maximum
        ordered = sorted(directories(), key=lambda p: p.stat().st_mtime_ns)
        total = sum(size(p) for p in ordered)
        for path in ordered:
            if total <= maximum:
                break
            total -= size(path)
            shutil.rmtree(path)


def configure(maximum=None, clear=False):
    with LOCK:
        if maximum is not None:
            maximum = int(maximum)
            if not 0 <= maximum <= 1024 ** 4:
                from app.localization import LocalizedError
                raise LocalizedError("stems.cacheLimitInvalid")
            path = provisioning.data_directory()
            path.mkdir(parents=True, exist_ok=True)
            target = path / "stem-cache.json"
            partial = target.with_suffix(".partial")
            partial.write_text(json.dumps({"limit": maximum}) + "\n")
            partial.replace(target)
        prune(0 if clear else None)
        return {"limit": limit(), "bytes": sum(size(p) for p in directories())}


def find(source_hash, processing, roles, destination, workspace):
    """Copy a hit locally under the lock so eviction cannot invalidate it."""
    with LOCK:
        local = root() / key(source_hash, processing)
        def candidates():
            try:
                if (local / "entry.json").stat().st_size <= MAX_MANIFEST_BYTES:
                    yield local, json.loads((local / "entry.json").read_text()), True
            except (OSError, ValueError):
                pass
            for drive in mounted_roots():
                if drive.resolve() == destination.resolve():
                    continue
                entries, _ = read_manifest(drive)
                for entry in entries:
                    yield drive / "RX3_STEMS", entry, False
        for directory, entry, cached in candidates():
            if not isinstance(entry, dict) or entry.get("source_sha256") != source_hash or entry.get("processing") != processing:
                continue
            files = verified_files(directory, entry, roles)
            if files is None:
                continue
            copies = {}
            try:
                for role, path in files.items():
                    expected = safety.digest(path) if hasattr(path, "crc") else next(
                        item["sha256"] for item in entry["stems"] if item["role"] == role)
                    target = workspace / (role + stem.ROLE_SUFFIXES[role])
                    with path.open("rb") as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    from app.stems import package
                    if (hasattr(path, "crc") and package.checksum(target) != path.crc or
                            safety.digest(target) != expected):
                        raise ValueError("cache changed")
                    copies[role] = target
                if cached:
                    os.utime(directory, None)
                return copies, entry
            except (OSError, ValueError):
                continue
    return None


def remember(directory, entry, roles):
    with LOCK:
        files = verified_files(directory, entry, roles)
        if files is None or sum(p.stat().st_size for p in files.values()) > limit():
            return
        base = root()
        base.mkdir(parents=True, exist_ok=True)
        target = base / key(entry["source_sha256"], entry["processing"])
        if target.exists():
            if verified_files(target, entry, roles):
                os.utime(target, None)
                return
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=base) as temp:
            stage = pathlib.Path(temp)
            copied = set()
            for member in files.values():
                path = getattr(member, "path", member)
                if path not in copied:
                    shutil.copyfile(path, stage / path.name)
                    copied.add(path)
            (stage / "entry.json").write_text(json.dumps(entry) + "\n")
            # The temporary directory context tolerates its renamed path.
            stage.replace(target)
        prune()
