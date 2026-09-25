# SPDX-License-Identifier: MPL-2.0
"""Fit artwork to the deck's boot pane and write the `RX3LOGO1` container.

The container is a 16-byte header followed by one little-endian RGB565 word per
pixel, row by row. Fully transparent pixels are written as the colour key the
core treats as "leave the screen alone", which is what lets a logo of any shape
sit over Pioneer's own background.

Resampling goes through Pillow's Lanczos filter rather than a filter of this
module's own. The deck reads whatever it is given, but the light and dark
variants of one logo have to agree pixel for pixel, and so do a logo rebuilt
from the same source months later; a shared implementation is what makes that
true without a stored intermediate.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


MAGIC = b"RX3LOGO1"
HEADER = struct.Struct("<8sII")
# Magenta. The core writes every other value straight to the framebuffer and
# skips this one, so it is the transparent background and never artwork.
COLOUR_KEY = 0xF81F
# A logo written before the header existed is exactly this, and nothing else
# is accepted without a header.
LEGACY_WIDTH = 492
LEGACY_HEIGHT = 70
# A header declaring more than the largest pane could hold is a corrupt file
# rather than a large logo.
MAX_WIDTH = 1000
MAX_HEIGHT = 400
# Below this weighted luminance the artwork is too dark to read against the
# deck's own dark background, which is worth saying before it is written.
FAINT_LUMINANCE = 34
# How far apart the channels may be while a colour still counts as grey. Only
# greys are inverted for the light theme: inverting a brand colour changes it
# into a different one, while inverting a grey only changes which theme it
# belongs to.
NEUTRAL_RANGE = 40
ZOOM_MIN = 0.25
ZOOM_MAX = 6.0
# However far the artwork is pushed, this much of it stays on the pane. Without
# it an offset typed by hand can place a logo entirely off screen, which looks
# exactly like a logo that failed to build.
MIN_VISIBLE = 24


@dataclass(frozen=True)
class Geometry:
    """One boot pane: the canvas written to the deck, and the area artwork fills.

    The canvas is larger than the ink area on every side. That margin is what
    the core samples to decide the pane is finished, so artwork never reaches
    the outermost pixels.
    """

    name: str
    canvas_width: int
    canvas_height: int
    ink_width: int
    ink_height: int

    @property
    def ink_origin(self) -> tuple[int, int]:
        return (
            (self.canvas_width - self.ink_width) // 2,
            (self.canvas_height - self.ink_height) // 2,
        )


CLASSIC = Geometry("classic", 420, 300, 400, 280)
FULL = Geometry("full", 888, 445, 868, 425)
GEOMETRIES = {geometry.name: geometry for geometry in (CLASSIC, FULL)}


def geometry(name: str) -> Geometry:
    """The named pane, falling back to the one every firmware build has."""
    return GEOMETRIES.get(name, CLASSIC)


def _luminance(r: int, g: int, b: int) -> int:
    """Pillow's ITU-R 601-2 luma, integer for integer.

    Written out rather than taken from `convert("L")` because it is applied to
    single pixels here, and because the two must not drift apart.
    """
    return (r * 19595 + g * 38470 + b * 7471 + 32768) >> 16


def _div255(value: int) -> int:
    """Pillow's rounding division by 255, used to premultiply by alpha."""
    tmp = value + 128
    return (tmp + (tmp >> 8)) >> 8


def pack_pixel(r: int, g: int, b: int) -> int:
    """One RGB565 word, with the colour key kept out of the artwork.

    A colour that happens to land on the key would be punched out of the logo
    it belongs to, so it is nudged by one step of green: the smallest change
    the panel can represent, and invisible beside the colour it replaces.
    """
    pixel = (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)
    return pixel | (1 << 5) if pixel == COLOUR_KEY else pixel


def unpack_pixel(pixel: int) -> tuple[int, int, int]:
    """Expand one RGB565 word back to 8 bits per channel, as the panel does."""
    r5, g6, b5 = pixel >> 11 & 0x1F, pixel >> 5 & 0x3F, pixel & 0x1F
    return r5 << 3 | r5 >> 2, g6 << 2 | g6 >> 4, b5 << 3 | b5 >> 2


