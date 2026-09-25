# SPDX-License-Identifier: MPL-2.0
"""Write a picture of every row a deck can show.

`python -m app.preview --out build/pad-preview`
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.preview import layout
from app.preview.atlas import INACTIVE, PRESSED, SELECTED
from app.preview.row import (BUTTON, SLIDER, STEPPER, TOGGLE, Widget,
                                 atlas_for, render)

STEM_NAMES = {2: ["DRUMS", "INSTRUMENTAL"],
              3: ["DRUMS", "BASS", "INST"],
              4: ["DRUMS", "BASS", "VOCAL", "INST"]}


def cases():
    """Every row worth looking at, named for what it is showing."""
    yield "key-idle", "deck", [Widget(STEPPER, captions=["< 3A", "KEY --", "5A >"],
                                      states=[INACTIVE] * 3)]
    yield "key-in-key", "deck", [Widget(STEPPER, captions=["< 3A", "*3A +2", "5A >"],
                                        states=[INACTIVE, SELECTED, INACTIVE])]
    for part, name in enumerate(("down", "value", "up")):
        states = [INACTIVE] * 3
        states[part] = PRESSED
        yield f"key-pressed-{name}", "deck", [
            Widget(STEPPER, captions=["< 3A", "*3A +2", "5A >"], states=states)
        ]
    yield "key-limit", "deck", [Widget(STEPPER, captions=["--", "*9A +5", "5A >"],
                                       states=[INACTIVE] * 3)]

    for count, names in STEM_NAMES.items():
        yield f"stems-{count}-idle", "deck", [
            Widget(TOGGLE, captions=[name], states=[INACTIVE]) for name in names
        ]
        lit = [
            Widget(TOGGLE, captions=[name],
                   states=[SELECTED if index else INACTIVE])
            for index, name in enumerate(names)
        ]
        yield f"stems-{count}-lit", "deck", lit
        pressed = [
            Widget(TOGGLE, captions=[name],
                   states=[PRESSED if index == 0 else INACTIVE])
            for index, name in enumerate(names)
        ]
        yield f"stems-{count}-pressed", "deck", pressed
    yield "stems-none", "deck", [Widget(TOGGLE, captions=["NO STEMS"],
                                        states=[INACTIVE])]
    yield "stems-failed", "deck", [Widget(TOGGLE, captions=["STEMS ERR"],
                                          states=[INACTIVE])]

    for value in (0, 1, 50, 85, 99, 100):
        yield f"samples-vol-{value}", "screen", [
            Widget(SLIDER, weight=9, value=value, maximum=100, captions=[""],
                   states=[INACTIVE]),
            Widget(TOGGLE, weight=1, captions=[f"VOL {value}"], states=[INACTIVE]),
        ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("build/pad-preview"))
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--theme", choices=("dark", "light", "both"), default="both")
    arguments = parser.parse_args(argv)

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required to draw the preview")
        return 2

    arguments.out.mkdir(parents=True, exist_ok=True)
    themes = ("dark", "light") if arguments.theme == "both" else (arguments.theme,)
    written = 0
    for theme in themes:
        atlas = atlas_for(theme)
        rows = []
        for name, scope, widgets in cases():
            band = render(widgets, theme, scope, atlas)
            rows.append((name, band))
            written += 1
        gap = 6
        sheet = Image.new(
            "RGB",
            (1280, sum(band.height + gap for _, band in rows) + gap),
            (24, 24, 28),
        )
        y = gap
        for _, band in rows:
            sheet.paste(band, (0, y))
            y += band.height + gap
        if arguments.scale > 1:
            sheet = sheet.resize(
                (sheet.width * arguments.scale, sheet.height * arguments.scale),
                Image.NEAREST,
            )
        sheet.save(arguments.out / f"pad-row-{theme}.png")
        print(f"{len(rows)} rows -> {arguments.out / f'pad-row-{theme}.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
