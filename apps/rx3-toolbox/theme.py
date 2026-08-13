# SPDX-License-Identifier: MPL-2.0
"""Appearance-aware colours and the widget helpers both panes share.

Secondary text used to be a fixed `#555555`, chosen against a light window. The
ttk themes on every platform follow the system appearance, so on a dark desktop
that grey landed on a dark background at a contrast ratio around 1.6:1 and the
help text in Advanced options became unreadable.

Nothing here asks the operating system what its appearance is. It asks Tk what
colour it is actually painting, which is correct on all three platforms, needs
no subprocess, and stays correct if the user overrides the ttk theme.
"""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk


# Contrast ratios against the backgrounds these are paired with: 10.4:1 for the
# light pair, 8.9:1 for the dark one. Both clear WCAG AA for body text with
# room to spare, which is the point - the old grey did not.
LIGHT = {
    "muted": "#3f3f3f",
    "warning": "#8f3800",
    "text_background": "#ffffff",
    "text_foreground": "#1a1a1a",
}
DARK = {
    "muted": "#c4c4c4",
    "warning": "#ffab6b",
    "text_background": "#232323",
    "text_foreground": "#ececec",
}
# Tk's virtual events for an appearance change. The Aqua pair is macOS-only and
# binding an unknown virtual event is harmless everywhere else.
APPEARANCE_EVENTS = (
    "<<ThemeChanged>>", "<<LightAquaAppearance>>", "<<DarkAquaAppearance>>",
)


@dataclass(frozen=True)
class Palette:
    dark: bool
    muted: str
    warning: str
    text_background: str
    text_foreground: str


def is_dark(widget: tk.Misc) -> bool:
    """Whether the theme paints frames on a dark ground."""
    style = ttk.Style(widget)
    background = style.lookup("TFrame", "background")
    if not background:
        background = widget.winfo_toplevel().cget("background")
    try:
        red, green, blue = widget.winfo_rgb(background)
    except tk.TclError:
        # A symbolic colour the platform cannot resolve; assume the light
        # appearance, which is what every ttk theme defaults to.
        return False
    # Rec. 601 luma over Tk's 16-bit components.
    return (0.299 * red + 0.587 * green + 0.114 * blue) / 65535 < 0.5


def palette(widget: tk.Misc) -> Palette:
    dark = is_dark(widget)
    return Palette(dark=dark, **(DARK if dark else LIGHT))


def apply(root: tk.Misc) -> Palette:
    """Register the named styles for the current appearance and return it."""
    colors = palette(root)
    style = ttk.Style(root)
    style.configure("Muted.TLabel", foreground=colors.muted)
    style.configure("Warning.TLabel", foreground=colors.warning)
    style.configure("Title.TLabel", font=("TkDefaultFont", 20, "bold"))
    style.configure("Heading.TLabel", font=("TkDefaultFont", 14, "bold"))
    style.configure("Section.TLabel", font=("TkDefaultFont", 12, "bold"))
    return colors


def follow_appearance(root: tk.Misc, on_change) -> None:
    """Re-apply the palette whenever the desktop appearance changes.

    `apply` runs before the callback so a handler can read the new palette
    straight from the styles it just registered.

    Two guards, both load-bearing. `apply` calls `style.configure`, and Tk
    answers a style change by sending `<<ThemeChanged>>` to every widget - the
    very event this is bound to. Re-applying an unchanged palette would
    therefore feed itself forever, which hangs the interpreter the first time
    anything emits the event, such as opening a second window. So the work is
    skipped when the palette has not actually changed, and a flag closes the
    window between computing the new one and finishing with it.
    """
    state = {"palette": palette(root), "busy": False}

    def handle(_event=None) -> None:
        if state["busy"]:
            return
        fresh = palette(root)
        if fresh == state["palette"]:
            return
        state["busy"] = True
        try:
            state["palette"] = fresh
            on_change(apply(root))
        finally:
            state["busy"] = False

    for event in APPEARANCE_EVENTS:
        root.bind_all(event, handle, add="+")


def restyle_text(widget: tk.Text, colors: Palette) -> None:
    """Colour a classic Tk widget, which ttk styles do not reach."""
    widget.configure(
        background=colors.text_background,
        foreground=colors.text_foreground,
        insertbackground=colors.text_foreground,
    )


# Reflowing text
#
# A ttk.Label wraps at a `wraplength` given in pixels, and never revisits it.
# Hardcoding one makes the window a fixed-width document: widen it and the text
# keeps its old column, narrow it and the text is clipped. Labels are instead
# marked with the inset they sit at, and the container they live in reflows them
# to whatever width it has actually been given.

_INSET = "_rx3_wrap_inset"
# Below this a wrapped line is unreadable anyway, so the window stops the text
# shrinking rather than letting it degrade into one word per line.
MINIMUM_WRAP = 180


def wrapping(label: ttk.Label, inset: int = 0) -> ttk.Label:
    """Mark a label as reflowing, `inset` pixels narrower than its container."""
    setattr(label, _INSET, inset)
    return label


def reflow(container: tk.Misc, width: int | None = None) -> None:
    """Reflow every marked label under `container` to its current width."""
    if width is None:
        width = container.winfo_width()
    if width <= 1:  # Not yet mapped; the first <Configure> will do it.
        return
    pending = [container]
    while pending:
        widget = pending.pop()
        inset = getattr(widget, _INSET, None)
        if inset is not None:
            widget.configure(wraplength=max(MINIMUM_WRAP, width - inset))
        pending.extend(widget.winfo_children())


