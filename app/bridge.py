# SPDX-License-Identifier: MPL-2.0
"""What the interface may call, and the only place it may call it from.

One object, one method per operation, plain values in and out. A window binds
this and knows nothing else about the toolkit; a test binds it and needs no
window. Every method returns something JSON can carry, because the interface is
on the other side of a bridge that only carries that.

Failures come back as `{"error": "..."}` rather than as exceptions. An exception
crossing this bridge reaches the interface as a stack trace with no sentence in
it, and the operator reads the sentence.

Arguments arrive positionally. The window packs what JavaScript passed into a
list and calls the method with it, so a method taking `**kwargs` can never be
reached with any of them set. Anything richer than a scalar is therefore one
dict parameter, which the bridge reduces to the keys it knows before a service
sees it.
"""

from __future__ import annotations

import functools
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import traceback

from app.localization import Message, LocalizedError, catalogs, normalize, translate, wire, error_message
from app.rx3_runtime import build as build_module
from app.rx3_samples import bank as bank_module
from app.rx3_service import drive as drive_service
from app.rx3_service import logo as logo_service
from app.rx3_service import mod as mod_service
from app.rx3_service import samples as samples_service
from app.rx3_service import stems as stems_service


# What a chooser offers per kind. The interface names a kind; it never hands
# over a filter string of its own, because that string is platform syntax and
# the screens hold no platform knowledge.
FILE_KINDS = {
    "audio": (("dialog.audio", "(*.wav;*.aiff;*.aif;*.flac;*.mp3;*.m4a;*.aac;*.ogg;*.oga;*.opus;*.wma)"), ("dialog.all", "(*.*)")),
    "image": (("dialog.image", "(*.png;*.jpg;*.jpeg;*.webp)"), ("dialog.all", "(*.*)")),
    "key": (("dialog.all", "(*.*)"),),
    "library": (("dialog.library", "(*.xml)"), ("dialog.all", "(*.*)")),
}


class Cancelled(Exception):
    """What a worker raises when the operator asked it to stop."""


def answered(method):
    """Turn any failure into a sentence the interface can show."""

    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        try:
            return {"ok": True, "value": wire(method(*args, **kwargs))}
        except Exception as error:
            detail = str(error) or error.__class__.__name__
            return {"ok": False, "error": detail, "errorMessage": wire(error_message(error)), "trace": traceback.format_exc()}

    return wrapper


def reveal(path: pathlib.Path) -> None:
    """Show a path in the platform file manager.

    This lives here rather than in a service because opening a file manager is
    something an interface does, and nothing under app/rx3_service opens
    anything.
    """
    path = pathlib.Path(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])


def _framing(value) -> dict:
    """Only the four keys the encoder frames with, coerced, or a sentence.

    Anything else reaching `container.placement` arrives as a TypeError with no
    sentence in it, and a screen is free to send whatever it likes.
    """
    frame = dict(value or {})
    mode = str(frame.get("mode", "contain"))
    if mode not in ("contain", "cover"):
        raise LocalizedError("error.framing", mode=mode)
    numbers = {}
    for key, name in (("zoom", "zoom"), ("offsetX", "offset_x"), ("offsetY", "offset_y")):
        raw = frame.get(key, 1.0 if key == "zoom" else 0.0)
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise LocalizedError("error.number", field=key) from None
        if number != number or number in (float("inf"), float("-inf")):
            raise LocalizedError("error.number", field=key)
        numbers[name] = number
    return {"mode": mode, **numbers}


def _logo_request(value) -> tuple:
    """An artwork choice as the encoder takes it: path, pane, framing."""
    request = dict(value or {})
    path = pathlib.Path(str(request.get("path", "")))
    if not path.is_file():
        raise LocalizedError("error.artwork", path=str(path))
    return path, str(request.get("canvas", "classic")), _framing(request)


def idle_job() -> dict:
    """The shape of the job slot with nothing in it.

    A module-level function rather than a constant, so a caller that keeps the
    answer cannot mutate what the next answer is built from.
    """
    return {
        "kind": "",
        "state": "idle",
        "message": "",
        "progress": None,
        "startedAt": 0.0,
        "detail": {},
        "result": None,
        "error": "",
    }