def pack_canvas(canvas, geometry: Geometry) -> bytes:
    """Write one full-size RGBA canvas as an `RX3LOGO1` container.

    Alpha is flattened here rather than by the caller: the deck has no alpha
    channel, so a partly transparent pixel has to be resolved against the only
    background the core will put behind it, which is the colour key.
    """
    if canvas.size != (geometry.canvas_width, geometry.canvas_height):
        raise ValueError(
            f"canvas is {canvas.width}x{canvas.height}, not the "
            f"{geometry.canvas_width}x{geometry.canvas_height} of the "
            f"{geometry.name} pane"
        )
    raw = canvas.convert("RGBA").tobytes()
    words = []
    for offset in range(0, len(raw), 4):
        r, g, b, a = raw[offset:offset + 4]
        if a == 0:
            words.append(COLOUR_KEY)
        else:
            words.append(pack_pixel(_div255(r * a), _div255(g * a), _div255(b * a)))
    return HEADER.pack(MAGIC, geometry.canvas_width, geometry.canvas_height) + struct.pack(
        f"<{len(words)}H", *words
    )


def decode(data: bytes):
    """Read a container back to RGBA, with the colour key as transparency.

    A file with no header is the one size that predates it, so its dimensions
    are assumed rather than read.
    """
    from PIL import Image

    if len(data) >= HEADER.size and data[:8] == MAGIC:
        _, width, height = HEADER.unpack_from(data, 0)
        offset = HEADER.size
        limit_width = max(MAX_WIDTH, FULL.canvas_width)
        limit_height = max(MAX_HEIGHT, FULL.canvas_height)
        if not (1 <= width <= limit_width and 1 <= height <= limit_height):
            raise ValueError(
                f"the header declares {width}x{height}, beyond the "
                f"{limit_width}x{limit_height} limit"
            )
    else:
        width, height, offset = LEGACY_WIDTH, LEGACY_HEIGHT, 0
    expected = offset + width * height * 2
    if len(data) != expected:
        raise ValueError(
            f"a {width}x{height} logo is {expected} bytes; this file is {len(data)}"
        )
    raw = bytearray(width * height * 4)
    for index, word in enumerate(struct.unpack_from(f"<{width * height}H", data, offset)):
        if word != COLOUR_KEY:
            raw[index * 4:index * 4 + 4] = bytes((*unpack_pixel(word), 255))
    return Image.frombytes("RGBA", (width, height), bytes(raw))


def ink_source(image):
    """The artwork as it is actually drawn, cropped to what it draws.

    Artwork exported with a transparent margin would otherwise be scaled to fit
    that margin and land on the deck visibly smaller than it was placed. This
    is lifted out of `fit_ink` so that anything answering "where will it land"
    measures the same image `encode` measures, rather than the one the operator
    picked. The two disagreed for every logo with a transparent edge.
    """
    source = image.convert("RGBA")
    box = source.getchannel("A").getbbox()
    if box is None:
        raise ValueError("the artwork is fully transparent: there is nothing to draw")
    return source.crop(box)


@dataclass(frozen=True)
class Measures:
    """What a screen has to say about artwork, from one pass over it."""

    luminance: float
    faint: bool
    themed: bool


def ink_measures(ink) -> Measures:
    """How the artwork reads, in one walk rather than three.

    `encode` walks the pixels five times, which is most of the 698 ms a
    full-size pane costs. A screen asking only how the artwork reads needs none
    of the packing and only one of the walks.
    """
    raw = ink.convert("RGBA").tobytes()
    weight = total = 0
    grey_weight = grey_total = 0
    for offset in range(0, len(raw), 4):
        r, g, b, a = raw[offset:offset + 4]
        if a == 0:
            continue
        luma = _luminance(r, g, b)
        weight += a
        total += luma * a
        if max(r, g, b) - min(r, g, b) < NEUTRAL_RANGE:
            grey_weight += a
            grey_total += luma * a
    luminance = total / weight if weight else 0.0
    themed = grey_weight > 0 and grey_total / grey_weight > 128
    return Measures(luminance, luminance < FAINT_LUMINANCE, themed)


def ink_luminance(ink) -> float:
    """Mean luma of the artwork, weighted by how opaque each pixel is.

    Transparent pixels are not dark artwork, so counting them would report
    every logo as too faint to read.
    """
    return ink_measures(ink).luminance


