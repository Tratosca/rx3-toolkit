# SPDX-License-Identifier: MPL-2.0
"""Additional desktop export; RX3 packages remain the primary output."""
import os
from pathlib import Path
import tempfile
import sys

from app.localization import LocalizedError, Message
from app.stems import overcue, package, rekordbox, safety
from app.stems.overcue_exact import NativePreparation

# Rounded from one 30-second, non-silent music fixture (74,935,926 bytes).
# This is a storage estimate, not a free-space requirement or a quality claim.
ESTIMATED_BYTES_PER_SECOND = 2_500_000


def estimate(tracks):
    tracks = list({str(t.location): t for t in tracks}.values())
    unknown = sum(not t.duration or t.duration <= 0 for t in tracks)
    seconds = sum(max(0, t.duration or 0) for t in tracks)
    return {"bytes": round(seconds * ESTIMATED_BYTES_PER_SECOND), "unknown": unknown}


def native():
    """Never silently replace the requested reference processing with FFmpeg."""
    executable = 'rx3-overcue-audio' + ('.exe' if sys.platform == 'win32' else '')
    default_helper = (Path(sys._MEIPASS) / 'overcue' / executable if hasattr(sys, '_MEIPASS') else
                      Path(__file__).resolve().parents[2] / 'build/overcue-audio/release' / executable)
    helper = os.environ.get("RX3_OVERCUE_HELPER", str(default_helper))
    coefficients = os.environ.get("RX3_OVERCUE_COEFFICIENTS")
    if not Path(helper).is_file() or not os.access(helper, os.X_OK):
        raise LocalizedError("stems.overcueUnavailable")
    try:
        return NativePreparation(helper, coefficients)
    except (OSError, ValueError) as error:
        raise LocalizedError("stems.overcueUnavailable") from error


def status():
    try:
        native()
    except LocalizedError:
        return {"ready": False, "message": Message("stems.overcueUnavailable")}
    return {"ready": True, "message": Message("stems.overcueExperimental")}


class Export:
    """Bind selected files to the destination's real export.pdb identities."""
    def __init__(self, root, tracks):
        self.root = Path(root).resolve()
        self.native = native()
        self.entries = {}
        if not rekordbox.has_export(self.root):
            raise LocalizedError("stems.overcueLibrary")
        library = rekordbox.parse_drive(self.root)
        by_path = {}
        for playlist in library.playlists:
            for track in playlist.tracks:
                by_path.setdefault(track.location.absolute(), set()).add(track.track_id)
        for track in tracks:
            path = track.location.absolute()
            try:
                relative = '/' + path.relative_to(self.root).as_posix()
                overcue._safe(self.root, relative)
            except ValueError as error:
                raise LocalizedError("stems.overcueTrack", name=track.title) from error
            ids = by_path.get(path, set())
            if len(ids) != 1 or not path.is_file():
                raise LocalizedError("stems.overcueTrack", name=track.title)
            if path.suffix.lower() not in ('.wav', '.aif', '.aiff', '.flac'):
                raise LocalizedError("stems.overcueLossless", name=track.title)
            self.entries[path] = (relative, next(iter(ids)))

    def __call__(self, track, container, ffmpeg, checkpoint):
        checkpoint()
        safety.require_library_closed()
        info = package.read(container)
        frames = info['frames'] * 320 // 147
        # Seven PCM16 roles plus worst-case zlib/page overhead and previews.
        safety.require_space(self.root, frames * 4 * 7 +
                             ((frames * 4 + overcue.PAGE_BYTES - 1) // overcue.PAGE_BYTES) * 1072 * 7 + 1024 * 1024)
        # Seven float roles, seven PCM roles, mixing/preview intermediates.
        safety.require_space(Path(tempfile.gettempdir()), frames * 96 + 1024 * 1024)
        relative, track_id = self.entries[track.location.absolute()]
        return overcue.export_package(self.root, relative, track_id, container,
                                      ffmpeg=ffmpeg, native=self.native, checkpoint=checkpoint)
