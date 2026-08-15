"""Run the RX3 1.19 user-space application in an ARM Docker container."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time

from tools.rx3_emulator.framebuffer import (
    FramebufferError,
    Frame,
    export_png,
    read_frame,
    write_png,
)


REPOSITORY = pathlib.Path(__file__).resolve().parents[2]
CONTAINER = pathlib.Path(__file__).with_name("container")
DEFAULT_SYSROOT = REPOSITORY / "local/research/rx3-lab/sysroot"
IMAGE = "rx3-toolbox-emulator:1.19"
SUPPORTED_RBP_SHA1 = {
    "cf309238491e73cdbdc1f08a09f7a3177e079068",
    "7b9d7a0333b6b0ad8adc47bb79875a977b80af75",
    "fe0e8685790c0980dcb661077862018d956077e0",
    "be05066245d857c654d297e40a5f6545dcfb3da4",
}
TOUCH_SEQUENCE = 0

# The screen coordinates `emulator_apply_touch` recognises
# (mod/modules/core/1.19/rx3_core_hook.c). A window button has to aim at the
# same pixels a finger would, so this is a second copy of the hook's geometry
# in another language; tests/test_rx3_emulator.py reads both and fails on drift.
TAB_ROW_Y = 388           # the KEY / STEMS tabs occupy y 363..413
MODE_ROW_Y = 458          # STATUS / BEAT FX occupy y 433..483
CONTROL_ROW_Y = 540       # the panel control row occupies y 521..560
LEFT_SLOT_X = 1135        # slot 0 spans x 1090..1179
RIGHT_SLOT_X = 1225       # slot 1 spans x 1181..1270
DECK_STRIDE = 640         # the hook reads the deck straight off x >= 640

# Control geometry per panel id, mirroring rx3_keyshift_panel.h and
# rx3_stems_panel.h. Labels are the mod's own, so a button says what the
# on-screen control it presses says.
PANEL_CONTROLS: dict[int, tuple[tuple[str, int, int], ...]] = {
    1: (("KEY -", 19, 201), ("KEY 0", 215, 397), ("KEY +", 411, 613)),
    2: (("INSTRUMENTAL", 19, 306), ("VOCAL", 326, 613)),
}
# Which panels a profile actually installs, matching the RX3_KEYSHIFT /
# RX3_STEMS_DIR / RX3_EMULATOR_PANEL cases in run.sh. The first is the one the
# hook opens at startup. Stock loads no hook at all, so nothing answers.
PROFILE_PANELS: dict[str, tuple[int, ...]] = {
    "stock": (),
    "keyshift": (1,),
    "stems": (2,),
    "all": (1, 2),
}
PANEL_NAMES = {1: "KEY", 2: "STEMS"}

# rbp's browse-key table indices, read out of InitUiBrowseKey: each entry it
# registers sits at pushKey + index * 16 + 12. These are the physical keys above
# the screen and the rotary encoder's push, and unlike the pads they do not
# depend on startUp(), because BrowseKeyProcessing() pumps the table from the UI
# cycle rather than from the front-panel micro.
# Third field is how long the key is held, in milliseconds. MENU is a long
# press on the deck -- up to three seconds -- and the duration is what the key
# handler measures, so tapping it would be a different gesture, not a faster one.
BROWSE_KEYS: tuple[tuple[str, int, int], ...] = (
    ("SOURCE", 4, 0),
    ("BROWSE", 5, 0),
    ("TAG LIST", 6, 0),
    ("PLAYLIST", 7, 0),
    ("SEARCH", 8, 0),
    ("MENU", 10, 3000),
    ("ENCODER", 11, 0),
    ("BACK", 17, 0),
)
# Deliberately separate: loading a deck is the one pair here with a side effect
# on playback rather than on what is displayed.
LOAD_KEYS: tuple[tuple[str, int, int], ...] = (("LOAD 1", 12, 0), ("LOAD 2", 13, 0))

# ui::KeyInput::KeyCode values from docs/rx3-key-codes.md, recovered statically
# from keyCodeAsText(). These are PlayerInnards methods rather than browse-table
# entries, so they travel a different verb and carry a deck.
PAD_MODE_KEYS: tuple[tuple[str, int], ...] = (
    ("HOT CUE", 0x4113),
    ("BEAT LOOP", 0x4114),
    ("SLIP LOOP", 0x4115),
    ("BEAT JUMP", 0x4116),
)
PAD_KEYS: tuple[tuple[str, int], ...] = tuple(
    (f"PAD {n}", 0x4117 + n - 1) for n in range(1, 9)
)

WINDOW_INTERVAL_MS = 100
# The window decodes every tick because that is cheap; the PNG is the archive
# that report.json cites and only needs to be current at the end.
ARCHIVE_INTERVAL_S = 5.0


def digest(path: pathlib.Path, algorithm: str = "sha1") -> str:
    checksum = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def require_environment(sysroot: pathlib.Path, profile: str) -> dict[str, str]:
    if not shutil.which("docker"):
        raise RuntimeError("docker is not installed")
    subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    rbp = sysroot / "root/pdj/rbp"
    directfb = sysroot / "usr/lib/libdirectfb-1.4.so.0.0.0"
    if not rbp.is_file() or not directfb.is_file():
        raise RuntimeError(f"incomplete RX3 sysroot: {sysroot}")
    rbp_sha1 = digest(rbp)
    if rbp_sha1 not in SUPPORTED_RBP_SHA1:
        raise RuntimeError(f"unsupported rbp SHA-1: {rbp_sha1}")
    result = {"rbp_sha1": rbp_sha1}
    if profile != "stock":
        subprocess.run(["make", "emulator-hook"], cwd=REPOSITORY, check=True)
        core = REPOSITORY / "build/librx3_core.so"
        emulator_core = REPOSITORY / "build/librx3_core_emulator.so"
        if not core.is_file() or not emulator_core.is_file():
            raise RuntimeError("make emulator-hook did not produce both hook variants")
        result["core_sha256"] = digest(core, "sha256")
        result["emulator_core_sha256"] = digest(emulator_core, "sha256")
    return result


def ensure_image(rebuild: bool) -> None:
    present = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if rebuild or not present:
        subprocess.run(
            [
                "docker", "build", "--platform", "linux/arm/v7",
                "--tag", IMAGE, str(CONTAINER),
            ],
            cwd=REPOSITORY,
            check=True,
        )


def default_output() -> pathlib.Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return REPOSITORY / "outputs/rx3-emulator" / stamp


def docker_command(
    sysroot: pathlib.Path,
    output: pathlib.Path,
    profile: str,
    duration: int,
    container_name: str,
    unblock_init: bool = False,
    trace_init: bool = False,
    trace_reads: bool = False,
    panel: int | None = None,
    trace_layers: bool = False,
    font_donor: int = 0,
    font_maxh: int = 0,
    pump: int | None = None,
) -> list[str]:
    return [
        "docker", "run", "--rm", "--privileged", "--platform", "linux/arm/v7",
        "--name", container_name,
        "--mount", f"type=bind,source={sysroot},target=/rx3,readonly",
        "--mount", f"type=bind,source={REPOSITORY},target=/repo,readonly",
        "--mount", f"type=bind,source={output},target=/output",
        "--tmpfs", "/rx3/tmp:rw,exec,mode=1777",
        "--tmpfs", "/rx3/media:rw,exec,mode=755",
        "--env", f"RX3EMU_PROFILE={profile}",
        "--env", f"RX3EMU_DURATION={duration}",
        "--env", f"RX3EMU_UNBLOCK_INIT={1 if unblock_init else 0}",
        "--env", f"RX3EMU_TRACE_INIT={1 if trace_init else 0}",
        "--env", f"RX3EMU_TRACE_READS={1 if trace_reads else 0}",
        "--env", f"RX3EMU_TRACE_LAYERS={1 if trace_layers else 0}",
        "--env", f"RX3EMU_FONT_DONOR={font_donor}",
        "--env", f"RX3EMU_FONT_MAXH={font_maxh}",
        *(["--env", f"RX3EMU_PANEL={panel}"] if panel is not None else []),
        *(["--env", f"RX3EMU_PUMP={pump}"] if pump is not None else []),
        IMAGE,
    ]


def frame_when_ready(output: pathlib.Path) -> Frame | None:
    raw = output / "framebuffer.raw"
    metadata = output / "framebuffer.json"
    if not raw.is_file() or not metadata.is_file():
        return None
    try:
        frame = read_frame(raw, metadata)
    except (OSError, FramebufferError):
        # DirectFB may be changing depth or page while this snapshot is read.
        return None
    return frame if frame.non_black_pixels else None


def convert_when_ready(output: pathlib.Path) -> dict[str, int | str] | None:
    frame = frame_when_ready(output)
    if frame is None:
        return None
    png = output / "framebuffer.png"
    write_png(frame, png)
    return frame.summary(png)


def framebuffer_mtime(output: pathlib.Path) -> int:
    try:
        return (output / "framebuffer.raw").stat().st_mtime_ns
    except OSError:
        return -1


def inject(container_name: str, output: pathlib.Path, arguments: str) -> None:
    """Send one command down the hook's FIFO.

    `<seq> <x> <y>` is a screen point and `<seq> k <index>` a browse key; the
    sequence number is what lets the hook ignore a repeated read of the same
    line rather than acting on it twice.
    """
    global TOUCH_SEQUENCE
    TOUCH_SEQUENCE = (TOUCH_SEQUENCE + 1) & 0x7FFFFFFF
    if TOUCH_SEQUENCE == 0:
        TOUCH_SEQUENCE = 1
    line = f"{TOUCH_SEQUENCE} {arguments}"
    command = output / "touch.command"
    temporary = output / "touch.command.tmp"
    temporary.write_text(line + "\n", encoding="ascii")
    temporary.replace(command)
    subprocess.run(
        [
            "docker", "exec", container_name, "sh", "-c",
            f"printf '{line}\\n' > /rx3/tmp/rx3emu-touch.fifo",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3,
    )


def inject_touch(container_name: str, output: pathlib.Path, x: int, y: int) -> None:
    inject(container_name, output, f"{x} {y}")


def inject_key(
    container_name: str, output: pathlib.Path, index: int, hold_ms: int = 0
) -> None:
    inject(container_name, output, f"k {index} {hold_ms}")


def inject_player_key(
    container_name: str, output: pathlib.Path, code: int, deck: int
) -> None:
    inject(container_name, output, f"p {code} {deck}")


def stream_logs(container_name: str, latest: list[str]) -> threading.Thread:
    """Print the hook and rbp logs to the console as rbp writes them.

    Both files are otherwise only copied out when the container stops, which is
    useless for watching a startup that never finishes. `latest` receives the
    most recent line so the window can show it too.
    """

    def follow() -> None:
        while True:
            reader = subprocess.Popen(
                [
                    "docker", "exec", container_name, "sh", "-c",
                    "tail -n +1 -F /rx3/tmp/rx3-stems.log 2>/dev/null",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if reader.stdout is not None:
                for line in reader.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    latest.append(line)
                    print(f"  hook | {line}", flush=True)
            reader.wait()
            # The container may not be up yet, or may have gone; either way
            # there is nothing to follow, so stop rather than spin.
            if reader.returncode != 0:
                time.sleep(1.0)
                if subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                    capture_output=True, text=True,
                ).stdout.strip() != "true":
                    return
            else:
                return

    thread = threading.Thread(target=follow, daemon=True)
    thread.start()
    return thread


def monitor(
    process: subprocess.Popen[bytes], output: pathlib.Path
) -> dict[str, int | str] | None:
    framebuffer = None
    last_mtime = -1
    while process.poll() is None:
        mtime = framebuffer_mtime(output)
        if mtime != last_mtime:
            framebuffer = convert_when_ready(output) or framebuffer
            last_mtime = mtime
        time.sleep(0.25)
    return convert_when_ready(output) or framebuffer


def screen_targets(profile: str) -> list[tuple[str, int, int, int]]:
    """The mode and tab buttons, as (label, x, y, panel it selects).

    Panel 0 means the button selects no feature panel. Only the tabs a profile
    actually installs are offered: a KEY tab under `--profile stems` would be
    a button that silently does nothing.
    """
    targets = [
        ("STATUS", LEFT_SLOT_X, MODE_ROW_Y, 0),
        ("BEAT FX", RIGHT_SLOT_X, MODE_ROW_Y, 0),
    ]
    for slot, panel in enumerate(PROFILE_PANELS.get(profile, ())):
        targets.append(
            (
                PANEL_NAMES[panel],
                LEFT_SLOT_X if slot == 0 else RIGHT_SLOT_X,
                TAB_ROW_Y,
                panel,
            )
        )
    return targets


def control_targets(panel: int) -> list[tuple[int, str, int, int]]:
    """The open panel's control row for both decks, as (deck, label, x, y).

    Each names a point on the virtual screen, because the emulator's only input
    channel today is the touch FIFO the hook polls. Physical keys that have no
    on-screen equivalent are a later stage, and are absent rather than dead.
    """
    return [
        (
            deck,
            label,
            deck * DECK_STRIDE + (left + right) // 2,
            CONTROL_ROW_Y,
        )
        for deck in (0, 1)
        for label, left, right in PANEL_CONTROLS.get(panel, ())
    ]


def monitor_window(
    process: subprocess.Popen[bytes],
    output: pathlib.Path,
    container_name: str,
    profile: str,
    log_tail: list[str] | None = None,
) -> dict[str, int | str] | None:
    import tkinter as tk

    log_tail = log_tail if log_tail is not None else []

    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(f"cannot open the virtual RX3 screen: {error}") from error
    root.title("XDJ-RX3 1.19 emulator")
    root.configure(background="#111111")
    image_label = tk.Label(root, borderwidth=0, highlightthickness=0, background="#000000")
    image_label.pack()
    status = tk.StringVar(value="Démarrage de rbp…")
    tk.Label(
        root,
        textvariable=status,
        anchor="w",
        foreground="#f4f4f4",
        background="#202020",
        padx=8,
        pady=5,
    ).pack(fill="x")

    state: dict[str, object] = {
        "frame": None,
        "archived": 0.0,
        "shown": 0,
        "since": time.monotonic(),
        "rate": 0.0,
    }

    def press(x: int, y: int, description: str) -> None:
        try:
            inject_touch(container_name, output, x, y)
            status.set(f"{description} → {x}, {y}")
        except (OSError, subprocess.SubprocessError) as error:
            status.set(f"Tactile indisponible : {error}")

    def press_key(index: int, description: str, hold_ms: int) -> None:
        try:
            inject_key(container_name, output, index, hold_ms)
            status.set(f"Touche {description} (index {index})")
        except (OSError, subprocess.SubprocessError) as error:
            status.set(f"Façade indisponible : {error}")

    def press_player(code: int, description: str, deck: int) -> None:
        try:
            inject_player_key(container_name, output, code, deck)
            status.set(f"{description} deck {deck + 1} (0x{code:04x})")
        except (OSError, subprocess.SubprocessError) as error:
            status.set(f"Façade indisponible : {error}")

    front_panel = tk.Frame(root, background="#181818", padx=8, pady=6)
    front_panel.pack(fill="x")

    def section(parent: tk.Frame, name: str) -> tk.Frame:
        row = tk.Frame(parent, background="#181818")
        row.pack(fill="x", pady=2)
        tk.Label(
            row,
            text=name,
            width=8,
            anchor="w",
            foreground="#7b7d7b",
            background="#181818",
        ).pack(side="left")
        return row

    def button(parent: tk.Frame, label: str, x: int, y: int, then=None) -> None:
        def activate() -> None:
            press(x, y, label)
            if then is not None:
                then()

        tk.Button(
            parent,
            text=label,
            width=13,
            highlightbackground="#181818",
            command=activate,
        ).pack(side="left", padx=2)

    decks = tk.Frame(front_panel, background="#181818")

    def show_controls(panel: int) -> None:
        """Rebuild the deck rows for whichever panel is now open.

        The control columns differ per panel -- KEY has three, STEMS two -- so
        a static row would aim at the wrong pixels the moment the tab changed.
        """
        for child in decks.winfo_children():
            child.destroy()
        rows: dict[int, tk.Frame] = {}
        for deck, label, x, y in control_targets(panel):
            if deck not in rows:
                rows[deck] = section(decks, f"Deck {deck + 1}")
            button(rows[deck], label, x, y)

    # The physical keys above the screen, plus the encoder push and the two
    # LOAD keys. These go through rbp's own browse-key table rather than the
    # touch FIFO's coordinate path.
    keys = section(front_panel, "Façade")
    for label, index, hold_ms in BROWSE_KEYS + LOAD_KEYS:
        tk.Button(
            keys,
            text=label,
            width=9,
            highlightbackground="#181818",
            command=lambda index=index, label=label, hold_ms=hold_ms: press_key(
                index, label, hold_ms
            ),
        ).pack(side="left", padx=2)

    # The pad-mode selectors and the eight pads, per deck. These are the
    # controls whose handlers the mod hooks and which no emulator run has ever
    # been able to exercise.
    for deck in (0, 1):
        row = section(front_panel, f"Pads {deck + 1}")
        for label, code in PAD_MODE_KEYS:
            tk.Button(
                row, text=label, width=10, highlightbackground="#181818",
                command=lambda c=code, l=label, d=deck: press_player(c, l, d),
            ).pack(side="left", padx=2)
        for label, code in PAD_KEYS:
            tk.Button(
                row, text=label.split()[1], width=2,
                highlightbackground="#181818",
                command=lambda c=code, l=label, d=deck: press_player(c, l, d),
            ).pack(side="left", padx=1)

    modes = section(front_panel, "Écran")
    for label, x, y, panel in screen_targets(profile):
        button(modes, label, x, y, then=lambda panel=panel: show_controls(panel))
    decks.pack(fill="x")
    installed = PROFILE_PANELS.get(profile, ())
    # The hook opens the first installed panel at startup, so start there.
    show_controls(installed[0] if installed else 0)

    def close() -> None:
        root.destroy()

    def click(event: tk.Event[tk.Misc]) -> None:
        frame = state["frame"]
        if not isinstance(frame, Frame):
            return
        shown_width = max(1, image_label.winfo_width())
        shown_height = max(1, image_label.winfo_height())
        x = int(event.x * frame.width / shown_width)
        y = int(event.y * frame.height / shown_height)
        press(x, y, "Tactile RX3")

    photo = tk.PhotoImage(width=1280, height=720)
    image_label.configure(image=photo)
    image_label.image = photo  # type: ignore[attr-defined]

    def refresh() -> None:
        if process.poll() is not None:
            root.destroy()
            return
        frame = frame_when_ready(output)
        if frame is not None:
            state["frame"] = frame
            # Straight from memory: no zlib, no temporary file, no second
            # decode. This is what makes the window watchable rather than a
            # slideshow.
            photo.configure(data=frame.ppm())
            shown = int(state["shown"]) + 1
            state["shown"] = shown
            elapsed = time.monotonic() - float(state["since"])
            if elapsed >= 1.0:
                state["rate"] = shown / elapsed
                state["shown"] = 0
                state["since"] = time.monotonic()
            lit = 100.0 * frame.non_black_pixels / frame.pixels
            recent = log_tail[-1] if log_tail else ""
            status.set(
                f"{float(state['rate']):.1f} i/s · {lit:.1f} % allumé"
                + (f" · {recent}" if recent else
                   " · cliquez ou utilisez la façade")
            )
            now = time.monotonic()
            if now - float(state["archived"]) >= ARCHIVE_INTERVAL_S:
                write_png(frame, output / "framebuffer.png")
                state["archived"] = now
        root.after(WINDOW_INTERVAL_MS, refresh)

    image_label.bind("<Button-1>", click)
    root.bind("<Escape>", lambda _event: close())
    root.bind("q", lambda _event: close())
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(0, refresh)
    root.mainloop()

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    final = convert_when_ready(output)
    if final is not None:
        return final
    frame = state["frame"]
    if isinstance(frame, Frame):
        # The container is gone and its last mmap page may already be torn, so
        # archive the last frame the window actually displayed instead.
        png = output / "framebuffer.png"
        write_png(frame, png)
        return frame.summary(png)
    return None


def evaluate(
    output: pathlib.Path,
    profile: str,
    provenance: dict[str, str],
    framebuffer: dict[str, int | str] | None,
    container_status: int,
) -> tuple[dict[str, object], bool]:
    hook_log_path = output / "hook.log"
    hook_log = hook_log_path.read_text(errors="replace") if hook_log_path.is_file() else ""
    touch_events = hook_log.count("emulator touch control = ")

    def counter(label: str) -> int:
        match = re.search(rf"^{re.escape(label)}\s*=\s*(\d+)$", hook_log, re.MULTILINE)
        return int(match.group(1)) if match else 0

    # DirectFB opens /dev/fb0 exactly once, and the shim writes this file when
    # it does. Its absence means graphics never started, which cascades into
    # half the checks below failing for a reason none of them names. Reported
    # separately so an infrastructure failure cannot be misread as a mod
    # regression.
    checks = {
        "directfb_started": (output / "framebuffer.json").is_file(),
        "container_completed": container_status == 0,
        "framebuffer_exported": framebuffer is not None,
        "framebuffer_non_empty": bool(framebuffer and framebuffer["non_black_pixels"]),
        "hook_ready": profile == "stock" or (output / "ready").is_file(),
        "hook_active": profile == "stock" or "RX3 performance hook active" in hook_log,
        "private_image_table": profile == "stock" or "extended private KEY/STEMS image table installed" in hook_log,
        "custom_tabs_rendered": profile == "stock" or (
            "emulator custom tab rendered" in hook_log
            or counter("probe custom tab draws") > 0
        ),
        "custom_pads_rendered": profile == "stock" or (
            "emulator custom PAD rendered" in hook_log
            or counter("probe custom PAD draws") > 0
        ),
        "virtual_touch_ready": profile == "stock" or "emulator virtual touch channel ready" in hook_log,
    }
    report: dict[str, object] = {
        "profile": profile,
        **provenance,
        "checks": checks,
        "virtual_touch_events": touch_events,
        "framebuffer": framebuffer,
        "scope": {
            "validated": [
                "rbp ARM startup",
                "DirectFB rendering",
                "hook guards",
                "native UI draw path",
                *(["virtual touch routing"] if touch_events else []),
            ],
            "not_validated": ["audio DSP", "hardware LEDs", "USB timing", "device stability"],
        },
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report, all(checks.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the genuine RX3 1.19 rbp binary with a host framebuffer."
    )
    parser.add_argument("--profile", choices=("stock", "keyshift", "stems", "all"), default="all")
    parser.add_argument("--sysroot", type=pathlib.Path, default=DEFAULT_SYSROOT)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="seconds to run, or 0 to run until the window is closed",
    )
    parser.add_argument("--window", action="store_true", help="show a live clickable 1280x720 screen")
    parser.add_argument(
        "--unblock-init",
        action="store_true",
        help="force main's branch into startUp(); inert until init() returns",
    )
    parser.add_argument(
        "--trace-init",
        action="store_true",
        help="log entry and exit of the constructors UiObjectManager::init() calls",
    )
    parser.add_argument(
        "--trace-reads",
        action="store_true",
        help="log reads that returned data on the faked device nodes",
    )
    parser.add_argument(
        "--panel",
        type=int,
        help="override which feature panel is forced open (0 = none)",
    )
    parser.add_argument(
        "--trace-layers",
        action="store_true",
        help="log each distinct window layer that issues a text draw",
    )
    parser.add_argument(
        "--font-donor",
        type=int,
        default=0,
        help="subtree to clone the control face from, e.g. 6 for the deck strip",
    )
    parser.add_argument(
        "--pump", type=int, choices=(0, 1), default=None,
        help="browse-key route: 1 drives BrowseKeyProcessing from the mod's own "
             "thread, 0 posts rbp's eventflag and lets Ui_EventTask run it. "
             "Unset lets the hook choose on whether the flag exists",
    )
    parser.add_argument("--font-maxh", type=int, default=0,
                        help="largest donor glyph box height to accept")
    parser.add_argument("--rebuild-image", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.duration < 0 or 0 < arguments.duration < 10:
        raise SystemExit("--duration must be 0 or at least 10 seconds")
    if arguments.duration == 0 and not arguments.window:
        # Without a window there is nothing to close, so an uncapped headless
        # run could only ever be ended by Ctrl-C, which discards the report.
        raise SystemExit("--duration 0 needs --window to have a way to stop")
    sysroot = arguments.sysroot.expanduser().resolve()
    output = (arguments.output or default_output()).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        provenance = require_environment(sysroot, arguments.profile)
        ensure_image(arguments.rebuild_image)
        container_name = f"rx3-toolbox-emulator-{os.getpid()}"
        command = docker_command(
            sysroot,
            output,
            arguments.profile,
            arguments.duration,
            container_name,
            arguments.unblock_init,
            arguments.trace_init,
            arguments.trace_reads,
            arguments.panel,
            arguments.trace_layers,
            arguments.font_donor,
            arguments.font_maxh,
            arguments.pump,
        )
        print(f"RX3 emulator output: {output}", flush=True)
        process = subprocess.Popen(command, cwd=REPOSITORY)
        latest_log: list[str] = []
        stream_logs(container_name, latest_log)
        try:
            framebuffer = (
                monitor_window(
                    process, output, container_name, arguments.profile, latest_log
                )
                if arguments.window
                else monitor(process, output)
            )
        except KeyboardInterrupt:
            process.terminate()
            process.wait(timeout=15)
            return 130
        report, passed = evaluate(
            output, arguments.profile, provenance, framebuffer, process.returncode or 0
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"emulator error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report["checks"], indent=2, sort_keys=True))
    print(f"Framebuffer: {output / 'framebuffer.png'}")
    print(f"Report: {output / 'report.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
