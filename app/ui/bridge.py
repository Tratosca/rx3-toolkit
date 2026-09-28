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
from app.firmware import key_source
from app.runtime import build as build_module
from app.samples import bank as bank_module
from app.services import drive as drive_service
from app.services import keyshift as keyshift_service
from app.services import key_match as key_match_service
from app.services import browse_columns as browse_columns_service
from app.services import logo as logo_service
from app.services import mod as mod_service
from app.services import samples as samples_service
from app.services import stems as stems_service
from app.stems import processes


# What a chooser offers per kind. The interface names a kind; it never hands
# over a filter string of its own, because that string is platform syntax and
# the screens hold no platform knowledge.
FILE_KINDS = {
    "stem": (("dialog.audio", "(*.wav;*.aiff;*.aif;*.flac)"),),
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
    something an interface does, and nothing under app/services opens
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


def _invert_light(value) -> bool:
    """Whether a light screen gets the artwork's greys inverted. On unless the
    screen said no, which is what every logo built before the choice existed got."""
    return dict(value or {}).get("invertLight", True) is not False


def _logo_request(value) -> tuple:
    """An artwork choice as the encoder takes it: path, pane, framing, inversion."""
    request = dict(value or {})
    path = pathlib.Path(str(request.get("path", "")))
    if not path.is_file():
        raise LocalizedError("error.artwork", path=str(path))
    return path, str(request.get("canvas", "classic")), _framing(request), _invert_light(request)


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
        self._preview_lock = threading.Lock()
        self._preview = None
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
        self._cancel_requested = False
        self._closing = False
        self._job_done = threading.Event()
        self._job_done.set()
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

    def _on_closing(self):
        """Keep the window alive until the worker has released files and children."""
        with self._lock:
            if self._closing:
                return self._job_done.is_set()
            running = self._job["state"] == "running"
            if running:
                self._closing = True
        if running:
            try:
                accepted = self._window.create_confirmation_dialog(
                    translate("tasks.closeTitle", self._locale),
                    translate("tasks.closeBody", self._locale),
                )
            except Exception:
                with self._lock:
                    self._closing = False
                raise
            if not accepted:
                with self._lock:
                    self._closing = False
                return False
        with self._preview_lock:
            if self._preview:
                self._preview.close()
                self._preview = None
        if not running:
            return True
        def finish():
            self.job_cancel()
            self._job_done.wait()
            self._window.destroy()
        threading.Thread(target=finish, daemon=True).start()
        return False

    # The one job slot -------------------------------------------------------

    def _claim(self, kind: str, message: str) -> None:
        """Take the slot, or refuse in a sentence naming what holds it."""
        with self._lock:
            if self._closing:
                raise LocalizedError("error.busy")
            if self._job["state"] == "running":
                held = self._job["message"] or self._job["kind"]
                raise LocalizedError("error.busy")
            self._job = idle_job()
            self._job.update(
                kind=kind, state="running", message=message, startedAt=time.time()
            )
            self._stop = None
            self._cancel_requested = False
            self._job_done.clear()

    def _watch(self, stop) -> None:
        """Register what cancelling this job calls."""
        with self._lock:
            self._stop = stop
            pending = self._cancel_requested
        if pending:
            stop()

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
            self._job_done.set()

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
            if self._job["state"] == "running":
                self._cancel_requested = True
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
                "category": patch.category,
                "categoryUi": patch.category_ui,
                "advanced": patch.advanced,
                "requires": list(patch.requires),
                "conflicts": list(patch.conflicts),
            }
            for patch in build_module.discover_patches(None, firmware)
        ]

    @answered
    def keyshift_preview(self, limit=1, mode="harmonic", rules=0) -> dict:
        return keyshift_service.preview(limit, mode, rules)

    @answered
    def mod_firmwares(self) -> list:
        return list(build_module.available_versions())

    @answered
    def mod_key_hint(self) -> dict:
        """Where the key is, so the field opens filled in.

        An explicit `RX3_KEY` wins over the kept one, so a developer's own key
        is never silently replaced by a download.
        """
        explicit = os.environ.get("RX3_KEY", "")
        kept = key_source.stored()
        return {
            "path": explicit or (str(kept) if kept else ""),
            "kept": bool(kept),
            "bytes": key_source.total_size(),
            "page": key_source.load_source().page,
        }

    @answered
    def mod_key_fetch(self, accepted=False) -> dict:
        """Start getting the key from the manufacturer's GPL source package.

        Refused unless the operator accepted the terms the page shows first.
        Checked here as well, so no other caller of this surface can skip them.
        """
        if accepted is not True:
            raise LocalizedError("error.keyTerms")
        kept = key_source.stored()
        if kept:
            return {"started": False, "path": str(kept)}
        self._claim("key", Message("job.keyDownload", part=1, count=len(key_source.load_source().parts)))
        stop = threading.Event()
        self._watch(stop.set)
        threading.Thread(target=self._fetch_key, args=(stop,), daemon=True).start()
        return {"started": True}

    @answered
    def mod_key_forget(self) -> dict:
        """Delete the key the app fetched. A key the operator chose is not touched."""
        with self._lock:
            if self._job["state"] == "running" and self._job["kind"] == "key":
                raise LocalizedError("error.busy")
        return {"removed": list(key_source.forget())}

    def _fetch_key(self, stop) -> None:
        """The download, off the calling thread. Every exit settles the slot."""
        count = len(key_source.load_source().parts)
        total = key_source.total_size()
        sizes = [part.size for part in key_source.load_source().parts]

        def progress(done, size, index):
            before = sum(sizes[:index])
            if before + done >= total:
                # Everything is here; what follows is one pass over it.
                self._step(Message("job.keyRead"), progress=None)
                return
            self._step(
                Message("job.keyDownload", part=index + 1, count=count),
                progress=round(100 * (before + done) / total, 1),
                detail={"done": before + done, "total": total},
            )

        try:
            path = key_source.obtain(progress=progress, stopped=stop.is_set)
        except key_source.Cancelled:
            self._settle("cancelled", Message("job.cancelled"))
        except Exception as error:
            self._settle("failed", Message("job.failed"), error=error_message(error))
        else:
            self._settle("done", Message("job.done"), result={"path": str(path)})

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
        self, firmware: str, selected: list, key: str, output: str, logo=None, key_sync_range=1, key_sync_mode="harmonic", key_match_rules=key_match_service.DEFAULT_RULES, browse_column=13
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

        key_sync_range = keyshift_service.sync_range(key_sync_range)
        key_sync_mode = keyshift_service.sync_mode(key_sync_mode)
        key_match_rules = key_match_service.rules(key_match_rules)
        browse_column = browse_columns_service.field(browse_column)
        self._claim("mod", Message("job.build"))
        stop = build_module.Cancellation()
        self._watch(stop.stop)
        threading.Thread(
            target=self._build,
            args=(firmware, chosen, key_path, destination, frame, stop, key_sync_range, key_sync_mode, key_match_rules, browse_column),
            daemon=True,
        ).start()
        return {"started": True}

    def _build(self, firmware, chosen, key_path, destination, frame, stop, key_sync_range=1, key_sync_mode="harmonic", key_match_rules=key_match_service.DEFAULT_RULES, browse_column=13) -> None:
        """The build, off the calling thread. Every exit settles the slot."""
        try:
            resolved = {module.patch_id for module in build_module.resolve_patches(
                build_module.discover_patches(None, firmware), chosen)}
            supplied = {}
            if "key-sync" in resolved:
                supplied["key-sync"] = keyshift_service.files(key_sync_range, key_sync_mode)
            if "browse-columns" in chosen:
                supplied["browse-columns"] = browse_columns_service.files(browse_column)
            if "key-match" in resolved:
                supplied["key-match"] = key_match_service.files(key_match_rules)
            if frame:
                self._step(Message("job.logo"))
                path, canvas, framing, invert = frame
                supplied[logo_service.MODULE_ID] = logo_service.files(
                    path, canvas, invert_light=invert, **framing)
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
    def samples_draft_load(self, path):
        from app.samples import drafts
        return drafts.load(path)

    @answered
    def samples_draft_store(self, path, project):
        from app.samples import drafts
        return drafts.store(path, project)

    @answered
    def samples_draft_asset(self, path):
        from app.samples import drafts
        return drafts.asset(path)

    @answered
    def samples_push(self, path, project):
        from app.samples import drafts
        drafts.validate(project, exporting=True)
        self._claim("samples", Message("job.bank"))
        stopping = threading.Event()
        self._watch(stopping.set)
        def run():
            def progress(done, count):
                if stopping.is_set(): raise Cancelled(Message("job.cancelled"))
                self._step(Message("job.sound", done=done, count=count), min(100, int(done*100/max(1,count))))
            try:
                drafts.push(path, project, progress)
            except Cancelled:
                self._settle("cancelled", Message("job.cancelled"))
            except Exception as error:
                self._settle("failed", Message("job.failed"), error=error_message(error))
            else:
                self._settle("done", Message("job.done"))
        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

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
            pathlib.Path(path), canvas, invert_light=_invert_light(frame), **_framing(frame)
        )

    # Separation -------------------------------------------------------------

    def _stem_track(self, track_id):
        library = self._held()
        matches = {track.location: track for playlist in library.collection.playlists
                   for track in playlist.tracks if track.track_id == str(track_id)}
        if len(matches) != 1:
            raise LocalizedError("stems.importTrack")
        track = next(iter(matches.values()))
        from app.stems.rekordbox import export_stem
        basename = export_stem(track.location.stem).casefold()
        if any(other.location != track.location and export_stem(other.location.stem).casefold() == basename
               for playlist in library.collection.playlists for other in playlist.tracks):
            raise LocalizedError("stems.importCollision")
        return track

    def _wave_collection(self, drive):
        destination = pathlib.Path(drive)
        if self._library and (not self._library.source.is_dir() or
                              self._library.source.resolve() == destination.resolve()):
            return self._library.collection
        from app.stems import rekordbox
        return rekordbox.parse_drive(destination) if rekordbox.has_export(destination) else None

    @answered
    def stems_wave_settings(self, drive, format=None):
        from app.stems import wave_conversion
        return wave_conversion.status(pathlib.Path(drive), self._wave_collection(drive), format)

    @answered
    def stems_wave_choose(self, drive, format, fingerprint):
        from app.stems import wave_settings
        with self._lock:
            if self._job["state"] == "running":
                raise LocalizedError("error.busy")
            return wave_settings.save(pathlib.Path(drive), format, fingerprint)

    @answered
    def stems_wave_convert(self, drive, format=None, fingerprint=None):
        from app.stems import wave_conversion, wave_settings, safety, provisioning
        safety.require_library_closed()
        destination = pathlib.Path(drive)
        if format is not None:
            if wave_settings.fingerprint(destination) != fingerprint:
                raise LocalizedError('stems.waveSettingsChanged')
            selected = wave_settings.choice(destination)
            if selected['format'] != format:
                raise LocalizedError('stems.waveSelection')
        collection = self._wave_collection(drive)
        report = wave_conversion.status(destination, collection, format)
        ids = {item['id'] for item in report['items'] if item['available']}
        tracks = {str(t.location): t for p in (collection.playlists if collection else [])
                  for t in p.tracks if t.track_id in ids}
        if not tracks:
            return {'started':False}
        self._claim('stems', Message('stems.wavePreparing'))
        control = processes.Control()
        self._watch(control.cancel)
        def run():
            try:
                with control.bind():
                    ffmpeg = provisioning.detect().ffmpeg or 'ffmpeg'
                    result = wave_conversion.run(list(tracks.values()), destination, format, fingerprint,
                                                 ffmpeg, control.checkpoint, self._step)
                self._settle('failed' if result['errors'] else 'done', Message('job.done'), result=result)
            except processes.Cancelled:
                self._settle('cancelled', Message('job.cancelled'))
            except Exception as error:
                self._settle('failed', Message('job.failed'), error=error_message(error))
        threading.Thread(target=run, daemon=True).start()
        return {'started':True}

    @answered
    def stems_waveform_status(self, playlist_id, output):
        from app.stems import deferred_waveforms
        if not output:
            return []
        return [{"id": track.track_id, "title": track.title, "artist": track.artist,
                 "status": deferred_waveforms.status(track, pathlib.Path(output))}
                for track in self._held().collection.playlist(playlist_id).tracks]

    @answered
    def stems_waveforms_start(self, playlist_id, output, track_id=None):
        from app.stems import deferred_waveforms, provisioning, safety
        safety.require_library_closed()
        drive = pathlib.Path(output)
        if not drive.is_dir():
            raise LocalizedError("error.directory", path=output)
        playlist = self._held().collection.playlist(playlist_id)
        ffmpeg = provisioning.detect().ffmpeg or "ffmpeg"
        self._claim("stems", Message("stems.wavePreparing"))
        control = processes.Control()
        self._watch(control.cancel)
        def run():
            try:
                with control.bind():
                    result = deferred_waveforms.run(playlist, drive, ffmpeg, control.checkpoint,
                                                   lambda stage, value: self._step(stage, value), track_id=track_id)
                if result["errors"]:
                    self._settle("failed", Message("job.failed"), result=result)
                else:
                    self._settle("done", Message("job.done"), result=result)
            except processes.Cancelled:
                self._settle("cancelled", Message("job.cancelled"))
            except Exception as error:
                self._settle("failed", Message("job.failed"), error=error_message(error))
        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

    @answered
    def stems_tracks(self, playlist_id):
        return [{"id": track.track_id, "title": track.title, "artist": track.artist}
                for track in self._held().collection.playlist(playlist_id).tracks]

    @answered
    def stems_import_assign(self, track_id, values=None):
        from app.stems import importing
        self._stem_track(track_id)
        return importing.assignments(self._held(), track_id, values)

    @answered
    def stems_preview_open(self, drive, track_id, imported=False):
        from app.stems import audition, importing, preview, provisioning
        track = self._stem_track(track_id)
        with self._preview_lock:
            if self._preview:
                self._preview.close()
                self._preview = None
            files, rejected = [], []
            inputs = None
            if imported:
                inputs = importing.assignments(self._held(), track_id)
            else:
                files, _, rejected = audition.role_files(
                    pathlib.Path(drive) / "RX3_STEMS", audition.export_stem(track.location.stem))
            self._preview = preview.Preview(track.location, files[:2], inputs,
                                            provisioning.detect().ffmpeg or "ffmpeg", streaming=True, verified=True)
            return dict(self._preview.describe(), rejected=rejected)

    @answered
    def stems_preview_chunk(self, token, first):
        with self._preview_lock:
            if not self._preview or self._preview.token != token:
                return None
            return self._preview.chunk(first)

    @answered
    def stems_preview_close(self, token):
        with self._preview_lock:
            if self._preview and self._preview.token == token:
                self._preview.close()
                self._preview = None
            return True

    @answered
    def stems_audition(self, drive, track_id, selection, start=0, seconds=30):
        from app.stems import audition, provisioning
        track = self._stem_track(track_id)
        return audition.on_drive(track.location, pathlib.Path(drive), selection, start, seconds,
                                 provisioning.detect().ffmpeg or "ffmpeg")

    @answered
    def stems_import_audition(self, drive, track_id, selection, start=0, seconds=30):
        from app.stems import audition, importing, provisioning
        track = self._stem_track(track_id)
        inputs = importing.assignments(self._held(), track_id)
        return audition.imported(track.location, inputs, selection, start, seconds,
                                 provisioning.detect().ffmpeg or "ffmpeg")

    @answered
    def stems_import_start(self, track_id, output, waveforms=True):
        from app.stems import importing, safety, provisioning
        safety.require_library_closed()
        track = self._stem_track(track_id)
        drive = pathlib.Path(output)
        if not drive.is_dir():
            raise LocalizedError("error.directory", path=output)
        inputs = importing.assignments(self._held(), track_id)
        ffmpeg = provisioning.detect().ffmpeg or "ffmpeg"
        self._claim("stems", Message("stems.importChecking"))
        control = processes.Control()
        self._watch(control.cancel)
        def run():
            try:
                with control.bind():
                    control.checkpoint()
                    entry = importing.publish(track, inputs, drive, ffmpeg, control.checkpoint, waveforms=bool(waveforms))
                self._settle("done", Message("job.done"), result={"imported": entry})
            except processes.Cancelled:
                self._settle("cancelled", Message("job.cancelled"))
            except Exception as error:
                self._settle("failed", Message("job.failed"), error=error_message(error))
        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

    @answered
    def stems_migration_status(self, output):
        from app.stems import migration, package
        from app.stems.rekordbox import export_stem
        directory = pathlib.Path(output) / "RX3_STEMS"
        by_base = {}
        library = self._library
        if library and library.source.is_dir() and library.source.resolve() != pathlib.Path(output).resolve():
            library = None
        for playlist in (library.collection.playlists if library else []):
            for track in playlist.tracks:
                by_base.setdefault(export_stem(track.location.stem).casefold(), {})[str(track.location)] = track
        items = []
        for path in sorted(directory.glob("*.rx3stem")):
            if package.is_package(path):
                continue
            matches = list(by_base.get(path.stem.casefold(), {}).values())
            track = matches[0] if len(matches) == 1 else None
            valid = bool(track and track.location.is_file())
            if valid:
                try:
                    valid = bool(migration.legacy_files(track, pathlib.Path(output)))
                except LocalizedError:
                    valid = False
            items.append({"id": track.track_id if valid else "", "title": track.title if track else path.stem,
                          "artist": track.artist if track else "", "available": valid})
        return {"items": items}

    @answered
    def stems_migrate(self, track_ids, output, add_drums=False):
        """Older clients enter the same fixed three-stem preparation pipeline."""
        destination = pathlib.Path(output)
        if not destination.is_dir():
            raise LocalizedError("error.directory", path=output)
        tracks = tuple(self._stem_track(key) for key in dict.fromkeys(track_ids))
        if not tracks:
            return {"started": False}
        job = stems_service.job(self._held(), None, destination, tracks=tracks,
                                observer=lambda state: self._step(Message("job.separate"), state.get("progress"), state))
        self._claim("stems", Message("job.separate"))
        self._watch(job.cancel)
        threading.Thread(target=self._separate, args=(job,), daemon=True).start()
        return {"started": True}

    @answered
    def stems_cache(self, maximum=None, clear=False) -> dict:
        from app.stems import cache
        return cache.configure(maximum, clear)

    @answered
    def stems_library_status(self) -> dict:
        from app.stems import safety
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
    def stems_qualities(self, roles=("vocals",)) -> dict:
        return stems_service.qualities(roles)

    @answered
    def stems_choose(self, mode=None, accelerator=None, roles=("vocals",)) -> dict:
        return stems_service.choose(mode or None, accelerator or None, roles)

    @answered
    def stems_forecast(self, playlist_id: str, roles=("vocals",), waveforms=True) -> dict:
        return stems_service.forecast(
            self._held(), playlist_id, stems_service.settings(), roles, bool(waveforms))

    @answered
    def stems_install(self, accelerator: str = "auto") -> dict:
        self._claim("runtime", Message("job.runtime"))
        control = processes.Control()
        self._watch(control.cancel)
        threading.Thread(
            target=self._provision, args=(accelerator, control), daemon=True
        ).start()
        return {"started": True}

    def _provision(self, accelerator, control) -> None:
        try:
            with control.bind():
                control.checkpoint()
                stems_service.install(accelerator, progress=lambda line: self._step(Message("job.runtime"), detail={"diagnostic": line}))
        except processes.Cancelled:
            self._settle("cancelled", Message("job.cancelled"))
        except Exception as error:
            detail = error_message(error)
            self._settle("failed", Message("job.failed"), error=detail)
        else:
            self._settle("done", Message("job.done"), result={"runtime": True})

    @answered
    def stems_start(self, playlist_id: str, output: str, roles: list, waveforms=True, overcue_compatible=False) -> dict:
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
            settings=stems_service.settings(), roles=wanted, waveforms=bool(waveforms),
            overcue_compatible=bool(overcue_compatible),
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
