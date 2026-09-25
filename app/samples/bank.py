# SPDX-License-Identifier: MPL-2.0
"""Prepare a bank of pad samples and write it where the deck reads them.

The deck does no conversion while a set is running, so everything is put into
the form it plays here: interleaved stereo signed 16-bit at 44.1 kHz, one WAV
file per pad. What arrives is whatever the operator had; ffmpeg does the work,
the same binary the stem encoder already uses.

The limits are refused on this side rather than on the deck. A pad that is too
long is a track someone dropped in by mistake, and finding that out from a
silent pad during a set is the worst possible time.
"""

from __future__ import annotations

import os
import math
import pathlib
import shutil
import subprocess
import re
import wave
from dataclasses import dataclass, field


RUNTIME_DIRECTORY = "RX3_RUNTIME"
SAMPLES_DIRECTORY = "samples"
BANKS_DIRECTORY = "banks"
# Which bank the deck loads. A name rather than a copy, so switching banks
# moves one small file instead of rewriting megabytes on a drive.
ACTIVE_NAME = "active"
CONFIG_NAME = "settings.ini"
CONFIG_VERSION = 1
# A settings file larger than this is not one, and the deck reads it into a
# fixed buffer.
CONFIG_MAX_BYTES = 4096

PAD_COUNT = 8
MAX_VOICES = 4
RATE = 44100
CHANNELS = 2
FRAME_BYTES = CHANNELS * 2

MIN_FRAMES = 1
MAX_FRAMES = RATE * 8
# One bank has to fit beside a music library on the same drive.
BANK_MAX_BYTES = 16 * 1024 * 1024

VOLUME_MAX = 100
VOLUME_DEFAULT = 50

# What a bank may be called. The deck reads this name out of a one-line file
# and refuses anything outside it, so an interface has to refuse it first.
NAME_RULE = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"

# What a pad does once it is hit. Once is what every pad did before the modes
# existed, and it is the value the file leaves out, so a bank written by an
# older build still means what it meant.
MODE_ONCE = 0
MODE_HOLD = 1
MODE_LOOP = 2
# Started and stopped by the same pad, without looping: what a long sound
# needed, because once ignores the release and only a loop could be stopped.
MODE_LATCH = 3
MODES = (MODE_ONCE, MODE_HOLD, MODE_LOOP, MODE_LATCH)
# Per-pad trim, in percent of the sound as it was recorded, written beside the
# audio rather than baked into it: a level can be corrected later without
# re-encoding, and the original file stays the original file.
GAIN_UNITY = 100
GAIN_MAX = 200
# A label an operator gives a pad. The deck never draws it: the pads are
# hardware buttons with a colour, and its parser passes over the key. It is
# here so the bank on the drive still says which sound is which.
NAME_MAX_CHARS = 48

PAD_COLOURS = (
    0xFF2828, 0xFF7800, 0xFFDC00, 0x28DC28,
    0x00C8DC, 0x2850FF, 0xB428FF, 0xFF28A0,
)


@dataclass(frozen=True)
class Pad:
    """One pad: the audio it plays and what it does when it is hit."""

    source: pathlib.Path | None = None
    colour: int | None = None
    name: str = ""
    mode: int = MODE_ONCE
    gain: int = GAIN_UNITY
    # Leave the sound already on the drive alone. Re-encoding a pad nobody
    # touched costs an operator a minute per bank and gains them nothing.
    keep: bool = False
    start: float = 0.0
    duration: float | None = None

    @property
    def empty(self) -> bool:
        return self.source is None and not self.keep


@dataclass(frozen=True)
class Bank:
    name: str
    pads: tuple[Pad, ...] = field(default=())
    volume: int = VOLUME_DEFAULT
    # SHIFT stops every pad at once rather than eight presses.
    shift_silence: bool = False

    def padded(self) -> tuple[Pad, ...]:
        """Exactly `PAD_COUNT` pads, so a short bank is not a different format."""
        pads = list(self.pads[:PAD_COUNT])
        while len(pads) < PAD_COUNT:
            pads.append(Pad())
        return tuple(pads)


def clean_name(name: str) -> str:
    """A pad label the file can carry, whatever an operator pasted in.

    The file is ASCII and one setting per line, so a tab, a newline or an emoji
    in a name would not be a strange label: it would be a malformed line, and
    the deck throws away the whole file over one of those.
    """
    kept = "".join(character if " " <= character <= "~" else " " for character in name)
    return " ".join(kept.split())[:NAME_MAX_CHARS]


