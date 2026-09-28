# SPDX-License-Identifier: MPL-2.0
"""Separating a playlist into the stems a deck plays.

The job itself already had the right shape and needed no rewriting: a frozen
snapshot replaced under a lock, an observer called with it, and a cancel that
signals the separator and stops at a checkpoint. What was missing is the naming,
so an interface can drive it without importing five modules and knowing which
of them owns the thread.

Everything long-running here is started by the caller's thread. That is
deliberate: an interface has its own idea of where work belongs, and a service
that spawns threads decides that for it.
"""

from __future__ import annotations

from app.localization import Message, LocalizedError

import dataclasses
import pathlib

from app.stems import estimate, limits, provisioning, separation, safety, stem, overcue_option
from app.stems.job import JobState, StemJob
from app.stems.rekordbox import Collection, Playlist, parse_collection, parse_drive
from app.stems.rekordbox import has_export


@dataclasses.dataclass(frozen=True)
class Library:
    """A collection of tracks, wherever it was read from."""

    source: pathlib.Path
    tracks: int
    playlists: tuple[dict, ...]
    collection: Collection


@dataclasses.dataclass(frozen=True)
class Runtime:
    """Whether this machine can separate anything, in one sentence."""

    ready: bool
    managed: bool
    summary: str
    accelerator: str | None
    accelerators: tuple[tuple[str, str], ...]


def runtime() -> Runtime:
    detected = provisioning.detect()
    return Runtime(
        ready=detected.ready,
        managed=detected.managed,
        summary=detected.summary,
        accelerator=provisioning.installed_accelerator(),
        accelerators=provisioning.available_accelerations(),
    )


def read_library(source: pathlib.Path) -> Library:
    """A Rekordbox export, or a drive's own database.

    A drive is offered the same way as an XML file because an operator has one
    or the other and should not have to know which reader that needs.
    """
    source = pathlib.Path(source)
    collection = parse_drive(source) if source.is_dir() else parse_collection(source)
    return Library(
        source=source,
        tracks=collection.track_count,
        playlists=tuple(
            {
                "id": item.playlist_id,
                "name": item.name,
                "path": item.path,
                "tracks": len(item.tracks),
                "missing": item.missing_count,
                "label": item.label,
            }
            for item in collection.playlists
        ),
        collection=collection,
    )


def is_library(source: pathlib.Path) -> bool:
    """Whether this path is something read_library could read."""
    source = pathlib.Path(source)
    if source.is_dir():
        return has_export(source)
    return source.is_file() and source.suffix.lower() == ".xml"


def prepared_roles(roles=None) -> tuple[str, ...]:
    """The Toolkit always prepares vocals and drums; INST is reconstructed."""
    return stem.PREPARED_ROLES


def preparation_settings(current=None, catalogue=None):
    """One preparation policy, including installations with old saved presets."""
    current = current or separation.load_settings(settings_file())
    fixed = separation.Settings(model="htdemucs.yaml", accelerator=current.accelerator,
                                values={"demucs_shifts": 1}, mode=separation.QUICK_MODE)
    return separation.for_roles(fixed, catalogue, stem.PREPARED_ROLES)


def drums_blocked(settings, catalogue, accelerates_torch) -> Message | None:
    """Report missing preparation capability without offering removed modes."""
    if catalogue is None:
        return Message("stems.drumsModelUnknown")
    model = catalogue.by_filename(settings.model)
    if model is not None and {"vocals", "drums"} <= set(model.roles):
        return None
    return Message("stems.preparationUnavailable")


def forecast(library: Library, playlist_id: str, settings=None, roles=stem.PREPARED_ROLES, waveforms=True) -> dict:
    """What the run would cost, before anyone commits to it.

    Returns no estimate rather than a fabricated one when the durations are not
    in the export, which is the case that made this worth having. Each track
    also gets the loader's verdict on its package, from its listed duration.
    """
    playlist = library.collection.playlist(playlist_id)
    catalogue = _catalogue()
    settings = preparation_settings(settings, catalogue)
    waveforms = True
    accelerator = provisioning.resolve_acceleration(settings.accelerator)
    estimator = estimate.estimator_for(
        provisioning.data_directory() / "rates.json", None, accelerator.key)
    result = estimate.forecast(playlist.tracks, estimator)
    selected = prepared_roles(roles)
    count = len(selected)
    memory = []
    for track in playlist.tracks:
        verdict = limits.estimate(track.duration, count, waveforms=waveforms)
        memory.append({"id": track.track_id, "title": track.title, "artist": track.artist,
                       "status": verdict.status, "reason": verdict.reason, "total": verdict.size,
                       "message": verdict.message(count)})
    refused = sum(item["status"] == "refused" for item in memory)
    blocked = drums_blocked(settings, catalogue, accelerator.accelerates_torch)
    return {
        "tracks": result.tracks,
        "overcueStorage": overcue_option.estimate(playlist.tracks),
        "roles": list(selected),
        "memory": memory,
        "refused": refused,
        "blocked": blocked,
        "limits": {"vocals": limits.clock(limits.max_frames(1, waveforms=waveforms)),
                   "drums": limits.clock(limits.max_frames(2, waveforms=waveforms)),
                   "resident": limits.mib(limits.RESIDENT_BYTES)},
        "audioSeconds": result.audio_seconds,
        "seconds": result.seconds,
        "measured": result.measured,
        "summary": (Message("stems.forecastUnknown") if result.seconds is None else
                    Message("stems.forecastMeasured" if result.measured else "stems.forecast",
                            minutes=max(1, round(result.seconds / 60)))),
    }


