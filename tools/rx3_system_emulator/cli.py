"""Probe the genuine RX3 1.19 U-Boot and kernel with QEMU's i.MX6 model."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import pathlib
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from typing import Sequence

from tools.rx3_emulator.framebuffer import FramebufferError, export_png


REPOSITORY = pathlib.Path(__file__).resolve().parents[2]
FIRMWARE_IMAGES = REPOSITORY / "local/firmware/rx3/extracted/119/iso/images"
BOOTSTUB_SOURCE = pathlib.Path(__file__).with_name("bootstub.S")
U_BOOT = FIRMWARE_IMAGES / "u-boot.bin.nand"
U_IMAGE = FIRMWARE_IMAGES / "uImage"
ROOTFS = FIRMWARE_IMAGES / "rootfs.cramfs"
SYSROOT = REPOSITORY / "local/research/rx3-lab/sysroot"
OVERLAY = pathlib.Path(__file__).with_name("overlay")
FBSHIM_IMAGE = "rx3-toolbox-emulator:1.19"
FBSHIM_CONTAINER_PATH = "/opt/rx3emu/fbshim.so"
INITRD_ADDRESS = 0x18000000
FRAME_MAGIC = b"RX3FB01\0"
FRAME_HEADER = struct.Struct("<8s6I")

RAW_KERNEL_GPU_INIT_OFFSET = 0x1C44C
RAW_KERNEL_GPU_INIT_ORIGINAL = bytes.fromhex("00009fe558e218ea")
RAW_KERNEL_RETURN_ZERO = bytes.fromhex("0000a0e31eff2fe1")

EXPECTED_SHA256 = {
    "u-boot.bin.nand": "a0ffbbaf9bc61d9ad642a35c5d0b369fe00108dcd13c29d633944bbe525e3c20",
    "uImage": "0ac237e5488c2640d753bd018ef14e71aef27d170da70880d3e072c267c05081",
    "rootfs.cramfs": "898e8af46b2d27b3183ac33e97e31bd0723840654c501c868521207bc12d16fd",
}

U_BOOT_MARKERS = (
    "U-Boot 2009.08-svn3101",
    "CPU: Freescale i.MX6 family",
    "Board: i.MX6Q-SABRESD: Rev3rd Board",
    "DRAM:   1 GB",
    "MMC:   FSL_USDHC: 0,FSL_USDHC: 1,FSL_USDHC: 2,FSL_USDHC: 3",
)
KERNEL_MARKERS = (
    "Linux version 3.0.101-2790-gc248ed7-svn3098",
    "Machine: Freescale i.MX 6Quad/DualLite/Solo Sabre-SD Board",
    "Memory: 752MB 256MB = 1008MB total",
    "subucom SPI user interface",
    "gpiodrv_module_init major:minor = 252:0",
    "TSC2007 TouchScreen user interface",
    "mxc_sdc_fb mxc_sdc_fb.0: register mxc display driver ldb",
)
FAST_MARKERS = KERNEL_MARKERS + (
    "RX3EMU: external rootfs ready",
    "### apl_start script ###",
    "### Application Start!! ###",
    "RX3EMU: rbp exec -r -a",
    "RX3EMU: framebuffer ready bytes=",
)


def digest(path: pathlib.Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def inspect_uimage(path: pathlib.Path) -> dict[str, int | str]:
    header = path.read_bytes()[:64]
    if len(header) != 64:
        raise RuntimeError(f"truncated uImage header: {path}")
    fields = struct.unpack(">7I4B32s", header)
    magic, _header_crc, timestamp, size, load, entry, _data_crc = fields[:7]
    os_id, architecture, image_type, compression, name = fields[7:]
    if magic != 0x27051956:
        raise RuntimeError(f"invalid uImage magic: 0x{magic:08x}")
    return {
        "timestamp": timestamp,
        "payload_size": size,
        "load_address": load,
        "entry_point": entry,
        "os": os_id,
        "architecture": architecture,
        "type": image_type,
        "compression": compression,
        "name": name.split(b"\0", 1)[0].decode("ascii", errors="replace"),
    }


def require_environment(*, fast: bool = False) -> dict[str, object]:
    tools = {name: shutil.which(name) for name in ("qemu-system-arm", "clang", "ld.lld")}
    missing = [name for name, location in tools.items() if location is None]
    if missing:
        raise RuntimeError(f"missing tools: {', '.join(missing)}")
    if not SYSROOT.is_dir():
        raise RuntimeError(f"missing private RX3 sysroot: {SYSROOT}")
    for artifact in (U_BOOT, U_IMAGE, ROOTFS):
        if not artifact.is_file():
            raise RuntimeError(f"missing private firmware artifact: {artifact}")
        actual = digest(artifact)
        expected = EXPECTED_SHA256[artifact.name]
        if actual != expected:
            raise RuntimeError(
                f"unsupported {artifact.name} SHA-256: {actual}; expected {expected}"
            )
    uimage = inspect_uimage(U_IMAGE)
    if uimage["load_address"] != 0x10008000 or uimage["entry_point"] != 0x10008000:
        raise RuntimeError(f"unsupported RX3 kernel addresses: {uimage}")
    if fast:
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("fast mode requires Docker and the ARM fbdev shim image")
        inspected = subprocess.run(
            [docker, "image", "inspect", FBSHIM_IMAGE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if inspected.returncode:
            raise RuntimeError(
                f"missing {FBSHIM_IMAGE}; run `make emulator-image` first"
            )
    return {
        "tools": tools,
        "artifacts_sha256": {
            artifact.name: EXPECTED_SHA256[artifact.name]
            for artifact in (U_BOOT, U_IMAGE, ROOTFS)
        },
        "uimage": uimage,
    }


def build_bootstub(directory: pathlib.Path, initrd_size: int = 0) -> pathlib.Path:
    object_file = directory / "bootstub.o"
    bootstub = directory / "bootstub.bin"
    subprocess.run(
        [
            "clang", "--target=armv7-none-eabi", "-march=armv7-a",
            f"-DRX3_INITRD_START=0x{INITRD_ADDRESS:x}",
            f"-DRX3_INITRD_SIZE={initrd_size}",
            "-c", str(BOOTSTUB_SOURCE), "-o", str(object_file),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ld.lld", "-Ttext=0x10000000", "--oformat=binary",
            str(object_file), "-o", str(bootstub),
        ],
        check=True,
    )
    return bootstub


def build_kernel_loaders(directory: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    bootstub = build_bootstub(directory)
    kernel = directory / "kernel.bin"
    image = U_IMAGE.read_bytes()
    kernel.write_bytes(image[64:])
    return bootstub, kernel


def extract_and_patch_raw_kernel(output: pathlib.Path) -> None:
    """Extract the Image from the RX3 zImage and bypass unsupported Galcore."""
    payload = U_IMAGE.read_bytes()[64:]
    gzip_offset = payload.find(b"\x1f\x8b\x08")
    if gzip_offset < 0:
        raise RuntimeError("RX3 zImage does not contain its expected gzip stream")
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    raw = bytearray(inflater.decompress(payload[gzip_offset:]) + inflater.flush())
    found = bytes(raw[
        RAW_KERNEL_GPU_INIT_OFFSET:RAW_KERNEL_GPU_INIT_OFFSET
        + len(RAW_KERNEL_GPU_INIT_ORIGINAL)
    ])
    if found != RAW_KERNEL_GPU_INIT_ORIGINAL:
        raise RuntimeError(
            "RX3 gpu_init guard rejected: "
            f"{found.hex()} != {RAW_KERNEL_GPU_INIT_ORIGINAL.hex()}"
        )
    raw[
        RAW_KERNEL_GPU_INIT_OFFSET:RAW_KERNEL_GPU_INIT_OFFSET
        + len(RAW_KERNEL_RETURN_ZERO)
    ] = RAW_KERNEL_RETURN_ZERO
    output.write_bytes(raw)


def extract_fbshim(output: pathlib.Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is required to extract the ARM fbdev shim")
    container = subprocess.check_output(
        [docker, "create", FBSHIM_IMAGE], text=True
    ).strip()
    try:
        subprocess.run(
            [docker, "cp", f"{container}:{FBSHIM_CONTAINER_PATH}", str(output)],
            check=True,
        )
    finally:
        subprocess.run(
            [docker, "rm", "-f", container],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _cpio_padding(size: int) -> bytes:
    return bytes((-size) % 4)


def _write_newc_entry(
    archive: gzip.GzipFile,
    name: str,
    mode: int,
    data: bytes = b"",
    *,
    inode: int,
    rdev_major: int = 0,
    rdev_minor: int = 0,
) -> None:
    encoded_name = name.encode("utf-8") + b"\0"
    fields = (
        inode, mode, 0, 0, 1, 0, len(data), 0, 0,
        rdev_major, rdev_minor, len(encoded_name), 0,
    )
    header = b"070701" + b"".join(f"{field:08x}".encode("ascii") for field in fields)
    archive.write(header)
    archive.write(encoded_name)
    archive.write(_cpio_padding(len(header) + len(encoded_name)))
    archive.write(data)
    archive.write(_cpio_padding(len(data)))


def build_fast_initramfs(output: pathlib.Path, fbshim: pathlib.Path) -> None:
    """Build a reproducible external initramfs from the private 1.19 sysroot."""
    renamed = {
        "root/pdj/rbp": "root/pdj/rbp.real",
        "usr/bin/fw_printenv": "usr/bin/fw_printenv.real",
        "usr/bin/bootmod": "usr/bin/bootmod.real",
        "usr/bin/boardrev": "usr/bin/boardrev.real",
        "usr/bin/gpio": "usr/bin/gpio.real",
        "usr/bin/regio": "usr/bin/regio.real",
    }
    overridden = set(renamed)
    overridden.update(
        str(path.relative_to(OVERLAY))
        for path in OVERLAY.rglob("*") if path.is_file()
    )
    device_nodes = {
        "dev/console": (0o600, 5, 1),
        "dev/null": (0o666, 1, 3),
        "dev/tty": (0o666, 5, 0),
        "dev/zero": (0o666, 1, 5),
        "dev/random": (0o666, 1, 8),
        "dev/urandom": (0o666, 1, 9),
    }
    inode = 1
    with output.open("wb") as raw_output:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw_output, mtime=0, compresslevel=1
        ) as archive:
            _write_newc_entry(archive, ".", stat.S_IFDIR | 0o755, inode=inode)
            inode += 1
            for source in sorted(SYSROOT.rglob("*")):
                relative = str(source.relative_to(SYSROOT))
                if relative in device_nodes or relative in overridden:
                    continue
                metadata = source.lstat()
                mode = metadata.st_mode
                if source.is_symlink():
                    data = os.readlink(source).encode("utf-8")
                elif source.is_file():
                    data = source.read_bytes()
                else:
                    data = b""
                _write_newc_entry(archive, relative, mode, data, inode=inode)
                inode += 1
            for original, destination in renamed.items():
                source = SYSROOT / original
                _write_newc_entry(
                    archive, destination, source.lstat().st_mode,
                    source.read_bytes(), inode=inode,
                )
                inode += 1
            for source in sorted(OVERLAY.rglob("*")):
                if not source.is_file():
                    continue
                relative = str(source.relative_to(OVERLAY))
                _write_newc_entry(
                    archive, relative, stat.S_IFREG | 0o755,
                    source.read_bytes(), inode=inode,
                )
                inode += 1
            _write_newc_entry(
                archive, "root/pdj/rx3emu-fbshim.so", stat.S_IFREG | 0o755,
                fbshim.read_bytes(), inode=inode,
            )
            inode += 1
            for name, (permissions, major, minor) in device_nodes.items():
                _write_newc_entry(
                    archive, name, stat.S_IFCHR | permissions, inode=inode,
                    rdev_major=major, rdev_minor=minor,
                )
                inode += 1
            _write_newc_entry(
                archive, "TRAILER!!!", 0, inode=inode,
            )


def build_fast_loaders(
    directory: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    kernel = directory / "kernel-fast.bin"
    initramfs = directory / "rootfs-fast.cpio.gz"
    fbshim = directory / "fbshim.so"
    extract_and_patch_raw_kernel(kernel)
    extract_fbshim(fbshim)
    build_fast_initramfs(initramfs, fbshim)
    bootstub = build_bootstub(directory, initramfs.stat().st_size)
    return bootstub, kernel, initramfs, fbshim


def qemu_base() -> list[str]:
    return [
        "qemu-system-arm", "-M", "sabrelite", "-m", "1G",
        "-display", "none", "-monitor", "none",
        "-serial", "stdio",
        "-serial", "null",
        "-serial", "null",
        "-serial", "null",
        "-serial", "null",
        "-no-reboot",
    ]


def uboot_command() -> list[str]:
    return qemu_base() + [
        "-device",
        f"loader,file={U_BOOT},addr=0x17800000,cpu-num=0,force-raw=on",
    ]


def kernel_command(
    bootstub: pathlib.Path,
    kernel: pathlib.Path,
    initramfs: pathlib.Path | None = None,
    export_framebuffer: bool = False,
) -> list[str]:
    command = qemu_base() + [
        "-device",
        f"loader,file={bootstub},addr=0x10000000,cpu-num=0,force-raw=on",
        "-device",
        f"loader,file={kernel},addr=0x10008000,force-raw=on",
    ]
    if initramfs is not None:
        command.extend([
            "-device",
            f"loader,file={initramfs},addr=0x{INITRD_ADDRESS:x},force-raw=on",
        ])
    if export_framebuffer:
        command.extend([
            "-semihosting-config",
            "enable=on,target=native,userspace=on",
        ])
    return command


def _write_host_frame(
    output: pathlib.Path,
    payload: bytes,
    *,
    width: int,
    height: int,
    bpp: int,
    stride: int,
) -> None:
    raw = output / "framebuffer.raw"
    raw_temporary = output / "framebuffer.raw.tmp"
    metadata = output / "framebuffer.json"
    metadata_temporary = output / "framebuffer.json.tmp"
    raw_temporary.write_bytes(payload)
    raw_temporary.replace(raw)
    metadata_temporary.write_text(
        json.dumps({
            "width": width,
            "height": height,
            "virtual_height": height,
            "bpp": bpp,
            "stride": stride,
            "yoffset": 0,
        }, sort_keys=True) + "\n",
        encoding="ascii",
    )
    metadata_temporary.replace(metadata)


def receive_framebuffer_file(
    transport: pathlib.Path,
    output: pathlib.Path,
    stop: threading.Event,
    statistics: dict[str, int],
) -> None:
    last_mtime = -1
    while not stop.wait(0.1):
        try:
            mtime = transport.stat().st_mtime_ns
            if mtime == last_mtime:
                continue
            blob = transport.read_bytes()
        except OSError:
            continue
        last_mtime = mtime
        if len(blob) < FRAME_HEADER.size:
            continue
        magic, width, height, bpp, stride, _guest_yoffset, size = (
            FRAME_HEADER.unpack_from(blob)
        )
        sane = (
            magic == FRAME_MAGIC
            and 1 <= width <= 4096
            and 1 <= height <= 4096
            and bpp in (16, 32)
            and width * (bpp // 8) <= stride <= 65536
            and size == stride * height
            and size <= 64 * 1024 * 1024
            and len(blob) == FRAME_HEADER.size + size
        )
        if not sane:
            continue
        _write_host_frame(
            output, blob[FRAME_HEADER.size:],
            width=width, height=height, bpp=bpp, stride=stride,
        )
        statistics["frames"] = statistics.get("frames", 0) + 1
        statistics["bytes"] = statistics.get("bytes", 0) + size
        statistics["width"] = width
        statistics["height"] = height
        statistics["bpp"] = bpp


def show_system_window(
    process: subprocess.Popen[bytes], output: pathlib.Path, deadline: float
) -> None:
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(f"cannot open the RX3 system framebuffer: {error}") from error
    root.title("XDJ-RX3 1.19 system emulator")
    root.configure(background="#111111")
    image_label = tk.Label(root, borderwidth=0, highlightthickness=0, background="#000000")
    image_label.pack()
    status = tk.StringVar(value="Démarrage du noyau RX3…")
    tk.Label(
        root, textvariable=status, anchor="w", foreground="#f4f4f4",
        background="#202020", padx=8, pady=5,
    ).pack(fill="x")

    def close() -> None:
        root.destroy()

    def refresh() -> None:
        if process.poll() is not None or time.monotonic() >= deadline:
            root.destroy()
            return
        try:
            framebuffer = export_png(
                output / "framebuffer.raw",
                output / "framebuffer.json",
                output / "framebuffer.png",
            )
        except (OSError, FramebufferError):
            framebuffer = None
        if framebuffer:
            photo = tk.PhotoImage(file=str(output / "framebuffer.png"))
            image_label.configure(image=photo)
            image_label.image = photo  # type: ignore[attr-defined]
            status.set("Framebuffer du système RX3 — tactile système non raccordé")
        root.after(250, refresh)

    root.bind("<Escape>", lambda _event: close())
    root.bind("q", lambda _event: close())
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(0, refresh)
    root.mainloop()


def run_fast_probe(
    command: Sequence[str],
    timeout: float,
    output: pathlib.Path,
    *,
    window: bool,
) -> tuple[str, int, dict[str, int]]:
    transport = output / "framebuffer.transport"
    transport.unlink(missing_ok=True)
    process = subprocess.Popen(
        list(command), cwd=output, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    chunks: list[bytes] = []
    statistics: dict[str, int] = {}

    def drain_output() -> None:
        assert process.stdout is not None
        reader = getattr(process.stdout, "read1", process.stdout.read)
        for block in iter(lambda: reader(65536), b""):
            chunks.append(block)

    output_thread = threading.Thread(target=drain_output, daemon=True)
    stop = threading.Event()
    receiver = threading.Thread(
        target=receive_framebuffer_file,
        args=(transport, output, stop, statistics),
        daemon=True,
    )
    output_thread.start()
    receiver.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    try:
        if window:
            show_system_window(process, output, deadline)
        else:
            remaining = max(0.0, deadline - time.monotonic())
            process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        stop.set()
        receiver.join(timeout=2)
        output_thread.join(timeout=2)
    status = process.returncode if process.returncode is not None else 124
    if timed_out or status == -15:
        status = 124
    return b"".join(chunks).decode("utf-8", errors="replace"), status, statistics


def run_probe(command: Sequence[str], timeout: float) -> tuple[str, int]:
    process = subprocess.Popen(
        list(command),
        cwd=REPOSITORY,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
        status = process.returncode
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
        status = 124
    return output.decode("utf-8", errors="replace"), status


def evaluate(log: str, markers: Sequence[str], status: int) -> dict[str, object]:
    checks = {marker: marker in log for marker in markers}
    return {
        "status": status,
        "checks": checks,
        "passed": all(checks.values()),
    }


def default_output() -> pathlib.Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return REPOSITORY / "outputs/rx3-system-emulator" / stamp


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Boot the genuine RX3 1.19 U-Boot/kernel on QEMU i.MX6",
    )
    parser.add_argument(
        "--mode", choices=("all", "uboot", "kernel", "fast"), default="all"
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=pathlib.Path, default=None)
    parser.add_argument(
        "--window", action="store_true",
        help="show the framebuffer exported by fast mode",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.window and args.mode != "fast":
        raise SystemExit("--window is only supported with --mode fast")
    output = (args.output or default_output()).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    provenance = require_environment(fast=args.mode == "fast")
    probes: dict[str, object] = {}

    with tempfile.TemporaryDirectory(prefix="rx3-system-emulator-") as temporary:
        temporary_path = pathlib.Path(temporary)
        if args.mode in ("all", "uboot"):
            log, status = run_probe(uboot_command(), args.timeout)
            (output / "uboot.log").write_text(log, encoding="utf-8")
            probes["uboot"] = evaluate(log, U_BOOT_MARKERS, status)
        if args.mode in ("all", "kernel"):
            bootstub, kernel = build_kernel_loaders(temporary_path)
            log, status = run_probe(kernel_command(bootstub, kernel), args.timeout)
            (output / "kernel.log").write_text(log, encoding="utf-8")
            probes["kernel"] = evaluate(log, KERNEL_MARKERS, status)
        if args.mode == "fast":
            bootstub, kernel, initramfs, fbshim = build_fast_loaders(temporary_path)
            log, status, framebuffer_transport = run_fast_probe(
                kernel_command(
                    bootstub, kernel, initramfs, export_framebuffer=True
                ),
                args.timeout,
                output,
                window=args.window,
            )
            (output / "fast.log").write_text(log, encoding="utf-8")
            fast_probe = evaluate(log, FAST_MARKERS, status)
            framebuffer = None
            try:
                framebuffer = export_png(
                    output / "framebuffer.raw",
                    output / "framebuffer.json",
                    output / "framebuffer.png",
                )
            except (OSError, FramebufferError):
                pass
            fast_probe["checks"]["host_framebuffer_received"] = bool(  # type: ignore[index]
                framebuffer_transport.get("frames")
            )
            fast_probe["checks"]["host_framebuffer_non_empty"] = bool(  # type: ignore[index]
                framebuffer and framebuffer["non_black_pixels"]
            )
            fast_probe["passed"] = all(fast_probe["checks"].values())  # type: ignore[union-attr]
            fast_probe["framebuffer"] = framebuffer
            fast_probe["transport"] = framebuffer_transport
            probes["fast"] = fast_probe
            provenance["fast_mode"] = {
                "kernel_patch": {
                    "symbol": "gpu_init",
                    "raw_offset": RAW_KERNEL_GPU_INIT_OFFSET,
                    "reason": "QEMU sabrelite has no Vivante Galcore device model",
                    "before": RAW_KERNEL_GPU_INIT_ORIGINAL.hex(),
                    "after": RAW_KERNEL_RETURN_ZERO.hex(),
                },
                "initramfs_sha256": digest(initramfs),
                "initramfs_size": initramfs.stat().st_size,
                "fbshim_sha256": digest(fbshim),
            }

    passed = all(bool(probe["passed"]) for probe in probes.values())  # type: ignore[index]
    validated = [
        "genuine Linux 3.0.101 kernel execution with legacy Sabre-SD ATAGs",
        "initialization reached RX3 subucom, gpiodrv, touchscreen and MXC framebuffer drivers",
    ]
    if "uboot" in probes:
        validated.insert(0, "genuine U-Boot execution on the QEMU i.MX6Q CPU model")
    if "fast" in probes:
        validated.append("genuine init, rcS, apl_start and rbp execution")
        validated.append("rbp created a 1280x720x32 virtual framebuffer inside the guest")
    report = {
        "firmware": "1.19",
        **provenance,
        "probes": probes,
        "passed": passed,
        "scope": {
            "validated": validated,
            "not_yet_emulated": [
                "GPMI NAND and APBH DMA",
                "i.MX6 IPU/LDB scanout and Vivante galcore GPU (fast mode uses an explicit fbdev shim)",
                "TSC2007 I2C samples and IRQ delivery",
                "Pioneer SPI sub-controllers, audio codecs and physical controls",
            ],
        },
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output / "report.json")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
