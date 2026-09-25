# SPDX-License-Identifier: MPL-2.0
"""Resolve a Rekordbox library to playlists of local audio files.

Two sources, and neither replaces the other. An XML export describes a library
that lives on the computer, which is where stems are prepared before a drive is
written. `export.pdb` describes a drive as the player will read it, which is the
only answer that cannot disagree with the deck.

Both return the same `Collection`, so nothing downstream learns which was used.
"""

from __future__ import annotations

import pathlib
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from app.stems import pdb, safety


DRIVE_LETTER = re.compile(r"^/[A-Za-z]:")
# Exporting to a drive shortens the filename: Rekordbox keeps the first 44
# characters of the stem and the extension, and leaves the library file alone.
# The deck asks for the stem under the basename of the file it loaded, which
# is the shortened one, so the stem has to carry the same cut. Trailing
# spaces survive the cut on the device, so nothing is trimmed after it.
EXPORT_STEM_LIMIT = 44

# Where the player keeps its own description of the drive.
PDB_PATH = "PIONEER/rekordbox/export.pdb"
# An export past this is not one this reads into memory in one go.
PDB_MAX_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class Track:
    track_id: str
    title: str
    artist: str
    duration: int
    location: pathlib.Path
    exists: bool

    @property
    def label(self) -> str:
        return f"{self.artist} — {self.title}"


@dataclass(frozen=True)
class Playlist:
    playlist_id: str
    name: str
    path: str
    tracks: tuple[Track, ...] = field(default=())

    @property
    def missing_count(self) -> int:
        return sum(not track.exists for track in self.tracks)

    @property
    def label(self) -> str:
        detail = f"{len(self.tracks)} tracks"
        if self.missing_count:
            detail += f", {self.missing_count} missing"
        return f"{self.path}  ({detail})"


@dataclass(frozen=True)
class Collection:
    xml: pathlib.Path
    track_count: int
    playlists: tuple[Playlist, ...]

    def playlist(self, playlist_id: str) -> Playlist:
        for entry in self.playlists:
            if entry.playlist_id == playlist_id:
                return entry
        raise ValueError(f"Unknown playlist: {playlist_id}")


