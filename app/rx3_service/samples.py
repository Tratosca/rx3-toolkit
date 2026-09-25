# SPDX-License-Identifier: MPL-2.0
"""Sample banks, as an interface asks about them.

The deck module that plays these has been finished for a while and there has
never been a way to put a bank on a drive. This is that way, minus the window.

`analyse` measures sources without writing. Longer sources remain available
for excerpt selection; the exported excerpt obeys the deck duration limit.
"""

from __future__ import annotations

from app.localization import Message, LocalizedError

import base64
import dataclasses
import math
import pathlib
import subprocess
import tempfile
import wave

from app.rx3_samples import bank as bank_module
from app.rx3_samples.bank import Bank, Pad


@dataclasses.dataclass(frozen=True)
class Source:
    """One file an operator has offered for a pad."""

    path: pathlib.Path
    seconds: float
    accepted: bool
    # Empty when accepted. A sentence, because a screen shows it as one.
    refusal: str = ""


@dataclasses.dataclass(frozen=True)
class DriveBanks:
    """What a drive is carrying, and which bank the deck would load."""

    root: pathlib.Path
    names: tuple[str, ...]
    active: str | None


MAX_SECONDS = bank_module.MAX_FRAMES / bank_module.RATE


def read(drive: pathlib.Path) -> DriveBanks:
    """The banks already on a drive. A drive with none is not an error."""
    root = bank_module.samples_root(drive)
    banks = root / bank_module.BANKS_DIRECTORY
    # A name starting with a dot is a bank being assembled or the one it is
    # replacing, not a bank. The deck refuses such a name as well.
    names = tuple(sorted(
        entry.name for entry in banks.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
        and (entry / bank_module.CONFIG_NAME).is_file()
    )) if banks.is_dir() else ()
    marker = root / bank_module.ACTIVE_NAME
    active = marker.read_text(encoding="utf-8").strip() if marker.is_file() else None
    return DriveBanks(root=root, names=names, active=active or None)


def analyse(
    paths, *, ffprobe: pathlib.Path | str = "ffprobe",
) -> tuple[Source, ...]:
    """Measure what an operator has chosen, without converting any of it.

    A file that cannot be measured is refused rather than guessed at: the
    conversion would fail later anyway, and later is during a set.
    """
    measured = []
    for path in paths:
        path = pathlib.Path(path)
        seconds = _duration(path, ffprobe)
        if seconds is None:
            measured.append(Source(path, 0.0, False, Message("error.audio")))
        else:
            measured.append(Source(path, seconds, True))
    return tuple(measured)


def _duration(path: pathlib.Path, ffprobe: pathlib.Path | str) -> float | None:
    if not path.is_file():
        return None
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode:
        return None
    try:
        value = float(result.stdout.strip())
        return value if math.isfinite(value) and value > 0 else None
    except ValueError:
        return None


