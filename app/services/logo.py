# SPDX-License-Identifier: MPL-2.0
"""The on-screen logo, as an interface asks about it.

The converter has been byte-exact against a released container for a while and
has never had a caller. What was missing is the way in: choosing an image,
seeing where it lands, and getting the two files the deck reads into the image
a drive carries.

`preview` writes nothing and answers the question a screen asks while the
operator is still dragging: where does the artwork sit, and is it too dark to
read against the deck's own background.
"""

from __future__ import annotations

from app.localization import Message, LocalizedError

import base64
import dataclasses
import io
import pathlib

from app.logo import container

# The two names the logo module copies to the player, from its own module.sh.
DARK_NAME = "rx3-logo-main.rgb565"
LIGHT_NAME = "rx3-logo-main-light.rgb565"
MODULE_ID = "logo"


@dataclasses.dataclass(frozen=True)
class Canvas:
    """One of the panes a logo can be built for."""

    name: str
    canvas_width: int
    canvas_height: int
    ink_width: int
    ink_height: int


# What a preview may take across the bridge. A logo is a few hundred kilobytes
# of base64 at full size, which is fine once and wrong sixty times a second.
PREVIEW_LONG_EDGE = 1024


@dataclasses.dataclass(frozen=True)
class Placement:
    """Where the artwork lands, in canvas pixels, before anything is written."""

    x: int
    y: int
    width: int
    height: int
    # True when the artwork is too dark to read against the deck's own dark
    # background. It is still built; this only lets a screen say so.
    faint: bool
    # False when the artwork needed no separate light form.
    themed: bool


def canvases() -> tuple[Canvas, ...]:
    """The panes a logo can be built for, in the order a picker should show."""
    return tuple(
        Canvas(item.name, item.canvas_width, item.canvas_height,
               item.ink_width, item.ink_height)
        for item in (container.CLASSIC, container.FULL)
    )


def zoom_range() -> tuple[float, float]:
    return container.ZOOM_MIN, container.ZOOM_MAX


def min_visible() -> int:
    """How much of the artwork stays on the pane however far it is pushed.

    A screen that lets an operator drag has to stop where the encoder stops,
    or the artwork appears to keep moving and then lands somewhere else.
    """
    return container.MIN_VISIBLE


def _canvas(name: str):
    """The named pane, refusing a name that is not one.

    container.geometry falls back to the classic pane on purpose: it also reads
    containers that predate the header and carry no name. Here the name comes
    from a screen, and falling back would silently build the wrong size.
    """
    if name not in container.GEOMETRIES:
        offered = ", ".join(sorted(container.GEOMETRIES))
        raise LocalizedError("error.pane", name=name, offered=offered)
    return container.GEOMETRIES[name]


def _open(path: pathlib.Path):
    from PIL import Image

    image = Image.open(pathlib.Path(path))
    image.load()
    return image.convert("RGBA")


def _png(image, long_edge: int | None = None) -> str:
    """One image as a data URL, because the bridge carries text and not bytes."""
    from PIL import Image

    if long_edge and max(image.size) > long_edge:
        scale = long_edge / max(image.size)
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.LANCZOS,
        )
    buffer = io.BytesIO()
    image.save(buffer, "PNG", compress_level=1)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def opened(path: pathlib.Path) -> dict:
    """The artwork itself, ready for a screen to frame it.

    The size reported is the size the encoder works from, which is the artwork
    cropped to what it actually draws rather than the file's own dimensions. A
    screen framing against the file's dimensions puts the artwork somewhere the
    deck will not.
    """
    ink = container.ink_source(_open(path))
    return {
        "path": str(path),
        "width": ink.width,
        "height": ink.height,
        "preview": _png(ink, PREVIEW_LONG_EDGE),
    }


def preview(path: pathlib.Path, canvas: str = "classic", **frame) -> Placement:
    """Where this image would land, and how it would read, without writing.

    One pass over the artwork rather than the five `encode` makes, because none
    of the packing is needed to answer this. Still far too slow to sit inside a
    drag: a screen moves the artwork itself and asks this once the pointer has
    stopped.
    """
    geometry = _canvas(canvas)
    ink = container.ink_source(_open(path))
    x, y, width, height = container.placement(
        ink.width, ink.height, geometry, **frame)
    measures = container.ink_measures(container.fit_ink(_open(path), geometry, **frame))
    return Placement(x, y, width, height, faint=measures.faint, themed=measures.themed)


def render(path: pathlib.Path, canvas: str = "classic", **frame) -> dict:
    """A picture of the pane as it will be written, and how it reads.

    Both pictures decode the actual RGB565 containers, including their colour
    quantization, transparency and theme transformation.
    """
    geometry = _canvas(canvas)
    logo = container.encode(_open(path), geometry, **frame)
    measures = preview(path, canvas, **frame)
    return {
        **dataclasses.asdict(measures),
        "canvas": _png(container.decode(logo.dark)),
        "lightCanvas": _png(container.decode(logo.light)),
    }


def files(path: pathlib.Path, canvas: str = "classic", **frame) -> dict[str, bytes]:
    """The two containers, named as the deck reads them.

    Hand this to `build_runtime(supplied_files={logo.MODULE_ID: ...})`. Both
    names are always present: a drive carrying only the dark one shows it under
    both themes, and the module says so, but writing both is what makes the
    light theme legible.
    """
    geometry = _canvas(canvas)
    logo = container.encode(_open(path), geometry, **frame)
    return {DARK_NAME: logo.dark, LIGHT_NAME: logo.light}
