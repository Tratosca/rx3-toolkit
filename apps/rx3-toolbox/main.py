#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""XDJ-RX3 Toolkit: the USB runtime builder and the vocal stem generator.

Both halves prepare the same USB drive for the same player, so they are one
window with one tab each rather than two applications to download, update, and
keep in step.
"""

from __future__ import annotations

import pathlib
import sys
import tkinter as tk
from tkinter import ttk

if __package__ in (None, ""):
    # Both the repository root, for `tools.*`, and this directory, for the
    # sibling panes, which PyInstaller also places alongside the entry point.
    _HERE = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(_HERE))
    sys.path.insert(0, str(_HERE.parents[1]))

import mod_generator
import stem_studio
import theme


PRODUCT = "XDJ-RX3 Toolkit"


class ToolboxApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(PRODUCT)
        self.geometry("900x860")
        # Small enough for a 1366x768 laptop. Everything inside reflows or
        # scrolls, so the window is free to be resized to whatever fits.
        self.minsize(560, 460)
        palette = theme.apply(self)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        self.runtime_pane = mod_generator.ModGeneratorPane(notebook)
        self.stems_pane = stem_studio.StemStudioPane(notebook)
        notebook.add(self.runtime_pane, text="USB Runtime")
        notebook.add(self.stems_pane, text="Vocal Stems")

        self._restyle(palette)
        theme.follow_appearance(self, self._restyle)

    def _restyle(self, palette: theme.Palette) -> None:
        """Named ttk styles update themselves; classic Tk widgets do not."""
        self.stems_pane.restyle(palette)


def self_test() -> None:
    """Run both panes' offline self-tests, as the packaged smoke test does."""
    mod_generator.self_test()
    stem_studio.self_test()


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return
    # Has to happen before any Tk window exists to have any effect.
    theme.enable_dpi_awareness()
    app = ToolboxApp()
    app.mainloop()


if __name__ == "__main__":
    main()
