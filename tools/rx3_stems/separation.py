# SPDX-License-Identifier: MPL-2.0
"""Separation model catalogue and the tunable parameters of each architecture.

`audio-separator` exposes one parameter group per model architecture, and a
model only accepts the group matching its own. The catalogue resolves a model
filename to its architecture so the interface can offer exactly the options
that apply, and so a stored setting for another architecture is never passed
on the command line.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable


CATALOGUE_NAME = "models.json"
SETTINGS_NAME = "separation.json"
# The best vocal SDR in the catalogue, which is what this pipeline extracts.
# audio-separator's own default scores roughly 0.8 dB lower.
DEFAULT_MODEL = "vocals_mel_band_roformer.ckpt"
VOCAL_STEM = "Vocals"


@dataclass(frozen=True)
class Option:
    """One tunable separation parameter, rendered generically by the interface.

    `default` is what this pipeline wants; `upstream` is audio-separator's own
    default when the two differ. An argument is only omitted when the effective
    value already matches what the separator would do on its own.
    """

    name: str
    flag: str
    label: str
    help: str
    default: Any
    kind: str  # "number", "integer", "text", or "flag"
    minimum: float | None = None
    maximum: float | None = None
    upstream: Any = None

    @property
    def implied(self) -> Any:
        """The value that needs no command-line argument."""
        return self.default if self.upstream is None else self.upstream

    def parse(self, value: str) -> Any:
        if self.kind == "integer":
            return int(value)
        if self.kind == "number":
            return float(value)
        return value

    def validate(self, value: Any) -> None:
        if self.kind in ("integer", "number"):
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"{self.label} must be at least {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"{self.label} must be at most {self.maximum}")


COMMON_OPTIONS: tuple[Option, ...] = (
    # The device reconstructs the instrumental as full mix minus vocal, so the
    # vocal has to stay in the gain domain of the untouched source file. The
    # separator's own 0.9 scales the mix, and therefore the vocal, by 0.9/peak;
    # what does not cancel on the deck is audible leftover vocal. At 1.0 no
    # stage rescales anything that decodes at or below full scale.
    Option("normalization", "--normalization", "Normalization",
           "Max peak amplitude the input and output are normalized to. Keep this "
           "at 1.0: a lower value rescales the vocal out of the source gain "
           "domain and leaves vocal in the instrumental on the deck.",
           1.0, "number", 0.0, 1.0, upstream=0.9),
    Option("amplification", "--amplification", "Amplification",
           "Min peak amplitude the input and output are amplified to.",
           0.0, "number", 0.0, 1.0),
    Option("invert_spect", "--invert_spect", "Invert with spectrogram",
           "Derive the stem by spectrogram inversion instead of direct output.",
           False, "flag"),
    Option("use_autocast", "--use_autocast", "Autocast",
           "Faster inference on a GPU. Leave off for the CPU separation used here.",
           False, "flag"),
)

ARCHITECTURE_OPTIONS: dict[str, tuple[Option, ...]] = {
    "MDX": (
        Option("mdx_segment_size", "--mdx_segment_size", "Segment size",
               "Larger uses more memory and may separate better.", 256, "integer", 32, 8192),
        Option("mdx_overlap", "--mdx_overlap", "Overlap",
               "Overlap between prediction windows. Higher is better and slower.",
               0.25, "number", 0.001, 0.999),
        Option("mdx_batch_size", "--mdx_batch_size", "Batch size",
               "Larger uses more memory and may process slightly faster.", 1, "integer", 1, 64),
        Option("mdx_hop_length", "--mdx_hop_length", "Hop length",
               "Network stride. Leave at the default unless you know the model.",
               1024, "integer", 64, 8192),
        Option("mdx_enable_denoise", "--mdx_enable_denoise", "Denoise",
               "Denoise while separating. Roughly doubles the processing time.",
               False, "flag"),
    ),
    "VR": (
        Option("vr_window_size", "--vr_window_size", "Window size",
               "1024 is fast and coarse, 320 is slow and finer.", 512, "integer", 64, 4096),
        Option("vr_aggression", "--vr_aggression", "Aggression",
               "Intensity of the extraction. 5 suits vocals and instrumentals.",
               5, "integer", -100, 100),
        Option("vr_batch_size", "--vr_batch_size", "Batch size",
               "Larger uses more memory and processes slightly faster.", 1, "integer", 1, 64),
        Option("vr_enable_tta", "--vr_enable_tta", "Test-time augmentation",
               "Slower, usually cleaner.", False, "flag"),
        Option("vr_high_end_process", "--vr_high_end_process", "High-end process",
               "Mirror the missing frequency range into the output.", False, "flag"),
        Option("vr_enable_post_process", "--vr_enable_post_process", "Post-process",
               "Identify leftover artifacts in the vocal output.", False, "flag"),
        Option("vr_post_process_threshold", "--vr_post_process_threshold",
               "Post-process threshold", "Only used when post-process is on.",
               0.2, "number", 0.1, 0.3),
    ),
    "MDXC": (
        Option("mdxc_segment_size", "--mdxc_segment_size", "Segment size",
               "Larger uses more memory and may separate better.", 256, "integer", 32, 8192),
        Option("mdxc_override_model_segment_size", "--mdxc_override_model_segment_size",
               "Override model segment size",
               "Use the segment size above instead of the model's own default.",
               False, "flag"),
        Option("mdxc_overlap", "--mdxc_overlap", "Overlap",
               "Overlap between prediction windows. Higher is better and slower.",
               8, "integer", 2, 50),
        Option("mdxc_batch_size", "--mdxc_batch_size", "Batch size",
               "Larger uses more memory and may process slightly faster.", 1, "integer", 1, 64),
        Option("mdxc_pitch_shift", "--mdxc_pitch_shift", "Pitch shift",
               "Shift by semitones while processing. May help very deep or high vocals.",
               0, "integer", -24, 24),
    ),
    "Demucs": (
        Option("demucs_shifts", "--demucs_shifts", "Shifts",
               "Predictions with random shifts. Higher is better and slower.",
               2, "integer", 1, 20),
        Option("demucs_overlap", "--demucs_overlap", "Overlap",
               "Overlap between prediction windows. Higher is better and slower.",
               0.25, "number", 0.001, 0.999),
        Option("demucs_segment_size", "--demucs_segment_size", "Segment size",
               "Split size for the audio. 'Default' keeps the model's own value.",
               "Default", "text"),
    ),
}


@dataclass(frozen=True)
class Model:
    architecture: str
    name: str
    filename: str
    stems: tuple[str, ...]
    vocal_sdr: float | None
    # Bare filenames and URLs alike are stored under their basename in the
    # model directory, so the basenames are what identifies a local copy.
    download_files: tuple[str, ...] = field(default=())

    @property
    def label(self) -> str:
        score = f"SDR {self.vocal_sdr:5.2f}" if self.vocal_sdr is not None else "SDR    — "
        return f"{score} · {self.architecture:6s} · {self.filename}"

    def local_files(self, models_directory: pathlib.Path) -> tuple[pathlib.Path, ...]:
        return tuple(
            models_directory / entry.rsplit("/", 1)[-1] for entry in self.download_files
        )

    def is_downloaded(self, models_directory: pathlib.Path) -> bool:
        files = self.local_files(models_directory)
        return bool(files) and all(path.is_file() for path in files)

    def size(self, models_directory: pathlib.Path) -> int:
        return sum(
            path.stat().st_size for path in self.local_files(models_directory) if path.is_file()
        )


@dataclass(frozen=True)
class Catalogue:
    models: tuple[Model, ...] = field(default=())

    def by_filename(self, filename: str) -> Model | None:
        for model in self.models:
            if model.filename == filename:
                return model
        return None

    def architecture_of(self, filename: str) -> str | None:
        model = self.by_filename(filename)
        return model.architecture if model else None


def parse_catalogue(data: dict[str, Any]) -> Catalogue:
    """Keep the vocal-capable models of every architecture, best score first."""
    models: list[Model] = []
    for architecture, entries in data.items():
        if not isinstance(entries, dict):
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict) or "filename" not in entry:
                continue
            stems = tuple(str(stem) for stem in entry.get("stems", ()))
            if VOCAL_STEM.lower() not in {stem.lower() for stem in stems}:
                continue
            score = entry.get("scores", {}).get("vocals", {}).get("SDR")
            downloads = entry.get("download_files") or [entry["filename"]]
            models.append(Model(
                architecture=architecture,
                name=name,
                filename=str(entry["filename"]),
                stems=stems,
                vocal_sdr=float(score) if isinstance(score, (int, float)) else None,
                download_files=tuple(str(item) for item in downloads),
            ))
    models.sort(key=lambda model: (-(model.vocal_sdr or -100.0), model.filename))
    return Catalogue(models=tuple(models))


def load_catalogue(
    runtime: Any,
    cache: pathlib.Path,
    *,
    refresh: bool = False,
) -> Catalogue:
    """Return the model catalogue, refreshing the on-disk cache when possible.

    The listing reaches the network, so a cached copy is preferred at startup
    and kept as the fallback when the refresh fails.
    """
    if not refresh and cache.is_file():
        try:
            return parse_catalogue(json.loads(cache.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    result = subprocess.run(
        [str(runtime.separator), "--list_models", "--list_format=json",
         f"--model_file_dir={runtime.models}", "--log_level=error"],
        capture_output=True, text=True,
        # audio-separator reaches for FFmpeg by name whatever it is asked to
        # do, so every invocation needs the prepared environment.
        env=runtime.subprocess_environment(),
    )
    if result.returncode or not result.stdout.strip():
        if cache.is_file():
            return parse_catalogue(json.loads(cache.read_text(encoding="utf-8")))
        detail = " ".join((result.stderr or result.stdout).split())[-300:]
        raise RuntimeError(f"The model list could not be retrieved: {detail or 'no output'}")
    data = json.loads(result.stdout)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return parse_catalogue(data)


@dataclass(frozen=True)
class Settings:
    model: str = DEFAULT_MODEL
    accelerator: str = "auto"
    values: dict[str, Any] = field(default_factory=dict)

    def value(self, option: Option) -> Any:
        return self.values.get(option.name, option.default)

    def with_model(self, model: str) -> "Settings":
        return replace(self, model=model)

    def with_accelerator(self, accelerator: str) -> "Settings":
        return replace(self, accelerator=accelerator)

    def with_value(self, option: Option, value: Any) -> "Settings":
        values = dict(self.values)
        if value == option.default:
            values.pop(option.name, None)
        else:
            values[option.name] = value
        return replace(self, values=values)

    def options(self, architecture: str | None) -> tuple[tuple[str, tuple[Option, ...]], ...]:
        groups = [("Common", COMMON_OPTIONS)]
        if architecture and architecture in ARCHITECTURE_OPTIONS:
            groups.append((f"{architecture} architecture", ARCHITECTURE_OPTIONS[architecture]))
        return tuple(groups)

    def arguments(self, architecture: str | None) -> list[str]:
        """Command-line arguments for the model, excluding other architectures."""
        arguments = [f"--model_filename={self.model}"]
        for _, options in self.options(architecture):
            for option in options:
                value = self.value(option)
                option.validate(value)
                if value == option.implied:
                    continue
                if option.kind == "flag":
                    if value:
                        arguments.append(option.flag)
                else:
                    arguments.append(f"{option.flag}={value}")
        return arguments


def load_settings(path: pathlib.Path) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return Settings()
    model = data.get("model")
    accelerator = data.get("accelerator")
    values = data.get("values")
    known = set(known_option_names())
    return Settings(
        model=model if isinstance(model, str) and model else DEFAULT_MODEL,
        accelerator=accelerator if isinstance(accelerator, str) and accelerator else "auto",
        # A setting written by a later version must not reach the command line.
        values={key: value for key, value in (values or {}).items() if key in known}
        if isinstance(values, dict) else {},
    )


def save_settings(path: pathlib.Path, settings: Settings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "model": settings.model,
        "accelerator": settings.accelerator,
        "values": settings.values,
    }, indent=2) + "\n", encoding="utf-8")


def download_model(
    runtime: Any,
    model: Model,
    progress: Callable[[str], None] = lambda message: None,
) -> None:
    """Fetch one model's files, leaving every other model untouched."""
    models_directory = runtime.models
    models_directory.mkdir(parents=True, exist_ok=True)
    progress(f"Downloading {model.filename}…")
    process = subprocess.Popen(
        [str(runtime.separator), "--download_model_only",
         f"--model_filename={model.filename}",
         f"--model_file_dir={models_directory}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        env=runtime.subprocess_environment(),
    )
    assert process.stdout is not None
    tail: list[str] = []
    for line in process.stdout:
        line = line.strip()
        if line:
            tail = (tail + [line])[-8:]
            progress(f"{model.filename}: {line[:140]}")
    if process.wait():
        raise RuntimeError(
            f"{model.filename} could not be downloaded: {' / '.join(tail)[-400:] or 'no output'}"
        )
    if not model.is_downloaded(models_directory):
        missing = [
            path.name for path in model.local_files(models_directory) if not path.is_file()
        ]
        raise RuntimeError(f"{model.filename} is still incomplete: missing {', '.join(missing)}")
    progress(f"{model.filename} downloaded.")


def delete_model(models_directory: pathlib.Path, model: Model) -> int:
    """Remove one model's files and return how many bytes were freed."""
    freed = 0
    for path in model.local_files(models_directory):
        if path.is_file():
            freed += path.stat().st_size
            path.unlink()
    return freed


def normalization_option() -> Option:
    return next(option for option in COMMON_OPTIONS if option.name == "normalization")


def input_normalization(settings: Settings, architecture: str | None) -> float | None:
    """The peak the separator scales the mix to before inference, if it does.

    MDX and MDXC rescale the mix, so their stem is returned in that scaled
    domain and the sidecar encoder has to undo the factor. Demucs and VR leave
    the mix alone; they only rescale a stem that peaks above the threshold on
    its own, which at 1.0 means a vocal above full scale that no `s16` sidecar
    could carry anyway. An unrecognised architecture is treated the same way.
    """
    if architecture not in ("MDX", "MDXC"):
        return None
    return float(settings.value(normalization_option()))


def known_option_names() -> Iterable[str]:
    for options in (COMMON_OPTIONS, *ARCHITECTURE_OPTIONS.values()):
        for option in options:
            yield option.name