def settings_text(bank: Bank) -> str:
    """The `settings.ini` the deck parses, `key=value` a line at a time.

    The version comes first because it is what the deck checks before trusting
    anything below it. A name and a mode are written only when they say
    something: the deck reads a missing mode as once, and passes over a name
    the way it passes over any key it does not know.
    """
    lines = [f"version={CONFIG_VERSION}", f"volume_default={_clamp_volume(bank.volume)}"]
    if bank.shift_silence:
        lines.append("shift.silence=1")
    for index, pad in enumerate(bank.padded(), start=1):
        colour = PAD_COLOURS[index - 1] if pad.colour is None else pad.colour
        if not isinstance(colour, int) or not 0 <= colour <= 0xFFFFFF:
            raise ValueError("pad colour must be an RGB value from 0x000000 to 0xFFFFFF")
        if pad.mode not in MODES:
            raise ValueError("pad mode must be once, hold, loop or latch")
        if not isinstance(pad.gain, int) or not 0 <= pad.gain <= GAIN_MAX:
            raise ValueError(f"pad trim must be a percentage up to {GAIN_MAX}")
        lines.append(f"pad{index}.color=#{colour:06X}")
        name = clean_name(pad.name)
        if name:
            lines.append(f"pad{index}.name={name}")
        if pad.mode != MODE_ONCE:
            lines.append(f"pad{index}.mode={pad.mode}")
        if pad.gain != GAIN_UNITY:
            lines.append(f"pad{index}.gain={pad.gain}")
    return "\n".join(lines) + "\n"


def read_settings(directory: pathlib.Path) -> Bank | None:
    """One bank read back, or None when the deck would refuse the file.

    This follows the deck's own parser rather than being lenient: an interface
    that shows what a file says while the deck falls back to compiled defaults
    is worse than one that says the file is unreadable.
    """
    directory = pathlib.Path(directory)
    try:
        raw = (directory / CONFIG_NAME).read_bytes()
    except OSError:
        return None
    if not raw or len(raw) > CONFIG_MAX_BYTES:
        return None
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None

    volume, silence = VOLUME_DEFAULT, False
    colours = list(PAD_COLOURS)
    names = [""] * PAD_COUNT
    modes = [MODE_ONCE] * PAD_COUNT
    gains = [GAIN_UNITY] * PAD_COUNT
    seen: set[str] = set()
    version = False
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            return None
        key, value = line.split("=", 1)
        # Only a key the deck knows is refused twice. It passes over a repeated
        # unknown key the way it passes over the first one.
        known = key in ("version", "volume_default", "shift.silence") or bool(
            re.fullmatch(r"pad[1-8]\.(?:color|mode|gain)", key)
        )
        if known:
            if key in seen:
                return None
            seen.add(key)
        if key == "version":
            if value != "1":
                return None
            version = True
        elif key == "volume_default":
            if not value.isdigit() or int(value) > VOLUME_MAX:
                return None
            volume = int(value)
        elif key == "shift.silence":
            if value not in ("0", "1"):
                return None
            silence = value == "1"
        elif re.fullmatch(r"pad[1-8]\.color", key):
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                return None
            colours[int(key[3]) - 1] = int(value[1:], 16)
        elif re.fullmatch(r"pad[1-8]\.mode", key):
            # Derived from MODES rather than written out again: the deck reads
            # one digit and this is the other side of that contract.
            if value not in tuple(str(mode) for mode in MODES):
                return None
            modes[int(key[3]) - 1] = int(value)
        elif re.fullmatch(r"pad[1-8]\.gain", key):
            if not value.isdigit() or len(value) > 3 or int(value) > GAIN_MAX:
                return None
            gains[int(key[3]) - 1] = int(value)
        elif re.fullmatch(r"pad[1-8]\.name", key):
            names[int(key[3]) - 1] = value
    if not version:
        return None
    pads = tuple(
        Pad(
            source=None,
            colour=colours[index],
            name=names[index],
            mode=modes[index],
            gain=gains[index],
            keep=(directory / pad_file_name(index)).is_file(),
        )
        for index in range(PAD_COUNT)
    )
    return Bank(directory.name, pads, volume=volume, shift_silence=silence)


def _clamp_volume(volume: int) -> int:
    if not isinstance(volume, int) or volume < 0:
        return VOLUME_DEFAULT
    return min(volume, VOLUME_MAX)


def pad_file_name(index: int) -> str:
    """PCM WAV for one pad, numbered as the deck numbers its pads."""
    if not 0 <= index < PAD_COUNT:
        raise ValueError("pad index must be between 0 and 7")
    return f"{index + 1}.wav"


