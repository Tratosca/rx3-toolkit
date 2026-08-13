#!/usr/bin/env python3
"""Score the hook's own pitch shifter with the metrics used on the firmware's.

emulate_pitch.py measures rbp's native BeatEffectPitch under emulation. This
runs the replacement shifter natively and applies the same analysis, so the two
tables can be read side by side.

Usage:
    measure_shifter.py [--semitones -12 .. 12] [--frequency 440]
"""

from __future__ import annotations

import argparse
import math
import pathlib
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from rx3_firmware.emulate_pitch import (  # noqa: E402
    goertzel,
    modulation,
    peak_near,
    semitone_ratio,
)

SOURCE = pathlib.Path(__file__).resolve().parent / "measure_shifter.c"


def build(destination: pathlib.Path) -> pathlib.Path:
    binary = destination / "measure_shifter"
    subprocess.run(
        ["clang", "-O2", "-Wall", "-Wextra", "-o", str(binary), str(SOURCE), "-lm"],
        check=True,
    )
    return binary


def render(
    binary: pathlib.Path, semitones: int, rate: int, frames: int, block: int,
    frequency: float,
) -> list[float]:
    result = subprocess.run(
        [
            str(binary),
            str(semitones),
            str(rate),
            str(frames),
            str(block),
            str(frequency),
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    count = len(result.stdout) // 8
    samples = struct.unpack(f"<{count * 2}f", result.stdout[: count * 8])
    return list(samples[0::2])  # left channel


def report(
    binary: pathlib.Path, semitones: int, rate: int, block: int, frequency: float
) -> None:
    left = render(binary, semitones, rate, rate * 2, block, frequency)
    # Drop the first third of a second: the glide and the initial grain fill.
    tail = left[rate // 3 :]
    if not tail or max(abs(value) for value in tail) < 1e-6:
        print(f"{semitones:+3d}   no output")
        return

    nominal = frequency * semitone_ratio(semitones)
    measured = peak_near(tail, nominal, rate)
    total = sum(value * value for value in tail) / len(tail)
    count = len(tail)

    def power_at(target: float) -> float:
        if target <= 0.0 or target >= rate / 2.0 or total <= 0.0:
            return 0.0
        return 2.0 * (goertzel(tail, target, rate) / count) ** 2 / total

    tonal = power_at(measured)
    leak = power_at(frequency)
    harmonic = sum(power_at(measured * multiple) for multiple in (2, 3, 4))
    depth, ripple_rate = modulation(tail, rate)
    cents = 1200.0 * math.log2(measured / nominal)
    peak = max(abs(value) for value in tail)
    print(
        f"{semitones:+3d}  {measured:8.1f}  {cents:+6.1f}  "
        f"{100.0 * tonal:6.1f}  {100.0 * (1.0 - tonal):6.1f}  "
        f"{100.0 * leak:6.1f}  {100.0 * harmonic:6.1f}  {depth:6.1f}  "
        f"{ripple_rate:7.1f}  {peak:5.3f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--block-frames", type=int, default=64)
    parser.add_argument("--frequency", type=float, default=440.0)
    parser.add_argument(
        "--semitones", type=int, nargs="*", default=[-12, -7, -5, 5, 7, 12]
    )
    arguments = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="rx3-shifter-") as temporary:
        binary = build(pathlib.Path(temporary))
        print(
            "st   measured   cents  tonal%  other%   leak%   harm%  AM dB  "
            "AM Hz   peak"
        )
        for semitones in arguments.semitones:
            report(
                binary,
                semitones,
                arguments.sample_rate,
                arguments.block_frames,
                arguments.frequency,
            )


if __name__ == "__main__":
    main()
