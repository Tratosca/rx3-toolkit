# SPDX-License-Identifier: MPL-2.0
"""Shared build engine for the RX3 runtime CLI and desktop application."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import re
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
    selectable: bool
    order: int
    runtime_directory: str
    namespace: str
    requires: tuple[str, ...]
    conflicts: tuple[str, ...]
    files: tuple[RuntimeFile, ...]
    build_files: tuple[str, ...]
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
    for manifest_path in sorted((root / "mod/modules").glob("**/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {
            "id", "name", "description", "firmware", "runtime_directory",
            "namespace", "files",
        }
        missing = required.difference(data)
        if missing:
            raise ValueError(f"{manifest_path}: missing {', '.join(sorted(missing))}")
        if manifest_path.parent.name != data["firmware"]:
            raise ValueError(f"{manifest_path}: directory and firmware version differ")
        if firmware is not None and data["firmware"] != firmware:
            continue
        identity = (data["firmware"], data["id"])
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["id"]):
            raise ValueError(f"{manifest_path}: unsafe module id {data['id']!r}")
        if identity in seen:
            raise ValueError(f"duplicate patch id {data['id']!r} for firmware {data['firmware']}")
        seen.add(identity)
        runtime_identity = (data["firmware"], data["runtime_directory"])
        runtime_path = pathlib.PurePosixPath(data["runtime_directory"])
        if (
            runtime_path.is_absolute()
            or len(runtime_path.parts) != 1
            or ".." in runtime_path.parts
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["runtime_directory"])
        ):
            raise ValueError(f"{manifest_path}: unsafe runtime directory")
        if runtime_identity in runtime_directories:
            raise ValueError(f"duplicate runtime directory {data['runtime_directory']!r}")
        runtime_directories.add(runtime_identity)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", data["namespace"]):
            raise ValueError(f"{manifest_path}: unsafe shell namespace")
        files = tuple(
            RuntimeFile(item["source"], item["target"], bool(item.get("executable", False)))
            for item in data["files"]
        )
        build_files = tuple(data.get("build_files", []))
        if not all(isinstance(item, str) for item in build_files):
            raise ValueError(f"{manifest_path}: build_files must be a list of paths")
        hook_data = data.get("arm_hook")
        hook = ArmHook(hook_data["source"], hook_data["target"]) if hook_data else None
        patch = PatchDefinition(
            patch_id=data["id"],
            name=data["name"],
            description=data["description"],
            firmware=data["firmware"],
            default=bool(data.get("default", False)),
            selectable=bool(data.get("selectable", True)),
            order=int(data.get("order", 100)),
            runtime_directory=data["runtime_directory"],
            namespace=data["namespace"],
            requires=_module_ids(manifest_path, data.get("requires", []), "requires"),
            conflicts=_module_ids(manifest_path, data.get("conflicts", []), "conflicts"),
            files=files,
            build_files=build_files,
            arm_hook=hook,
            directory=manifest_path.parent,
        )
        if patch.default and not patch.selectable:
            raise ValueError(f"{patch.patch_id}: an internal module cannot be default")
        _validate_patch_files(patch)
        patches.append(patch)
    patches = sorted(patches, key=lambda patch: (patch.firmware, patch.order, patch.name.lower()))
    _validate_module_graph(patches)
    return patches


def _module_ids(manifest_path: pathlib.Path, value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{manifest_path}: {field} must be a list of module ids")
    identifiers = tuple(dict.fromkeys(value))
    if len(identifiers) != len(value):
        raise ValueError(f"{manifest_path}: duplicate module id in {field}")
    for identifier in identifiers:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identifier):
            raise ValueError(f"{manifest_path}: unsafe module id {identifier!r} in {field}")
    return identifiers


def _validate_patch_files(patch: PatchDefinition) -> None:
    for build_file in patch.build_files:
        build_path = pathlib.PurePosixPath(build_file)
        if build_path.is_absolute() or ".." in build_path.parts:
            raise ValueError(f"{patch.patch_id}: unsafe build file {build_file!r}")
        if not (patch.directory / build_file).is_file():
            raise ValueError(f"{patch.patch_id}: missing build file {build_file}")
    for runtime_file in patch.files:
        source_path = pathlib.PurePosixPath(runtime_file.source)
        target_path = pathlib.PurePosixPath(runtime_file.target)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise ValueError(f"{patch.patch_id}: unsafe source {runtime_file.source!r}")
        if not (patch.directory / runtime_file.source).is_file():
            raise ValueError(f"{patch.patch_id}: missing {runtime_file.source}")
        if target_path.is_absolute() or ".." in target_path.parts:
            raise ValueError(f"{patch.patch_id}: unsafe target {runtime_file.target!r}")
    if patch.arm_hook:
        source_path = pathlib.PurePosixPath(patch.arm_hook.source)
        target_path = pathlib.PurePosixPath(patch.arm_hook.target)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise ValueError(f"{patch.patch_id}: unsafe hook source {patch.arm_hook.source!r}")
        if target_path.is_absolute() or ".." in target_path.parts:
            raise ValueError(f"{patch.patch_id}: unsafe hook target {patch.arm_hook.target!r}")
        if not (patch.directory / patch.arm_hook.source).is_file():
            raise ValueError(f"{patch.patch_id}: missing {patch.arm_hook.source}")
    module_scripts = [item for item in patch.files if item.target == "module.sh"]
    if len(module_scripts) != 1:
        raise ValueError(f"{patch.patch_id}: exactly one module.sh contract is required")
    module_text = (patch.directory / module_scripts[0].source).read_text(encoding="utf-8")
    declaration = re.compile(
        rf"^module_begin[ \t]+{re.escape(patch.patch_id)}[ \t]+"
        rf"{re.escape(patch.namespace)}[ \t]*$",
        re.MULTILINE,
    )
    if not declaration.search(module_text):
        raise ValueError(
            f"{patch.patch_id}: module.sh must declare "
            f"module_begin {patch.patch_id} {patch.namespace}"
        )


def _validate_module_graph(patches: list[PatchDefinition]) -> None:
    """Reject invalid dependency graphs while the manifest path is still known."""
    by_firmware: dict[str, dict[str, PatchDefinition]] = {}
    for patch in patches:
        by_firmware.setdefault(patch.firmware, {})[patch.patch_id] = patch
    for firmware, definitions in by_firmware.items():
        namespaces: dict[str, str] = {}
        for patch in definitions.values():
            previous = namespaces.get(patch.namespace)
            if previous:
                raise ValueError(
                    f"{patch.patch_id}: shell namespace also belongs to {previous}"
                )
            namespaces[patch.namespace] = patch.patch_id
            if patch.patch_id in patch.requires:
                raise ValueError(f"{patch.patch_id}: a module cannot require itself")
            if patch.patch_id in patch.conflicts:
                raise ValueError(f"{patch.patch_id}: a module cannot conflict with itself")
            unknown = sorted(set(patch.requires + patch.conflicts).difference(definitions))
            if unknown:
                raise ValueError(
                    f"{patch.patch_id}: unknown firmware {firmware} module(s): "
                    f"{', '.join(unknown)}"
                )
            contradictory = sorted(set(patch.requires).intersection(patch.conflicts))
            if contradictory:
                raise ValueError(
                    f"{patch.patch_id}: both requires and conflicts with "
                    f"{', '.join(contradictory)}"
                )
            for required in patch.requires:
                if definitions[required].order >= patch.order:
                    raise ValueError(
                        f"{patch.patch_id}: dependency {required} must have a lower order"
                    )

        visiting: list[str] = []
        visited: set[str] = set()

        def visit(identifier: str) -> None:
            if identifier in visiting:
                cycle = visiting[visiting.index(identifier):] + [identifier]
                raise ValueError(f"module dependency cycle: {' -> '.join(cycle)}")
            if identifier in visited:
                return
            visiting.append(identifier)
            for required in definitions[identifier].requires:
                visit(required)
            visiting.pop()
            visited.add(identifier)

        for identifier in definitions:
            visit(identifier)


def resolve_patches(
    definitions: Iterable[PatchDefinition], patch_ids: Iterable[str]
) -> list[PatchDefinition]:
    """Resolve a selection to a stable, dependency-first module load order."""
    definitions = sorted(
        definitions,
        key=lambda patch: (patch.firmware, patch.order, patch.name.lower()),
    )
    by_id = {patch.patch_id: patch for patch in definitions}
    if len(by_id) != len(definitions):
        raise ValueError("duplicate module id in resolver input")
    requested = list(dict.fromkeys(patch_ids))
    unknown = sorted(set(requested).difference(by_id))
    if unknown:
        raise ValueError(f"unknown patch selection: {', '.join(unknown)}")
    if not requested:
        raise ValueError("Select at least one patch")
    internal = sorted(identifier for identifier in requested if not by_id[identifier].selectable)
    if internal:
        raise ValueError(
            f"internal module cannot be selected directly: {', '.join(internal)}"
        )

    selected: set[str] = set()
    resolving: list[str] = []

    def include(identifier: str) -> None:
        if identifier in selected:
            return
        if identifier in resolving:
            cycle = resolving[resolving.index(identifier):] + [identifier]
            raise ValueError(f"module dependency cycle: {' -> '.join(cycle)}")
        resolving.append(identifier)
        for required in by_id[identifier].requires:
            include(required)
        resolving.pop()
        selected.add(identifier)

    for identifier in requested:
        include(identifier)

    conflicts = []
    for identifier in sorted(selected):
        for conflicting in by_id[identifier].conflicts:
            if conflicting in selected:
                conflicts.append(tuple(sorted((identifier, conflicting))))
    if conflicts:
        left, right = sorted(set(conflicts))[0]
        raise ValueError(f"incompatible modules selected: {left}, {right}")

    # discover_patches already validates acyclicity. Filtering its stable order
    # is dependency-first because every dependency must have a lower order; the
    # explicit assertion prevents a future manifest from quietly violating it.
    ordered = [patch for patch in definitions if patch.patch_id in selected]
    emitted: set[str] = set()
    for patch in ordered:
        missing = set(patch.requires).difference(emitted)
        if missing:
            raise ValueError(
                f"{patch.patch_id}: dependencies must have a lower manifest order: "
                f"{', '.join(sorted(missing))}"
            )
        emitted.add(patch.patch_id)
    return ordered


def required_closure(
    definitions: Iterable[PatchDefinition], patch_ids: Iterable[str]
) -> set[str]:
    """Every module the given selection pulls in, transitively, plus itself.

    `resolve_patches` answers the same question but refuses an internal module
    and an empty selection, because it guards a build. A checkbox being ticked
    is not a build, so the interface needs the bare graph.
    """
    by_id = {patch.patch_id: patch for patch in definitions}
    closure: set[str] = set()
    pending = [identifier for identifier in patch_ids if identifier in by_id]
    while pending:
        identifier = pending.pop()
        if identifier in closure:
            continue
        closure.add(identifier)
        pending.extend(by_id[identifier].requires)
    return closure


def dependent_closure(
    definitions: Iterable[PatchDefinition], patch_ids: Iterable[str]
) -> set[str]:
    """Every module that would be left with a missing dependency, plus itself."""
    definitions = list(definitions)
    by_id = {patch.patch_id: patch for patch in definitions}
    closure: set[str] = set()
    pending = [identifier for identifier in patch_ids if identifier in by_id]
    while pending:
        identifier = pending.pop()
        if identifier in closure:
            continue
        closure.add(identifier)
        pending.extend(
            patch.patch_id for patch in definitions if identifier in patch.requires
        )
    return closure


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
        raise ValueError("Clang is required to compile the performance core from source")
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
            "The performance core could not be compiled. Install Clang and LLD, "
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
    selected = resolve_patches(definitions, patch_ids)

    compatibility = root / f"mod/{firmware}/compatibility.sh"
    if not compatibility.is_file():
        raise ValueError(f"firmware {firmware} has no runtime compatibility definition")

    notify("Preparing selected modules…")
    with tempfile.TemporaryDirectory(prefix="rx3-runtime-") as temporary:
        staging = pathlib.Path(temporary) / "runtime"
        modules = staging / "modules"
        modules.mkdir(parents=True)
        shutil.copy2(root / "mod/autoexec.sh", staging / "autoexec.sh")
        library = staging / "lib"
        library.mkdir()
        shutil.copy2(root / "mod/lib/module-api.sh", library / "module-api.sh")
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
                    notify("Checking the bundled ARM component…")
                    shutil.copy2(supplied, target)
                    validate_arm_hook(target)
                else:
                    notify("Compiling the performance core…")
                    compile_arm_hook(patch.directory / patch.arm_hook.source, target)
        module_index = ["compatibility"] + [patch.runtime_directory for patch in selected]
        # newline="" keeps Python from translating these \n to os.linesep. The
        # index is read by /bin/sh on the player, where a trailing CR is part of
        # the directory name and fails the module-name check on every line.
        (modules / "index").write_text(
            "".join(f"{item}\n" for item in module_index), encoding="ascii", newline="",
        )
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