def job(
    library: Library,
    playlist_id: str,
    output: pathlib.Path,
    *,
    settings=None,
    roles=stem.PREPARED_ROLES,
    waveforms=True,
    observer=lambda snapshot: None,
    tracks=None,
    overcue_compatible=False,
) -> StemJob:
    """A job ready to run, not a job running.

    `run()` is synchronous and never raises: every outcome lands in the state
    the observer receives. `cancel()` is safe at any point, because a stem
    already written is renamed into place and a partial one is removed.
    """
    safety.require_library_closed()
    playlist = (library.collection.playlist(playlist_id) if tracks is None else
                Playlist("selection", "Selection", "Selection", tuple(tracks)))
    detected = provisioning.detect()
    if not detected.ready:
        raise LocalizedError("stems.engineMissing")
    catalogue = _catalogue()
    current = preparation_settings(settings, catalogue)
    wanted = prepared_roles(roles)
    acceleration = provisioning.resolve_acceleration(current.accelerator)
    blocked = drums_blocked(current, catalogue, acceleration.accelerates_torch)
    if blocked is not None:
        raise LocalizedError(blocked.key, **blocked.params)
    architecture = catalogue.architecture_of(current.model) if catalogue else None
    additional = overcue_option.Export(output, playlist.tracks) if overcue_compatible else None
    return StemJob(
        detected, library.collection, playlist, pathlib.Path(output),
        settings=current, roles=wanted, architecture=architecture, waveforms=True,
        observer=lambda state: observer(state.as_dict()), upgrade_existing=True,
        overcue_export=additional,
    )


CATALOGUE_NAME = "models.json"


def settings_file() -> pathlib.Path:
    return provisioning.data_directory() / separation.SETTINGS_NAME


def _catalogue(refresh: bool = False):
    """The model list, from the cache when the runtime cannot be asked.

    An operator choosing a quality before installing anything is the ordinary
    case, and `load_catalogue` reads its cache before it reaches for a runtime,
    so the choice is answerable with nothing installed as long as it has been
    answered once.
    """
    cache = provisioning.data_directory() / CATALOGUE_NAME
    detected = provisioning.detect()
    if not detected.ready and not cache.is_file():
        return None
    try:
        return separation.load_catalogue(detected, cache, refresh=refresh)
    except (RuntimeError, OSError, ValueError):
        return None


def qualities(roles=None) -> dict:
    """Compatibility response for the fixed three-stem preparation policy."""
    catalogue = _catalogue()
    current = preparation_settings(catalogue=catalogue)
    acceleration = provisioning.resolve_acceleration(current.accelerator)
    return {
        "mode": current.mode, "model": current.model,
        "accelerator": current.accelerator, "custom": False,
        "drumsBlocked": drums_blocked(current, catalogue, acceleration.accelerates_torch) if catalogue else None,
        "presets": [],
        "overcue": overcue_option.status(),
    }


def choose(mode=None, accelerator=None, roles=None) -> dict:
    """Only acceleration remains configurable; stale clients cannot change policy."""
    current = preparation_settings(catalogue=_catalogue())
    if accelerator is not None:
        current = current.with_accelerator(accelerator)
    separation.save_settings(settings_file(), current)
    return qualities()


def settings() -> "separation.Settings":
    return preparation_settings(catalogue=_catalogue())


def install(accelerator: str, progress=lambda message: None) -> Runtime:
    """Put a separation runtime on this machine, or change its accelerator."""
    provisioning.provision(accelerator=accelerator, progress=progress)
    return runtime()


def remove(progress=lambda message: None) -> Runtime:
    provisioning.uninstall(progress=progress)
    return runtime()


def snapshot(state: JobState) -> dict:
    """One job state as plain values, for an interface that is not Python."""
    return state.as_dict()
