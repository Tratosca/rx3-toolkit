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

Palette is measured, not chosen: sampled from assets/key-selected_180x50.png,
which is the artwork the tab strip already ships.

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
# Pioneer's captions carry no border; the control frame belongs to the pane.
BORDER_WIDTH = 0

# One KEY control: x 19..201 and y 521..560 from rx3_keyshift_panel.h and the
# hook's control row band.
LABEL_WIDTH = 183
LABEL_HEIGHT = 40

STATES = ("inactive", "selected", "pressed")


def label_set() -> list[str]:
    """Every string a control can show.

    The KEY centre is a value, not a caption: rx3_keyshift formats a sign and
    up to two digits over -12..+12, so each spelling needs its own image.
    """
    labels = ["KEY -", "KEY +", "INSTRUMENTAL", "VOCAL", "0"]
    labels += [f"{value:+d}" for value in range(-12, 13) if value]
    return labels


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


def render(text: str, state: str, font, width: int, height: int):
    from PIL import Image, ImageDraw

    ground, ink = {
        "inactive": (GROUND_BLACK, INK_DIM),
        "selected": (GROUND_BLUE, INK_WHITE),
        "pressed": (GROUND_BLACK, INK_WHITE),
    }[state]

    # Draw the lettering as coverage only, so the downsample averages shape
    # rather than colour and the ink stays exactly the measured value.
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((width - (right - left)) // 2 - left,
         (height - (bottom - top)) // 2 - top),
        text, font=font, fill=255,
    )
    steps = COVERAGE_LEVELS - 1
    mask = mask.point(lambda value: round(value / 255 * steps) * 255 // steps)

    image = Image.new("RGB", (width, height), ground)
    image.paste(Image.new("RGB", (width, height), ink), (0, 0), mask)
    return image


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=pathlib.Path,
                        default=pathlib.Path("mod/modules/core/1.19/assets/labels"))
    parser.add_argument("--font", help="TrueType path; the face is a judgement call")
    parser.add_argument("--font-size", type=int, default=22)
    parser.add_argument("--font-index", type=int, default=0,
                        help="face index inside a .ttc")
    parser.add_argument("--width", type=int, default=LABEL_WIDTH)
    parser.add_argument("--height", type=int, default=LABEL_HEIGHT)
    parser.add_argument("--preview", type=pathlib.Path,
                        help="also write a contact sheet for review")
    arguments = parser.parse_args(argv)

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required to regenerate label artwork", file=sys.stderr)
        return 2

    font = load_font(arguments.font, arguments.font_size, arguments.font_index)
    arguments.output.mkdir(parents=True, exist_ok=True)
    rendered = []
    for text in label_set():
        for state in STATES:
            image = render(text, state, font, arguments.width, arguments.height)
            slug = text.replace(" ", "_").replace("+", "plus").replace("-", "minus")
            name = f"{slug or 'blank'}-{state}.rgb565"
            payload = to_rgb565(image)
            expected = arguments.width * arguments.height * 2
            if len(payload) != expected:
                raise SystemExit(f"{name}: {len(payload)} bytes, expected {expected}")
            (arguments.output / name).write_bytes(payload)
            rendered.append((name, image))

    print(f"{len(rendered)} labels -> {arguments.output}")
    if arguments.preview:
        columns = len(STATES)
        rows = (len(rendered) + columns - 1) // columns
        sheet = Image.new(
            "RGB", (columns * arguments.width, rows * arguments.height), (0, 0, 0)
        )
        for index, (_, image) in enumerate(rendered):
            sheet.paste(
                image,
                ((index % columns) * arguments.width, (index // columns) * arguments.height),
            )
        sheet.save(arguments.preview)
        print(f"preview -> {arguments.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
