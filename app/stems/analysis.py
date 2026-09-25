# SPDX-License-Identifier: MPL-2.0
"""Read bounded analysis templates without modifying the exported library."""
from __future__ import annotations

import hashlib
import pathlib
import struct
from dataclasses import dataclass

from app.stems import pdb, safety
from app.stems.rekordbox import PDB_MAX_BYTES, export_stem, pdb_path

MAX_BYTES = 32 * 1024 * 1024
MAX_COLUMNS = 540000
STRIDES = {b"PWV3": 1, b"PWV5": 2}


@dataclass(frozen=True)
class Template:
    tag: bytes
    columns: bytes
    count: int
    beats: tuple
    sha256: str
    files: tuple = ()


def tags(data):
    if len(data) < 12 or data[:4] != b"PMAI" or len(data) > MAX_BYTES:
        raise ValueError("analysis header")
    offset, total = struct.unpack_from(">II", data, 4)
    if not 12 <= offset <= total == len(data):
        raise ValueError("analysis length")
    seen = set()
    result = {}
    while offset < total:
        if offset + 12 > total:
            raise ValueError("tag header")
        tag, header, size = struct.unpack_from(">4sII", data, offset)
        if not 12 <= header <= size <= total - offset or tag in seen:
            raise ValueError("tag length or duplicate")
        seen.add(tag)
        block = data[offset:offset + size]
        if tag in STRIDES:
            if header != 24:
                raise ValueError("wave header")
            stride, count, frequency = struct.unpack_from(">III", block, 12)
            if (stride != STRIDES[tag] or frequency != 150 << 16 or
                    not 0 < count <= MAX_COLUMNS or size != header + count * stride):
                raise ValueError("wave axis")
            result[tag] = block[header:]
        elif tag == b"PQTZ":
            if header != 24:
                raise ValueError("beat header")
            count = struct.unpack_from(">I", block, 20)[0]
            if count > MAX_COLUMNS or size != header + count * 8:
                raise ValueError("beat length")
            beats = tuple(struct.iter_unpack(">HHI", block[header:]))
            if any(not 1 <= beat <= 4 or not tempo for beat, tempo, _ in beats):
                raise ValueError("beat values")
            if any(a[2] >= b[2] for a, b in zip(beats, beats[1:])):
                raise ValueError("beat order")
            result[tag] = beats
        elif tag in (b"PWAV", b"PWV2", b"PWV4"):
            minimum = 24 if tag == b"PWV4" else 20
            if header != minimum:
                raise ValueError("preview header")
            if tag == b"PWV4":
                stride, count = struct.unpack_from(">II", block, 12)
                if stride != 6:
                    raise ValueError("preview stride")
            else:
                stride, count = 1, struct.unpack_from(">I", block, 12)[0]
            if count > MAX_COLUMNS or size != header + stride * count:
                raise ValueError("preview length")
        offset += size
    return result


def parse(dat, ext):
    try:
        merged = tags(dat)
        for key, value in tags(ext).items():
            if key in merged:
                raise ValueError("duplicate analysis")
            merged[key] = value
        if b"PQTZ" not in merged:
            return None
        counts = {len(merged[tag]) // stride for tag, stride in STRIDES.items() if tag in merged}
        if len(counts) != 1:
            return None
        tag = b"PWV5" if b"PWV5" in merged else b"PWV3"
        # Length framing makes the two-file identity unambiguous.
        identity = hashlib.sha256(struct.pack("<Q", len(dat)) + dat + ext).hexdigest()
        return Template(tag, merged[tag], counts.pop(), merged[b"PQTZ"], identity)
    except (ValueError, struct.error, OverflowError):
        return None


def contained(root, name):
    parts = pathlib.PurePosixPath(name.replace("\\", "/").lstrip("/"))
    if ".." in parts.parts or not parts.parts or ":" in str(parts):
        raise ValueError("analysis path")
    path = root / parts
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("analysis outside drive")
    return path


def locate(track, drive, source_sha256):
    """Match the output drive's exported audio, not a possibly unrelated track ID."""
    try:
        source = pdb_path(drive)
        if not source.is_file() or source.stat().st_size > PDB_MAX_BYTES:
            return None
        tables = pdb.read_tables(source.read_bytes())
        matches = []
        for row in pdb.iter_rows(tables, pdb.TABLE_TRACKS):
            try:
                entry = pdb.parse_track(row)
            except ValueError:
                continue
            if export_stem(pathlib.PurePosixPath(entry.file_path).stem) == export_stem(track.location.stem):
                matches.append(entry)
        if len(matches) != 1 or not matches[0].analysis_path:
            return None
        entry = matches[0]
        audio = contained(drive, entry.file_path)
        if safety.digest(audio) != source_sha256:
            return None
        dat = contained(drive, entry.analysis_path)
        if dat.suffix.upper() != ".DAT":
            return None
        ext = dat.with_suffix(".EXT")
        if not ext.is_file():
            ext = dat.with_suffix(".ext")
        if not ext.resolve().is_relative_to(drive.resolve()):
            return None
        if any(path.stat().st_size > MAX_BYTES for path in (dat, ext)):
            return None
        stamps = tuple((path, safety.source_stamp(path)) for path in (dat, ext))
        template = parse(dat.read_bytes(), ext.read_bytes())
        for path, stamp in stamps:
            safety.check_source(path, stamp)
        if template:
            return Template(template.tag, template.columns, template.count, template.beats,
                            template.sha256, stamps)
    except (OSError, ValueError, RuntimeError):
        return None
    return None
