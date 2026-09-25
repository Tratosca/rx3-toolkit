# SPDX-License-Identifier: MPL-2.0
"""Generation pipeline: separate a playlist locally and write `RX3_STEMS`."""

from __future__ import annotations

import json
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Sequence

from app.localization import Message, error_message
from app.rx3_stems import safety, cache
from app.rx3_stems.estimate import Estimator
from app.rx3_stems.provisioning import Acceleration, Runtime, resolve_acceleration
from app.rx3_stems.rekordbox import Collection, Playlist, Track, export_stem
from app.rx3_stems.separation import ROLE_STEMS, VOCAL_STEM, Settings, input_normalization
from app.rx3_stems.stem import ROLE_ORDER, ROLE_SUFFIXES, write_stem


MANIFEST_NAME = "rx3-stems-manifest.json"
OUTPUT_NAME = "RX3_STEMS"
STEM_SUFFIX = ROLE_SUFFIXES["vocals"]
# A shorter file cannot hold the stem header, so it is treated as incomplete.
MINIMUM_STEM_BYTES = 64
PERCENT = re.compile(r"(\d{1,3})%")
# Percent detection only needs to see the current tqdm bar, but a failure has to
# be explained from the same stream, and tqdm floods it with carriage returns.
PERCENT_WINDOW = 96
TRANSCRIPT_LIMIT = 16384
REPORTED_DETAIL = 600
# The separator reports its inference device in its first lines, well before
# the rolling transcript window starts dropping anything.
HEAD_LIMIT = 8192
CPU_FALLBACK = "No hardware acceleration could be configured"


def failure_detail(transcript: str) -> str:
    """Summarise a separator transcript, dropping its progress-bar noise."""
    lines = [
        line.strip() for line in transcript.replace("\r", "\n").splitlines()
        if line.strip() and "%|" not in line
    ]
    if not lines:
        return "no output"
    # The final traceback line names the exception, which is what identifies
    # the failure; anything before it is context.
    detail = " / ".join(lines[-6:])
    return detail[-REPORTED_DETAIL:]


@dataclass(frozen=True)
class Stem:
    """One container written for one track, named after the role it holds."""

    role: str
    name: str
    size: int
    # Samples this stem alone pushed past full scale, which only the container
    # it was written into can report.
    clipped: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class TrackResult:
    track_id: str
    artist: str
    title: str
    source_file: str
    # Vocals first, so `stem` below names the one every deck build reads.
    stems: tuple[Stem, ...]
    status: str
    # Correction applied to keep the stems in the gain domain of the source.
    # It is measured from the source, so every role carries the same one.
    gain: float = 1.0
    # Encoder padding the stems were pushed back by to land on the deck's grid,
    # also measured from the source and so also shared.
    delay: int = 0
    source_sha256: str | None = None
    source_bytes: int | None = None
    processing: dict | None = None

    @property
    def stem(self) -> str:
        """The vocal container, which is what a single-stem deck asks for."""
        return self.stems[0].name

    @property
    def size(self) -> int:
        return self.stems[0].size

    @property
    def clipped(self) -> int:
        return sum(entry.clipped for entry in self.stems)

    def as_manifest_entry(self) -> dict[str, object]:
        return {
            "trackId": self.track_id, "artist": self.artist, "title": self.title,
            "sourceFile": self.source_file, "stem": self.stem,
            "bytes": self.size, "status": self.status,
            "gainCorrection": round(self.gain, 6), "clippedSamples": self.clipped,
            "encoderDelayFrames": self.delay,
            "source_sha256": self.source_sha256, "source_bytes": self.source_bytes,
            "processing": self.processing,
            "stems": [
                {"role": entry.role, "file": entry.name, "bytes": entry.size,
                 "clippedSamples": entry.clipped, "sha256": entry.sha256}
                for entry in self.stems
            ],
        }


@dataclass(frozen=True)
class TrackError:
    track: str
    error: str


