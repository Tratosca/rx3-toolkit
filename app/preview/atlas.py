# SPDX-License-Identifier: MPL-2.0
"""Read an `RX3GLYF1` glyph atlas and compose a string from it.

The deck does exactly this in C, from the same file. Composing is the whole of
what the pad row's typography is: the artwork carries one image per character
on one ground, and a label is those images laid end to end.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"RX3GLYF1"
HEADER = struct.Struct("<8sHHHHHH")
ENTRY = struct.Struct("<HHHHI")

# The grounds, in the order the artwork stores them.
INACTIVE, PRESSED, SELECTED = 0, 1, 2


@dataclass(frozen=True)
class Glyph:
    codepoint: int
    width: int
    advance: int
    offset: int


class Atlas:
    def __init__(self, blob: bytes):
        (magic, self.cell_height, count, self.state_count,
         self.colour_key, self.space_advance, self.ink_left) = HEADER.unpack_from(blob)
        if magic != MAGIC:
            raise ValueError("not a glyph atlas")
        self.blob = blob
        # The ground each set of glyphs was drawn on, so anything compositing
        # them paints the same colour underneath.
        self.grounds = [
            struct.unpack_from("<I", blob, HEADER.size + slot * 4)[0]
            for slot in range(self.state_count)
        ]
        directory = HEADER.size + self.state_count * 4
        self.glyphs: dict[int, Glyph] = {}
        for index in range(count):
            codepoint, width, advance, _, offset = ENTRY.unpack_from(
                blob, directory + index * ENTRY.size
            )
            self.glyphs[codepoint] = Glyph(codepoint, width, advance, offset)

    def ground(self, state: int) -> tuple[int, int, int]:
        packed = self.grounds[state]
        return ((packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF)

    @classmethod
    def load(cls, path: Path) -> "Atlas":
        return cls(Path(path).read_bytes())

    def glyph(self, character: str) -> Glyph | None:
        """Upper case is folded, because the row is upper case."""
        return self.glyphs.get(ord(character.upper()))

    def advance(self, character: str) -> int:
        if character == " ":
            return self.space_advance
        found = self.glyph(character)
        return found.advance if found else 0

    def width(self, text: str) -> int:
        return sum(self.advance(character) for character in text)

    def cell(self, character: str, state: int):
        """The RGB565 cell for one character on one ground, as an image."""
        from PIL import Image

        found = self.glyph(character)
        if found is None:
            return None
        size = found.width * self.cell_height * 2
        start = found.offset + state * size
        raw = self.blob[start:start + size]
        image = Image.new("RGB", (found.width, self.cell_height))
        pixels = image.load()
        for y in range(self.cell_height):
            for x in range(found.width):
                word = raw[(y * found.width + x) * 2] | (
                    raw[(y * found.width + x) * 2 + 1] << 8
                )
                pixels[x, y] = (
                    (word >> 8) & 0xF8, (word >> 3) & 0xFC, (word << 3) & 0xF8,
                )
        return image

    def draw(self, target, text: str, pen: int, top: int, state: int,
             seam: int = 0) -> int:
        """Lay the string down from pen, and answer where it ended.

        `seam` is the width of one deck window. The deck paints each half
        separately in that window's own coordinates, and draws a letter whole or
        not at all, so a glyph straddling the boundary is skipped there. The
        preview would otherwise show a letter no deck will draw.
        """
        key = (
            ((self.colour_key >> 8) & 0xF8),
            ((self.colour_key >> 3) & 0xFC),
            ((self.colour_key << 3) & 0xF8),
        ) if self.colour_key else None
        for character in text:
            if character != " ":
                cell = self.cell(character, state)
                left = pen - self.ink_left
                straddles = seam and (left // seam) != ((left + cell.width - 1) // seam) \
                    if cell is not None else False
                if cell is not None and not straddles:
                    # The glyph origin sits ink_left into its cell.
                    target.paste(
                        cell, (pen - self.ink_left, top),
                        _keyed(cell, key) if key else None,
                    )
            pen += self.advance(character)
        return pen


def _keyed(cell, key):
    """A mask that drops exactly the key colour, which is what the deck skips."""
    from PIL import Image

    mask = Image.new("L", cell.size, 255)
    source = cell.load()
    holes = mask.load()
    for y in range(cell.height):
        for x in range(cell.width):
            if source[x, y] == key:
                holes[x, y] = 0
    return mask
