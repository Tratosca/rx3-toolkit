# SPDX-License-Identifier: MPL-2.0
"""What a drive carries, and taking it back off.

These are the two questions a support conversation starts with, and neither had
an answer. Installing was the only thing the toolkit could do to a drive.

`status` deliberately reads the manifest the build leaves rather than the image
itself. Decrypting autoexec.bin would need the operator's key to tell them what
they could have been told without it, and a drive built by an older toolkit has
no manifest at all, which is an answer worth giving plainly.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

from app.rx3_runtime import build as build_module
from app.rx3_session import log as session_log

IMAGE_NAME = "autoexec.bin"
RUNTIME_DIRECTORY = session_log.RUNTIME_DIRECTORY


@dataclasses.dataclass(frozen=True)
class Status:
    """What is on the drive, as far as the drive itself says."""

    # An autoexec.bin is present. Everything below may still be unknown.
    installed: bool
    firmware: str | None = None
    modules: tuple[str, ...] = ()
    built_at: str | None = None
    bytes: int = 0
    sha256: str | None = None
    # True when an image is present and nothing recorded what it is: a drive
    # written by a toolkit that predates the manifest, or one hand-copied.
    unrecorded: bool = False
    # What the deck itself reported on its last insertion, which is the only
    # account of what actually loaded rather than what was written.
    loaded: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()


def status(drive: pathlib.Path) -> Status:
    drive = pathlib.Path(drive)
    image = drive / IMAGE_NAME
    session = session_log.read(drive)
    if not image.is_file():
        return Status(installed=False, loaded=session.modules,
                      disabled=session.disabled)
    manifest = drive / build_module.MANIFEST_NAME
    if not manifest.is_file():
        return Status(installed=True, unrecorded=True,
                      bytes=image.stat().st_size,
                      loaded=session.modules, disabled=session.disabled)
    try:
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A manifest that cannot be read says less than no manifest, because it
        # would otherwise be reported as fact.
        return Status(installed=True, unrecorded=True,
                      bytes=image.stat().st_size,
                      loaded=session.modules, disabled=session.disabled)
    return Status(
        installed=True,
        firmware=recorded.get("firmware"),
        modules=tuple(recorded.get("modules") or ()),
        built_at=recorded.get("createdAt"),
        bytes=int(recorded.get("bytes") or image.stat().st_size),
        sha256=recorded.get("sha256"),
        loaded=session.modules,
        disabled=session.disabled,
    )


def remove(drive: pathlib.Path) -> tuple[str, ...]:
    """Take the mod off a drive, and nothing else.

    RX3_RUNTIME holds the deck's session log and the sample banks as well, so
    this is not a directory to delete. What goes is the image, its manifest,
    and the log the mod wrote. What stays is anything the operator put there.
    """
    drive = pathlib.Path(drive)
    removed = []
    for name in (IMAGE_NAME, build_module.MANIFEST_NAME):
        path = drive / name
        if path.is_file():
            path.unlink()
            removed.append(name)
    runtime = drive / RUNTIME_DIRECTORY
    for name in (session_log.SESSION_NAME, session_log.PREVIOUS_NAME):
        path = runtime / name
        if path.is_file():
            path.unlink()
            removed.append(f"{RUNTIME_DIRECTORY}/{name}")
    # Only if the mod was the only thing using it.
    if runtime.is_dir() and not any(runtime.iterdir()):
        runtime.rmdir()
        removed.append(f"{RUNTIME_DIRECTORY}/")
    return tuple(removed)
