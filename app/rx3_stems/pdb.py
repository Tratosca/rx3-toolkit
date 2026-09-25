# SPDX-License-Identifier: MPL-2.0
"""Read the DeviceSQL export a drive carries, without needing Rekordbox.

`PIONEER/rekordbox/export.pdb` is what the player itself reads, so it is the
only description of a drive that cannot disagree with what the deck will do.
An XML export is a description of a library; this is a description of a drive.

The file is a sequence of fixed-size pages. Each page belongs to a table, holds
its rows at the front and an index of their offsets at the back, and points at
the next page of its table. Rows are read through that index rather than by
walking forward, because a row is variable length and the index is the only
thing that says where the next one starts.

Every row is parsed defensively. A drive is written by a player that may have
been unplugged mid-write, and one unreadable row is not a reason to refuse the
other nine hundred: a row that does not parse is skipped and counted.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterator


class PdbError(ValueError):
    """The file is not a DeviceSQL export, or the part being read is damaged."""


TABLE_TRACKS = 0
TABLE_ARTISTS = 2
TABLE_PLAYLIST_TREE = 7
TABLE_PLAYLIST_ENTRIES = 8

PAGE_HEADER_SIZE = 40
# Rows are indexed in groups of sixteen, each group taking this many bytes at
# the end of the page: a presence bitmap and sixteen offsets.
ROW_GROUP_BYTES = 36
ROWS_PER_GROUP = 16

TRACK_FIXED_SIZE = 94
TRACK_ARTIST_ID = 68
TRACK_ID = 72
TRACK_DURATION = 84
# The fixed part is followed by this many offsets, one per string the row can
# carry. Only two of them are read here.
TRACK_STRING_COUNT = 21
STRING_TITLE = 17
STRING_FILE_PATH = 20

PLAYLIST_NAME = 20
# A folder that contains itself would otherwise walk forever.
PLAYLIST_MAX_DEPTH = 32

# String kinds. A short string carries its length in the same byte as its tag;
# a long one is tagged and then gives a 16-bit length.
STRING_LONG_ASCII = 0x40
STRING_LONG_UTF16 = 0x90


@dataclass(frozen=True)
class Row:
    page: memoryview
    position: int


@dataclass(frozen=True)
class Tables:
    data: bytes
    page_bytes: int
    index: dict[int, tuple[int, int]] = field(default_factory=dict)


def _u8(page: memoryview, position: int) -> int:
    if position < 0 or position >= len(page):
        raise PdbError("read past the end of a page")
    return page[position]


def _u16(page: memoryview, position: int) -> int:
    if position < 0 or position + 2 > len(page):
        raise PdbError("read past the end of a page")
    return struct.unpack_from("<H", page, position)[0]


def _u32(page: memoryview, position: int) -> int:
    if position < 0 or position + 4 > len(page):
        raise PdbError("read past the end of a page")
    return struct.unpack_from("<I", page, position)[0]


def read_string(page: memoryview, position: int) -> str:
    """One string of any of the three forms a row can hold."""
    kind = _u8(page, position)
    if kind in (STRING_LONG_ASCII, STRING_LONG_UTF16):
        length = _u16(page, position + 1)
        if length < 4:
            raise PdbError("a long string declares an impossible length")
        raw = bytes(page[position + 4:min(len(page), position + length)])
        if kind == STRING_LONG_ASCII:
            # Anything above ASCII in a row tagged ASCII is damage, not a
            # character, and replacing it keeps one bad byte from losing a title.
            return raw.decode("ascii", "replace")
        return raw.decode("utf-16-le", "replace")
    length = kind >> 1
    if length < 1:
        raise PdbError("a short string declares an impossible length")
    return bytes(page[position + 1:min(len(page), position + length)]).decode("latin-1")


def read_tables(data: bytes) -> Tables:
    """The page size and where each table starts and ends."""
    if len(data) < 28:
        raise PdbError("the file is too small to be an export")
    zero, page_bytes, table_count = struct.unpack_from("<III", data, 0)
    if zero != 0 or not 512 <= page_bytes <= 65536 or table_count > 64:
        raise PdbError("this is not a DeviceSQL export")
    if 28 + table_count * 16 > len(data):
        raise PdbError("the table directory is truncated")
    index: dict[int, tuple[int, int]] = {}
    for entry in range(table_count):
        base = 28 + entry * 16
        table_type = struct.unpack_from("<I", data, base)[0]
        first, last = struct.unpack_from("<II", data, base + 8)
        index.setdefault(table_type, (first, last))
    return Tables(data=data, page_bytes=page_bytes, index=index)


def iter_rows(tables: Tables, table_type: int) -> Iterator[Row]:
    """Every row of one table, page by page.

    Pages are chained, and a damaged chain can point back at a page already
    read. Visiting each page once is what stops that becoming an endless walk.
    """
    located = tables.index.get(table_type)
    if not located:
        return
    first, last = located
    page_bytes = tables.page_bytes
    view = memoryview(tables.data)
    index = first
    visited: set[int] = set()
    while index not in visited:
        visited.add(index)
        start = index * page_bytes
        if start < 0 or start + page_bytes > len(view):
            return
        page = view[start:start + page_bytes]
        page_type = _u32(page, 8)
        next_page = _u32(page, 12)
        row_count = (_u8(page, 24) | _u8(page, 25) << 8 | _u8(page, 26) << 16) & 0x1FFF
        # The high bit of this byte marks a page that indexes other pages
        # rather than holding rows of its own.
        is_data_page = (_u8(page, 27) & 0x40) == 0
        if page_type == table_type and is_data_page and row_count:
            yield from _iter_page_rows(page, page_bytes, row_count)
        if index == last:
            return
        index = next_page


def _iter_page_rows(page: memoryview, page_bytes: int, row_count: int) -> Iterator[Row]:
    groups = (row_count - 1) // ROWS_PER_GROUP + 1
    emitted: set[int] = set()
    for group in range(groups):
        base = page_bytes - group * ROW_GROUP_BYTES
        if base - 4 < 0:
            return
        present = _u16(page, base - 4)
        remaining = min(ROWS_PER_GROUP, row_count - group * ROWS_PER_GROUP)
        for slot in range(remaining):
            if not (present >> slot) & 1:
                continue
            slot_position = base - 6 - 2 * slot
            if slot_position < 0:
                return
            position = PAGE_HEADER_SIZE + _u16(page, slot_position)
            # A repeated offset is a damaged index, and following it would
            # yield the same row twice.
            if position >= page_bytes or position in emitted:
                continue
            emitted.add(position)
            yield Row(page=page, position=position)


@dataclass(frozen=True)
class TrackRow:
    track_id: int
    artist_id: int
    duration: int
    title: str
    file_path: str


def parse_artist(row: Row) -> tuple[int, str]:
    """An artist id and its name.

    Where the name sits depends on a bit in the row's own subtype, which is how
    the format grew a longer offset without changing the rows that came before.
    """
    subtype = _u16(row.page, row.position)
    artist_id = _u32(row.page, row.position + 4)
    if subtype & 4:
        name_offset = _u16(row.page, row.position + 10)
    else:
        name_offset = _u8(row.page, row.position + 9)
    return artist_id, read_string(row.page, row.position + name_offset).strip()


def parse_track(row: Row) -> TrackRow:
    if row.position + TRACK_FIXED_SIZE + TRACK_STRING_COUNT * 2 > len(row.page):
        raise PdbError("the track row is truncated")

    def string_at(index: int) -> str:
        offset = _u16(row.page, row.position + TRACK_FIXED_SIZE + index * 2)
        return read_string(row.page, row.position + offset).strip()

    return TrackRow(
        track_id=_u32(row.page, row.position + TRACK_ID),
        artist_id=_u32(row.page, row.position + TRACK_ARTIST_ID),
        duration=_u16(row.page, row.position + TRACK_DURATION),
        title=string_at(STRING_TITLE),
        file_path=string_at(STRING_FILE_PATH),
    )


@dataclass(frozen=True)
class PlaylistRow:
    playlist_id: int
    parent_id: int
    sort_order: int
    is_folder: bool
    name: str


def parse_playlist_tree_row(row: Row) -> PlaylistRow:
    return PlaylistRow(
        parent_id=_u32(row.page, row.position),
        sort_order=_u32(row.page, row.position + 8),
        playlist_id=_u32(row.page, row.position + 12),
        is_folder=_u32(row.page, row.position + 16) != 0,
        name=read_string(row.page, row.position + PLAYLIST_NAME).strip(),
    )


def parse_playlist_entry_row(row: Row) -> tuple[int, int, int]:
    """`(entry index, track id, playlist id)` for one line of one playlist."""
    return (
        _u32(row.page, row.position),
        _u32(row.page, row.position + 4),
        _u32(row.page, row.position + 8),
    )


def playlist_path(row: PlaylistRow, by_id: dict[int, PlaylistRow]) -> str:
    """The folders a playlist sits under, as one displayable path."""
    names = [row.name]
    parent = by_id.get(row.parent_id)
    depth = 0
    while parent is not None and depth < PLAYLIST_MAX_DEPTH:
        names.append(parent.name)
        parent = by_id.get(parent.parent_id)
        depth += 1
    return " / ".join(reversed([name for name in names if name]))