def light_ink(ink):
    """The same artwork for a light background, or None when it needs none.

    Only greys are inverted, and only when the artwork reads as light on dark
    to begin with. Inverting a brand colour would produce a different colour;
    inverting a grey only moves it to the other end of the same axis, which is
    what a theme switch is.
    """
    from PIL import Image

    source = ink.convert("RGBA")
    raw = bytearray(source.tobytes())
    weight = total = 0
    for offset in range(0, len(raw), 4):
        r, g, b, a = raw[offset:offset + 4]
        if a == 0 or max(r, g, b) - min(r, g, b) >= NEUTRAL_RANGE:
            continue
        weight += a
        total += _luminance(r, g, b) * a
    # Artwork that is already dark, or carries no grey at all, is left as it is
    # and both themes are served by the one container.
    if weight == 0 or total / weight <= 128:
        return None
    for offset in range(0, len(raw), 4):
        r, g, b, a = raw[offset:offset + 4]
        if a == 0 or max(r, g, b) - min(r, g, b) >= NEUTRAL_RANGE:
            continue
        raw[offset:offset + 3] = bytes((255 - r, 255 - g, 255 - b))
    return Image.frombytes("RGBA", source.size, bytes(raw))


def _round_half_up(value: float) -> int:
    """Round halves away from zero, as the interface that framed the logo does.

    Python rounds halves to even, so a logo placed at an exact half pixel would
    land one pixel from where the operator positioned it.
    """
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def placement(
    art_width: int,
    art_height: int,
    geometry: Geometry,
    *,
    mode: str = "contain",
    zoom: float = 1.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> tuple[int, int, int, int]:
    """Where the artwork lands in the ink area, as `(x, y, width, height)`.

    `x` and `y` may fall outside the ink area: `cover`, or any zoom above the
    fit, is meant to overflow it and be cropped.
    """
    if art_width < 1 or art_height < 1:
        raise ValueError("the artwork is empty")
    fits = (geometry.ink_width / art_width, geometry.ink_height / art_height)
    fit = max(fits) if mode == "cover" else min(fits)
    scale = fit * min(ZOOM_MAX, max(ZOOM_MIN, zoom))
    width = max(1, _round_half_up(art_width * scale))
    height = max(1, _round_half_up(art_height * scale))

    def room(drawn: int, limit: int, offset: float) -> int:
        centred = _round_half_up((limit - drawn) / 2) + _round_half_up(offset)
        visible = min(MIN_VISIBLE, drawn, limit)
        return min(limit - visible, max(visible - drawn, centred))

    return room(width, geometry.ink_width, offset_x), room(
        height, geometry.ink_height, offset_y
    ), width, height


def fit_ink(image, geometry: Geometry, **frame):
    """Scale and place artwork into the ink area, returning an RGBA ink canvas.

    The source is cropped to what it actually draws first. Artwork exported with
    a transparent margin would otherwise be scaled to fit that margin, and land
    on the deck visibly smaller than the operator placed it.
    """
    from PIL import Image

    source = ink_source(image)
    x, y, width, height = placement(source.width, source.height, geometry, **frame)
    scaled = source.resize((width, height), Image.LANCZOS)
    # What survives the ink area once the placement has been applied.
    from_x, from_y = max(0, -x), max(0, -y)
    visible_width = min(width, geometry.ink_width - x) - from_x
    visible_height = min(height, geometry.ink_height - y) - from_y
    ink = Image.new("RGBA", (geometry.ink_width, geometry.ink_height), (0, 0, 0, 0))
    if visible_width > 0 and visible_height > 0:
        ink.paste(
            scaled.crop((from_x, from_y, from_x + visible_width, from_y + visible_height)),
            (x + from_x, y + from_y),
        )
    return ink


def pad_canvas(ink, geometry: Geometry):
    """Centre the ink area on the canvas the deck is actually sent."""
    from PIL import Image

    canvas = Image.new(
        "RGBA", (geometry.canvas_width, geometry.canvas_height), (0, 0, 0, 0)
    )
    canvas.paste(ink.convert("RGBA"), geometry.ink_origin)
    return canvas


@dataclass(frozen=True)
class Logo:
    geometry: Geometry
    dark: bytes
    light: bytes
    # True when the artwork is too dark to read against the deck's own dark
    # background. The logo is written anyway; this only lets the caller say so.
    faint: bool
    # False when the artwork needed no separate light form, which is why `light`
    # then repeats `dark`.
    themed: bool


def encode(image, geometry: Geometry = CLASSIC, **frame) -> Logo:
    """Frame artwork and write both theme variants of the container."""
    ink = fit_ink(image, geometry, **frame)
    dark = pack_canvas(pad_canvas(ink, geometry), geometry)
    light = light_ink(ink)
    return Logo(
        geometry=geometry,
        dark=dark,
        light=pack_canvas(pad_canvas(light, geometry), geometry) if light else dark,
        faint=ink_luminance(ink) < FAINT_LUMINANCE,
        themed=light is not None,
    )
