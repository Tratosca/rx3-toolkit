# SPDX-License-Identifier: MPL-2.0
"""Verify removable-media writes before publishing files to the player."""
from __future__ import annotations

import csv
import errno
import hashlib
import math
import os
import pathlib
import shutil
import subprocess
import sys

from app.localization import LocalizedError
from app.rx3_stems.stem import ROLE_SUFFIXES, SAMPLE_RATE

MANIFEST_NAME = "rx3-stems-manifest.json"
# Covers integer-second library durations, encoder padding, allocation rounding
# and a small manifest without assuming that replacement frees the old file.
FREE_MARGIN = 16 * 1024 * 1024
BLOCK_BYTES = 1024 * 1024


class SpaceError(LocalizedError):
    pass


def digest(path, progress=lambda done, total: None):
    total = path.stat().st_size
    done = 0
    value = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(BLOCK_BYTES):
            value.update(block)
            done += len(block)
            progress(done, total)
    return value.hexdigest()


def source_stamp(path):
    before = path.stat()
    value = digest(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise LocalizedError("stems.sourceChanged", name=path.name)
    return after.st_size, after.st_mtime_ns, value


def check_source(path, expected):
    if source_stamp(path) != expected:
        raise LocalizedError("stems.sourceChanged", name=path.name)


def check_target(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise LocalizedError("stems.symlink", path=str(path))


def require_space(output, size):
    available = shutil.disk_usage(output).free
    required = size + FREE_MARGIN
    if available < required:
        raise SpaceError("stems.space", required=required, available=available)


def estimated_bytes(track, count, ffmpeg):
    seconds = track.duration
    if not seconds or seconds < 0:
        sibling = pathlib.Path(ffmpeg).with_name("ffprobe" + (".exe" if sys.platform == "win32" else ""))
        probe = str(sibling) if sibling.is_file() else "ffprobe"
        try:
            answer = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                                     "-of", "default=noprint_wrappers=1:nokey=1", str(track.location)],
                                    capture_output=True, text=True, check=True)
            seconds = float(answer.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise LocalizedError("stems.durationUnknown", name=track.location.name) from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise LocalizedError("stems.durationUnknown", name=track.location.name)
    return count * (math.ceil(seconds * SAMPLE_RATE) * 4 + 64)


def sync_directory(path):
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as error:
        if error.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
            raise


def clean_metadata(output):
    check_target(output / MANIFEST_NAME)
    for path in output.iterdir():
        if not path.name.startswith("._"):
            continue
        name = path.name[2:]
        if name == MANIFEST_NAME or any(name.endswith(suffix) for suffix in ROLE_SUFFIXES.values()):
            if path.is_file() or path.is_symlink():
                path.unlink()


def strip_attributes(path):
    if not hasattr(os, "listxattr"):
        return
    try:
        for name in os.listxattr(path, follow_symlinks=False):
            os.removexattr(path, name, follow_symlinks=False)
    except OSError as error:
        if error.errno not in (errno.ENOTSUP, errno.EINVAL):
            raise


def publish(local, destination):
    """A failed readback must leave the previously published file intact."""
    check_target(destination)
    partial = destination.with_name(destination.name + ".partial")
    check_target(partial)
    expected = digest(local)
    # Exclusive creation refuses abandoned files and closes the symlink race at
    # the staging filename. Copy bytes only: source metadata never belongs here.
    created = False
    try:
        with partial.open("xb") as target, local.open("rb") as source:
            created = True
            shutil.copyfileobj(source, target, BLOCK_BYTES)
            target.flush()
            strip_attributes(partial)
            os.fsync(target.fileno())
        if digest(partial) != expected:
            raise LocalizedError("stems.readback", name=destination.name)
        check_target(destination)
        partial.replace(destination)
        clean_metadata(destination.parent)
        sync_directory(destination.parent)
    finally:
        if created:
            partial.unlink(missing_ok=True)


def library_busy():
    try:
        if sys.platform == "win32":
            result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                                    text=True, check=True)
            return any(row and row[0].casefold() == "rekordbox.exe"
                       for row in csv.reader(result.stdout.splitlines()))
        result = subprocess.run(["pgrep", "-ix", "rekordbox"], capture_output=True, text=True)
        if result.returncode not in (0, 1):
            raise OSError("process query failed")
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as error:
        raise LocalizedError("stems.processUnknown") from error


def require_library_closed():
    if library_busy():
        raise LocalizedError("stems.libraryBusy")
