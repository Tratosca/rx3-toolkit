# SPDX-License-Identifier: MPL-2.0
"""What the RX3 stems loader accepts, and what one track's stems cost it.

The values are those of `mod/modules/stems/rx3_stems_limits.h`.
`tests/test_stem_limits.py` compiles that header and fails when they differ.

Three limits apply to a package, and they are not the same kind of limit:

- the frame count, fixed for each track: 0.1 s to 31 min 42 s;
- the package size, fixed for each track, since the loader keeps the whole
  file resident (PCM, waveforms, index and manifest);
- the room left by the other deck and by the player, known only on the deck:
  both decks share one 512 MiB ceiling, and each allocation keeps 300 MiB of
  available memory for the player.

The first two decide a certain refusal. The third is a risk, reported as such.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.localization import LocalizedError, Message

SAMPLE_RATE = 44100
MIN_FRAMES = 4410
MAX_FRAMES = 0x5000000
RESIDENT_BYTES = 0x20000000
PLAYER_RESERVE_KIB = 0x4B000
MANIFEST_BYTES = 65536
MAX_COLUMNS = 540000
WAVE_STEP = SAMPLE_RATE // 150
# RX3WAV2/3 store BLUE + RGB + 3Band: six bytes per combination/cell.
WAVE_STRIDE = 6
# A library lists whole seconds, and decoding a lossy file keeps its encoder
# padding. The decoded length can differ from the listed one by this much.
DURATION_MARGIN = 2 * SAMPLE_RATE
# Past half the ceiling, two such tracks no longer fit on the two decks.
SHARED_BYTES = RESIDENT_BYTES // 2


def package_bytes(frames, roles, *, stride=WAVE_STRIDE, manifest=MANIFEST_BYTES, waveforms=True):
    """Size of a package holding `roles` PCM stems, as `package.write` lays it out.

    The waveform section carries all three or seven audible combinations.
    Explicit legacy strides (1/2) retain role-based accounting. With the
    default `manifest`, the result is an upper bound.
    """
    columns = (frames + WAVE_STEP - 1) // WAVE_STEP
    pcm = roles * (64 + frames * 4)
    combinations = (3 if roles == 1 else 7) if stride == 6 else roles + 1
    wave = (128 + combinations * 64 + combinations * columns * stride) if waveforms else 0
    return 64 + (roles + 2) * 64 + pcm + wave + manifest


def max_frames(roles, **sizes):
    """The longest track, in frames, whose package the loader accepts."""
    low, high = MIN_FRAMES, MAX_FRAMES
    if package_bytes(high, roles, **sizes) <= RESIDENT_BYTES:
        return high
    while low < high:
        middle = (low + high + 1) // 2
        if package_bytes(middle, roles, **sizes) <= RESIDENT_BYTES:
            low = middle
        else:
            high = middle - 1
    return low


def clock(frames):
    """A duration as the interface writes it, rounded down: 31 min 42 s."""
    seconds = int(frames // SAMPLE_RATE)
    # Non-breaking spaces: the value never wraps inside a sentence.
    return f"{seconds // 60}\u00a0min\u00a0{seconds % 60:02d}\u00a0s"


def mib(size):
    return Message("unit.mib", value=round(size / 1048576, 1))


@dataclass(frozen=True)
class Verdict:
    """What the loader will do with one track's package.

    `status` is `ok`, `shared` (fits alone, may be refused next to the other
    deck), `near` (a listed duration too close to a limit to decide),
    `refused` or `unknown`. `reason` names the limit behind `refused` or `near`.
    """

    status: str
    reason: str | None = None
    frames: int | None = None
    size: int | None = None
    waveforms: bool = True

    @property
    def refused(self):
        return self.status == "refused"

    def message(self, roles):
        """The sentence the interface shows, with the action that resolves it.

        It does not name the track: the list or the notice around it does.
        """
        if self.status == "refused" and self.reason == "short":
            return Message("stems.limitShort")
        if self.status == "refused" and self.reason == "duration":
            return Message("stems.limitDuration", duration=clock(self.frames),
                           limit=clock(MAX_FRAMES))
        if self.status == "refused":
            return Message("stems.limitSize", size=mib(self.size),
                           limit=mib(RESIDENT_BYTES), duration=clock(max_frames(1, waveforms=self.waveforms)))
        if self.status == "near" and self.reason == "short":
            return Message("stems.limitNearShort")
        if self.status == "near":
            limit = MAX_FRAMES if self.reason == "duration" else max_frames(roles, waveforms=self.waveforms)
            return Message("stems.limitNear", duration=clock(self.frames), limit=clock(limit))
        if self.status == "shared":
            return Message("stems.limitShared", size=mib(self.size),
                           free=mib(RESIDENT_BYTES - self.size))
        if self.status == "unknown":
            return Message("stems.sizeUnknown")
        return Message("stems.limitFits", size=mib(self.size))


def assess(frames, roles, *, waveforms=True):
    """Verdict for an exact frame count, as decoded."""
    size = package_bytes(frames, roles, waveforms=waveforms)
    if frames < MIN_FRAMES:
        return Verdict("refused", "short", frames, size, waveforms)
    if frames > MAX_FRAMES:
        return Verdict("refused", "duration", frames, size, waveforms)
    if size > RESIDENT_BYTES:
        return Verdict("refused", "size", frames, size, waveforms)
    if size > SHARED_BYTES:
        return Verdict("shared", None, frames, size, waveforms)
    return Verdict("ok", None, frames, size, waveforms)


def estimate(seconds, roles, *, waveforms=True):
    """Verdict for a listed duration, which is only known to the second.

    A refusal is reported only when every length the listing allows is refused.
    A track that is refused at one end of that range and not at the other is
    `near`: the job decodes it and decides on the exact count.
    """
    if not seconds or seconds <= 0:
        return Verdict("unknown")
    frames = round(seconds * SAMPLE_RATE)
    shortest = assess(max(0, frames - DURATION_MARGIN), roles, waveforms=waveforms)
    longest = assess(frames + DURATION_MARGIN, roles, waveforms=waveforms)
    middle = assess(frames, roles, waveforms=waveforms)
    if shortest.refused and longest.refused:
        return Verdict("refused", (middle if middle.refused else longest).reason,
                       frames, middle.size, waveforms)
    if shortest.refused or longest.refused:
        reason = (longest if longest.refused else shortest).reason
        return Verdict("near", reason, frames, middle.size, waveforms)
    return Verdict(middle.status, None, frames, middle.size, waveforms)


def require(frames, roles, *, waveforms=True):
    """Raise the interface's refusal when the loader would reject this package."""
    verdict = assess(frames, roles, waveforms=waveforms)
    if verdict.refused:
        raise LimitError(verdict.message(roles))
    return verdict


class LimitError(LocalizedError):
    """A certain refusal, raised before any costly work where possible."""

    def __init__(self, message):
        self.message = message
        ValueError.__init__(self, message)