@dataclass(frozen=True)
class JobState:
    state: str = "idle"
    stage: str = ""
    current: str = ""
    progress: int = 0
    track_progress: int = 0
    # How many tracks are finished, which is what the closing summary counts.
    completed: int = 0
    # Which track `current` is, counting from one. Reporting `completed` beside
    # the name of the track being worked on reads as an off-by-one, because it
    # answers a different question.
    position: int = 0
    total: int = 0
    # Computation left, from a rate this machine measured where it could.
    eta_seconds: float | None = None
    elapsed_seconds: float = 0.0
    output: pathlib.Path | None = None
    manifest: pathlib.Path | None = None
    fatal: str = ""
    results: tuple[TrackResult, ...] = field(default=())
    errors: tuple[TrackError, ...] = field(default=())
    # Conditions worth telling the operator about that are not failures.
    notices: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict:
        """The snapshot as plain values, for an interface that is not Python.

        Paths and the two result tuples do not survive a JSON boundary on their
        own, and an interface that has to know that is an interface coupled to
        this module. Everything else passes through unchanged.
        """
        return {
            "state": self.state,
            "stage": self.stage,
            "current": self.current,
            "progress": self.progress,
            "trackProgress": self.track_progress,
            "completed": self.completed,
            "position": self.position,
            "total": self.total,
            "etaSeconds": self.eta_seconds,
            "elapsedSeconds": self.elapsed_seconds,
            "output": str(self.output) if self.output else None,
            "manifest": str(self.manifest) if self.manifest else None,
            "fatal": self.fatal,
            "results": [item.as_manifest_entry() for item in self.results],
            "errors": [
                {"track": item.track, "error": item.error}
                for item in self.errors
            ],
            "notices": list(self.notices),
        }


class Cancelled(Exception):
    """The operator stopped the job."""


