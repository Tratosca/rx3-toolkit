#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Render the KEY/STEMS control labels to raw RGB565, at build time.

Why images rather than text. The mod used to draw its controls by cloning one
of rbp's own text objects and rewriting the string, on the assumption that the
clone carried the typeface. Two measurements killed that: the pad subtree
(`0x17xx`/`0x18xx`) issues no text draw at all -- those stock labels are images
-- and cloning four different donor glyphs rendered the label at 19 px every
time, the same as the header donor. Nothing about the clone selects the face.

So the labels become build-time artwork, the way Pioneer's own are, and reach
the screen through the private image ids the tab strip already uses.

Palette is measured, not chosen: read off the stock tab strip on the device,
beside which these labels sit.

Geometry comes from the panel headers -- a KEY control box is 183x40 at
x 19..201, y 521..560 -- so a label is drawn to fill one control exactly.
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys


# Measured from Pioneer's own BEAT FX labels in imagedata.dat, ids 0x1439..,
# 160x40, which ship four variants of every caption: dim or white lettering on
# a black or blue ground. That is the whole colour language -- the interface is
# monochrome and blue marks the selected item -- and it is why an earlier
# attempt at "colour grading" looked foreign: it used greys sampled from the
# KEY/STEMS tab strip, which is the project's own artwork rather than Pioneer's.
GROUND_BLACK = (0, 0, 0)
GROUND_BLUE = (0, 125, 230)
INK_DIM = (98, 101, 98)
INK_WHITE = (255, 255, 255)

# The same three states for a lit room. Measured off the light artwork of a
# build that shipped with the display mode, rather than derived: applying the
# mode's own pixel transform to the dark artwork reproduces almost none of it,
# because the light assets were drawn and not converted.
#
# Blue is not among them. It means "selected" in both modes, and a selection
# that changed colour with the room would have to be learned twice.
GROUND_LIGHT = (222, 219, 222)
INK_DARK = (41, 40, 41)
INK_MID = (82, 81, 82)

THEMES = {
    "dark": {
        "inactive": (GROUND_BLACK, INK_DIM),
        "selected": (GROUND_BLUE, INK_WHITE),
        "pressed": (GROUND_BLACK, INK_WHITE),
    },
    "light": {
        "inactive": (GROUND_LIGHT, INK_MID),
        "selected": (GROUND_BLUE, INK_WHITE),
        "pressed": (GROUND_LIGHT, INK_DARK),
    },
}
# Pioneer's captions carry no border; the control frame belongs to the pane.
BORDER_WIDTH = 0

def to_rgb565(image) -> bytes:
    packed = bytearray()
    for red, green, blue in list(image.getdata()):
        packed += struct.pack(
            "<H", ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        )
    return bytes(packed)


# Pioneer's captions quantise to sixteen grey levels -- 4-bit anti-aliasing.
# That was first inferred from the caption pixels; it is now confirmed at the
# source, because the firmware's own font file is 4 bpp: NS_FONT_ID_ISO8859_w.bin
# stores 189-byte cells of 14x27 pixels at one nibble each, coverage 0..15.
# See REFERENCES.md, "The bitmap font".
#
# Supersampling matches the coverage totals but fails the eye, and the reason is
# visible at high zoom: Pioneer's vertical stems are solid white with hard
# edges and the anti-aliasing sits only on curves and diagonals. That is
# hinting, snapping stems to the pixel grid, and downsampling an oversized
# render destroys exactly that. So the lettering is drawn once at final size,
# hinted, and the coverage is then quantised to sixteen steps.
COVERAGE_LEVELS = 16


