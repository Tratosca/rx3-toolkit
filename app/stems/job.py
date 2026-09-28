# SPDX-License-Identifier: MPL-2.0
"""Generation pipeline: separate a playlist locally and write `RX3_STEMS`."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Sequence

from app.localization import LocalizedError, Message, error_message
from app.stems import audition, limits, safety, cache, waveform, package, wave_settings, migration
from app.stems.processes import Control, Cancelled
from app.stems.estimate import Estimator
from app.stems.provisioning import Acceleration, Runtime, resolve_acceleration
from app.stems.rekordbox import Collection, Playlist, Track, export_stem
from app.stems.engine import AudioSeparatorEngine, configuration, PREFIX, model_identity, runtime_identity, OutputError
from app.stems.separation import Settings, input_normalization
from app.stems.stem import PREPARED_ROLES, ROLE_ORDER, ROLE_SUFFIXES, count_frames, write_stem


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


def role_label(role: str) -> Message:
    """A role as the interface names it, never its identifier."""
    return Message({"vocals": "stems.roleVocals", "drums": "stems.roleDrums"}.get(role, "stems.listenRest"))


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
    provenance: dict | None = None

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
            **(self.provenance or {}),
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
        waveforms: bool = True,
        upgrade_existing: bool = False,
        overcue_export=None,
        architecture: str | None = None,
        acceleration: Acceleration | None = None,
        estimator: Estimator | None = None,
        observer: Callable[[JobState], None] = lambda state: None,
    ) -> None:
        self.upgrade_existing = upgrade_existing
        self.overcue_export = overcue_export
        self.waveforms = waveforms
        self.runtime = runtime
        self.collection = collection
        self.playlist = playlist
        self.output_root = output_root
        self.settings = settings or Settings()
        # Vocals is not optional: it is the only role every deck build reads,
        # and a run that produced drums alone would look complete while the
        # deck found nothing to load.
        wanted = {role for role in roles if role in PREPARED_ROLES} | {"vocals"}
        self.roles = tuple(role for role in ROLE_ORDER if role in wanted)
        self.architecture = architecture
        self.acceleration = acceleration or resolve_acceleration(self.settings.accelerator)
        self.estimator = estimator or Estimator(architecture, self.acceleration.key)
        self.observer = observer
        self._lock = threading.Lock()
        self._state = JobState()
        self._process: subprocess.Popen[str] | None = None
        self._engine = AudioSeparatorEngine(runtime, configuration(self.settings, architecture, self.roles, runtime, self.acceleration))
        self._cancelled = False
        self._control = Control()
        self._started = 0.0
        # Audio the current track carries, and audio every track after it does.
        self._current_audio = 0.0
        self._later_audio = 0.0
        self._entries, self._has_manifest = cache.read_manifest(output_root)
        self._signature = cache.signature(self.settings, architecture, self.roles)
        self._identity_loaded = False

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
        self._control.cancel()

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
        self._notice(Message("stems.cpuFallback", accelerator=Message("accelerator." + self.acceleration.key)))

    def _separate(
        self, source: pathlib.Path, workspace: pathlib.Path, index: int, total: int, *, progress=None
    ) -> dict[str, pathlib.Path]:
        if self.runtime.separator is None:
            raise LocalizedError("stems.engineMissing")
        process = self._engine.submit(source, workspace)
        self._process = process
        assert process.stdout is not None
        window = ""
        transcript = ""
        head = ""
        last = -1
        line = ""
        completion = None
        # tqdm uses carriage returns rather than line feeds. Reading one
        # character at a time preserves live progress updates.
        while True:
            character = process.stdout.read(1)
            if not character:
                break
            line = (line + character)[-16384:]
            if character == "\n":
                if line.startswith(PREFIX):
                    completion = json.loads(line[len(PREFIX):])
                    break
                line = ""
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
                        if progress is not None:
                            progress(track_progress / 100)
                        else:
                            self._update(
                                track_progress=track_progress, progress=overall,
                                **self._timings(track_progress / 100),
                            )
                        last = track_progress
            if self._cancelled:
                break
        if completion is None or not completion.get("ok"):
            self._engine.close()
        self._process = None
        self._note_inference_device(head)
        self._checkpoint()
        if completion is None or not completion.get("ok"):
            raise LocalizedError("stems.separatorFailed", code=process.returncode or 1,
                                 detail=failure_detail(transcript + "\n" + (completion or {}).get("error", "")))
        try:
            return self._engine.outputs(workspace, self.roles)
        except OutputError as error:
            raise LocalizedError("stems.separatorOutput", role=role_label(error.role),
                                 count=error.count, detail=failure_detail(transcript)) from error

    def prepare_drum(self, track, workspace, *, index=0, total=1, progress=None, close_engine=True):
        """Create only the new drum payload for a legacy remux; never publish."""
        if not getattr(self, "_started", 0):
            self._started = time.monotonic()
        self._check_limits(track, track.location)
        try:
            separated = self._separate(track.location, workspace, index, total, progress=progress)
            self._checkpoint()
            output = workspace / "migration.rx3drums"
            write_stem(separated["drums"], output, ffmpeg=self.runtime.ffmpeg or "ffmpeg", sample_format="s16_gain",
                       match_full=track.location,
                       separator_normalization=input_normalization(self.settings, self.architecture))
            self._checkpoint()
            return output
        finally:
            if close_engine:
                self._engine.close()

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
            raise LocalizedError("stems.sourceMissing", name=source.name)
        # The name the track carries on the exported drive, which is the only
        # name the deck ever asks for.
        base = export_stem(source.stem)
        collision = used_names.get(base.casefold())
        if collision is not None and collision != source:
            raise LocalizedError("stems.collision", name=source.name, other=collision.name, base=base)
        used_names[base.casefold()] = source

        targets = {role: output / f"{base}{ROLE_SUFFIXES[role]}" for role in self.roles}
        for suffix in ROLE_SUFFIXES.values():
            safety.check_target(output / (base + suffix))
        self._update(stage=Message("stems.hashing"), track_progress=0)
        before = safety.source_stamp(source, progress=lambda done, size: (
            self._checkpoint(), self._update(track_progress=round(done * 100 / max(1, size)))))
        previous = next((entry for entry in self._entries if entry.get("stem") == targets["vocals"].name), None)
        if self.upgrade_existing and self.roles == ("vocals", "drums"):
            # A known changed source cannot inherit legacy PCM. Modern packages
            # carry their own source identity, even if the outer manifest is lost.
            legacy_changed = (previous and previous.get("source_sha256") and
                              previous["source_sha256"] != before[2] and
                              targets["vocals"].is_file() and not package.is_package(targets["vocals"]))
            def report(stage, fraction):
                self._checkpoint()
                self._update(stage=Message("stems.migrationStage." + stage, name=track.title),
                             track_progress=round(fraction * 100),
                             progress=round((index + fraction) * 100 / total))
            upgraded = None if legacy_changed else migration.ensure_three(
                track, self.output_root, before, self.runtime.ffmpeg or "ffmpeg", self._checkpoint,
                lambda track, work: self.prepare_drum(
                    track, work, index=index, total=total, close_engine=False,
                    progress=lambda fraction: report("drums", .1 + .4 * fraction)),
                self._signature, report)
            if upgraded:
                status, metadata = upgraded
                self._update(stage=Message("stems.verified"), track_progress=100)
                safety.check_source(source, before)
                return self._result(track, {role: targets["vocals"] for role in self.roles},
                                    status, before, metadata, preserve_processing=True)
        known = previous is not None and previous.get("source_sha256") is not None
        matching = not self.upgrade_existing and known and previous.get("source_sha256") == before[2] and previous.get("processing") == self._signature
        verified = cache.verified_files(output, previous, self.roles) if matching else None
        current_waveform = (verified and package.is_package(targets["vocals"]) and
                            (not self.waveforms or wave_settings.supports(package.read(targets["vocals"])["waveform"])))
        if current_waveform:
            safety.check_source(source, before)
            self._update(stage=Message("stems.verified"), track_progress=100)
            return self._result(track, {r: targets["vocals"] for r in self.roles}, "existing", before, previous)
        imported = (not self.upgrade_existing and known and previous.get("origin") == "imported" and
                    previous.get("source_sha256") == before[2] and
                    cache.verified_files(output, previous, self.roles))
        if imported:
            # Keep the operator's PCM and import identity. Only the waveform
            # member may need rebuilding; never substitute a separator's output.
            parsed = package.read(targets["vocals"]) if package.is_package(targets["vocals"]) else None
            if parsed and (not self.waveforms or wave_settings.supports(parsed["waveform"])):
                safety.check_source(source, before)
                self._notice(Message("stems.importedKept", name=source.name))
                return self._result(track, {r: targets["vocals"] for r in self.roles}, "existing", before, previous)
            verified = imported
        if not self.upgrade_existing and not known and (not self._has_manifest or previous is not None) and \
                self._present_roles(targets["vocals"]) == self.roles:
            self._notice(Message("stems.unverified", name=source.name))
            # An old stem cannot acquire proof by merely hashing today's source.
            paths = self._present_files(targets)
            return TrackResult(track.track_id, track.artist, track.title, source.name,
                               tuple(Stem(role, path.name, path.stat().st_size) for role, path in paths.items()),
                               "existing")
        if verified:
            self._notice(Message("stems.waveUpgrade", name=source.name))
        elif previous is not None or any(path.exists() for path in targets.values()):
            self._notice(Message("stems.regenerating", name=source.name))
        frames = self._check_limits(track, source)
        safety.require_space(output, len(self.roles) * (frames * 4 + 64) if frames else
                             safety.estimated_bytes(track, len(self.roles), self.runtime.ffmpeg or "ffmpeg"))
        with tempfile.TemporaryDirectory(prefix="rx3-stem-") as directory:
            workspace = pathlib.Path(directory)
            hit = ((verified, previous) if verified else
                   cache.find(before[2], self._signature, self.roles, self.output_root, workspace))
            metadata = {"gainCorrection": 1.0, "encoderDelayFrames": 0, "stems": []}
            if hit:
                prepared, metadata = hit
                status = "reused"
                self._notice(Message("stems.reusing", name=source.name))
            else:
                status = "created"
                self._update(stage=Message("stems.separating"), track_progress=1)
                separated = self._separate(source, workspace, index, total)
                if self._identity_loaded and any(v is None for v in self._signature["model_assets"].values()):
                    self._signature["model_assets"] = model_identity(self.runtime, self.settings)
                prepared = {}
                for position, role in enumerate(self.roles):
                    self._checkpoint()
                    self._update(stage=Message("stems.encoding", role=role_label(role)), track_progress=min(96 + position, 99))
                    local = workspace / targets[role].name
                    encoded = write_stem(separated[role], local,
                                         ffmpeg=self.runtime.ffmpeg or "ffmpeg", sample_format="s16_gain",
                                         match_full=source, separator_normalization=input_normalization(self.settings, self.architecture))
                    prepared[role] = local
                    # The decoded length is exact from here on; the waveforms
                    # still to compute are not spent on a refused package.
                    limits.require(audition.header(local), len(self.roles), waveforms=self.waveforms)
                    metadata["gainCorrection"], metadata["encoderDelayFrames"] = encoded.gain, encoded.delay
                    metadata["stems"].append({"role": role, "clippedSamples": encoded.clipped, "playbackGain": encoded.playback_gain})
                    if not encoded.aligned:
                        self._notice(Message("stems.alignmentUnknown", name=source.name))
                    if encoded.clipped:
                        self._notice(Message("stems.clipped", name=source.name, count=encoded.clipped))
            safety.check_source(source, before)
            safety.require_space(output, sum(path.stat().st_size for path in prepared.values()))
            self._update(stage=Message("stems.wavePreparing" if self.waveforms else "stems.packaging"), eta_seconds=None)
            package_metadata = {"gainCorrection": metadata.get("gainCorrection", 1.0),
                                "encoderDelayFrames": metadata.get("encoderDelayFrames", 0),
                                "processing": self._signature}
            if metadata.get("origin") == "imported":
                package_metadata.update({key: metadata[key] for key in
                                         ("origin", "processing", "checks", "import_sha256") if key in metadata})
            local_package = package.build(track, output.parent, prepared, workspace, before[2],
                                          self.runtime.ffmpeg or "ffmpeg", self._checkpoint,
                                          package_metadata, waveforms=self.waveforms)
            safety.check_source(source, before)
            self._checkpoint()
            package.publish(local_package, targets["vocals"])
            targets = {role: targets["vocals"] for role in self.roles}
            result = self._result(track, targets, status, before, metadata)
            try:
                cache.remember(output, result.as_manifest_entry(), self.roles)
            except OSError:
                self._notice(Message("stems.cacheUnavailable"))
            return result

    def _present_roles(self, container: pathlib.Path) -> tuple[str, ...] | None:
        """The roles already on the drive for this track, whichever format holds them.

        A v2 package names its roles itself; the separate files it replaced are
        gone once it is published, and their absence says nothing about it.
        """
        try:
            if container.is_file() and package.is_package(container):
                return package.read(container)["roles"]
        except (OSError, ValueError, LocalizedError):
            return None
        files = self._present_files({role: container.with_suffix(ROLE_SUFFIXES[role]) for role in ROLE_ORDER})
        return tuple(files) or None

    def _present_files(self, targets):
        if targets["vocals"].is_file() and package.is_package(targets["vocals"]):
            return {role: targets["vocals"] for role in self.roles}
        present = {}
        for role, path in targets.items():
            if not (path.is_file() and path.stat().st_size > MINIMUM_STEM_BYTES):
                break
            present[role] = path
        return present

    def _check_limits(self, track, source):
        """Refuse a track the deck would reject, before separating it.

        The listed duration settles most tracks. One too close to a limit to
        tell, or with no duration at all, is decoded once and counted exactly;
        that count is returned, and None when the listing sufficed.
        """
        verdict = limits.estimate(track.duration, len(self.roles), waveforms=self.waveforms)
        frames = None
        if verdict.status in ("near", "unknown"):
            self._update(stage=Message("stems.measuring"))
            frames = count_frames(source, self.runtime.ffmpeg or "ffmpeg", self._checkpoint)
            verdict = limits.assess(frames, len(self.roles), waveforms=self.waveforms)
        if verdict.refused:
            raise limits.LimitError(verdict.message(len(self.roles)))
        if verdict.status == "shared":
            self._notice(Message("stems.trackNotice", name=source.name,
                                 detail=verdict.message(len(self.roles))))
        return frames

    def _result(self, track, targets, status, before, metadata, *, preserve_processing=False):
        return TrackResult(
            track.track_id, track.artist, track.title, track.location.name,
            tuple(Stem(role, path.name, path.stat().st_size,
                       next((item.get("clippedSamples", 0) for item in metadata.get("stems", []) if item.get("role") == role), 0),
                       safety.digest(path)) for role, path in targets.items()),
            status, metadata.get("gainCorrection", 1.0), metadata.get("encoderDelayFrames", 0),
            before[2], before[0], metadata.get("processing") if preserve_processing or metadata.get("origin") == "imported" else self._signature,
            {key: metadata[key] for key in ("origin", "checks", "import_sha256", "separation_provenance", "drum_processing") if key in metadata}
            if preserve_processing or metadata.get("origin") == "imported" else None,
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
        with self._control.bind():
            return self._run()

    def _run(self) -> JobState:
        """Process every track, recording per-track failures without stopping."""
        try:
            self._checkpoint()
            safety.require_library_closed()
            self._signature["runtime"] = runtime_identity(self.runtime)
            self._signature["model_assets"] = model_identity(self.runtime, self.settings)
            self._identity_loaded = True
            tracks = self.playlist.tracks
            if not tracks:
                raise LocalizedError("stems.playlistEmpty")
            output = self.output_root / OUTPUT_NAME
            safety.check_target(output / MANIFEST_NAME)
            try:
                output.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise LocalizedError("stems.outputUnavailable", path=str(output),
                                     detail=error.strerror or str(error)) from error
            safety.clean_metadata(output)
            self._started = time.monotonic()
            durations = [float(max(0, track.duration or 0)) for track in tracks]
            self._current_audio = 0.0
            self._later_audio = sum(durations)
            self._update(
                state="running", total=len(tracks), output=output, stage=Message("stems.stagePreparing"),
                **self._timings(0.0),
            )

            results: list[TrackResult] = []
            errors: list[TrackError] = []
            used_names: dict[str, pathlib.Path] = {}
            for index, track in enumerate(tracks):
                self._checkpoint()
                if not output.is_dir():
                    raise LocalizedError("stems.outputGone", path=str(output))
                self._current_audio = durations[index]
                self._later_audio = sum(durations[index + 1:])
                self._update(
                    current=track.label, completed=index, position=index + 1,
                    track_progress=0, progress=round(index / len(tracks) * 100),
                    stage=Message("stems.stageChecking"), **self._timings(0.0),
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
                    if self.overcue_export is not None:
                        self._checkpoint()
                        self._update(stage=Message("stems.overcuePreparing"),
                                     track_progress=0, eta_seconds=None)
                        try:
                            self.overcue_export(track, output / (export_stem(track.location.stem) + STEM_SUFFIX),
                                                self.runtime.ffmpeg or "ffmpeg", self._checkpoint)
                        except Cancelled:
                            raise
                        except Exception:
                            self._notice(Message("stems.overcueRx3Kept", name=track.title))
                            raise
                except Cancelled:
                    raise
                except Exception as error:
                    self._engine.close()
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
        finally:
            self._engine.close()
            self._process = None
        return self.state