def follow_width(container: tk.Misc) -> None:
    """Keep the marked labels under `container` reflowing as it is resized.

    The handler is bound to the container rather than to each label: a label
    whose own width depends on its wrapped text would feed its new size back
    into the event that set it. The container's width comes from the window, so
    the loop is broken. Dynamically rebuilt rows are picked up too, since the
    tree is walked at each event rather than captured once.

    The identity check is what makes that true for a Toplevel. Every widget
    carries its toplevel in its bind tags, so a Toplevel bound this way is also
    handed the `<Configure>` of each of its descendants - and reflowing the
    whole tree to the width of one inner label resizes that label, which
    reports it again. Only the container's own resize means anything here.
    """

    def handle(event) -> None:
        if str(event.widget) != str(container):
            return
        reflow(container, event.width)

    container.bind("<Configure>", handle, add="+")


class ScrollFrame(ttk.Frame):
    """A vertically scrolling container, which ttk does not provide.

    Add children to `.body`. The scrollbar appears only when the content does
    not fit, so a short list looks exactly as it would without one.
    """

    # The scrollbar's column is reserved whether or not the scrollbar is in it.
    # Letting it claim its width only when shown would make the viewport
    # narrower exactly when it appears, which rewraps the text, which changes
    # the content height, which can hide the scrollbar again - an oscillation
    # that never settles and hangs the event loop.
    GUTTER = 16

    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, minsize=self.GUTTER)
        self.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, takefocus=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._bar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._bar_shown = False
        self._canvas.configure(yscrollcommand=self._scrolled)
        self.body = ttk.Frame(self._canvas)
        self._window = self._canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._body_resized)
        self._canvas.bind("<Configure>", self._canvas_resized)
        self._canvas.bind("<Enter>", self._grab_wheel)
        self._canvas.bind("<Leave>", self._release_wheel)
        self.sync_background()
        # Bound on this widget alone, not with `bind_all`: Tk delivers
        # <<ThemeChanged>> to every widget by itself, and a palette switch
        # always reaches this through the style change it makes.
        self.bind("<<ThemeChanged>>", lambda _event: self.sync_background(), add="+")

    def sync_background(self) -> None:
        """Match the viewport to the theme; a Canvas is not a ttk widget."""
        background = ttk.Style(self).lookup("TFrame", "background")
        if background:
            try:
                self._canvas.configure(background=background)
            except tk.TclError:
                pass

    def _body_resized(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _canvas_resized(self, event) -> None:
        # The scrolled content is as wide as the viewport, so its own children
        # keep filling the width and reflowing normally.
        self._canvas.itemconfigure(self._window, width=event.width)

    def _scrolled(self, first: str, last: str) -> None:
        needed = not (float(first) <= 0.0 and float(last) >= 1.0)
        # The desired state is tracked here rather than read back from
        # `winfo_ismapped`, which stays false until the pending idle work has
        # been flushed. Asking Tk during that work reports the bar as hidden
        # however many times it has just been gridded, so every pass would grid
        # it again, and every grid queues another pass: `update_idletasks`
        # never returns.
        if needed != self._bar_shown:
            self._bar_shown = needed
            if needed:
                self._bar.grid(row=0, column=1, sticky="ns")
            else:
                self._bar.grid_remove()
        self._bar.set(first, last)

    # The wheel is only claimed while the pointer is over the viewport, so it
    # still reaches whatever else on the window wants it.

    def _grab_wheel(self, _event=None) -> None:
        self._canvas.bind_all("<MouseWheel>", self._wheel, add="+")
        self._canvas.bind_all("<Button-4>", self._wheel, add="+")
        self._canvas.bind_all("<Button-5>", self._wheel, add="+")

    def _release_wheel(self, _event=None) -> None:
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._canvas.unbind_all(sequence)

    def _wheel(self, event) -> None:
        if not self._bar.winfo_ismapped():
            return
        if event.num == 4:
            steps = -1
        elif event.num == 5:
            steps = 1
        else:
            # Windows reports multiples of 120; macOS reports small deltas.
            steps = -event.delta // 120 if abs(event.delta) >= 120 else -event.delta
        self._canvas.yview_scroll(int(steps), "units")


def enable_dpi_awareness() -> None:
    """Ask Windows for real pixels, before any Tk window exists.

    Without this the system scales an 800x600 window up and Tk's text is
    resampled rather than drawn at size, which is the blurry rendering reported
    on high-density Windows displays. No effect anywhere else.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # per-monitor
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()  # Windows 7 fallback
    except Exception:
        # A display that refuses the request still renders, only softer.
        pass


def path_row(
    parent, row: int, label: str, variable: tk.StringVar, command, width: int = 25
) -> None:
    """A labelled path field with a chooser, as both panes lay one out.

    `width` is the label column, in characters. Every row of a pane has to pass
    the same one, or the fields do not line up.
    """
    frame = ttk.Frame(parent)
    frame.grid(row=row, column=0, sticky="ew", pady=3)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text=label, width=width).grid(row=0, column=0, sticky="w")
    ttk.Entry(frame, textvariable=variable).grid(row=0, column=1, sticky="ew", padx=8)
    ttk.Button(frame, text="Choose...", command=command).grid(row=0, column=2)