def load_font(path: str | None, size: int, index: int = 0):
    from PIL import ImageFont

    if path:
        return ImageFont.truetype(path, size, index=index)
    # The deck's face is named, not guessed: rekordbox 7 declares
    # font-family="HelveticaNeueLTW1G" in its own skin SVGs, and W1G -- the
    # Linotype "World 1 Glyph set", Latin plus Greek plus Cyrillic -- is exactly
    # the 422-glyph repertoire of the firmware's NS_FONT_ID_ISO8859_w.bin. Two
    # independent artefacts, one answer: Helvetica Neue LT W1G. It is licensed
    # and not redistributable, so we approximate it with the system cut.
    #
    # Regular at 22 rather than Light at 24. This is fitted per glyph against
    # nineteen of Pioneer's own letters, segmented out of the fourteen BEAT FX
    # captions in imagedata.dat (their cap height is a consistent 16 px, with
    # O/C/G/S overshooting to 17). Sweeping face x size over that ground truth:
    # Regular 22 gives 29.3 mean absolute error per pixel, Light 24 gives 61.3.
    # The earlier Light 24 came from matching whole-word ink extents, which is
    # a weaker signal -- it can trade weight against size and still fit.
    for candidate, face in (
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 0),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
    ):
        if pathlib.Path(candidate).is_file():
            return ImageFont.truetype(candidate, size, index=face)
    raise SystemExit("no usable font found; pass --font")



# ---------------------------------------------------------------------------
# The glyph atlas.
#
# One image per caption cannot spell what the row now says. The KEY centre
# carries a Camelot key and a move, `*3A +2`, which is twenty-four keys times
# twenty-five shifts; the sample row shows a volume. So the artwork becomes one
# image per character and the deck composes the string, which is the same thing
# the firmware's own font file does one level lower.
#
# Why the cells are keyed rather than opaque. Ink overflows its advance on A, W,
# V, X, Y and the solidus -- Helvetica sets them a pixel wider than they step --
# so opaque cells laid end to end would have the next cell erase the last column
# of the letter before it. Keying only the pixels that are *exactly* the ground
# fixes that without the usual cost: an anti-aliased edge is a blend of ink and
# this ground, it is kept, and it is already correct, because the cell was drawn
# on the ground it will be seen on. Only untouched ground is punched out. That
# is why there is a set of glyphs per ground rather than one tinted at draw time.

ATLAS_MAGIC = b"RX3GLYF1"
# Ink measured at 22 pt sits in rows 5..22 with a 16 px cap height, so twenty
# rows hold every glyph including the descender on Q, and the widest advance in
# the repertoire is the per cent sign at 22.
ATLAS_CELL_HEIGHT = 20
ATLAS_CELL_PAD = 2
ATLAS_INK_LEFT = 1
ATLAS_INK_TOP = -4
COLOUR_KEY = (248, 0, 248)          # 0xf81f in RGB565: the deck skips it

# Digits, capitals and the punctuation a control can show. Deliberately wider
# than the strings the three panels spell today, so a label added later renders
# a character rather than a hole. There are no lower case letters: the row is
# upper case and the composer folds what it is given.
ATLAS_REPERTOIRE = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ+-*<>.:/%#"
ATLAS_SPACE = " "

# The ground each set of glyphs is drawn on, in the order the deck indexes them.
# These are grounds, not widget states: the atlas never learns what a button is.
ATLAS_SLOTS = ("inactive", "pressed", "selected")


