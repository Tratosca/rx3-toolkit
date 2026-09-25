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

from app.rx3_stems import estimate, provisioning, separation, safety
from app.rx3_stems.job import JobState, StemJob
from app.rx3_stems.rekordbox import Collection, parse_collection, parse_drive
from app.rx3_stems.rekordbox import has_export


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


def forecast(library: Library, playlist_id: str, settings=None, roles=("vocals",)) -> dict:
    """What the run would cost, before anyone commits to it.

    Returns no estimate rather than a fabricated one when the durations are not
    in the export, which is the case that made this worth having.
    """
    playlist = library.collection.playlist(playlist_id)
    settings = settings or separation.Settings()
    accelerator = provisioning.resolve_acceleration(settings.accelerator)
    estimator = estimate.estimator_for(
        provisioning.data_directory() / "rates.json", None, accelerator.key)
    result = estimate.forecast(playlist.tracks, estimator)
    selected = set(roles) | {"vocals"}
    if "bass" in selected:
        selected.add("drums")
    selected &= {"vocals", "drums", "bass"}
    # Half the 512 MiB shared resident cap leaves the other deck equal room.
    warning_bytes = 256 * 1024 * 1024
    memory = []
    for track in playlist.tracks:
        per_role = int(track.duration * 44100) * 4 + 64 if track.duration > 0 else None
        total = per_role * len(selected) if per_role is not None else None
        memory.append({"id": track.track_id, "title": track.title, "artist": track.artist,
                       "perRole": per_role, "total": total,
                       "warning": total is not None and total > warning_bytes})
    return {
        "tracks": result.tracks,
        "memory": memory, "memoryWarningBytes": warning_bytes,
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
    roles=("vocals",),
    observer=lambda snapshot: None,
) -> StemJob:
    """A job ready to run, not a job running.

    `run()` is synchronous and never raises: every outcome lands in the state
    the observer receives. `cancel()` is safe at any point, because a stem
    already written is renamed into place and a partial one is removed.
    """
    safety.require_library_closed()
    playlist = library.collection.playlist(playlist_id)
    detected = provisioning.detect()
    if not detected.ready:
        raise LocalizedError("stems.engineMissing")
    current = settings or separation.Settings()
    catalogue = _catalogue()
    architecture = catalogue.architecture_of(current.model) if catalogue else None
    return StemJob(
        detected, library.collection, playlist, pathlib.Path(output),
        settings=current, roles=roles, architecture=architecture,
        observer=lambda state: observer(state.as_dict()),
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


def qualities() -> dict:
    """The speed and quality trade-offs, in the terms of this machine.

    Which model expresses a preset depends on what this build accelerates, so
    the summaries are resolved here rather than quoted from a table.
    """
    current = separation.load_settings(settings_file())
    acceleration = provisioning.resolve_acceleration(current.accelerator)
    torch = acceleration.accelerates_torch
    return {
        "mode": current.mode,
        "model": current.model,
        "accelerator": current.accelerator,
        "custom": current.mode == separation.CUSTOM_MODE,
        "presets": [
            {
                "key": item.key,
                "label": Message("quality." + item.key + ".name"),
                "summary": Message("quality." + item.key + (".torch" if torch else ".light")),
            }
            for item in separation.PRESETS
        ],
    }


def choose(mode: str | None = None, accelerator: str | None = None) -> dict:
    """Store a quality, an accelerator, or both, and answer with the result."""
    path = settings_file()
    current = separation.load_settings(path)
    if accelerator is not None:
        current = current.with_accelerator(accelerator)
    if mode is not None:
        item = separation.preset(mode)
        if item is None:
            raise LocalizedError("error.quality", mode=mode)
        catalogue = _catalogue()
        acceleration = provisioning.resolve_acceleration(current.accelerator)
        if catalogue is None:
            # The model cannot be resolved yet. Recording the choice is still
            # right: it is applied the next time the catalogue is readable,
            # rather than being silently dropped.
            current = dataclasses.replace(current, mode=item.key)
        else:
            current = separation.apply_preset(
                current, item, catalogue,
                accelerates_torch=acceleration.accelerates_torch,
            )
    separation.save_settings(path, current)
    return qualities()


def settings() -> "separation.Settings":
    """What a run would use, as the separator takes it."""
    return separation.load_settings(settings_file())


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
