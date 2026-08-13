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

QUALITY_MODE = "quality"
NORMAL_MODE = "normal"
QUICK_MODE = "quick"
CUSTOM_MODE = "custom"
# Modes that older settings files hold, and what they mean now. `fast` named
# the top of the ladder by the time it was retired - the roformer at the step
# its own weights default to - so it reads as `quality` rather than as the
# cheapest preset, which is what its name would otherwise suggest.
LEGACY_MODES = {"fast": QUALITY_MODE}


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
        # Unlike the MDX and Demucs options of the same name, this one is a hop
        # divisor, not an amount of overlap: raising it moves the prediction
        # window further each step, so it separates from fewer passes. The
        # direction is the opposite of what this help text used to state.
        Option("mdxc_overlap", "--mdxc_overlap", "Overlap",
               "Step between prediction windows. Lower stitches the result from "
               "more passes over the audio: better, and considerably slower.",
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


# The roformer family, best vocal SDR first, which is what the catalogue's own
# scores say and all this project claims about it. These are PyTorch
# checkpoints, so they reach the GPU wherever PyTorch does and nowhere else.
ROFORMER_CANDIDATES: tuple[str, ...] = (
    DEFAULT_MODEL,
    "mel_band_roformer_kim_ft_unwa.ckpt",
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
)
# The MDX-Net family: ONNX models of a few tens of megabytes against the
# roformer's several hundred, for 10.2 dB of vocal SDR against 12.6. They are
# also band-limited - `dim_f` 3072 over an `n_fft` of 7680 puts the wall at
# 17.6 kHz - so nothing above that is ever separated, and the air of a vocal
# stays in the instrumental the deck reconstructs.
#
# They are kept for the builds that cannot run a roformer on the GPU at all,
# not as a speed trade-off: see `PRESETS`.
MDX_CANDIDATES: tuple[str, ...] = (
    "Kim_Vocal_2.onnx",
    "UVR-MDX-NET-Voc_FT.onnx",
    "UVR-MDX-NET_Main_406.onnx",
)
# Demucs, which is what "very fast" means where PyTorch reaches the GPU. A
# waveform model rather than a transformer, and measured on this project's
# reference machine at 0.161 s of computation per second of audio against the
# roformer's 0.526 - the only real step down in cost the catalogue offers.
#
# `htdemucs` and not `htdemucs_ft`: the fine-tuned variant runs four sub-models
# and was measured at 0.502 s/s, which is the roformer's cost for 1.8 dB less.
# Being full-band, this gives up SDR without giving up the top of the spectrum
# the way an MDX-Net does.
DEMUCS_CANDIDATES: tuple[str, ...] = (
    "htdemucs.yaml",
    "hdemucs_mmi.yaml",
)
# Demucs averages predictions over randomly shifted copies of the input. Two is
# the separator's own default and doubles the work for a fraction of a dB,
# which is not the trade this preset exists to make.
QUICK_SHIFTS = 1
# `mdxc_overlap` on a roformer is a step in seconds, not a divisor: the chunk
# is `stft_hop_length * (dim_t - 1)` samples and the window advances
# `min(overlap * sample_rate, chunk)` each time, so a lower value stitches the
# result from more passes. For `vocals_mel_band_roformer` the chunk is 11.0 s,
# which makes the option's own default of 8 a 27% overlap over 1.38 passes.
#
# `quality` therefore keeps the default rather than naming a value: a preset
# that restated the default would only be noise in the stored settings.
#
# `normal` is the largest step that still leaves a crossfade. At the chunk
# length and above - 11 and up here - the step is clamped to the chunk and the
# passes stop overlapping at all, which was measured as a discontinuity every
# 11.0 s reaching 25x the surrounding sample-to-sample difference, against 0.7x
# away from a boundary. That is a click, and the deck subtracts the stem from
# the mix, so it lands in the instrumental too. One second of overlap removes
# it and costs nothing measurable: 0.399 s/s at 10 against 0.406 at 11, both
# against 0.526 at the default.
NORMAL_OVERLAP = 10
# The same ladder for the MDX architecture, whose `mdx_overlap` is a real
# fraction and does read the way its name suggests. Three presets have to mean
# three things on a build that can only run this one architecture, so they are
# expressed as three amounts of overlap on one model rather than three models.
MDX_QUALITY_OVERLAP = 0.5
MDX_QUICK_OVERLAP = 0.1


@dataclass(frozen=True)
class Variant:
    """One model plus its tuning: what a preset means for one inference runtime.

    Models are named as an ordered list rather than singly because the
    catalogue is fetched from audio-separator at runtime and its contents are
    not this project's to pin. The first candidate the catalogue actually
    offers wins, and a catalogue that offers none of them still resolves to
    something sensible.

    `summary` belongs to the variant rather than to the preset because the two
    variants of one preset are not the same offer: on a build that runs neither
    architecture on the GPU, `fast` is a weaker model rather than a cheaper
    setting, and the interface has to say so instead of promising one quality
    everywhere.
    """

    architecture: str
    candidates: tuple[str, ...]
    summary: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Preset:
    """A named speed/quality trade-off, in the terms of the machine running it.

    Which model is quicker is not a property of the model alone: a build
    accelerates PyTorch, ONNX Runtime, both or neither, and a model that misses
    its runtime's accelerator is slower than a heavier one that reaches it. A
    preset therefore names the trade-off and lets the machine pick the variant
    that expresses it here.

    The split is between the two runtimes, and it is not the same split on
    every platform. PyTorch reaches the GPU through CUDA, Apple Silicon MPS and
    ROCm; ONNX Runtime reaches it through CUDA and DirectML, and on Apple
    Silicon CoreML lists a provider but takes only 151 of an MDX-Net's 178
    nodes across 28 partitions, so the run spends its time handing tensors back
    to the CPU. A roformer is a Torch checkpoint and an MDX-Net is an ONNX
    graph, so where PyTorch is accelerated the roformer is both the better and
    the faster answer, and where it is not - DirectML, and any CPU-only build -
    an MDX-Net is the only one that reaches the hardware at all.
    """

    key: str
    label: str
    # Where PyTorch reaches the GPU, which is also where the better model runs.
    torch: Variant
    # Where it does not, and the work has to go through ONNX Runtime instead.
    onnx: Variant

    def resolve(self, *, accelerates_torch: bool = True) -> Variant:
        return self.torch if accelerates_torch else self.onnx


# Best first, which is the order the interface offers them in.
#
# No ratio is quoted in any summary on purpose: how much quicker one preset is
# than another depends on the model, the device and the machine's load, and the
# status line answers it from this machine's own measured throughput.
#
# The top two are one model at two steps, so moving between them downloads
# nothing and gives up no SDR. Only `quick` trades the model itself, because
# below the roformer every architecture in the catalogue lands within a quarter
# of the same cost - there is no third speed class to build a preset on.
PRESETS: tuple[Preset, ...] = (
    Preset(
        key=QUALITY_MODE,
        label="High quality",
        torch=Variant(
            architecture="MDXC", candidates=ROFORMER_CANDIDATES,
            summary="The cleanest, and the slowest.",
        ),
        # "runs at all" rather than "runs on the GPU": these variants also
        # serve the CPU-only build, where there is no GPU to be the better of.
        onnx=Variant(
            architecture="MDX", candidates=MDX_CANDIDATES,
            summary="A lighter model, the only kind this build runs at a usable speed, "
                    "over more passes. Nothing is separated above 17.6 kHz.",
            values={"mdx_overlap": MDX_QUALITY_OVERLAP},
        ),
    ),
    Preset(
        key=NORMAL_MODE,
        label="Normal",
        torch=Variant(
            architecture="MDXC", candidates=ROFORMER_CANDIDATES,
            summary="The same model. Noticeably quicker, with almost no difference in quality.",
            values={"mdxc_overlap": NORMAL_OVERLAP},
        ),
        onnx=Variant(
            architecture="MDX", candidates=MDX_CANDIDATES,
            summary="The same lighter model at its own default overlap. "
                    "Nothing is separated above 17.6 kHz.",
        ),
    ),
    Preset(
        key=QUICK_MODE,
        label="Very fast",
        torch=Variant(
            architecture="Demucs", candidates=DEMUCS_CANDIDATES,
            summary="A waveform model. Several times quicker, with noticeably more instrument left in the vocal.",
            values={"demucs_shifts": QUICK_SHIFTS},
        ),
        onnx=Variant(
            architecture="MDX", candidates=MDX_CANDIDATES,
            summary="The same lighter model, over fewer passes. As quick as possible,"
                    " and the least clean.",
            values={"mdx_overlap": MDX_QUICK_OVERLAP},
        ),
    ),
)


def preset(key: str) -> Preset | None:
    return next((item for item in PRESETS if item.key == key), None)


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

    def best_of(self, architecture: str) -> Model | None:
        """The highest-scoring vocal model of one architecture, if any."""
        # `models` is already sorted best score first.
        return next(
            (model for model in self.models if model.architecture == architecture), None
        )


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
    # Which quality preset produced `model` and `values`, or CUSTOM once either
    # has been edited by hand. A preset therefore always names exactly one
    # known configuration, and hand tuning is never silently relabelled.
    mode: str = QUALITY_MODE

    def value(self, option: Option) -> Any:
        return self.values.get(option.name, option.default)

    def with_model(self, model: str) -> "Settings":
        return replace(self, model=model, mode=CUSTOM_MODE)

    def as_custom(self) -> "Settings":
        """Keep the configuration, stop claiming a preset produced it."""
        return replace(self, mode=CUSTOM_MODE)

    def with_accelerator(self, accelerator: str) -> "Settings":
        # Acceleration is a property of the machine, not of the quality traded
        # for speed, so choosing it leaves the preset intact. Which model
        # expresses that preset here does change with it, but resolving one
        # takes the catalogue, so the caller reapplies the preset afterwards.
        return replace(self, accelerator=accelerator)

    def with_value(self, option: Option, value: Any) -> "Settings":
        values = dict(self.values)
        if value == option.default:
            values.pop(option.name, None)
        else:
            values[option.name] = value
        if values == self.values:
            return self
        return replace(self, values=values, mode=CUSTOM_MODE)

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


def resolve_preset_model(variant: Variant, catalogue: Catalogue) -> str:
    """The model a preset variant means on this installation.

    A candidate is preferred over the catalogue's own best because the
    candidates are the models this pipeline has been tuned and measured
    against; the architecture fallback only matters when every one of them has
    been renamed or withdrawn upstream.
    """
    for candidate in variant.candidates:
        if catalogue.by_filename(candidate) is not None:
            return candidate
    best = catalogue.best_of(variant.architecture)
    if best is not None:
        return best.filename
    # No catalogue at all, which is the state before the runtime is installed.
    # The first candidate is still the intended answer; it just cannot be
    # confirmed yet, and is re-resolved once the catalogue loads.
    return variant.candidates[0] if variant.candidates else DEFAULT_MODEL


def apply_preset(
    settings: Settings,
    item: Preset,
    catalogue: Catalogue,
    *,
    accelerates_torch: bool = True,
) -> Settings:
    """Return `settings` reconfigured for one preset, discarding hand tuning.

    `accelerates_torch` is `Acceleration.accelerates_torch` for the machine
    this will run on; it decides which variant expresses the preset here.
    """
    variant = item.resolve(accelerates_torch=accelerates_torch)
    model = resolve_preset_model(variant, catalogue)
    architecture = catalogue.architecture_of(model) or variant.architecture
    applicable = {
        option.name: option
        for _, options in Settings().options(architecture)
        for option in options
    }
    # An override for another architecture must not reach the command line, and
    # one that already matches the default is noise in the stored settings.
    values = {
        name: value for name, value in variant.values.items()
        if name in applicable and value != applicable[name].default
    }
    return replace(settings, model=model, values=values, mode=item.key)


def load_settings(path: pathlib.Path) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return Settings()
    model = data.get("model")
    accelerator = data.get("accelerator")
    values = data.get("values")
    mode = LEGACY_MODES.get(data.get("mode"), data.get("mode"))
    known = set(known_option_names())
    return Settings(
        model=model if isinstance(model, str) and model else DEFAULT_MODEL,
        accelerator=accelerator if isinstance(accelerator, str) and accelerator else "auto",
        # A setting written by a later version must not reach the command line.
        values={key: value for key, value in (values or {}).items() if key in known}
        if isinstance(values, dict) else {},
        # Settings written before presets existed carry no mode, and describing
        # them as a preset would misreport what they hold. A renamed preset is
        # the other case: the mode is still a preset, just not under the name
        # it was stored as, and `LEGACY_MODES` above maps it back. The values
        # stored beside it can be the previous preset's rather than the current
        # one's, which `apply_preset` replaces wholesale on the next
        # reconciliation.
        mode=mode if mode in {item.key for item in PRESETS} | {CUSTOM_MODE} else CUSTOM_MODE,
    )


def save_settings(path: pathlib.Path, settings: Settings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "model": settings.model,
        "accelerator": settings.accelerator,
        "mode": settings.mode,
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
