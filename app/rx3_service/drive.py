# SPDX-License-Identifier: MPL-2.0
"""One drive, described in the terms a screen shows.

Nothing here reads anything new. Four readers already existed and were never
asked together: what was installed, what the deck reported loading, what music
the drive carries, and which sample banks are on it. A screen wants all four at
once and wants none of them to be fatal.

Reading a drive is the one place where a missing part is normal. A drive with
no mod, no export and no banks is a blank USB stick, which is a valid answer and
not a failure.
"""

from __future__ import annotations

from app.localization import Message, LocalizedError

import dataclasses
import pathlib

from app.rx3_service import mod as mod_service
from app.rx3_service import samples as samples_service
from app.rx3_session import log as session_log
from app.rx3_stems import rekordbox


@dataclasses.dataclass(frozen=True)
class Music:
    """The drive's own library, read from its export rather than from Rekordbox."""

    present: bool
    tracks: int = 0
    playlists: int = 0
    # Set when an export is there and could not be read, which is different
    # from there being none.
    unreadable: str = ""


@dataclasses.dataclass(frozen=True)
class Report:
    path: pathlib.Path
    writable: bool
    mod: mod_service.Status
    music: Music
    banks: tuple[str, ...]
    active_bank: str | None
    # The five capabilities the deck declared on its last insertion, each one
    # of ready, declared, disabled, absent or unknown.
    capabilities: dict[str, str]


CAPABILITIES = ("stems", "multi_stems", "samples", "sample_modes", "shift_silence")


def report(path: pathlib.Path) -> Report:
    """Everything known about one drive, with nothing raising on the way."""
    path = pathlib.Path(path)
    if not path.is_dir():
        raise LocalizedError("error.directory", path=str(path))
    session = session_log.read(path)
    banks = samples_service.read(path)
    return Report(
        path=path,
        writable=_writable(path),
        mod=mod_service.status(path),
        music=_music(path),
        banks=banks.names,
        active_bank=banks.active,
        capabilities={name: getattr(session, name) for name in CAPABILITIES},
    )


def _writable(path: pathlib.Path) -> bool:
    """Whether anything could be written here at all.

    A drive mounted read-only reads perfectly and installs nothing, and finding
    that out from a failed write halfway through a build is late.
    """
    probe = path / ".rx3-write-probe"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _music(path: pathlib.Path) -> Music:
    if not rekordbox.has_export(path):
        return Music(present=False)
    try:
        collection = rekordbox.parse_drive(path)
    except Exception as error:  # the reader raises several unrelated types
        return Music(present=True, unreadable=str(error) or error.__class__.__name__)
    return Music(
        present=True,
        tracks=collection.track_count,
        playlists=len(collection.playlists),
    )
