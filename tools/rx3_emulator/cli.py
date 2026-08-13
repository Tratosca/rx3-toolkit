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
import time

from tools.rx3_emulator.framebuffer import FramebufferError, export_png


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
        IMAGE,
    ]


def convert_when_ready(output: pathlib.Path) -> dict[str, int | str] | None:
    raw = output / "framebuffer.raw"
    metadata = output / "framebuffer.json"
    if not raw.is_file() or not metadata.is_file():
        return None
    try:
        framebuffer = export_png(raw, metadata, output / "framebuffer.png")
        return framebuffer if framebuffer["non_black_pixels"] else None
    except (OSError, FramebufferError):
        # DirectFB may be changing depth or page while this snapshot is read.
        return None


def framebuffer_mtime(output: pathlib.Path) -> int:
    try:
        return (output / "framebuffer.raw").stat().st_mtime_ns
    except OSError:
        return -1


def inject_touch(container_name: str, output: pathlib.Path, x: int, y: int) -> None:
    global TOUCH_SEQUENCE
    TOUCH_SEQUENCE = (TOUCH_SEQUENCE + 1) & 0x7FFFFFFF
    if TOUCH_SEQUENCE == 0:
        TOUCH_SEQUENCE = 1
    command = output / "touch.command"
    temporary = output / "touch.command.tmp"
    temporary.write_text(f"{TOUCH_SEQUENCE} {x} {y}\n", encoding="ascii")
    temporary.replace(command)
    subprocess.run(
        [
            "docker", "exec", container_name, "sh", "-c",
            f"printf '{TOUCH_SEQUENCE} {x} {y}\\n' > /rx3/tmp/rx3emu-touch.fifo",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3,
    )


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


def monitor_window(
    process: subprocess.Popen[bytes], output: pathlib.Path, container_name: str
) -> dict[str, int | str] | None:
    import tkinter as tk

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

    state: dict[str, object] = {"framebuffer": None, "mtime": -1, "closing": False}

    def close() -> None:
        state["closing"] = True
        root.destroy()

    def click(event: tk.Event[tk.Misc]) -> None:
        framebuffer = state["framebuffer"]
        if not isinstance(framebuffer, dict):
            return
        shown_width = max(1, image_label.winfo_width())
        shown_height = max(1, image_label.winfo_height())
        x = int(event.x * int(framebuffer["width"]) / shown_width)
        y = int(event.y * int(framebuffer["height"]) / shown_height)
        try:
            inject_touch(container_name, output, x, y)
            status.set(f"Tactile RX3 : {x}, {y}")
        except (OSError, subprocess.SubprocessError) as error:
            status.set(f"Tactile indisponible : {error}")

    def refresh() -> None:
        if process.poll() is not None:
            root.destroy()
            return
        framebuffer = convert_when_ready(output)
        if framebuffer:
            state["framebuffer"] = framebuffer
            state["mtime"] = framebuffer_mtime(output)
            photo = tk.PhotoImage(file=str(output / "framebuffer.png"))
            image_label.configure(image=photo)
            image_label.image = photo  # type: ignore[attr-defined]
            status.set("Écran virtuel actif — cliquez pour injecter un appui")
        root.after(250, refresh)

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
    return convert_when_ready(output) or state["framebuffer"]  # type: ignore[return-value]


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

    checks = {
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
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--window", action="store_true", help="show a live clickable 1280x720 screen")
    parser.add_argument("--rebuild-image", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.duration < 10:
        raise SystemExit("--duration must be at least 10 seconds")
    sysroot = arguments.sysroot.expanduser().resolve()
    output = (arguments.output or default_output()).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        provenance = require_environment(sysroot, arguments.profile)
        ensure_image(arguments.rebuild_image)
        container_name = f"rx3-toolbox-emulator-{os.getpid()}"
        command = docker_command(
            sysroot, output, arguments.profile, arguments.duration, container_name
        )
        print(f"RX3 emulator output: {output}", flush=True)
        process = subprocess.Popen(command, cwd=REPOSITORY)
        try:
            framebuffer = (
                monitor_window(process, output, container_name)
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