def file_url_to_path(value: str) -> pathlib.Path:
    """Resolve a Rekordbox `Location` attribute to a local filesystem path."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError(f"Location is not a local file: {value}")
    path = urllib.parse.unquote(parsed.path if parsed.scheme else value)
    # Rekordbox on Windows exports file://localhost/C:/Music/Track.aiff. The
    # leading slash belongs to the URL path, not to the filesystem path.
    if DRIVE_LETTER.match(path):
        path = path[1:]
    return pathlib.Path(path)


def safe_stem(value: str) -> str:
    """Reduce a filename stem to what the RX3 load interface can match."""
    value = unicodedata.normalize("NFC", value).replace("/", "_").replace(":", "_")
    value = "".join(character for character in value if ord(character) >= 32).strip(" .")
    return value[:180] or "track"


def export_stem(value: str) -> str:
    """The stem this file carries once Rekordbox has exported it to a drive.

    A stem already within the limit is returned unchanged, so a drive filled by
    hand rather than by an export matches just the same.
    """
    return safe_stem(value)[:EXPORT_STEM_LIMIT] or "track"


def parse_collection(xml_path: pathlib.Path) -> Collection:
    """Parse a Rekordbox XML export into playlists of resolved tracks."""
    safety.require_library_closed()
    root = ET.parse(xml_path).getroot()
    if root.tag != "DJ_PLAYLISTS":
        raise ValueError("This file is not a Rekordbox XML export")
    collection = root.find("COLLECTION")
    playlists_root = root.find("PLAYLISTS")
    if collection is None or playlists_root is None:
        raise ValueError("COLLECTION or PLAYLISTS is missing from the XML export")

    tracks: dict[str, Track] = {}
    for node in collection.findall("TRACK"):
        try:
            path = file_url_to_path(node.get("Location", ""))
        except ValueError:
            path = pathlib.Path("")
        track_id = node.get("TrackID", "")
        tracks[track_id] = Track(
            track_id=track_id,
            title=node.get("Name", "Untitled"),
            artist=node.get("Artist", "Unknown artist"),
            duration=int(float(node.get("TotalTime", "0") or 0)),
            location=path,
            exists=path.is_file(),
        )

    playlists: list[Playlist] = []

    def walk(parent: ET.Element, names: tuple[str, ...]) -> None:
        for node in parent.findall("NODE"):
            name = node.get("Name", "Unnamed")
            path_names = names + (name,)
            if node.get("Type") == "1":
                selected = tuple(
                    tracks[key]
                    for key in (child.get("Key", "") for child in node.findall("TRACK"))
                    if key in tracks
                )
                playlists.append(Playlist(
                    playlist_id=str(len(playlists)),
                    name=name,
                    path=" / ".join(path_names),
                    tracks=selected,
                ))
            else:
                walk(node, path_names)

    # Rekordbox wraps every playlist in a single folder node named ROOT, which
    # carries no information and only lengthens each displayed path.
    top_level = playlists_root.findall("NODE")
    container = top_level[0] if len(top_level) == 1 and top_level[0].get("Type") == "0" \
        else playlists_root
    walk(container, ())
    return Collection(xml=xml_path, track_count=len(tracks), playlists=tuple(playlists))


def pdb_path(drive: pathlib.Path) -> pathlib.Path:
    """Where the export sits on a drive, whatever the mount point is called."""
    return pathlib.Path(drive) / PDB_PATH


def has_export(drive: pathlib.Path) -> bool:
    return pdb_path(drive).is_file()


def parse_drive(drive: pathlib.Path) -> Collection:
    """Read a drive's own export into the same shape the XML reader returns.

    Track locations come back relative to the drive root, so a drive that
    mounted somewhere else today still resolves. `export_stem` is applied by the
    caller exactly as it is for XML, which is what keeps the stems named the
    way the deck will ask for them whichever reader found the track.
    """
    safety.require_library_closed()
    drive = pathlib.Path(drive)
    export = pdb_path(drive)
    if not export.is_file():
        raise ValueError(f"No Rekordbox export on {drive}")
    if export.stat().st_size > PDB_MAX_BYTES:
        raise ValueError("The Rekordbox export is too large to read")
    tables = pdb.read_tables(export.read_bytes())

    artists: dict[int, str] = {}
    for row in pdb.iter_rows(tables, pdb.TABLE_ARTISTS):
        try:
            artist_id, name = pdb.parse_artist(row)
        except ValueError:
            continue
        artists[artist_id] = name

    tracks: dict[str, Track] = {}
    for row in pdb.iter_rows(tables, pdb.TABLE_TRACKS):
        try:
            parsed = pdb.parse_track(row)
        except ValueError:
            continue
        if not parsed.file_path:
            continue
        # The path is recorded from the drive root with a leading separator.
        location = drive / parsed.file_path.lstrip("/\\")
        key = str(parsed.track_id)
        tracks[key] = Track(
            track_id=key,
            title=parsed.title or location.stem,
            artist=artists.get(parsed.artist_id, "Unknown artist"),
            duration=parsed.duration,
            location=location,
            exists=location.is_file(),
        )

    playlists = _drive_playlists(tables, tracks)
    return Collection(xml=export, track_count=len(tracks), playlists=playlists)


def _drive_playlists(
    tables: pdb.Tables, tracks: dict[str, Track]
) -> tuple[Playlist, ...]:
    """Every playlist on the drive, folders resolved into displayable paths."""
    rows: dict[int, pdb.PlaylistRow] = {}
    for row in pdb.iter_rows(tables, pdb.TABLE_PLAYLIST_TREE):
        try:
            parsed = pdb.parse_playlist_tree_row(row)
        except ValueError:
            continue
        if parsed.playlist_id and parsed.playlist_id not in rows:
            rows[parsed.playlist_id] = parsed
    if not rows:
        return ()

    ordered: dict[int, list[tuple[int, int]]] = {}
    for row in pdb.iter_rows(tables, pdb.TABLE_PLAYLIST_ENTRIES):
        try:
            entry_index, track_id, playlist_id = pdb.parse_playlist_entry_row(row)
        except ValueError:
            continue
        if playlist_id in rows:
            ordered.setdefault(playlist_id, []).append((entry_index, track_id))

    playlists: list[Playlist] = []
    for parsed in sorted(rows.values(), key=lambda item: (item.sort_order, item.name)):
        if parsed.is_folder:
            continue
        selected: list[Track] = []
        seen: set[str] = set()
        for _, track_id in sorted(ordered.get(parsed.playlist_id, ())):
            key = str(track_id)
            # A drive can list one track twice in a playlist. The deck plays it
            # once, and a duplicate would be separated twice for one stem.
            if key in seen or key not in tracks:
                continue
            seen.add(key)
            selected.append(tracks[key])
        playlists.append(Playlist(
            playlist_id=str(parsed.playlist_id),
            name=parsed.name,
            path=pdb.playlist_path(parsed, rows),
            tracks=tuple(selected),
        ))
    return tuple(playlists)