def _colour(value) -> int | None:
    """A pad colour as an interface writes it, or as the file already had it."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).lstrip("#")
    if len(text) != 6:
        raise LocalizedError("error.colour", value=str(value))
    try:
        return int(text, 16)
    except ValueError:
        raise LocalizedError("error.colour", value=str(value)) from None


def _pad(entry) -> Pad:
    """One pad as a screen describes it."""
    if not entry:
        return Pad()
    if isinstance(entry, (str, pathlib.Path)):
        return Pad(source=pathlib.Path(entry))
    source = entry.get("source") or None
    mode = int(entry.get("mode", bank_module.MODE_ONCE) or 0)
    if mode not in bank_module.MODES:
        raise LocalizedError("error.padMode")
    gain = int(entry.get("gain", bank_module.GAIN_UNITY))
    if not 0 <= gain <= bank_module.GAIN_MAX:
        raise LocalizedError("error.padGain", maximum=bank_module.GAIN_MAX)
    return Pad(
        source=pathlib.Path(source) if source else None,
        colour=_colour(entry.get("colour")),
        name=bank_module.clean_name(str(entry.get("name") or "")),
        mode=mode,
        gain=gain,
        keep=bool(entry.get("keep")),
        start=float(entry.get("start", 0)),
        duration=entry.get("duration"),
    )


def audition(
    source: pathlib.Path | str,
    *,
    ffmpeg: pathlib.Path | str = "ffmpeg",
    start: float = 0.0,
    duration: float | None = None,
) -> dict:
    """One sound, converted the way the deck will hear it.

    Nothing here reaches a deck, so a pad set to hold or to latch cannot be
    tried before someone carries the drive to one. This is what lets it be
    tried: the file is put through the same conversion `save` uses, so what
    plays in the interface is what the player will play, eight second cap and
    all, rather than the source the operator happens to have.

    The bytes come back inline because the only surface a screen has is this
    one, and a pad is at most eight seconds of PCM.
    """
    path = pathlib.Path(source)
    if not path.is_file():
        raise LocalizedError("error.file", path=str(path))
    with tempfile.TemporaryDirectory(prefix="rx3-audition-") as workspace:
        converted = pathlib.Path(workspace) / "pad.wav"
        frames = bank_module.convert_pad(path, converted, ffmpeg=ffmpeg,
                                          start=start, duration=duration)
        payload = converted.read_bytes()
    return {
        "audio": base64.b64encode(payload).decode("ascii"),
        "seconds": frames / bank_module.RATE,
        "bytes": len(payload),
    }


def save(
    drive: pathlib.Path,
    name: str,
    pads,
    *,
    volume: int = bank_module.VOLUME_DEFAULT,
    shift_silence: bool = False,
    ffmpeg: pathlib.Path | str = "ffmpeg",
    activate: bool = True,
    progress=None,
) -> pathlib.Path:
    """Write one bank to a drive.

    `pads` is up to eight entries, each one a path, nothing, or a mapping
    carrying the sound and what the pad does with it.
    """
    bank = Bank(
        name=name,
        pads=tuple(_pad(entry) for entry in pads),
        volume=volume,
        shift_silence=shift_silence,
    )
    return bank_module.write_bank(
        drive, bank, ffmpeg=ffmpeg, activate=activate, progress=progress
    )


def describe(drive: pathlib.Path, name: str) -> dict:
    """One bank as a screen shows it, read back from the drive itself.

    `settingsOk` is false when the deck's own parser would throw the file away
    and fall back to its compiled defaults. An interface that showed the file's
    colours while the deck showed different ones would be lying quietly.
    """
    root = bank_module.samples_root(drive)
    directory = root / bank_module.BANKS_DIRECTORY / name
    if not directory.is_dir():
        raise LocalizedError("error.bank", name=name)
    read = bank_module.read_settings(directory)
    bank = read or Bank(name)
    total = 0
    pads = []
    for index, pad in enumerate(bank.padded()):
        audio = directory / bank_module.pad_file_name(index)
        present = audio.is_file()
        seconds, size = 0.0, 0
        if present:
            size = audio.stat().st_size
            try:
                with wave.open(str(audio), "rb") as opened:
                    seconds = opened.getnframes() / bank_module.RATE
                    total += opened.getnframes() * bank_module.FRAME_BYTES
            except (wave.Error, OSError):
                present = False
        colour = pad.colour if pad.colour is not None else bank_module.PAD_COLOURS[index]
        pads.append({
            "index": index,
            "present": present,
            "path": str(audio) if present else None,
            "seconds": round(seconds, 2),
            "bytes": size,
            "colour": f"#{colour:06X}",
            "name": pad.name,
            "mode": pad.mode,
            "gain": pad.gain,
        })
    return {
        "name": name,
        "volume": bank.volume,
        "shiftSilence": bank.shift_silence,
        "settingsOk": read is not None,
        "bytes": total,
        "pads": pads,
    }


def activate(drive: pathlib.Path, name: str) -> None:
    """Point the deck at a bank already on the drive.

    Switching banks moves one small file rather than rewriting megabytes, which
    is the whole reason the marker exists.
    """
    root = bank_module.samples_root(drive)
    if not (root / bank_module.BANKS_DIRECTORY / name / bank_module.CONFIG_NAME).is_file():
        raise LocalizedError("error.bank", name=name)
    (root / bank_module.ACTIVE_NAME).write_text(name + "\n", encoding="utf-8")


def remove(drive: pathlib.Path, name: str) -> None:
    """Delete a bank. The active marker goes with it if it named this one."""
    root = bank_module.samples_root(drive)
    directory = root / bank_module.BANKS_DIRECTORY / name
    if not directory.is_dir():
        raise LocalizedError("error.bank", name=name)
    for entry in sorted(directory.iterdir()):
        entry.unlink()
    directory.rmdir()
    marker = root / bank_module.ACTIVE_NAME
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == name:
        marker.unlink()