def atlas_cells(font, theme: str, opaque: bool):
    """Render every glyph on every ground, and measure its advance."""
    from PIL import Image, ImageDraw

    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    glyphs = []
    for character in ATLAS_REPERTOIRE:
        advance = int(round(font.getlength(character)))
        box = probe.textbbox((0, 0), character, font=font)
        # The cell holds the advance and whatever the ink spills past it.
        width = max(advance, box[2]) - min(0, box[0]) + ATLAS_CELL_PAD
        states = []
        for slot in ATLAS_SLOTS:
            ground, ink = THEMES[theme][slot]
            mask = Image.new("L", (width, ATLAS_CELL_HEIGHT), 0)
            ImageDraw.Draw(mask).text(
                (ATLAS_INK_LEFT, ATLAS_INK_TOP), character, font=font, fill=255,
            )
            steps = COVERAGE_LEVELS - 1
            mask = mask.point(lambda value: round(value / 255 * steps) * 255 // steps)
            cell = Image.new("RGB", (width, ATLAS_CELL_HEIGHT), ground)
            cell.paste(Image.new("RGB", (width, ATLAS_CELL_HEIGHT), ink), (0, 0), mask)
            if not opaque:
                # Only pixels the ink never reached become the key. A blended
                # edge is kept: it is this ground and this ink, which is exactly
                # what belongs there.
                pixels = cell.load()
                cover = mask.load()
                for y in range(ATLAS_CELL_HEIGHT):
                    for x in range(width):
                        if cover[x, y] == 0:
                            pixels[x, y] = COLOUR_KEY
            states.append(cell)
        glyphs.append((ord(character), width, advance, states))
    return glyphs


def atlas_blob(glyphs, opaque: bool, space_advance: int, theme: str) -> bytes:
    """`RX3GLYF1`: a header, the grounds, a directory, then the cells.

    The grounds are in the file because a keyed cell only carries its ink, and
    whatever draws it has to paint the same colour underneath or the letters sit
    in a rectangle of the wrong shade. Shipping the colour beside the artwork it
    was drawn on is what stops the two from being written down twice and
    drifting: the deck reads its pad colours from here rather than from a
    constant of its own.
    """
    # ink_left travels with the artwork because it is the one number the
    # composer needs and cannot see: the glyph origin sits that far into its
    # cell, so a cell is drawn at pen - ink_left for the letter to land on pen.
    header = struct.pack(
        "<8sHHHHHH", ATLAS_MAGIC, ATLAS_CELL_HEIGHT, len(glyphs),
        len(ATLAS_SLOTS), 0 if opaque else 0xF81F, space_advance, ATLAS_INK_LEFT,
    )
    grounds = b"".join(
        struct.pack("<I", (red << 16) | (green << 8) | blue)
        for red, green, blue in
        (THEMES[theme][slot][0] for slot in ATLAS_SLOTS)
    )
    entry = struct.Struct("<HHHHI")
    directory_bytes = entry.size * len(glyphs)
    offset = len(header) + len(grounds) + directory_bytes
    directory, payload = bytearray(), bytearray()
    for codepoint, width, advance, states in glyphs:
        directory += entry.pack(codepoint, width, advance, 0, offset)
        for cell in states:
            payload += to_rgb565(cell)
        offset += width * ATLAS_CELL_HEIGHT * 2 * len(states)
    return bytes(header) + grounds + bytes(directory) + bytes(payload)


def build_atlas(arguments, font) -> int:
    from PIL import Image

    opaque = arguments.opaque
    glyphs = atlas_cells(font, arguments.theme, opaque)
    space = int(round(font.getlength(ATLAS_SPACE)))
    blob = atlas_blob(glyphs, opaque, space, arguments.theme)
    arguments.output.mkdir(parents=True, exist_ok=True)
    name = f"glyph-atlas-{arguments.theme}.rgb565"
    (arguments.output / name).write_bytes(blob)
    print(f"{len(glyphs)} glyphs x {len(ATLAS_SLOTS)} grounds, "
          f"{len(blob)} bytes -> {arguments.output / name}")

    if arguments.preview:
        pad = 2
        width = sum(glyph[1] + pad for glyph in glyphs)
        sheet = Image.new(
            "RGB", (width, (ATLAS_CELL_HEIGHT + pad) * len(ATLAS_SLOTS)),
            THEMES[arguments.theme]["inactive"][0],
        )
        for slot in range(len(ATLAS_SLOTS)):
            x = 0
            for _, cell_width, _, states in glyphs:
                sheet.paste(states[slot], (x, slot * (ATLAS_CELL_HEIGHT + pad)))
                x += cell_width + pad
        sheet.save(arguments.preview)
        print(f"preview -> {arguments.preview}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=pathlib.Path, default=None,
                        help="where the artwork lands; defaults to assets/")
    parser.add_argument("--font", help="TrueType path; the face is a judgement call")
    parser.add_argument("--font-size", type=int, default=22)
    parser.add_argument("--font-index", type=int, default=0,
                        help="face index inside a .ttc")
    parser.add_argument("--theme", choices=sorted(THEMES), default="dark",
                        help="which room the labels are for")
    parser.add_argument("--opaque", action="store_true",
                        help="atlas: bake the ground instead of keying it out. "
                             "The escape hatch if a deck turns out not to honour "
                             "the colour key on these records.")
    parser.add_argument("--preview", type=pathlib.Path,
                        help="also write a contact sheet for review")
    arguments = parser.parse_args(argv)

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is required to regenerate label artwork", file=sys.stderr)
        return 2

    if arguments.output is None:
        arguments.output = pathlib.Path(__file__).resolve().with_name("assets")

    font = load_font(arguments.font, arguments.font_size, arguments.font_index)
    return build_atlas(arguments, font)


if __name__ == "__main__":
    raise SystemExit(main())