class Bridge:
    """The toolkit, as one flat surface."""

    def __init__(self) -> None:
        # Set once the window exists. Only the choosers need it: progress is
        # polled rather than pushed, so nothing else here draws anything.
        self._window = None
        self._locale = "en"
        self._lock = threading.Lock()
        # One slot, not one per kind. A build and a separation both write the
        # same drive, so two at once damages a stick rather than keeping the
        # computer busy, and one slot makes cancelling mean exactly one thing.
        self._job = idle_job()
        self._stop = None
        # The last export or drive that was read, so a forecast and a run do
        # not each parse it again.
        self._library = None

    @answered
    def localization_catalogs(self):
        return catalogs()

    @answered
    def localization_language(self, locale):
        self._locale = normalize(locale)
        return self._locale

    def _attach(self, window) -> None:
        """Hand over the window once it exists.

        Underscored so it stays off the surface the interface sees: the window
        binds this object before it is shown, and no screen may reach it.
        """
        self._window = window

    # The one job slot -------------------------------------------------------

    def _claim(self, kind: str, message: str) -> None:
        """Take the slot, or refuse in a sentence naming what holds it."""
        with self._lock:
            if self._job["state"] == "running":
                held = self._job["message"] or self._job["kind"]
                raise LocalizedError("error.busy")
            self._job = idle_job()
            self._job.update(
                kind=kind, state="running", message=message, startedAt=time.time()
            )
            self._stop = None

    def _watch(self, stop) -> None:
        """Register what cancelling this job calls."""
        with self._lock:
            self._stop = stop

    def _step(self, message: str, progress=None, detail=None) -> None:
        """Report where a running job has got to. Never raises."""
        with self._lock:
            if self._job["state"] != "running":
                return
            self._job["message"] = message
            if progress is not None:
                self._job["progress"] = progress
            if detail is not None:
                self._job["detail"] = detail

    def _settle(self, state: str, message: str, result=None, error: str = "") -> None:
        """Close the slot. Every worker ends here, including on the way out."""
        with self._lock:
            self._job.update(
                state=state, message=message, result=result, error=error
            )
            self._stop = None

    @answered
    def job_status(self) -> dict:
        """Where the running job is, or the idle shape when there is none.

        Polled by the interface rather than pushed at it. A push needs a shown
        window, which is exactly what a headless self-test does not have, and
        progress is a snapshot rather than a stream, so a dropped frame costs
        nothing.
        """
        with self._lock:
            return dict(self._job)

    @answered
    def job_cancel(self) -> bool:
        """Ask the running job to stop. False when there is nothing to stop."""
        with self._lock:
            stop = self._stop if self._job["state"] == "running" else None
        if stop is None:
            return False
        stop()
        return True

    # Choosing things --------------------------------------------------------

    def _choose(self, dialog, start, multiple=False, kind=""):
        """One chooser, on the window, answering with plain paths.

        The window's chooser has no title of its own to set, so the screens say
        what they are asking for beside the button rather than in the dialog.
        """
        window = self._window
        if window is None:
            raise LocalizedError("error.window")
        types = tuple(translate(key, self._locale) + " " + pattern
                      for key, pattern in FILE_KINDS.get(kind, ()))
        chosen = window.create_file_dialog(
            dialog,
            directory=str(start or ""),
            allow_multiple=multiple,
            file_types=types,
        )
        return [str(item) for item in (chosen or ())]

    @answered
    def pick_folder(self, start: str = "") -> dict:
        import webview

        chosen = self._choose(webview.FileDialog.FOLDER, start)
        return {"path": chosen[0] if chosen else None}

    @answered
    def pick_file(self, kind: str = "key", start: str = "") -> dict:
        import webview

        chosen = self._choose(webview.FileDialog.OPEN, start, kind=kind)
        return {"path": chosen[0] if chosen else None}

    @answered
    def pick_files(self, kind: str = "audio", start: str = "") -> dict:
        import webview

        return {
            "paths": self._choose(
                webview.FileDialog.OPEN, start, multiple=True, kind=kind
            )
        }

    @answered
    def reveal(self, path: str) -> bool:
        reveal(pathlib.Path(path))
        return True

    # Drives -----------------------------------------------------------------

    @answered
    def drive_report(self, path: str) -> dict:
        # Reporting writes a probe file to find out whether the drive is
        # writable, so nothing may poll this on a timer.
        report = drive_service.report(pathlib.Path(path))
        return {
            "path": str(report.path),
            "writable": report.writable,
            "mod": {
                "installed": report.mod.installed,
                "unrecorded": report.mod.unrecorded,
                "firmware": report.mod.firmware,
                "modules": list(report.mod.modules),
                "builtAt": report.mod.built_at,
                "bytes": report.mod.bytes,
                "sha256": report.mod.sha256,
                "loaded": list(report.mod.loaded),
                "disabled": list(report.mod.disabled),
            },
            "music": {
                "present": report.music.present,
                "tracks": report.music.tracks,
                "playlists": report.music.playlists,
                "unreadable": report.music.unreadable,
            },
            "banks": list(report.banks),
            "activeBank": report.active_bank,
            "capabilities": report.capabilities,
        }

    # The mod ----------------------------------------------------------------

    @answered
    def mod_modules(self, firmware: str) -> list:
        return [
            {
                "id": patch.patch_id,
                "name": patch.name,
                "description": patch.description,
                "default": patch.default,
                "selectable": patch.selectable,
                "requires": list(patch.requires),
                "conflicts": list(patch.conflicts),
            }
            for patch in build_module.discover_patches(None, firmware)
        ]

    @answered
    def mod_firmwares(self) -> list:
        return list(build_module.available_versions())

    @answered
    def mod_key_hint(self) -> dict:
        """Where the key was last said to be, so the field opens filled in."""
        return {"path": os.environ.get("RX3_KEY", "")}

    @answered
    def mod_selection(self, firmware: str, selected: list, toggled: str, on: bool) -> list:
        """What ticking one box does to the others.

        Dependencies tick themselves on, and what only they needed ticks off
        with them. The interface holds no rule of its own about this.
        """
        definitions = build_module.discover_patches(None, firmware)
        chosen = set(selected)
        if on:
            chosen |= build_module.required_closure(definitions, [toggled])
        else:
            chosen -= build_module.dependent_closure(definitions, [toggled])
        # An internal module is ticked exactly when something still needs it.
        # Without this pass, unticking the last thing that wanted the core
        # leaves the core ticked and the interface showing a selection nobody
        # asked for.
        picked = {
            patch.patch_id for patch in definitions
            if patch.selectable and patch.patch_id in chosen
        }
        needed = build_module.required_closure(definitions, picked) if picked else set()
        for patch in definitions:
            if patch.selectable:
                continue
            chosen.discard(patch.patch_id)
            if patch.patch_id in needed:
                chosen.add(patch.patch_id)
        return sorted(chosen)

    @answered
    def mod_remove(self, path: str) -> list:
        return list(mod_service.remove(pathlib.Path(path)))

    @answered
    def mod_build(
        self, firmware: str, selected: list, key: str, output: str, logo=None
    ) -> dict:
        """Start writing an autoexec.bin, and answer once it has started.

        Everything an operator can get wrong is checked here, on the thread
        that called, so a refusal comes back as the answer to the button they
        pressed rather than as a job that fails a second later.
        """
        chosen = [str(item) for item in selected]
        if not chosen:
            raise LocalizedError("error.selection")
        key_path = pathlib.Path(key)
        if not key_path.is_file():
            raise LocalizedError("error.key", path=str(key_path))
        destination = pathlib.Path(output)
        if not destination.is_dir():
            raise LocalizedError("error.directory", path=str(destination))
        frame = None
        if logo:
            if logo_service.MODULE_ID not in chosen:
                raise LocalizedError("error.logoModule")
            frame = _logo_request(logo)

        self._claim("mod", Message("job.build"))
        stop = build_module.Cancellation()
        self._watch(stop.stop)
        threading.Thread(
            target=self._build,
            args=(firmware, chosen, key_path, destination, frame, stop),
            daemon=True,
        ).start()
        return {"started": True}

    def _build(self, firmware, chosen, key_path, destination, frame, stop) -> None:
        """The build, off the calling thread. Every exit settles the slot."""
        try:
            supplied = None
            if frame:
                self._step(Message("job.logo"))
                path, canvas, framing = frame
                supplied = {
                    logo_service.MODULE_ID: logo_service.files(path, canvas, **framing)
                }
            result = build_module.build_runtime(
                firmware,
                chosen,
                key_path,
                destination,
                supplied_files=supplied,
                cancellation=stop,
                progress=lambda message: self._step(message),
            )
        except build_module.Cancelled:
            self._settle("cancelled", Message("job.cancelled"))
        except Exception as error:
            detail = error_message(error)
            self._settle("failed", Message("job.failed"), error=detail)
        else:
            self._settle(
                "done",
                Message("job.done"),
                result={
                    "output": str(result.output),
                    "bytes": result.size,
                    "sha256": result.sha256,
                    "modules": list(result.patches),
                },
            )

    # Samples ----------------------------------------------------------------

    @answered
    def samples_defaults(self) -> dict:
        """Every limit and default the editor obeys, so it holds none itself."""
        return {
            "padCount": bank_module.PAD_COUNT,
            "maxVoices": bank_module.MAX_VOICES,
            "maxSeconds": samples_service.MAX_SECONDS,
            "bankMaxBytes": bank_module.BANK_MAX_BYTES,
            "volumeDefault": bank_module.VOLUME_DEFAULT,
            "volumeMax": bank_module.VOLUME_MAX,
            "nameMaxChars": bank_module.NAME_MAX_CHARS,
            "gainUnity": bank_module.GAIN_UNITY,
            "gainMax": bank_module.GAIN_MAX,
            "bankNameRule": bank_module.NAME_RULE,
            "colours": [f"#{colour:06X}" for colour in bank_module.PAD_COLOURS],
            "modes": list(bank_module.MODES),
        }

    @answered
    def samples_read(self, path: str) -> dict:
        """Every bank on a drive, as the drive itself has them."""
        drive = pathlib.Path(path)
        banks = samples_service.read(drive)
        return {
            "active": banks.active,
            "banks": [samples_service.describe(drive, name) for name in banks.names],
        }

    @answered
    def samples_save(self, path: str, name: str, pads: list, options=None) -> dict:
        """Start writing one bank, and answer once it has started."""
        choices = dict(options or {})
        drive = pathlib.Path(path)
        if not drive.is_dir():
            raise LocalizedError("error.directory", path=str(drive))
        if not re.fullmatch(bank_module.NAME_RULE, str(name)):
            raise LocalizedError("error.bankName")
        volume = int(choices.get("volume", bank_module.VOLUME_DEFAULT))
        silence = bool(choices.get("shiftSilence"))
        activate = bool(choices.get("activate", True))

        self._claim("samples", Message("job.bank"))
        stopping = threading.Event()
        self._watch(stopping.set)
        threading.Thread(
            target=self._save_bank,
            args=(drive, str(name), list(pads), volume, silence, activate, stopping),
            daemon=True,
        ).start()
        return {"started": True}

    def _save_bank(self, drive, name, pads, volume, silence, activate, stopping) -> None:
        def onwards(done, count):
            if stopping.is_set():
                raise Cancelled(Message("job.cancelled"))
            self._step(Message("job.sound", done=done, count=count), int(done * 100 / max(count, 1)))

        try:
            directory = samples_service.save(
                drive, name, pads,
                volume=volume, shift_silence=silence, activate=activate,
                progress=onwards,
            )
        except Cancelled:
            self._settle("cancelled", Message("job.cancelled"))
        except Exception as error:
            detail = error_message(error)
            self._settle("failed", Message("job.failed"), error=detail)
        else:
            self._settle("done", Message("job.done"), result={"bank": str(directory), "name": name})

    @answered
    def samples_analyse(self, paths: list) -> list:
        return [
            {
                "path": str(source.path),
                "name": source.path.name,
                "seconds": source.seconds,
                "accepted": source.accepted,
                "refusal": source.refusal,
            }
            for source in samples_service.analyse(paths)
        ]

    @answered
    def samples_audition(self, path: str, start=0, duration=None) -> dict:
        """One sound as the deck will play it, so a pad mode can be heard.

        The conversion is the one a save performs, not a shortcut: what the
        screen plays is what the player will, eight second cap included.
        """
        return samples_service.audition(pathlib.Path(path), start=start, duration=duration)

    @answered
    def samples_activate(self, path: str, name: str) -> bool:
        samples_service.activate(pathlib.Path(path), name)
        return True

    @answered
    def samples_remove(self, path: str, name: str) -> bool:
        samples_service.remove(pathlib.Path(path), name)
        return True

    # The logo ---------------------------------------------------------------

    @answered
    def logo_canvases(self) -> list:
        return [
            {
                "name": canvas.name,
                "canvasWidth": canvas.canvas_width,
                "canvasHeight": canvas.canvas_height,
                "inkWidth": canvas.ink_width,
                "inkHeight": canvas.ink_height,
                # Where the ink area sits on the canvas the deck is sent. The
                # interface draws both, so it must not work this out itself.
                "inkOriginX": (canvas.canvas_width - canvas.ink_width) // 2,
                "inkOriginY": (canvas.canvas_height - canvas.ink_height) // 2,
            }
            for canvas in logo_service.canvases()
        ]

    @answered
    def logo_limits(self) -> dict:
        """Every number the framing obeys, so the interface holds none."""
        low, high = logo_service.zoom_range()
        return {
            "zoomMin": low,
            "zoomMax": high,
            "minVisible": logo_service.min_visible(),
            "modes": ["contain", "cover"],
        }

    @answered
    def logo_open(self, path: str) -> dict:
        """Read one image and hand the screen what it needs to frame it."""
        return logo_service.opened(pathlib.Path(path))

    @answered
    def logo_render(self, path: str, canvas: str = "classic", frame=None) -> dict:
        """The pane as it will be written, once the operator has stopped moving.

        The framing arrives as one dict because the window packs JavaScript
        arguments positionally and never passes keywords, so a method taking
        them could only ever run at its defaults.
        """
        return logo_service.render(
            pathlib.Path(path), canvas, **_framing(frame)
        )

    # Separation -------------------------------------------------------------

    @answered
    def stems_cache(self, maximum=None, clear=False) -> dict:
        from app.rx3_stems import cache
        return cache.configure(maximum, clear)

    @answered
    def stems_library_status(self) -> dict:
        from app.rx3_stems import safety
        return {"busy": safety.library_busy()}

    @answered
    def stems_runtime(self) -> dict:
        runtime = stems_service.runtime()
        return {
            "ready": runtime.ready,
            "managed": runtime.managed,
            "summary": Message("stems.engineReady" if runtime.ready else "stems.engineMissing"),
            "diagnostic": runtime.summary,
            "accelerator": runtime.accelerator,
            "accelerators": [
                {"key": key, "label": Message("accelerator." + key)} for key, label in runtime.accelerators
            ],
        }

    @answered
    def stems_library(self, path: str) -> dict:
        """Read a Rekordbox export or a drive, and keep what was parsed.

        The parsed collection is held here because a forecast and a run both
        need it, and parsing an export twice to answer two questions about the
        same file is a second of an operator's time for nothing.
        """
        library = stems_service.read_library(pathlib.Path(path))
        with self._lock:
            self._library = library
        return {
            "source": str(library.source),
            "tracks": library.tracks,
            "playlists": list(library.playlists),
        }

    def _held(self):
        with self._lock:
            library = self._library
        if library is None:
            raise LocalizedError("error.library")
        return library

    @answered
    def stems_qualities(self) -> dict:
        return stems_service.qualities()

    @answered
    def stems_choose(self, mode=None, accelerator=None) -> dict:
        return stems_service.choose(mode or None, accelerator or None)

    @answered
    def stems_forecast(self, playlist_id: str, roles=("vocals",)) -> dict:
        return stems_service.forecast(
            self._held(), playlist_id, stems_service.settings(), roles)

    @answered
    def stems_install(self, accelerator: str = "auto") -> dict:
        self._claim("runtime", Message("job.runtime"))
        threading.Thread(
            target=self._provision, args=(accelerator,), daemon=True
        ).start()
        return {"started": True}

    def _provision(self, accelerator) -> None:
        try:
            stems_service.install(accelerator, progress=lambda line: self._step(Message("job.runtime"), detail={"diagnostic": line}))
        except Exception as error:
            detail = error_message(error)
            self._settle("failed", Message("job.failed"), error=detail)
        else:
            self._settle("done", Message("job.done"), result={"runtime": True})

    @answered
    def stems_start(self, playlist_id: str, output: str, roles: list) -> dict:
        """Start separating one playlist into the files a deck reads."""
        library = self._held()
        destination = pathlib.Path(output)
        if not destination.is_dir():
            raise LocalizedError("error.directory", path=str(destination))
        wanted = tuple(str(role) for role in roles) or ("vocals",)
        # Built before the slot is claimed, because refusing an unprepared
        # machine is the answer to the button rather than a job that fails.
        job = stems_service.job(
            library, playlist_id, destination,
            settings=stems_service.settings(), roles=wanted,
            observer=lambda state: self._step(
                Message("job.separate"), state.get("progress"), state,
            ),
        )
        self._claim("stems", Message("job.separate"))
        self._watch(job.cancel)
        threading.Thread(target=self._separate, args=(job,), daemon=True).start()
        return {"started": True}

    def _separate(self, job) -> None:
        """`run()` is synchronous and never raises: the state carries the news."""
        state = stems_service.snapshot(job.run())
        if state["state"] == "cancelled":
            self._settle("cancelled", Message("job.cancelled"), result=state)
        elif state["state"] == "failed":
            self._settle("failed", Message("job.failed"), result=state,
                         error=state.get("fatal") or Message("job.failed"))
        else:
            self._settle("done", Message("job.done"), result=state)


def operations(bridge: Bridge) -> list:
    """Every name the interface may call, so a test can hold the surface."""
    return sorted(
        name for name in dir(bridge)
        if not name.startswith("_") and callable(getattr(bridge, name))
    )
