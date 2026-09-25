# SPDX-License-Identifier: MPL-2.0
"""Draw the performance pad row the way a deck would, on the computer.

Nothing in this repository reaches a deck, so this is the only way to see a
control before someone carries a stick to one. It is deliberately not a
simulator: it draws one row from the artwork that ships and the layout the deck
solves, and stops there.

The colours are not written down here. They arrive from the glyph atlas, which
carries the ground each set of glyphs was drawn on, so the picture cannot show a
shade the artwork does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.preview import layout
from app.preview.atlas import INACTIVE, PRESSED, SELECTED, Atlas

REPOSITORY = Path(__file__).resolve().parents[2]
ASSETS = REPOSITORY / "mod/modules/core/1.19/assets"

BUTTON, TOGGLE, STEPPER, SLIDER = "button", "toggle", "stepper", "slider"


@dataclass
class Widget:
    kind: str = BUTTON
    weight: int = 1
    captions: list[str] = field(default_factory=list)
    states: list[int] = field(default_factory=list)
    value: int = 0
    maximum: int = 100

    def parts(self) -> int:
        return 3 if self.kind == STEPPER else 1

    def caption(self, part: int) -> str:
        return self.captions[part] if part < len(self.captions) else ""

    def state(self, part: int) -> int:
        return self.states[part] if part < len(self.states) else INACTIVE


def atlas_for(theme: str) -> Atlas:
    return Atlas.load(ASSETS / f"glyph-atlas-{theme}.rgb565")


def caption_top(atlas: Atlas) -> int:
    """Where a caption's cells start, in the row's own coordinates.

    One halving, no division: the deck does the same arithmetic and has no
    integer divide instruction to spend on it.
    """
    return layout.CTRL_TOP + (
        (layout.CTRL_BOTTOM - layout.CTRL_TOP + 1 - atlas.cell_height) >> 1
    )


def _caption(target, atlas: Atlas, cell: layout.Cell, text: str, state: int,
             shift: int):
    """Centred in the cell. `shift` puts row coordinates into the band image."""
    slack = cell.width - atlas.width(text)
    if slack < 0:
        slack = 0
    pen = cell.x1 + (slack >> 1)
    atlas.draw(target, text, pen, caption_top(atlas) - shift, state,
               seam=layout.DECK_STRIDE)


def render(widgets, theme: str = "dark", scope: str = "deck", atlas: Atlas | None = None):
    """One row band, 1280 wide, as the screen shows it."""
    from PIL import Image, ImageDraw

    atlas = atlas or atlas_for(theme)
    origin = layout.DECK_ORIGIN if scope == "deck" else layout.SCREEN_ORIGIN
    span = layout.DECK_SPAN if scope == "deck" else layout.SCREEN_SPAN

    band = Image.new(
        "RGB", (1280, layout.GROUND_BOTTOM - layout.GROUND_TOP + 1),
        atlas.ground(INACTIVE),
    )
    draw = ImageDraw.Draw(band)
    # The band image starts at GROUND_TOP, so every y below is shifted into it.
    shift = layout.GROUND_TOP

    halves = [0, 1] if scope == "deck" else [0]
    for half in halves:
        base = half * layout.DECK_STRIDE if scope == "deck" else 0
        cells = layout.solve([w.weight for w in widgets], origin, span)
        for widget, cell in zip(widgets, cells):
            cell = layout.Cell(cell.x1 + base, cell.x2 + base)
            if widget.kind == STEPPER:
                boxes = layout.stepper_parts(cell)
            else:
                boxes = [cell]
            for part, box in enumerate(boxes):
                state = widget.state(part)
                if widget.kind == SLIDER:
                    draw.rectangle(
                        [box.x1, layout.CTRL_TOP - shift,
                         box.x2, layout.CTRL_BOTTOM - shift],
                        fill=atlas.ground(INACTIVE),
                        outline=atlas.ground(SELECTED),
                    )
                    filled = layout.slider_x(box, widget.value, widget.maximum)
                    if filled > box.x1:
                        draw.rectangle(
                            [box.x1 + 1, layout.CTRL_TOP + 1 - shift,
                             filled, layout.CTRL_BOTTOM - 1 - shift],
                            fill=atlas.ground(SELECTED),
                        )
                else:
                    draw.rectangle(
                        [box.x1, layout.CTRL_TOP - shift,
                         box.x2, layout.CTRL_BOTTOM - shift],
                        fill=atlas.ground(state),
                    )
                _caption(band, atlas, layout.Cell(box.x1, box.x2),
                         widget.caption(part), state, shift)
    return band
