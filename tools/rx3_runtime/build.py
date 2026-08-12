# SPDX-License-Identifier: MPL-2.0
"""Shared build engine for the RX3 runtime CLI and desktop application."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Iterable


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class RuntimeFile:
    source: str
    target: str
    executable: bool = False


@dataclass(frozen=True)
class ArmHook:
    source: str
    target: str


@dataclass(frozen=True)
class PatchDefinition:
    patch_id: str
    name: str
    description: str
    firmware: str
    default: bool
    order: int
    runtime_directory: str
    files: tuple[RuntimeFile, ...]
    arm_hook: ArmHook | None
    directory: pathlib.Path


@dataclass(frozen=True)
class BuildResult:
    output: pathlib.Path
    size: int
    sha256: str
    patches: tuple[str, ...]


def repository_root() -> pathlib.Path:
    """Return source resources or the resources embedded by PyInstaller."""
    try:
        import sys

        bundle = pathlib.Path(sys._MEIPASS)  # type: ignore[attr-defined]
    except AttributeError:
        return pathlib.Path(__file__).resolve().parents[2]
    return bundle / "resources"


def discover_patches(root: pathlib.Path | None = None, firmware: str | None = None) -> list[PatchDefinition]:
    """Discover and validate versioned runtime manifests."""
    root = pathlib.Path(root or repository_root())
    patches = []
    seen = set()
    runtime_directories = set()
    for manifest_path in sorted((root / "runtime/modules").glob("**/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {"id", "name", "description", "firmware", "runtime_directory", "files"}
        missing = required.difference(data)
        if missing:
            raise ValueError(f"{manifest_path}: missing {', '.join(sorted(missing))}")
        if manifest_path.parent.name != data["firmware"]:
            raise ValueError(f"{manifest_path}: directory and firmware version differ")
        if firmware is not None and data["firmware"] != firmware:
            continue
        identity = (data["firmware"], data["id"])
        if identity in seen:
            raise ValueError(f"duplicate patch id {data['id']!r} for firmware {data['firmware']}")
        seen.add(identity)
        runtime_identity = (data["firmware"], data["runtime_directory"])
        runtime_path = pathlib.PurePosixPath(data["runtime_directory"])
        if runtime_path.is_absolute() or len(runtime_path.parts) != 1 or ".." in runtime_path.parts:
            raise ValueError(f"{manifest_path}: unsafe runtime directory")
        if runtime_identity in runtime_directories:
            raise ValueError(f"duplicate runtime directory {data['runtime_directory']!r}")
        runtime_directories.add(runtime_identity)
        files = tuple(
            RuntimeFile(item["source"], item["target"], bool(item.get("executable", False)))
            for item in data["files"]
        )
        hook_data = data.get("arm_hook")
        hook = ArmHook(hook_data["source"], hook_data["target"]) if hook_data else None
        patch = PatchDefinition(
            patch_id=data["id"],
            name=data["name"],
            description=data["description"],
            firmware=data["firmware"],
            default=bool(data.get("default", False)),
            order=int(data.get("order", 100)),
            runtime_directory=data["runtime_directory"],
            files=files,
            arm_hook=hook,
            directory=manifest_path.parent,
        )
        _validate_patch_files(patch)
        patches.append(patch)
    return sorted(patches, key=lambda patch: (patch.firmware, patch.order, patch.name.lower()))


def _validate_patch_files(patch: PatchDefinition) -> None:
    for runtime_file in patch.files:
        if not (patch.directory / runtime_file.source).is_file():
            raise ValueError(f"{patch.patch_id}: missing {runtime_file.source}")
        if pathlib.PurePosixPath(runtime_file.target).is_absolute() or ".." in pathlib.PurePosixPath(runtime_file.target).parts:
            raise ValueError(f"{patch.patch_id}: unsafe target {runtime_file.target!r}")
    if patch.arm_hook and not (patch.directory / patch.arm_hook.source).is_file():
        raise ValueError(f"{patch.patch_id}: missing {patch.arm_hook.source}")


def available_versions(root: pathlib.Path | None = None) -> list[str]:
    return sorted({patch.firmware for patch in discover_patches(root)})


def validate_arm_hook(path: pathlib.Path) -> None:
    """Validate the architecture and EABI marker without a host `file` tool."""
    header = path.read_bytes()[:52]
    if len(header) < 52 or header[:4] != b"\x7fELF":
        raise ValueError(f"{path}: compiled hook is not an ELF file")
    if header[4:6] != b"\x01\x01":
        raise ValueError(f"{path}: hook must be 32-bit little-endian ELF")
    machine = struct.unpack_from("<H", header, 18)[0]
    flags = struct.unpack_from("<I", header, 36)[0]
    if machine != 40 or (flags & 0xFF000000) != 0x05000000:
        raise ValueError(f"{path}: hook must target ARM EABI5")


def compile_arm_hook(source: pathlib.Path, output: pathlib.Path, compiler: str | None = None) -> None:
    compiler = compiler or os.environ.get("CC") or shutil.which("clang")
    if not compiler:
        raise ValueError("Clang is required to compile the stems hook from source")
    command = [
        compiler,
        "--target=arm-linux-gnueabi",
        "-march=armv7-a",
        "-marm",
        "-mfloat-abi=softfp",
        "-mfpu=neon",
        "-fPIC",
        "-fno-stack-protector",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fuse-ld=lld",
        "-shared",
        "-nostdlib",
        "-Wl,--hash-style=sysv",
        "-Wl,--build-id=none",
        "-o",
        str(output),
        str(source),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error)).strip()
        raise ValueError(
            "The stems component could not be compiled. Install Clang and LLD, "
            f"or use a packaged desktop release.\n\n{detail}"
        ) from error
    validate_arm_hook(output)


def _load_firmware_module(root: pathlib.Path):
    path = root / "tools/rx3_firmware/firmware_image.py"
    spec = importlib.util.spec_from_file_location("rx3_firmware_image", path)
    if not spec or not spec.loader:
        raise ValueError(f"cannot load firmware codec from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_runtime(
    firmware: str,
    patch_ids: Iterable[str],
    key_path: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    root: pathlib.Path | None = None,
    prebuilt_hook: pathlib.Path | None = None,
    progress: ProgressCallback | None = None,
) -> BuildResult:
    """Build an atomic `autoexec.bin` from selected versioned modules."""
    root = pathlib.Path(root or repository_root())
    key_path = pathlib.Path(key_path)
    output_directory = pathlib.Path(output_directory)
    notify = progress or (lambda _message: None)

    if not key_path.is_file():
        raise ValueError("Select an existing RX3 key file")
    if not output_directory.is_dir():
        raise ValueError("Select an existing output folder or mounted USB drive")

    firmware_module = _load_firmware_module(root)
    firmware_module.load_key(key_path)
    definitions = discover_patches(root, firmware)
    by_id = {patch.patch_id: patch for patch in definitions}
    selected_ids = list(dict.fromkeys(patch_ids))
    unknown = sorted(set(selected_ids).difference(by_id))
    if unknown:
        raise ValueError(f"unknown patch selection: {', '.join(unknown)}")
    if not selected_ids:
        raise ValueError("Select at least one patch")
    selected = [patch for patch in definitions if patch.patch_id in selected_ids]

    compatibility = root / f"runtime/{firmware}/compatibility.sh"
    if not compatibility.is_file():
        raise ValueError(f"firmware {firmware} has no runtime compatibility definition")

    notify("Preparing selected modules…")
    with tempfile.TemporaryDirectory(prefix="rx3-runtime-") as temporary:
        staging = pathlib.Path(temporary) / "runtime"
        modules = staging / "modules"
        modules.mkdir(parents=True)
        shutil.copy2(root / "runtime/autoexec.sh", staging / "autoexec.sh")
        compatibility_target = modules / "compatibility/module.sh"
        compatibility_target.parent.mkdir(parents=True)
        shutil.copy2(compatibility, compatibility_target)

        for patch in selected:
            destination = modules / patch.runtime_directory
            destination.mkdir(parents=True, exist_ok=True)
            for runtime_file in patch.files:
                target = destination / runtime_file.target
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(patch.directory / runtime_file.source, target)
                target.chmod(0o755 if runtime_file.executable else 0o644)
            if patch.arm_hook:
                target = destination / patch.arm_hook.target
                supplied = prebuilt_hook or root / f"prebuilt/{patch.arm_hook.target}"
                if supplied.is_file():
                    notify("Checking the bundled stems component…")
                    shutil.copy2(supplied, target)
                    validate_arm_hook(target)
                else:
                    notify("Compiling the stems component…")
                    compile_arm_hook(patch.directory / patch.arm_hook.source, target)
        (staging / "autoexec.sh").chmod(0o755)

        notify("Creating and encrypting autoexec.bin…")
        temporary_output = output_directory / f".autoexec.bin.{os.getpid()}.tmp"
        try:
            size = firmware_module.write_autoexec(staging, temporary_output, key_path)
            plain = firmware_module.read_autoexec(temporary_output, key_path)
            if firmware_module.autoexec_iso_metadata(plain) != "UsbAuto":
                raise ValueError("generated runtime has an unexpected ISO volume")
            final_output = output_directory / "autoexec.bin"
            os.replace(temporary_output, final_output)
        finally:
            temporary_output.unlink(missing_ok=True)

    digest = hashlib.sha256(final_output.read_bytes()).hexdigest()
    notify("Runtime ready.")
    return BuildResult(final_output, size, digest, tuple(patch.patch_id for patch in selected))
