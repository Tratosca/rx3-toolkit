# SPDX-License-Identifier: MPL-2.0
"""Shared build engine for the RX3 runtime CLI and desktop application."""

from __future__ import annotations

from app.localization import Message
from app.runtime.metadata import categories, category_metadata, localized

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
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence


ProgressCallback = Callable[[str], None]

# What was built, beside the thing that was built. Named like the stems job's
# own manifest, which sits in the same place for the same reason.
MANIFEST_NAME = "rx3-mod-manifest.json"


class Cancelled(Exception):
    """The operator stopped the build."""


class Cancellation:
    """A flag a caller sets and the work reads at its own safe points.

    The same shape as StemJob's, and safe here for the same reason: everything
    is staged in a temporary directory and installed in one move at the end, so
    stopping before that move leaves the drive exactly as it was. Nothing is
    signalled: the only subprocess a build runs is the cross-compiler, which is
    short, and killing a linker halfway writes a truncated object.
    """

    def __init__(self) -> None:
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    @property
    def stopped(self) -> bool:
        return self._stopped

    def checkpoint(self) -> None:
        if self._stopped:
            raise Cancelled("Cancelled")


@dataclass(frozen=True)
class RuntimeFile:
    source: str
    target: str
    executable: bool = False
    artifact: bool = False
    directory: bool = False


@dataclass(frozen=True)
class ArmHook:
    source: str
    target: str
    sources: tuple[str, ...] = ()


# Where a module sits in the app's module list, in the order the list shows
# them. It says what a DJ uses the module for and nothing about how it is built:
# the load order is `order`, not this.


@dataclass(frozen=True)
class PatchDefinition:
    patch_id: str
    name: str
    description: str
    firmwares: tuple[str, ...]
    default: bool
    selectable: bool
    order: int
    runtime_directory: str
    namespace: str
    requires: tuple[str, ...]
    conflicts: tuple[str, ...]
    profiles: tuple[str, ...]
    files: tuple[RuntimeFile, ...]
    build_files: tuple[str, ...]
    arm_hook: ArmHook | None
    directory: pathlib.Path
    category: str | None = None
    category_ui: dict | None = None
    advanced: bool = False


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


try:
    import fcntl
except ImportError:  # Windows carries neither the module nor the call.
    fcntl = None


def _flush(descriptor: int) -> None:
    """Push what has been written past the drive's own cache, where possible.

    On macOS `fsync` reaches the drive and stops: the data sits in the device
    cache, which a drive pulled out of the port does not keep. `F_FULLFSYNC` is
    the documented way to ask for the rest of the trip. It has no counterpart
    elsewhere because elsewhere `fsync` already means this.

    Every step here is best effort by design. A filesystem that refuses the
    stronger call still gets the weaker one, and a platform that offers neither
    still gets a correct file; what changes is only how long the window lasts
    in which pulling the drive loses it.
    """
    if fcntl is not None and hasattr(fcntl, "F_FULLFSYNC"):
        try:
            fcntl.fcntl(descriptor, fcntl.F_FULLFSYNC)
            return
        except OSError:
            pass
    try:
        os.fsync(descriptor)
    except OSError:
        pass


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_durably(temporary: pathlib.Path, final: pathlib.Path) -> str:
    """Rename a staged image into place and confirm it survived the trip.

    A drive is pulled, not unmounted. Everything written to it sits in the page
    cache until something forces it out, so a build that returned successfully
    can still reach the deck as a short file. The flush is the difference
    between a verified image and a verified copy of it in memory.

    The file is hashed before the rename and read back after it, because those
    answer different questions: the first says the image was built correctly,
    the second says that is what the drive now holds.

    Returns the digest as the medium reads it back.
    """
    expected = _sha256(temporary)
    with temporary.open("rb+") as handle:
        handle.flush()
        _flush(handle.fileno())
    os.replace(temporary, final)
    # A rename is a directory operation, and the directory entry has its own
    # trip to make: the file can be on the medium while the name pointing at it
    # is not. Windows has no file descriptor for a directory, so this is taken
    # where it is offered rather than required.
    try:
        descriptor = os.open(final.parent, os.O_RDONLY)
    except OSError:
        pass
    else:
        try:
            _flush(descriptor)
        finally:
            os.close(descriptor)
    written = _sha256(final)
    if written != expected:
        raise ValueError(
            f"{final.name} does not read back as it was written: "
            f"{written} is not {expected}. The drive should be rewritten before "
            f"it is used."
        )
    return written


