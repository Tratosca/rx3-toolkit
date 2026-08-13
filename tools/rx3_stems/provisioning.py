# SPDX-License-Identifier: MPL-2.0
"""Locate or provision the separation runtime used by RX3 Stem Studio.

The desktop application is a few megabytes; audio-separator, PyTorch, and
FFmpeg are two orders of magnitude larger and cannot be shipped inside a
release archive. They live in a managed virtual environment under the user
data directory instead, created on request and reused afterwards. An existing
installation on `PATH` is preferred over the managed copy.

audio-separator picks its own inference device at run time, in this order:
CUDA, then Apple Silicon MPS, then DirectML when explicitly enabled, then the
CPU. What the accelerator selection controls here is therefore which packages
are installed — a CPU-only PyTorch cannot be accelerated later — and whether
DirectML is requested on the command line.
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Sequence


ProgressCallback = Callable[[str], None]

APPLICATION_NAME = "RX3 Stem Studio"
SEPARATOR_COMMAND = "audio-separator"
# audio-separator still calls librosa.get_duration(filename=...) and imports
# audioread, both removed in librosa 1.0, so the managed environment pins the
# last release that provides them.
LIBROSA_PIN = "librosa<1.0"
# imageio-ffmpeg ships a static FFmpeg for every platform this project releases
# on, which avoids maintaining a per-platform download and checksum matrix.
SUPPORT_PACKAGES = (LIBROSA_PIN, "imageio-ffmpeg")
MINIMUM_PYTHON = (3, 10)
# audio-separator pins beartype below 0.19, whose newest declared interpreter is
# 3.13. On 3.14 it rejects the separator's own annotations, so an interpreter
# beyond this is refused up front rather than after a multi-gigabyte download.
MAXIMUM_PYTHON = (3, 13)

CPU_WHEEL_INDEX = "https://download.pytorch.org/whl/cpu"
ROCM_WHEEL_INDEX = "https://download.pytorch.org/whl/rocm6.4"
# PyPI publishes a CPU-only PyTorch for Windows, so a CUDA build has to come
# from an explicit index or `torch.cuda.is_available()` is simply False there.
# CUDA 13 covers Blackwell and later but dropped everything before Turing, so
# the older cards keep the 12.6 build; both indexes carry the same release for
# Windows and Linux. Compute capability 7.5 is Turing.
CUDA_WHEEL_INDEX = "https://download.pytorch.org/whl/cu130"
LEGACY_CUDA_WHEEL_INDEX = "https://download.pytorch.org/whl/cu126"
LEGACY_CUDA_CAPABILITY = (7, 5)
# Filters the sidecar encoder and the separator rely on. A build configured
# without one of them fails partway through a job rather than at startup.
REQUIRED_FILTERS = ("aformat", "apad", "aresample", "astats", "atrim", "volume")


class ProvisioningError(RuntimeError):
    """The separation runtime could not be installed."""


@dataclass(frozen=True)
class Acceleration:
    """How the managed environment is built, and what it needs at run time."""

    key: str
    label: str
    detail: str
    extra: str
    torch_index: str | None
    separation_flags: tuple[str, ...] = ()
    # Which of the two inference runtimes this build actually gets its work
    # done on the GPU with. Not derivable from `extra`, and not answered by
    # asking ONNX Runtime what providers it has: a provider it lists can still
    # leave the work on the CPU. These record the measured outcome instead.
    accelerates_torch: bool = True
    accelerates_onnx: bool = True

    @property
    def requirement(self) -> str:
        return f"audio-separator[{self.extra}]"

    @property
    def prefers_torch(self) -> bool:
        """Whether an ONNX model should be run through PyTorch on this build.

        True where the GPU covers PyTorch and not ONNX Runtime, which is where
        the ONNX runtime would leave the work on the CPU. Where neither is
        accelerated there is nothing to move the work to, so ONNX Runtime -
        which is the quicker of the two on a CPU - is kept.
        """
        return self.accelerates_torch and not self.accelerates_onnx


AUTOMATIC = "auto"
ACCELERATIONS: dict[str, Acceleration] = {
    "cuda": Acceleration(
        "cuda", "NVIDIA CUDA",
        "PyTorch and ONNX Runtime builds for NVIDIA GPUs.",
        "gpu", CUDA_WHEEL_INDEX,
    ),
    "rocm": Acceleration(
        "rocm", "AMD ROCm",
        "PyTorch built for AMD GPUs on Linux. ONNX models still run on the CPU.",
        "cpu", ROCM_WHEEL_INDEX, accelerates_onnx=False,
    ),
    "directml": Acceleration(
        "directml", "DirectML",
        "Experimental acceleration for AMD and Intel GPUs on Windows. "
        "Only ONNX models reach the GPU; PyTorch ones run on the CPU.",
        "dml", CPU_WHEEL_INDEX, ("--use_directml",), accelerates_torch=False,
    ),
    # ONNX Runtime does offer CoreML here, and audio-separator does enable it,
    # but CoreML cannot take the graph whole: on an MDX-Net model it claims 151
    # of 178 nodes and splits them across 28 partitions, so the run spends its
    # time handing tensors back and forth with the CPU. Measured on an M-series
    # Mac, the same model was 3.5x quicker converted to Torch and run on Metal,
    # which is why this build is not treated as accelerating ONNX.
    "mps": Acceleration(
        "mps", "Apple Silicon (Metal)",
        "Metal Performance Shaders on ARM Macs, selected automatically. "
        "ONNX models are run through PyTorch rather than CoreML.",
        "cpu", None, accelerates_onnx=False,
    ),
    "cpu": Acceleration(
        "cpu", "CPU only",
        "No GPU acceleration. Works everywhere and is the slowest option.",
        "cpu", CPU_WHEEL_INDEX,
        accelerates_torch=False, accelerates_onnx=False,
    ),
}


def _has_nvidia_gpu() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    probe = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
    return probe.returncode == 0 and "GPU" in probe.stdout


def _nvidia_compute_capability() -> tuple[int, int] | None:
    """The highest compute capability `nvidia-smi` reports, if it answers."""
    if not shutil.which("nvidia-smi"):
        return None
    probe = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True, text=True,
    )
    if probe.returncode:
        return None
    capabilities = []
    for line in probe.stdout.splitlines():
        major, _, minor = line.strip().partition(".")
        if major.isdigit() and minor.isdigit():
            capabilities.append((int(major), int(minor)))
    return max(capabilities) if capabilities else None


def _has_rocm() -> bool:
    return bool(shutil.which("rocminfo")) or pathlib.Path("/opt/rocm").is_dir()


def detect_acceleration() -> str:
    """Resolve the accelerator to use when the operator has not chosen one."""
    if sys.platform == "darwin":
        # Upstream gates MPS on an ARM processor, so Intel Macs stay on the CPU
        # whatever GPU they carry.
        return "mps" if platform.machine() in ("arm64", "aarch64") else "cpu"
    if _has_nvidia_gpu():
        return "cuda"
    if sys.platform == "win32":
        return "directml"
    if _has_rocm():
        return "rocm"
    return "cpu"


def resolve_acceleration(key: str = AUTOMATIC) -> Acceleration:
    """Return the acceleration profile for a stored setting."""
    if key == AUTOMATIC or key not in ACCELERATIONS:
        key = detect_acceleration()
    acceleration = ACCELERATIONS[key]
    if acceleration.key == "cuda":
        capability = _nvidia_compute_capability()
        if capability is not None and capability < LEGACY_CUDA_CAPABILITY:
            return replace(acceleration, torch_index=LEGACY_CUDA_WHEEL_INDEX)
        return acceleration
    if acceleration.torch_index == CPU_WHEEL_INDEX and sys.platform == "darwin":
        # macOS wheels are published on PyPI only, and carry Metal support.
        return replace(acceleration, torch_index=None)
    return acceleration


def available_accelerations() -> tuple[tuple[str, str], ...]:
    """Selectable accelerators for this platform, as (key, label) pairs."""
    keys = ["cpu"]
    if sys.platform == "darwin":
        if platform.machine() in ("arm64", "aarch64"):
            keys.insert(0, "mps")
    else:
        keys.insert(0, "cuda")
        if sys.platform == "win32":
            keys.insert(1, "directml")
        else:
            keys.insert(1, "rocm")
    detected = ACCELERATIONS[detect_acceleration()].label
    return ((AUTOMATIC, f"Automatic ({detected})"),) + tuple(
        (key, ACCELERATIONS[key].label) for key in keys
    )


def data_directory() -> pathlib.Path:
    """Return the per-user directory holding the managed runtime and models."""
    override = os.environ.get("RX3_STEM_STUDIO_HOME")
    if override:
        return pathlib.Path(override).expanduser()
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library/Application Support" / APPLICATION_NAME
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData/Local")
        return pathlib.Path(base) / APPLICATION_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(pathlib.Path.home() / ".local/share")
    return pathlib.Path(base) / "rx3-stem-studio"


def _script(environment: pathlib.Path, name: str) -> pathlib.Path:
    if sys.platform == "win32":
        return environment / "Scripts" / f"{name}.exe"
    return environment / "bin" / name


def _executable_name(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _find_on_path(name: str) -> pathlib.Path | None:
    """Look up a tool on `PATH`, then in the usual install prefixes.

    An application launched from a desktop shell inherits a minimal `PATH`
    that omits Homebrew and other package prefixes.
    """
    found = shutil.which(name)
    if found:
        return pathlib.Path(found)
    for directory in _search_directories():
        if directory is None:
            continue
        candidate = directory / _executable_name(name)
        if candidate.is_file():
            return candidate
    return None


_FILTER_PROBES: dict[tuple[str, int, int], tuple[str, ...]] = {}


def missing_filters(ffmpeg: pathlib.Path) -> tuple[str, ...]:
    """Report which required filters this FFmpeg build does not carry.

    Distributions and hand-built copies do turn filters off, and the failure
    then lands in the middle of a job instead of at startup. The result is
    cached per binary, since `detect` is called on every interface refresh.
    """
    try:
        stamp = ffmpeg.stat()
    except OSError:
        return REQUIRED_FILTERS
    key = (str(ffmpeg), stamp.st_size, int(stamp.st_mtime))
    cached = _FILTER_PROBES.get(key)
    if cached is not None:
        return cached

    try:
        probe = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        probe = None
    if probe is None or probe.returncode or not probe.stdout:
        # A binary that cannot even list its filters is not one to rely on.
        result = REQUIRED_FILTERS
    else:
        # Each line reads `  T.. name  A->A  description`; the name is second.
        present = {
            parts[1] for parts in
            (line.split() for line in probe.stdout.splitlines())
            if len(parts) >= 2
        }
        result = tuple(name for name in REQUIRED_FILTERS if name not in present)
    _FILTER_PROBES[key] = result
    return result


def _bundled_ffmpeg(environment: pathlib.Path) -> pathlib.Path | None:
    roots = [environment / "Lib/site-packages"] if sys.platform == "win32" else list(
        environment.glob("lib/python3.*/site-packages")
    )
    for root in roots:
        for candidate in sorted((root / "imageio_ffmpeg/binaries").glob("ffmpeg-*")):
            if candidate.is_file():
                return candidate
    return None


@dataclass(frozen=True)
class Runtime:
    """Resolved locations of everything the separation pipeline shells out to."""

    environment: pathlib.Path
    models: pathlib.Path
    separator: pathlib.Path | None
    ffmpeg: pathlib.Path | None
    # FFmpeg copies found to be missing filters the pipeline uses, whether they
    # were passed over for a complete one or kept because they were overridden.
    ffmpeg_incomplete: tuple[tuple[pathlib.Path, tuple[str, ...]], ...] = ()

    @property
    def ready(self) -> bool:
        return self.separator is not None and self.ffmpeg is not None

    @property
    def managed(self) -> bool:
        """Whether the separator in use is the one this application installed.

        A copy already present on `PATH` wins over the managed environment, and
        it is not ours to remove or to rebuild for another accelerator.
        """
        if self.separator is None:
            return False
        return self.separator == _script(self.environment, SEPARATOR_COMMAND)

    @property
    def summary(self) -> str:
        notes = " ".join(
            f"{path.name} lacks the {', '.join(absent)} filter."
            for path, absent in self.ffmpeg_incomplete
        )
        if self.ready:
            return " ".join(filter(None, ("Separation runtime ready.", notes)))
        missing = [
            name for name, path in
            (("audio-separator", self.separator), ("FFmpeg", self.ffmpeg))
            if path is None
        ]
        return " ".join(filter(None, (
            f"Missing: {' and '.join(missing)}.", notes,
            "Install the separation runtime to continue.",
        )))

    def subprocess_environment(self) -> dict[str, str]:
        """Environment giving the separator its model cache and a reachable FFmpeg."""
        values = os.environ.copy()
        values["AUDIO_SEPARATOR_MODEL_DIR"] = str(self.models)
        values["TORCH_HOME"] = str(self.models)
        directory = self.ffmpeg_directory()
        if directory is not None:
            values["PATH"] = os.pathsep.join(
                [str(directory), values.get("PATH", "")]
            ).strip(os.pathsep)
        return values

    def ffmpeg_directory(self) -> pathlib.Path | None:
        """Return a directory holding an executable literally named `ffmpeg`.

        The separator invokes FFmpeg by name through pydub, so putting the
        resolved binary's own directory on `PATH` is not enough: the copy
        bundled by imageio-ffmpeg is named after its platform and version.
        """
        if self.ffmpeg is None:
            return None
        expected = _executable_name("ffmpeg")
        if self.ffmpeg.name == expected:
            return self.ffmpeg.parent
        return _link_as(self.ffmpeg, data_directory() / "bin" / expected)


def _link_as(target: pathlib.Path, alias: pathlib.Path) -> pathlib.Path | None:
    """Expose `target` under `alias`, preferring a link over a copy.

    A dangling alias is worse than none: it sits first on the separator's
    `PATH` and would shadow a working installation further down.
    """
    if not target.is_file():
        return None
    try:
        if alias.is_file() and alias.stat().st_size == target.stat().st_size:
            return alias.parent
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.unlink(missing_ok=True)
        try:
            alias.symlink_to(target)
        except (OSError, NotImplementedError):
            # Windows restricts symlinks to privileged accounts, and a hard
            # link needs both paths on one volume.
            try:
                os.link(target, alias)
            except OSError:
                shutil.copy2(target, alias)
        return alias.parent
    except OSError:
        return None


def detect(environment: pathlib.Path | None = None) -> Runtime:
    """Resolve the separator and FFmpeg from overrides, `PATH`, then the managed copy."""
    root = data_directory()
    environment = environment or root / "runtime"
    models = root / "models"

    override = os.environ.get("RX3_SEPARATOR")
    separator = pathlib.Path(override) if override else None
    if separator is None or not separator.is_file():
        managed = _script(environment, SEPARATOR_COMMAND)
        found = managed if managed.is_file() else shutil.which(SEPARATOR_COMMAND)
        separator = pathlib.Path(found) if found else None

    override = os.environ.get("RX3_FFMPEG")
    override_path = pathlib.Path(override) if override else None
    if override_path is not None and override_path.is_file():
        # An explicit override is the operator's decision and the documented
        # escape hatch; discarding it over a probe this application invented
        # would be worse than honouring it. Any gap is reported, not acted on.
        ffmpeg_path = override_path
        absent = missing_filters(override_path)
        incomplete = ((override_path, absent),) if absent else ()
    else:
        # A real installation carries ffprobe beside ffmpeg, which the bundled
        # single-binary copy does not, so it is preferred — but only if it is
        # complete. An incomplete one falls through to the copy this
        # application installs, built with everything the pipeline uses.
        ffmpeg_path, incomplete = _first_complete_ffmpeg([
            _find_on_path("ffmpeg"), _bundled_ffmpeg(environment),
        ])

    return Runtime(
        environment=environment,
        models=models,
        separator=separator,
        ffmpeg=ffmpeg_path,
        ffmpeg_incomplete=incomplete,
    )


def _first_complete_ffmpeg(
    candidates: Iterable[pathlib.Path | None],
) -> tuple[pathlib.Path | None, tuple[tuple[pathlib.Path, tuple[str, ...]], ...]]:
    """The first candidate carrying every required filter, and what was skipped."""
    rejected: list[tuple[pathlib.Path, tuple[str, ...]]] = []
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        absent = missing_filters(candidate)
        if not absent:
            return candidate, tuple(rejected)
        rejected.append((candidate, absent))
    return None, tuple(rejected)


def _search_directories() -> list[pathlib.Path | None]:
    """Directories to search besides `PATH`, which stays minimal for GUI apps."""
    directories: list[pathlib.Path | None] = [None]
    # uv keeps its interpreters outside PATH, and they are often the only ones
    # in the supported range on a machine tracking the newest Python.
    directories += sorted(
        (pathlib.Path.home() / ".local/share/uv/python").glob("cpython-3.*/bin"),
        reverse=True,
    )
    if sys.platform == "darwin":
        directories += [pathlib.Path("/opt/homebrew/bin"), pathlib.Path("/usr/local/bin")]
        directories += sorted(
            pathlib.Path("/Library/Frameworks/Python.framework/Versions").glob("3.*/bin"),
            reverse=True,
        )
    elif sys.platform != "win32":
        directories += [pathlib.Path("/usr/local/bin"), pathlib.Path("/usr/bin")]
    return directories


def _candidate_interpreters() -> list[pathlib.Path]:
    names = [f"python3.{minor}" for minor in range(MAXIMUM_PYTHON[1], MINIMUM_PYTHON[1] - 1, -1)]
    names += ["python3", "python"]
    candidates: list[pathlib.Path] = []
    seen: set[str] = set()
    for directory in _search_directories():
        for name in names:
            if directory is None:
                found = shutil.which(name)
                path = pathlib.Path(found) if found else None
            else:
                path = directory / name
                if not path.is_file():
                    path = None
            # python3, python3.12, and python are usually the same binary, so
            # resolve before probing to keep the number of subprocesses small.
            if path is None:
                continue
            key = os.path.realpath(path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)
    if sys.platform == "win32":
        launcher = shutil.which("py")
        if launcher:
            probe = subprocess.run(
                [launcher, "-3", "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True,
            )
            if not probe.returncode and probe.stdout.strip():
                candidates.append(pathlib.Path(probe.stdout.strip()))
    return candidates


def supported_python_range() -> str:
    return (
        f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} to "
        f"{MAXIMUM_PYTHON[0]}.{MAXIMUM_PYTHON[1]}"
    )


def host_python() -> pathlib.Path:
    """Return the newest supported interpreter able to seed the environment.

    A frozen application cannot seed a virtual environment from itself, so a
    real interpreter has to be found on the host. The newest one inside the
    supported range wins: a stock macOS only carries an end-of-life
    interpreter, and the newest release usually runs ahead of the separation
    stack.
    """
    if not getattr(sys, "frozen", False) and _venv_version(pathlib.Path(sys.executable)):
        return pathlib.Path(sys.executable)
    usable = [
        (version, path) for path, version in
        ((path, _venv_version(path)) for path in _candidate_interpreters())
        if version is not None and MINIMUM_PYTHON <= version <= MAXIMUM_PYTHON
    ]
    if not usable:
        raise ProvisioningError(
            f"No Python {supported_python_range()} interpreter with the venv module was "
            "found. Install one from python.org, then install the separation runtime again."
        )
    return max(usable)[1]


def _venv_version(interpreter: pathlib.Path) -> tuple[int, int] | None:
    """Return the interpreter version, or None if it cannot seed an environment."""
    probe = subprocess.run(
        [str(interpreter), "-c",
         "import sys, venv; print(sys.version_info.major, sys.version_info.minor)"],
        capture_output=True, text=True,
    )
    if probe.returncode:
        return None
    try:
        major, minor = (int(part) for part in probe.stdout.split())
    except ValueError:
        return None
    return (major, minor) if MINIMUM_PYTHON <= (major, minor) <= MAXIMUM_PYTHON else None


def _stream(command: Sequence[str], progress: ProgressCallback, label: str) -> None:
    """Run a provisioning step, forwarding its output to the interface."""
    progress(label)
    process = subprocess.Popen(
        [str(item) for item in command],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    assert process.stdout is not None
    tail: list[str] = []
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        tail = (tail + [line])[-12:]
        progress(f"{label}: {line[:160]}")
    if process.wait():
        detail = " / ".join(tail)[-500:]
        raise ProvisioningError(f"{label} failed: {detail or 'no output'}")


def install_packages(
    environment: pathlib.Path, acceleration: Acceleration
) -> Iterable[tuple[str, list[str]]]:
    """Yield the labelled pip invocations that populate the managed runtime."""
    python = _script(environment, "python")
    yield "Updating pip", [str(python), "-m", "pip", "install", "--upgrade", "pip"]
    if acceleration.torch_index:
        yield f"Installing PyTorch for {acceleration.label}", [
            str(python), "-m", "pip", "install",
            "--index-url", acceleration.torch_index, "torch",
        ]
    yield f"Installing audio-separator for {acceleration.label}", [
        str(python), "-m", "pip", "install", acceleration.requirement, *SUPPORT_PACKAGES,
    ]


STATE_NAME = "runtime.json"


def installed_accelerator() -> str | None:
    """Return the accelerator the managed environment was built for."""
    try:
        data = json.loads((data_directory() / STATE_NAME).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    key = data.get("accelerator")
    return key if isinstance(key, str) and key in ACCELERATIONS else None


def needs_reinstall(accelerator: str, runtime: Runtime | None = None) -> bool:
    """Whether the installed environment matches the selected accelerator."""
    runtime = runtime or detect()
    if not runtime.managed:
        return False
    installed = installed_accelerator()
    return installed is not None and installed != resolve_acceleration(accelerator).key


def uninstall(progress: ProgressCallback = lambda message: None) -> None:
    """Remove the managed environment, leaving downloaded models in place."""
    root = data_directory()
    for target in (root / "runtime", root / "bin"):
        if target.exists():
            progress(f"Removing {target}")
            shutil.rmtree(target, ignore_errors=True)
    (root / STATE_NAME).unlink(missing_ok=True)
    progress("Separation runtime removed.")


def provision(
    progress: ProgressCallback = lambda message: None,
    accelerator: str = AUTOMATIC,
) -> Runtime:
    """Create or complete the managed runtime and return the resolved locations."""
    acceleration = resolve_acceleration(accelerator)
    runtime = detect()
    environment = runtime.environment
    interpreter = host_python()
    environment.parent.mkdir(parents=True, exist_ok=True)
    runtime.models.mkdir(parents=True, exist_ok=True)

    existing = _script(environment, "python")
    # An environment left by an older release may sit on an interpreter that
    # audio-separator no longer supports; completing it in place would fail on
    # every install step, so it is rebuilt instead.
    if existing.is_file() and _venv_version(existing) is None:
        progress("Replacing an environment built on an unsupported interpreter")
        shutil.rmtree(environment)
    # Switching accelerator in place cannot work: pip sees the PyTorch already
    # installed as satisfying the requirement and keeps the build made for the
    # previous one, leaving `torch.cuda.is_available()` false on a GPU machine.
    previous = installed_accelerator()
    if existing.is_file() and previous is not None and previous != acceleration.key:
        progress(
            f"Rebuilding the environment: it was built for "
            f"{ACCELERATIONS[previous].label}, not {acceleration.label}"
        )
        shutil.rmtree(environment, ignore_errors=True)
    if not existing.is_file():
        if environment.exists():
            shutil.rmtree(environment)
        _stream(
            [str(interpreter), "-m", "venv", str(environment)],
            progress, "Creating the runtime environment",
        )
    for label, command in install_packages(environment, acceleration):
        _stream(command, progress, label)

    runtime = detect(environment)
    if not runtime.ready:
        raise ProvisioningError(
            "The runtime was installed but audio-separator or FFmpeg could not be "
            f"resolved under {environment}."
        )
    (data_directory() / STATE_NAME).write_text(
        json.dumps({"accelerator": acceleration.key}, indent=2) + "\n", encoding="utf-8"
    )
    progress(f"Separation runtime ready ({acceleration.label}).")
    return runtime