class StemJob:
    """Run one playlist through separation and stem encoding."""

    def __init__(
        self,
        runtime: Runtime,
        collection: Collection,
        playlist: Playlist,
        output_root: pathlib.Path,
        *,
        settings: Settings | None = None,
        roles: Sequence[str] = ("vocals",),
        architecture: str | None = None,
        acceleration: Acceleration | None = None,
        estimator: Estimator | None = None,
        observer: Callable[[JobState], None] = lambda state: None,
    ) -> None:
        self.runtime = runtime
        self.collection = collection
        self.playlist = playlist
        self.output_root = output_root
        self.settings = settings or Settings()
        # Vocals is not optional: it is the only role every deck build reads,
        # and a run that produced drums alone would look complete while the
        # deck found nothing to load.
        wanted = {role for role in roles if role in ROLE_SUFFIXES} | {"vocals"}
        if "bass" in wanted:
            wanted.add("drums")
        self.roles = tuple(role for role in ROLE_ORDER if role in wanted)
        self.architecture = architecture
        self.acceleration = acceleration or resolve_acceleration(self.settings.accelerator)
        self.estimator = estimator or Estimator(architecture, self.acceleration.key)
        self.observer = observer
        self._lock = threading.Lock()
        self._state = JobState()
        self._process: subprocess.Popen[str] | None = None
        self._cancelled = False
        self._started = 0.0
        # Audio the current track carries, and audio every track after it does.
        self._current_audio = 0.0
        self._later_audio = 0.0
        self._entries, self._has_manifest = cache.read_manifest(output_root)
        self._signature = cache.signature(self.settings, architecture, self.roles)

    @property
    def state(self) -> JobState:
        with self._lock:
            return self._state

    def _update(self, **values: object) -> None:
        with self._lock:
            self._state = replace(self._state, **values)
            snapshot = self._state
        self.observer(snapshot)

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process is not None and process.poll() is None:
            # Windows only delivers SIGINT to a dedicated process group, so the
            # separator is terminated directly there.
            if sys.platform == "win32":
                process.terminate()
            else:
                process.send_signal(signal.SIGINT)

    def _checkpoint(self) -> None:
        if self._cancelled:
            raise Cancelled("Cancelled")

    def _timings(self, track_fraction: float) -> dict[str, object]:
        """Elapsed time, and the computation the rest of the playlist needs.

        The current track contributes only the share of its audio that has not
        been read yet, so the estimate falls smoothly rather than in steps.
        """
        remaining = self._later_audio + self._current_audio * max(0.0, 1.0 - track_fraction)
        elapsed = time.monotonic() - self._started if self._started else 0.0
        return {
            "eta_seconds": self.estimator.remaining(remaining),
            "elapsed_seconds": elapsed,
        }

    def _notice(self, message: str) -> None:
        """Record a condition once, however many tracks reproduce it."""
        if message not in self._state.notices:
            self._update(notices=self._state.notices + (message,))

    def _note_inference_device(self, head: str) -> None:
        """Say so when an accelerated runtime silently ran on the CPU.

        audio-separator chooses its device from `torch.cuda.is_available()` and
        reports the outcome at INFO level, which nothing here would otherwise
        show; the run just takes an order of magnitude longer.
        """
        if self.acceleration.key == "cpu" or CPU_FALLBACK not in head:
            return
        self._notice(
            f"{self.acceleration.label} was selected but the separator found no "
            "usable device and ran on the CPU. Install the separation runtime "
            "again for this accelerator, which rebuilds PyTorch for it."
        )

    def _separate(
        self, source: pathlib.Path, workspace: pathlib.Path, index: int, total: int
    ) -> dict[str, pathlib.Path]:
        if self.runtime.separator is None:
            raise RuntimeError("audio-separator is not installed")
        command = [
            str(self.runtime.separator), str(source),
            f"--model_file_dir={self.runtime.models}",
            f"--output_dir={workspace}",
            "--output_format=WAV",
            # Asking for one stem lets the separator skip reconstructing the
            # others, so the vocal-only run stays as cheap as it ever was.
            *([f"--single_stem={VOCAL_STEM}"] if self.roles == ("vocals",) else []),
            *self.settings.arguments(self.architecture),
            *self.acceleration.separation_flags,
        ]
        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=self.runtime.subprocess_environment(),
            )
        except OSError as error:
            # A relocated virtual environment leaves the launcher in place with
            # a dangling interpreter, which surfaces as a bare ENOENT.
            raise RuntimeError(
                f"audio-separator could not be started from {self.runtime.separator}: "
                f"{error}. Install the separation runtime again."
            ) from error
        self._process = process
        assert process.stdout is not None
        window = ""
        transcript = ""
        head = ""
        last = -1
        # tqdm uses carriage returns rather than line feeds. Reading one
        # character at a time preserves live progress updates.
        while True:
            character = process.stdout.read(1)
            if not character:
                break
            window = (window + character)[-PERCENT_WINDOW:]
            transcript = (transcript + character)[-TRANSCRIPT_LIMIT:]
            if len(head) < HEAD_LIMIT:
                head += character
            if character == "%":
                match = PERCENT.search(window)
                if match:
                    track_progress = min(int(match.group(1)), 95)
                    if track_progress != last:
                        overall = round(((index + track_progress / 100) / total) * 100)
                        self._update(
                            track_progress=track_progress, progress=overall,
                            **self._timings(track_progress / 100),
                        )
                        last = track_progress
            if self._cancelled:
                break
        return_code = process.wait()
        self._process = None
        self._note_inference_device(head)
        self._checkpoint()
        if return_code:
            raise RuntimeError(
                f"audio-separator exited with code {return_code}: "
                f"{failure_detail(transcript)}"
            )
        # The output name carries the stem and a truncated model name, so each
        # WAV in the private workspace says which role it holds.
        candidates = sorted(workspace.rglob("*.wav"))
        if self.roles == ("vocals",):
            if len(candidates) != 1:
                raise RuntimeError(
                    f"Expected one separated stem, found {len(candidates)}: "
                    f"{failure_detail(transcript)}"
                )
            return {"vocals": candidates[0]}
        separated: dict[str, pathlib.Path] = {}
        for role in self.roles:
            marker = f"({ROLE_STEMS[role]})".casefold()
            matches = [item for item in candidates if marker in item.name.casefold()]
            if len(matches) != 1:
                raise RuntimeError(
                    f"Expected one {ROLE_STEMS[role]} stem, found {len(matches)}: "
                    f"{failure_detail(transcript)}"
                )
            separated[role] = matches[0]
        return separated

    def _process_track(
        self,
        track: Track,
        index: int,
        total: int,
        output: pathlib.Path,
        used_names: dict[str, pathlib.Path],
    ) -> TrackResult:
        safety.require_library_closed()
        source = track.location
        if not source.is_file():
            raise FileNotFoundError("Source file not found")
        # The name the track carries on the exported drive, which is the only
        # name the deck ever asks for.
        base = export_stem(source.stem)
        collision = used_names.get(base.casefold())
        if collision is not None and collision != source:
            raise ValueError(
                f"Ambiguous filename with {collision.name}: both are exported as "
                f"{base}, and the RX3 load interface cannot distinguish them"
            )
        used_names[base.casefold()] = source

        targets = {role: output / f"{base}{ROLE_SUFFIXES[role]}" for role in self.roles}
        for suffix in ROLE_SUFFIXES.values():
            safety.check_target(output / (base + suffix))
        self._update(stage=Message("stems.hashing"), track_progress=0)
        before = safety.source_stamp(source, progress=lambda done, size: (
            self._checkpoint(), self._update(track_progress=round(done * 100 / max(1, size)))))
        previous = next((entry for entry in self._entries if entry.get("stem") == targets["vocals"].name), None)
        known = previous is not None and previous.get("source_sha256") is not None
        matching = known and previous.get("source_sha256") == before[2] and previous.get("processing") == self._signature
        if matching and cache.verified_files(output, previous, self.roles):
            safety.check_source(source, before)
            self._update(stage=Message("stems.verified"), track_progress=100)
            return self._result(track, targets, "existing", before, previous)
        if not known and (not self._has_manifest or previous is not None) and all(
                path.is_file() and path.stat().st_size > MINIMUM_STEM_BYTES for path in targets.values()):
            self._notice(Message("stems.unverified", name=source.name))
            # An old stem cannot acquire proof by merely hashing today's source.
            return TrackResult(track.track_id, track.artist, track.title, source.name,
                               tuple(Stem(role, path.name, path.stat().st_size) for role, path in targets.items()),
                               "existing")
        if previous is not None or any(path.exists() for path in targets.values()):
            self._notice(Message("stems.regenerating", name=source.name))
        safety.require_space(output, safety.estimated_bytes(track, len(self.roles), self.runtime.ffmpeg or "ffmpeg"))
        with tempfile.TemporaryDirectory(prefix="rx3-stem-") as directory:
            workspace = pathlib.Path(directory)
            hit = cache.find(before[2], self._signature, self.roles, self.output_root, workspace)
            metadata = {"gainCorrection": 1.0, "encoderDelayFrames": 0, "stems": []}
            if hit:
                prepared, metadata = hit
                status = "reused"
                self._notice(Message("stems.reusing", name=source.name))
            else:
                status = "created"
                self._update(stage=Message("stems.separating"), track_progress=1)
                separated = self._separate(source, workspace, index, total)
                prepared = {}
                for position, role in enumerate(self.roles):
                    self._checkpoint()
                    self._update(stage=Message("stems.encoding", role=role), track_progress=min(96 + position, 99))
                    local = workspace / targets[role].name
                    encoded = write_stem(separated[role], local,
                                         ffmpeg=self.runtime.ffmpeg or "ffmpeg", sample_format="s16",
                                         match_full=source, separator_normalization=input_normalization(self.settings, self.architecture))
                    prepared[role] = local
                    metadata["gainCorrection"], metadata["encoderDelayFrames"] = encoded.gain, encoded.delay
                    metadata["stems"].append({"role": role, "clippedSamples": encoded.clipped})
                    if not encoded.aligned:
                        self._notice(Message("stems.alignmentUnknown", name=source.name))
                    if encoded.clipped:
                        self._notice(Message("stems.clipped", name=source.name, count=encoded.clipped))
            safety.check_source(source, before)
            safety.require_space(output, sum(path.stat().st_size for path in prepared.values()))
            # Optional roles from the previous source must not survive a new
            # vocal. An interrupted publication can then only reduce the set.
            for role in reversed(ROLE_ORDER[1:]):
                old = output / (base + ROLE_SUFFIXES[role])
                safety.check_target(old)
                old.unlink(missing_ok=True)
            safety.sync_directory(output)
            for role in self.roles:
                self._checkpoint()
                safety.check_source(source, before)
                safety.publish(prepared[role], targets[role])
            result = self._result(track, targets, status, before, metadata)
            try:
                cache.remember(output, result.as_manifest_entry(), self.roles)
            except OSError:
                self._notice(Message("stems.cacheUnavailable"))
            return result

    def _result(self, track, targets, status, before, metadata):
        return TrackResult(
            track.track_id, track.artist, track.title, track.location.name,
            tuple(Stem(role, path.name, path.stat().st_size,
                       next((item.get("clippedSamples", 0) for item in metadata.get("stems", []) if item.get("role") == role), 0),
                       safety.digest(path)) for role, path in targets.items()),
            status, metadata.get("gainCorrection", 1.0), metadata.get("encoderDelayFrames", 0),
            before[2], before[0], self._signature,
        )

    def _save_manifest(self, output, result):
        self._entries = [entry for entry in self._entries if entry.get("stem") != result.stem]
        self._entries.append(result.as_manifest_entry())
        manifest = output / MANIFEST_NAME
        contents = json.dumps({"format": 2, "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                               "tracks": self._entries}, ensure_ascii=False, indent=2) + "\n"
        with tempfile.TemporaryDirectory(prefix="rx3-manifest-") as directory:
            local = pathlib.Path(directory) / MANIFEST_NAME
            local.write_text(contents, encoding="utf-8")
            safety.publish(local, manifest)
        self._update(manifest=manifest)

    def run(self) -> JobState:
        """Process every track, recording per-track failures without stopping."""
        try:
            safety.require_library_closed()
            tracks = self.playlist.tracks
            if not tracks:
                raise ValueError("The playlist is empty")
            output = self.output_root / OUTPUT_NAME
            safety.check_target(output / MANIFEST_NAME)
            try:
                output.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise RuntimeError(
                    f"{output} could not be created: {error.strerror or error}. "
                    "Choose a writable output folder or mounted USB drive."
                ) from error
            safety.clean_metadata(output)
            self._started = time.monotonic()
            durations = [float(max(0, track.duration or 0)) for track in tracks]
            self._current_audio = 0.0
            self._later_audio = sum(durations)
            self._update(
                state="running", total=len(tracks), output=output, stage="Preparing",
                **self._timings(0.0),
            )

            results: list[TrackResult] = []
            errors: list[TrackError] = []
            used_names: dict[str, pathlib.Path] = {}
            for index, track in enumerate(tracks):
                self._checkpoint()
                if not output.is_dir():
                    raise RuntimeError(
                        f"The output directory disappeared: {output}. "
                        "The USB drive was most likely unmounted."
                    )
                self._current_audio = durations[index]
                self._later_audio = sum(durations[index + 1:])
                self._update(
                    current=track.label, completed=index, position=index + 1,
                    track_progress=0, progress=round(index / len(tracks) * 100),
                    stage="Checking", **self._timings(0.0),
                )
                track_started = time.monotonic()
                try:
                    result = self._process_track(track, index, len(tracks), output, used_names)
                    self._save_manifest(output, result)
                    results.append(result)
                    # Only a separation that actually ran says anything about
                    # how fast this machine separates; a resumed stem is
                    # instantaneous and would collapse the rate to nothing.
                    if result.status == "created":
                        self.estimator.observe(
                            durations[index], time.monotonic() - track_started
                        )
                    self._update(results=tuple(results))
                except Cancelled:
                    raise
                except Exception as error:
                    errors.append(TrackError(track=track.label, error=error_message(error)))
                    self._update(errors=tuple(errors))
                    if isinstance(error, safety.SpaceError):
                        raise
                self._current_audio = 0.0
                self._update(
                    completed=index + 1, track_progress=100,
                    progress=round((index + 1) / len(tracks) * 100),
                    **self._timings(1.0),
                )

            self._update(
                state="done", stage="Finished", current="", progress=100,
                completed=len(tracks), position=len(tracks),
                eta_seconds=0.0, elapsed_seconds=time.monotonic() - self._started,
            )
        except Cancelled:
            self._update(state="cancelled", stage="Cancelled", current="")
        except Exception as error:
            self._update(
                state="failed", stage="Error", current="",
                fatal=error_message(error),
            )
        return self.state
