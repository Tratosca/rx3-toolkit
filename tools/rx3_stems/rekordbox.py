# SPDX-License-Identifier: MPL-2.0
"""Read a Rekordbox XML export and resolve its playlists to local audio files."""

from __future__ import annotations

import pathlib
import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


DRIVE_LETTER = re.compile(r"^/[A-Za-z]:")
# Exporting to a drive shortens the filename: Rekordbox keeps the first 44
# characters of the stem and the extension, and leaves the library file alone.
# The deck asks for the sidecar under the basename of the file it loaded, which
# is the shortened one, so the sidecar has to carry the same cut. Trailing
# spaces survive the cut on the device, so nothing is trimmed after it.
EXPORT_STEM_LIMIT = 44


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
