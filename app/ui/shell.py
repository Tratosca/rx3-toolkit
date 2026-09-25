#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""The window, and nothing else.

Every rule about what the toolkit does lives in app/services and reaches
the interface through bridge.Bridge. This file opens a window, points it at a
local page, and gets out of the way.

--self-test runs before any window exists, which is what lets a headless build
server prove the packaged application works without a display.
"""

from __future__ import annotations

import pathlib
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.ui import bridge

PRODUCT = "XDJ-RX3 Toolkit"

# Every local file the page pulls in, so the self-test proves the packaged
# application shipped all of them rather than a list written down twice.
ASSET = re.compile(r"""(?:src|href)\s*=\s*["']([^"':#]+)["']""")


def resources() -> pathlib.Path:
    """Where the page lives, frozen or not.

    PyInstaller puts data under _MEIPASS, which inside a .app is
    Contents/Frameworks and not beside the executable.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return pathlib.Path(bundled) / "web"
    return pathlib.Path(__file__).resolve().parent / "web"


def enable_dpi_awareness() -> None:
    """Ask Windows for real pixels, before any window exists.

    Without this the system scales the window up and its text is resampled
    rather than drawn at size, which is the blurry rendering reported on
    high-density Windows displays. No effect anywhere else.
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


def assets(page: pathlib.Path) -> list[str]:
    """What the page asks the window to load, in the order it asks for it."""
    seen = []
    for name in ASSET.findall(page.read_text(encoding="utf-8")):
        if name not in seen:
            seen.append(name)
    return seen


def self_test() -> None:
    """Everything the packaged application must prove without a display.

    Importing the window toolkit is part of it. A backend that reaches for a
    display at import time fails here, on a build server, rather than in front
    of an operator.
    """
    import webview  # noqa: F401

    page = resources() / "index.html"
    if not page.is_file():
        raise SystemExit(f"the interface did not ship: {page}")
    for name in assets(page):
        if not (resources() / name).is_file():
            raise SystemExit(f"the interface did not ship: {resources() / name}")

    from app.localization import catalogs
    catalogs()  # Refuse a bundle missing its translation resources.
    surface = bridge.Bridge()
    names = bridge.operations(surface)
    if not names:
        raise SystemExit("the bridge exposes nothing")
    # Two operations that touch neither a drive nor a network, so the answer
    # shape is proven without anything being plugged in.
    for answer in (surface.logo_canvases(), surface.mod_firmwares()):
        if not answer.get("ok"):
            raise SystemExit(f"bridge operation failed: {answer.get('error')}")
    # Progress is polled rather than pushed, so the whole of it is reachable
    # here, with no window and no display.
    status = surface.job_status()
    if not status.get("ok") or status["value"] != bridge.idle_job():
        raise SystemExit(f"the job slot does not start idle: {status}")
    if surface.job_cancel()["value"]:
        raise SystemExit("cancelling an idle job claimed to have stopped one")
    print(f"self-test ok: {len(names)} operations, interface at {page}")


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return

    # Has to happen before any window exists to have any effect.
    enable_dpi_awareness()
    import webview

    surface = bridge.Bridge()
    window = webview.create_window(
        PRODUCT,
        url=(resources() / "index.html").as_uri(),
        js_api=surface,
        width=1180,
        height=820,
        # Small enough for a 1366x768 laptop. Everything inside reflows.
        min_size=(880, 560),
    )
    # The choosers are the window's, and there is no other way to turn what an
    # operator picked into a path the services can open.
    surface._attach(window)
    # Retain local editor preferences (logo framing and language) between runs.
    webview.start(private_mode=False,
                  storage_path=str(pathlib.Path.home() / ".rx3-toolbox" / "webview"))


if __name__ == "__main__":
    main()
