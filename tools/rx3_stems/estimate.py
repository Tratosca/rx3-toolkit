# SPDX-License-Identifier: MPL-2.0
"""How long separation takes, estimated up front and corrected while it runs.

Separation cost is proportional to the audio it reads, and the constant of
proportionality depends almost entirely on two things: the model architecture
and whether inference lands on a GPU. That constant is expressed here as a
*rate*: seconds of computation per second of audio. The seeded table is only a
starting point, deliberately pessimistic; the first completed track replaces it
with what the machine actually did, and the measurement is kept so the next run
starts calibrated.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any, Iterable


THROUGHPUT_NAME = "throughput.json"
# Weight given to a fresh measurement when blending it into the running rate. A
# single track is a noisy sample - one long intro of silence separates faster
# than the song around it - so it moves the estimate without owning it.
BLEND = 0.4
# Rates below this would mean the separator ran faster than real time on every
# architecture measured, which in practice means the track was resolved from an
# existing sidecar rather than separated.
MINIMUM_RATE = 0.01
# Seconds of computation per second of audio, before this machine has measured
# anything. Deliberately keyed on the accelerator alone: which architecture is
# quicker on which device depends on whether each model's runtime reaches that
# device at all, and ordering them here would mean generalising from whatever
# hardware happened to be on hand. Nothing in this project has measured that
# across devices, so nothing here claims it.
#
# These are opening guesses and nothing more. They are rounded up, because an
# estimate that comes in early is a better failure than one that overruns, and
# each is replaced by a measurement of the real pairing after a single track.
SEED_RATES: dict[str, float] = {
    "cpu": 6.5, "cuda": 0.40, "rocm": 0.55, "mps": 0.90, "directml": 1.20,
}
DEFAULT_RATE = 6.5


def seeded_rate(architecture: str | None, accelerator: str) -> float:
    """The rate to assume before this machine has measured anything.

    `architecture` is part of the calibration key rather than the seed: rates
    are stored per architecture and accelerator, so the two are measured
    separately even though they start from the same guess.
    """
    return SEED_RATES.get(accelerator, DEFAULT_RATE)


def format_duration(seconds: float | None) -> str:
    """Phrase a duration at the precision the number actually supports."""
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return "under a minute"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"about {minutes} min"
    hours, minutes = divmod(minutes, 60)
    if not minutes:
        return f"about {hours} h"
    return f"about {hours} h {minutes:02d} min"


def format_audio_length(seconds: float) -> str:
    """Phrase an amount of audio, which is a measurement rather than a guess."""
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d}"


@dataclass
class Estimator:
    """The rate for one (architecture, accelerator) pair, refined as it runs."""

    architecture: str | None
    accelerator: str
    rate: float = 0.0
    # False until a real separation has been timed on this machine, which is
    # what separates a table lookup from a measurement.
    measured: bool = False

    def __post_init__(self) -> None:
        if self.rate <= 0.0:
            self.rate = seeded_rate(self.architecture, self.accelerator)

    @property
    def key(self) -> str:
        return f"{self.architecture or 'unknown'}/{self.accelerator}"

    def remaining(self, audio_seconds: float) -> float | None:
        """Computation time left for `audio_seconds` of unprocessed audio.

        None rather than zero when there is no audio to go on: an export
        without `TotalTime` must not be reported as almost finished.
        """
        if audio_seconds <= 0:
            return None
        return audio_seconds * self.rate

    def observe(self, audio_seconds: float, elapsed: float) -> None:
        """Fold one completed separation into the rate.

        The first measurement replaces the seeded guess outright; later ones
        are blended, so a single unusual track cannot swing the estimate.
        """
        if audio_seconds <= 0 or elapsed <= 0:
            return
        rate = elapsed / audio_seconds
        if rate < MINIMUM_RATE:
            return
        self.rate = rate if not self.measured else (
            self.rate * (1 - BLEND) + rate * BLEND
        )
        self.measured = True


def load_rates(path: pathlib.Path) -> dict[str, float]:
    """Read the measured rates, treating any damage as no measurement at all."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: float(value) for key, value in data.items()
        if isinstance(key, str) and isinstance(value, (int, float)) and value > 0
    }


def save_rates(path: pathlib.Path, rates: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({key: round(value, 4) for key, value in sorted(rates.items())}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def estimator_for(
    path: pathlib.Path, architecture: str | None, accelerator: str
) -> Estimator:
    """Build an estimator, preferring what this machine measured previously."""
    estimator = Estimator(architecture, accelerator)
    measured = load_rates(path).get(estimator.key)
    if measured:
        estimator.rate = measured
        estimator.measured = True
    return estimator


def remember(path: pathlib.Path, estimator: Estimator) -> None:
    """Persist a measured rate. An unmeasured one carries no information."""
    if not estimator.measured:
        return
    rates = load_rates(path)
    rates[estimator.key] = estimator.rate
    try:
        save_rates(path, rates)
    except OSError:
        # A missing calibration only costs a coarser estimate next time, which
        # is not worth failing a finished job over.
        pass


@dataclass(frozen=True)
class Forecast:
    """What a playlist is expected to cost, before anything has run."""

    tracks: int = 0
    audio_seconds: float = 0.0
    seconds: float | None = None
    # False while the estimate still comes from the seeded table rather than
    # from a separation this machine has actually timed.
    measured: bool = False

    @property
    def summary(self) -> str:
        if not self.tracks:
            return ""
        parts = [f"{self.tracks} track{'s' if self.tracks != 1 else ''}"]
        if self.audio_seconds:
            parts.append(f"{format_audio_length(self.audio_seconds)} of audio")
        if self.seconds is not None and self.audio_seconds:
            estimate = format_duration(self.seconds)
            parts.append(estimate if self.measured else f"{estimate} (rough)")
        return " · ".join(parts)


def forecast(tracks: Iterable[Any], estimator: Estimator) -> Forecast:
    """Estimate a whole playlist from the durations its export carries.

    A Rekordbox export without `TotalTime` leaves the durations at zero, which
    yields no estimate rather than a fabricated one.
    """
    durations = [max(0, int(getattr(track, "duration", 0) or 0)) for track in tracks]
    audio = float(sum(durations))
    return Forecast(
        tracks=len(durations),
        audio_seconds=audio,
        seconds=estimator.remaining(audio),
        measured=estimator.measured,
    )