def discover_patches(root: pathlib.Path | None = None, firmware: str | None = None) -> list[PatchDefinition]:
    """Discover and validate the modules built for one firmware version.

    A module says which versions it is built against, because that is a fact
    about the module and nothing else can be asked for it. Several versions
    share one module when the addresses it touches are the same in each: 1.19
    and 1.20 differ by three bytes of the player, none of them anywhere a module
    reads or writes, so every module carries both.
    """
    root = pathlib.Path(root or repository_root())
    patches = []
    seen = set()
    runtime_directories = set()
    category_definitions = categories(root)
    for manifest_path in sorted((root / "mod/modules").glob("**/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {
            "id", "name", "description", "firmwares", "runtime_directory",
            "namespace", "files",
        }
        missing = required.difference(data)
        if missing:
            raise ValueError(f"{manifest_path}: missing {', '.join(sorted(missing))}")
        if manifest_path.parent.name != data["id"]:
            raise ValueError(f"{manifest_path}: directory and module id differ")
        firmwares = data["firmwares"]
        if not isinstance(firmwares, list) or not firmwares:
            raise ValueError(f"{manifest_path}: firmwares must be a non-empty list")
        if firmware is not None and firmware not in firmwares:
            continue
        identity = data["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["id"]):
            raise ValueError(f"{manifest_path}: unsafe module id {data['id']!r}")
        if identity in seen:
            raise ValueError(f"duplicate patch id {data['id']!r}")
        seen.add(identity)
        runtime_identity = data["runtime_directory"]
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
            RuntimeFile(
                item["source"],
                item["target"],
                bool(item.get("executable", False)),
                bool(item.get("artifact", False)),
                bool(item.get("directory", False)),
            )
            for item in data["files"]
        )
        build_files = tuple(data.get("build_files", []))
        if not all(isinstance(item, str) for item in build_files):
            raise ValueError(f"{manifest_path}: build_files must be a list of paths")
        category = data.get("category")
        if category is not None and not isinstance(category, str):
            raise ValueError(f"{manifest_path}: category must be an identifier")
        if category is None and data.get("selectable", True):
            raise ValueError(f"{manifest_path}: selectable modules require a category")
        if category is not None and category_definitions and category not in category_definitions:
            raise ValueError(f"{manifest_path}: unknown category {category}")
        category_ui = (category_definitions.get(category) or category_metadata(category)) if category else None
        if type(data.get("advanced", False)) is not bool:
            raise ValueError(f"{manifest_path}: advanced must be a boolean")
        hook_data = data.get("arm_hook")
        hook = ArmHook(hook_data["source"], hook_data["target"], tuple(hook_data.get("sources", ()))) if hook_data else None
        profiles_directory = manifest_path.parent / "profiles"
        profiles = _discover_profiles(profiles_directory)
        if bool(data.get("profile_required", False)) != bool(profiles):
            raise ValueError(
                f"{manifest_path}: profile_required must match the profiles directory"
            )
        patch = PatchDefinition(
            patch_id=data["id"],
            name=localized(data["name"], "name")["en"] if isinstance(data["name"], dict) else data["name"],
            description=localized(data["description"], "description")["en"] if isinstance(data["description"], dict) else data["description"],
            firmwares=tuple(firmwares),
            default=bool(data.get("default", False)),
            selectable=bool(data.get("selectable", True)),
            order=int(data.get("order", 100)),
            runtime_directory=data["runtime_directory"],
            namespace=data["namespace"],
            requires=_module_ids(manifest_path, data.get("requires", []), "requires"),
            conflicts=_module_ids(manifest_path, data.get("conflicts", []), "conflicts"),
            profiles=profiles,
            files=files,
            build_files=build_files,
            arm_hook=hook,
            directory=manifest_path.parent,
            category=category,
            category_ui=category_ui,
            advanced=data.get("advanced", False),
        )
        if patch.default and not patch.selectable:
            raise ValueError(f"{patch.patch_id}: an internal module cannot be default")
        _validate_patch_files(patch)
        patches.append(patch)
    patches = sorted(patches, key=lambda patch: (patch.order, patch.name.lower()))
    _validate_module_graph(patches)
    return patches


def _discover_profiles(directory: pathlib.Path) -> tuple[str, ...]:
    if not directory.is_dir():
        return ()

    profiles = []
    for path in sorted(item for item in directory.iterdir() if item.is_dir()):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", path.name):
            raise ValueError(f"{path}: unsafe profile id")
        profile_path = path / "profile.json"
        if not profile_path.is_file():
            raise ValueError(f"{path}: missing profile.json")
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{profile_path}: profile must be an object")
        required = {"id", "name"}
        missing = required.difference(data)
        if missing:
            raise ValueError(
                f"{profile_path}: missing {', '.join(sorted(missing))}"
            )
        if data["id"] != path.name:
            raise ValueError(f"{profile_path}: id does not match its directory")
        if not isinstance(data["name"], str) or not data["name"].strip():
            raise ValueError(f"{profile_path}: name must be a non-empty string")
        profiles.append(path.name)
    return tuple(profiles)


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
        if runtime_file.directory and not runtime_file.artifact:
            raise ValueError(f"{patch.patch_id}: directory inputs must be artifacts")
        if (
            not runtime_file.artifact
            and not (patch.directory / runtime_file.source).is_file()
        ):
            raise ValueError(f"{patch.patch_id}: missing {runtime_file.source}")
        if target_path.is_absolute() or ".." in target_path.parts:
            raise ValueError(f"{patch.patch_id}: unsafe target {runtime_file.target!r}")
    if patch.arm_hook:
        for unit in patch.arm_hook.sources:
            if not isinstance(unit, str):
                raise ValueError(f"{patch.patch_id}: invalid compilation unit")
            unit_path = pathlib.PurePosixPath(unit)
            if unit_path.is_absolute() or ".." in unit_path.parts or unit_path.suffix != ".c":
                raise ValueError(f"{patch.patch_id}: unsafe compilation unit {unit!r}")
            if not (patch.directory.parent / unit).is_file():
                raise ValueError(f"{patch.patch_id}: missing compilation unit {unit}")
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
    definitions = {patch.patch_id: patch for patch in patches}
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
                f"{patch.patch_id}: unknown module(s): "
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
        key=lambda patch: (patch.order, patch.name.lower()),
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
    """Every firmware version some module is built for."""
    return sorted({
        version for patch in discover_patches(root) for version in patch.firmwares
    })


def validate_arm_hook(path: pathlib.Path) -> None:
    """Validate the architecture and EABI marker without a host `file` tool."""
    data = path.read_bytes()
    header = data[:52]
    if len(header) < 52 or header[:4] != b"\x7fELF":
        raise ValueError(f"{path}: compiled hook is not an ELF file")
    if header[4:6] != b"\x01\x01":
        raise ValueError(f"{path}: hook must be 32-bit little-endian ELF")
    machine = struct.unpack_from("<H", header, 18)[0]
    flags = struct.unpack_from("<I", header, 36)[0]
    if machine != 40 or (flags & 0xFF000000) != 0x05000000:
        raise ValueError(f"{path}: hook must target ARM EABI5")

    forbidden = {"bcmp", "__memcmp_chk"}
    imported = _undefined_elf32_symbols(data)
    rejected = sorted(imported & forbidden)
    if rejected:
        names = ", ".join(rejected)
        raise ValueError(f"{path}: hook imports unavailable symbol(s): {names}")


def _undefined_elf32_symbols(data: bytes) -> set[str]:
    """Return undefined dynamic symbols from a little-endian ELF32 image."""
    section_offset, = struct.unpack_from("<I", data, 0x20)
    section_size, section_count = struct.unpack_from("<HH", data, 0x2E)

    def section(index: int) -> tuple[int, int, int, int, int]:
        base = section_offset + index * section_size
        section_type, = struct.unpack_from("<I", data, base + 4)
        offset, size, link = struct.unpack_from("<III", data, base + 0x10)
        entry_size, = struct.unpack_from("<I", data, base + 0x24)
        return section_type, offset, size, link, entry_size

    names: set[str] = set()
    for index in range(section_count):
        section_type, offset, size, link, entry_size = section(index)
        if section_type != 11 or not entry_size:  # SHT_DYNSYM
            continue
        _, strings_offset, _, _, _ = section(link)
        for entry in range(size // entry_size):
            base = offset + entry * entry_size
            name_offset, _, _, _, _, defined = struct.unpack_from(
                "<IIIBBH", data, base
            )
            if defined != 0 or not name_offset:  # SHN_UNDEF only
                continue
            start = strings_offset + name_offset
            end = data.index(b"\0", start)
            names.add(data[start:end].decode("ascii"))
    return names


def compile_arm_hook(source: pathlib.Path, output: pathlib.Path, compiler: str | None = None,
                     sources: tuple[pathlib.Path, ...] = ()) -> None:
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
        "-fno-builtin-memcmp",
        "-fno-builtin-bcmp",
        "-fvisibility=hidden",
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
        *(str(unit) for unit in sources),
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
    path = root / "app/firmware/firmware_image.py"
    spec = importlib.util.spec_from_file_location("rx3_firmware_image", path)
    if not spec or not spec.loader:
        raise ValueError(f"cannot load firmware codec from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_manifest(
    drive: pathlib.Path,
    firmware: str,
    modules: Sequence[str],
    size: int,
    digest: str,
) -> pathlib.Path:
    """Record what was written, beside what was written.

    Without this, answering "what does this drive carry" means decrypting
    autoexec.bin, which needs the operator's key and tells them nothing they
    could have read off the drive. The stems job has kept its own manifest for
    the same reason.

    The digest is the one install_durably read back off the medium, so a file
    that was truncated on the way out does not match its own record.
    """
    manifest = pathlib.Path(drive) / MANIFEST_NAME
    manifest.write_text(json.dumps({
        "format": 1,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "firmware": firmware,
        "modules": list(modules),
        "bytes": size,
        "sha256": digest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _validate_supplied_files(
    supplied: Mapping[str, Mapping[str, bytes]] | None,
    selected: Sequence[PatchDefinition],
) -> Mapping[str, Mapping[str, bytes]]:
    """Refuse anything that would land somewhere the module does not read.

    A name with a separator in it, or one that shadows a file the manifest
    already ships, is a silent substitution rather than an addition. The module
    would still work and would not be carrying what it appears to carry.
    """
    if not supplied:
        return {}
    by_id = {patch.patch_id: patch for patch in selected}
    for patch_id, files in supplied.items():
        patch = by_id.get(patch_id)
        if patch is None:
            raise ValueError(f"files supplied for a module that is not selected: {patch_id}")
        declared = {runtime_file.target for runtime_file in patch.files}
        if patch.arm_hook:
            declared.add(patch.arm_hook.target)
        for name in files:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
                raise ValueError(f"supplied file name is not a plain name: {name}")
            if name in declared:
                raise ValueError(
                    f"{patch_id} already ships {name}; supplying it would replace it silently"
                )
    return supplied


def runtime_file_source(
    root: pathlib.Path,
    firmware: str,
    patch: PatchDefinition,
    runtime_file: RuntimeFile,
    artifact_directory: pathlib.Path | None = None,
    profile: str | None = None,
) -> pathlib.Path:
    if not runtime_file.artifact:
        return patch.directory / runtime_file.source

    base = pathlib.Path(artifact_directory or root / "build/artifacts")
    base = base / firmware / patch.patch_id
    if patch.profiles:
        if profile not in patch.profiles:
            choices = ", ".join(patch.profiles)
            raise ValueError(
                f"{patch.patch_id}: select a hardware profile ({choices})"
            )
        base = base / profile
    source = base / runtime_file.source
    expected = source.is_dir() if runtime_file.directory else source.is_file()
    if not expected:
        raise ValueError(
            f"{patch.patch_id}: missing generated artifact {runtime_file.source}. "
            f"Build it into {source} before packaging"
        )
    return source


def build_runtime(
    firmware: str,
    patch_ids: Iterable[str],
    key_path: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    root: pathlib.Path | None = None,
    prebuilt_hook: pathlib.Path | None = None,
    supplied_files: Mapping[str, Mapping[str, bytes]] | None = None,
    cancellation: Cancellation | None = None,
    artifact_directory: pathlib.Path | None = None,
    profiles: Mapping[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> BuildResult:
    """Build an atomic `autoexec.bin` from selected versioned modules.

    `supplied_files` carries what an operator brings rather than what the source
    tree ships: a logo they chose, keyed by module id and then by the name the
    module reads. A module cannot declare these in its manifest because they do
    not exist until the operator picks them.
    """
    root = pathlib.Path(root or repository_root())
    key_path = pathlib.Path(key_path)
    output_directory = pathlib.Path(output_directory)
    notify = progress or (lambda _message: None)
    stop = cancellation or Cancellation()

    if not key_path.is_file():
        raise ValueError("Select an existing RX3 key file")
    if not output_directory.is_dir():
        raise ValueError("Select an existing output folder or mounted USB drive")

    firmware_module = _load_firmware_module(root)
    firmware_module.load_key(key_path)
    definitions = discover_patches(root, firmware)
    if not definitions:
        known = ", ".join(available_versions(root)) or "no firmware"
        raise ValueError(
            f"no module is built for firmware {firmware}; this tree knows {known}"
        )
    selected = resolve_patches(definitions, patch_ids)
    by_module = _validate_supplied_files(supplied_files, selected)
    profiles = dict(profiles or {})
    selected_ids = {patch.patch_id for patch in selected}
    unknown_profiles = sorted(set(profiles).difference(selected_ids))
    if unknown_profiles:
        raise ValueError(
            "profile supplied for an unselected module: " + ", ".join(unknown_profiles)
        )
    for patch in selected:
        if patch.profiles and patch.patch_id not in profiles:
            choices = ", ".join(patch.profiles)
            raise ValueError(
                f"{patch.patch_id}: select a hardware profile ({choices})"
            )
        if patch.patch_id in profiles and profiles[patch.patch_id] not in patch.profiles:
            choices = ", ".join(patch.profiles)
            raise ValueError(
                f"{patch.patch_id}: unknown profile {profiles[patch.patch_id]!r}; "
                f"choose one of: {choices}"
            )

    compatibility = root / "mod/compatibility.sh"
    if not compatibility.is_file():
        raise ValueError("mod/compatibility.sh is missing")

    notify(Message("job.modules"))
    with tempfile.TemporaryDirectory(prefix="rx3-runtime-") as temporary:
        staging = pathlib.Path(temporary) / "runtime"
        modules = staging / "modules"
        modules.mkdir(parents=True)
        shutil.copy2(root / "mod/autoexec.sh", staging / "autoexec.sh")
        library = staging / "lib"
        library.mkdir()
        shutil.copy2(root / "mod/lib/module-api.sh", library / "module-api.sh")
        shutil.copy2(root / "mod/lib/safe-mode.sh", library / "safe-mode.sh")
        compatibility_target = modules / "compatibility/module.sh"
        compatibility_target.parent.mkdir(parents=True)
        shutil.copy2(compatibility, compatibility_target)

        for patch in selected:
            stop.checkpoint()
            destination = modules / patch.runtime_directory
            destination.mkdir(parents=True, exist_ok=True)
            for runtime_file in patch.files:
                written = destination / runtime_file.target
                written.parent.mkdir(parents=True, exist_ok=True)
                source = runtime_file_source(
                    root,
                    firmware,
                    patch,
                    runtime_file,
                    artifact_directory,
                    profiles.get(patch.patch_id),
                )
                if runtime_file.directory:
                    shutil.copytree(source, written, dirs_exist_ok=True)
                else:
                    shutil.copy2(source, written)
                    written.chmod(0o755 if runtime_file.executable else 0o644)
            for name, content in by_module.get(patch.patch_id, {}).items():
                (destination / name).write_bytes(content)
                (destination / name).chmod(0o644)
            if patch.arm_hook:
                hook_path = destination / patch.arm_hook.target
                supplied = prebuilt_hook or root / f"prebuilt/{patch.arm_hook.target}"
                if supplied.is_file():
                    notify(Message("job.armCheck"))
                    shutil.copy2(supplied, hook_path)
                    validate_arm_hook(hook_path)
                else:
                    notify(Message("job.compile"))
                    compile_arm_hook(patch.directory / patch.arm_hook.source, hook_path,
                                     sources=tuple(patch.directory.parent / unit
                                                   for unit in patch.arm_hook.sources))
        module_index = ["compatibility"] + [patch.runtime_directory for patch in selected]
        # newline="" keeps Python from translating these \n to os.linesep. The
        # index is read by /bin/sh on the player, where a trailing CR is part of
        # the directory name and fails the module-name check on every line.
        (modules / "index").write_text(
            "".join(f"{item}\n" for item in module_index), encoding="ascii", newline="",
        )
        (staging / "autoexec.sh").chmod(0o755)

        # The last point where stopping costs nothing: past here the image is
        # written, and install_durably is one move that either happens or does
        # not.
        stop.checkpoint()
        notify(Message("job.encrypt"))
        temporary_output = output_directory / f".autoexec.bin.{os.getpid()}.tmp"
        try:
            size = firmware_module.write_autoexec(staging, temporary_output, key_path)
            plain = firmware_module.read_autoexec(temporary_output, key_path)
            if firmware_module.autoexec_iso_metadata(plain) != "UsbAuto":
                raise ValueError("generated runtime has an unexpected ISO volume")
            final_output = output_directory / "autoexec.bin"
            notify(Message("job.write"))
            digest = install_durably(temporary_output, final_output)
        finally:
            temporary_output.unlink(missing_ok=True)

    installed = tuple(patch.patch_id for patch in selected)
    write_manifest(output_directory, firmware, installed, size, digest)
    notify(Message("job.done"))
    return BuildResult(final_output, size, digest, installed)