def convert_pad(
    source: pathlib.Path,
    destination: pathlib.Path,
    *,
    ffmpeg: pathlib.Path | str = "ffmpeg",
    start: float = 0.0,
    duration: float | None = None,
) -> int:
    """Decode one source into the deck's raw form, returning the frame count."""
    start = float(start)
    duration = MAX_FRAMES / RATE if duration is None else float(duration)
    if not math.isfinite(start) or start < 0:
        raise ValueError("sample start must be finite and non-negative")
    if not math.isfinite(duration) or not 0 < duration <= MAX_FRAMES / RATE:
        raise ValueError("sample duration must be between zero and eight seconds")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(start), "-i", str(source), "-map", "0:a:0", "-vn",
        "-ar", str(RATE), "-ac", str(CHANNELS),
        "-t", str(duration), "-c:a", "pcm_s16le", "-f", "wav", str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = " ".join((result.stderr or result.stdout).split())[-260:]
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"{source.name} could not be decoded: {detail}")
    try:
        return playable_frames(destination)
    except ValueError:
        destination.unlink(missing_ok=True)
        raise


def samples_root(drive: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(drive) / RUNTIME_DIRECTORY / SAMPLES_DIRECTORY


def _discard(directory: pathlib.Path) -> None:
    """Remove a working directory, whether or not it is there."""
    shutil.rmtree(directory, ignore_errors=True)


def playable_frames(path: pathlib.Path) -> int:
    """Frames in a pad file, refusing anything the deck would not play.

    The deck skips a pad it cannot read and logs a line nobody sees, so a pad
    that is silently absent during a set is exactly what this refuses here.
    """
    try:
        with wave.open(str(path), "rb") as audio:
            frames = audio.getnframes()
            shape = (audio.getnchannels(), audio.getframerate(), audio.getsampwidth())
    except (wave.Error, OSError):
        raise ValueError(f"{path.name} is not a sound the deck reads") from None
    if shape != (CHANNELS, RATE, 2):
        raise ValueError(f"{path.name} is not 44.1 kHz stereo PCM16")
    if not MIN_FRAMES <= frames <= MAX_FRAMES:
        raise ValueError(f"{path.name} has no playable sample frames")
    return frames


def write_bank(
    drive: pathlib.Path,
    bank: Bank,
    *,
    ffmpeg: pathlib.Path | str = "ffmpeg",
    activate: bool = True,
    progress=None,
) -> pathlib.Path:
    """Convert and write one bank onto a drive, returning its directory.

    The bank is assembled beside the one it replaces and moved into place in a
    single rename, so a conversion that fails at pad five, a drive that fills
    up, or a stick pulled part way through leaves the bank that was already
    there exactly as it was. Writing in place used to leave four new pads, four
    old ones and the old settings over them, which is a bank nobody assembled
    and which the deck would happily play during a set.

    Two renames inside one directory, rather than an atomic directory swap,
    because the drive is FAT and has no such thing.
    """
    if not re.fullmatch(NAME_RULE, bank.name):
        raise ValueError("bank name must be a single ASCII name, at most 64 characters")
    root = samples_root(drive)
    banks = root / BANKS_DIRECTORY
    banks.mkdir(parents=True, exist_ok=True)
    final = banks / bank.name
    staging = banks / f".{bank.name}.new.{os.getpid()}"
    previous = banks / f".{bank.name}.old.{os.getpid()}"
    _discard(staging)
    _discard(previous)
    staging.mkdir()

    notify = progress or (lambda _index, _count: None)
    try:
        total = 0
        sounds = sum(1 for pad in bank.padded() if not pad.empty)
        done = 0
        for index, pad in enumerate(bank.padded()):
            target = staging / pad_file_name(index)
            if not pad.empty:
                done += 1
                notify(done, sounds)
            if pad.source is not None:
                total += convert_pad(pad.source, target, ffmpeg=ffmpeg,
                                     start=pad.start, duration=pad.duration) * FRAME_BYTES
            elif pad.keep:
                carried = final / pad_file_name(index)
                if not carried.is_file():
                    raise ValueError(
                        f"pad {index + 1} was to be kept, but the drive has no sound for it"
                    )
                shutil.copyfile(carried, target)
                total += playable_frames(target) * FRAME_BYTES
        if total > BANK_MAX_BYTES:
            raise ValueError(
                f"the bank is {total // (1024 * 1024)} MiB, over the "
                f"{BANK_MAX_BYTES // (1024 * 1024)} MiB a bank may take on the drive"
            )
        text = settings_text(bank)
        if len(text.encode("ascii")) > CONFIG_MAX_BYTES:
            raise ValueError("the settings file is larger than the deck will read")
        (staging / CONFIG_NAME).write_text(text, encoding="ascii")
    except BaseException:
        _discard(staging)
        raise

    replaced = final.is_dir()
    if replaced:
        final.rename(previous)
    try:
        staging.rename(final)
    except OSError:
        # Put back what was there before saying the save failed.
        if replaced:
            previous.rename(final)
        _discard(staging)
        raise
    _discard(previous)

    if activate:
        (root / ACTIVE_NAME).write_text(bank.name + "\n", encoding="utf-8")
    return final
