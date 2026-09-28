# SPDX-License-Identifier: MPL-2.0
"""Host reconstruction of the player's s16-role, float32-mix audio path."""
from __future__ import annotations

import array
import math
import operator
from itertools import repeat
import struct
from dataclasses import dataclass, field

from app.localization import LocalizedError

FLOAT = struct.Struct("<f")
RAMP_FRAMES = 256


def f32(value):
    return FLOAT.unpack(FLOAT.pack(value))[0]


@dataclass
class MixState:
    gain: list = field(default_factory=lambda: [1.0] * 4)
    start: list = field(default_factory=lambda: [1.0] * 4)
    target: list = field(default_factory=lambda: [1.0] * 4)
    cursor: int = RAMP_FRAMES

    def as_dict(self):
        return {"gain": list(self.gain), "start": list(self.start),
                "target": list(self.target), "cursor": self.cursor}

    @classmethod
    def read(cls, value):
        if value is None:
            return cls()
        try:
            vectors = [[float(v) for v in value[key]] for key in ("gain", "start", "target")]
            cursor = int(value["cursor"])
            if not 0 <= cursor <= RAMP_FRAMES or any(len(v) != 4 for v in vectors):
                raise ValueError()
            if any(not math.isfinite(v) or not 0 <= v <= 1 for vector in vectors for v in vector):
                raise ValueError()
            return cls(*vectors, cursor)
        except (TypeError, KeyError, ValueError):
            raise LocalizedError("stems.auditionSelection") from None


def reconstruct(mix, roles, selected, state=None, *, timeline=None):
    state = state or MixState()
    count = len(roles)
    available = (2 << count) - 1
    if not 1 <= count <= 3 or selected < 0 or selected & ~available or len(mix) % 2:
        raise LocalizedError("stems.auditionSelection")
    if any(len(role) != len(mix) for role in roles):
        raise LocalizedError("stems.auditionLength")
    output = array.array("f", mix)
    target = [float(bool(selected & (1 << (0 if i == 3 else i)))) for i in range(count + 1)]
    changed = any(target[i] != state.target[i] for i in range(count + 1))
    if changed:
        state.start = list(state.gain)
        state.target[:count + 1] = target
        state.cursor = 0
    elif state.cursor >= RAMP_FRAMES:
        state.gain[:count + 1] = target
        if selected == available:
            return output
    for frame in range(len(mix) // 2):
        index = frame * 2
        if mix[index] == 0 and mix[index + 1] == 0:
            continue
        if state.cursor < RAMP_FRAMES:
            state.cursor += 1
            alpha = state.cursor / RAMP_FRAMES
            for role in range(count + 1):
                state.gain[role] = f32(state.start[role] + f32(f32(state.target[role] - state.start[role]) * alpha))
            if timeline is not None:
                timeline.append([frame + 1, state.as_dict()])
        residual = state.gain[0]
        for channel in (0, 1):
            value = f32(mix[index + channel] * residual)
            for role in range(count):
                gain = f32(f32(state.gain[role + 1] - residual) / 32768.0)
                value = f32(value + f32(roles[role][index + channel] * gain))
            output[index + channel] = value
        if state.cursor >= RAMP_FRAMES:
            state.gain[:count + 1] = state.target[:count + 1]
    return output


def reconstruct_static(mix, roles, selected):
    """Exact player arithmetic for waveform masks, without volume ramps.

    Each array construction rounds one addition to float32, in player order.
    An s16 or gain-restored float32 value times 0 or +/-2**-15 is already exactly representable, so
    it needs no struct pack/unpack. Only current one/two-file packages use it.
    """
    count = len(roles)
    if (not 1 <= count <= 2 or selected < 0 or
            selected > (3 if count == 1 else 7) or len(mix) % 2):
        raise LocalizedError("stems.auditionSelection")
    if any(len(role) != len(mix) for role in roles):
        raise LocalizedError("stems.auditionLength")
    if selected == (2 << count) - 1:
        return array.array("f", mix)
    residual = float(bool(selected & 1))
    output = array.array("f", map(operator.mul, mix, repeat(residual)))
    for index, role in enumerate(roles):
        bit = 1 << (index + 1)
        gain = (float(bool(selected & bit)) - residual) / 32768.0
        # Keep even zero-gain additions: they can change the sign of zero.
        output = array.array("f", map(operator.add, output, map(operator.mul, role, repeat(gain))))
    # The player suppresses all stems when both original channels are zero.
    for index in range(0, len(mix), 2):
        if mix[index] == 0 and mix[index + 1] == 0:
            output[index] = mix[index]
            output[index + 1] = mix[index + 1]
    return output
