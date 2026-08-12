# SPDX-License-Identifier: MPL-2.0
"""Encode a separated vocal stem into the RX3 `.rx3stem` sidecar container."""

from __future__ import annotations

import math
import pathlib
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass


HEADER = struct.Struct("<8sIIIIQ32s")
MAGIC = b"RX3STM1\0"
SAMPLE_RATE = 44100
CHANNELS = 2
# Sample format identifier, ffmpeg raw format, and interleaved stereo frame size.
FORMATS = {"s16": (2, "s16le", 4), "f32": (1, "f32le", 8)}
# ffmpeg negotiates a filter chain backwards from the output format, so an
# `s16le` destination would hand `astats` samples already clamped to full scale
# and hide the very overshoot being measured. The conversion has to come after.
MEASURE = "aformat=sample_fmts=fltp,astats=reset=0"
# `astats` reports one figure per channel and one overall; the loudest wins.
# Each line carries an ffmpeg `[Parsed_astats_N @ ...]` prefix, so no anchor.
PEAK_LEVEL = re.compile(r"Peak level dB:\s*(-?\d+(?:\.\d+)?|-?inf)")
CLIPPED_SAMPLES = re.compile(r"Number of clipped samples:\s*(\d+)")


@dataclass(frozen=True)
class SidecarResult:
    output: pathlib.Path
    frames: int
    seconds: float
    payload_bytes: int
    # Factor applied to return the stem to the gain domain of the source file.
    gain: float = 1.0
    # Samples the container could not hold once that factor was applied.
    clipped: int = 0


def _decode(
    ffmpeg: pathlib.Path | str,
    arguments: list[str],
    *,
    report: bool = False,
) -> str:
    """Run one ffmpeg pass, returning its log when `report` asks for measurements."""
    level = "info" if report else "error"
    command = [str(ffmpeg), "-hide_banner", "-loglevel", level, "-y", *arguments]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = " ".join((result.stderr or result.stdout).split())[-260:]
        raise RuntimeError(f"ffmpeg exited with code {result.returncode}: {detail}")
    return result.stderr or ""


def _peak_amplitude(report: str) -> float | None:
    """The largest sample magnitude `astats` saw, or None when it said nothing.

    Measured before the container's own conversion, so a lossy or resampled
    source that reconstructs above full scale is reported as such.
    """
    levels = [
        -math.inf if value.endswith("inf") else float(value)
        for value in PEAK_LEVEL.findall(report)
    ]
    if not levels:
        return None
    loudest = max(levels)
    return 0.0 if loudest == -math.inf else 10.0 ** (loudest / 20.0)


def write_sidecar(
    vocals: pathlib.Path,
    output: pathlib.Path,
    *,
    ffmpeg: pathlib.Path | str = "ffmpeg",
    sample_format: str = "s16",
    match_full: pathlib.Path | None = None,
    separator_normalization: float | None = None,
) -> SidecarResult:
    """Convert `vocals` to the RX3 audio domain and write the sidecar container.

    `match_full` aligns the frame count to the full track decoded at 44.1 kHz
    rather than trusting the separator output duration.

    `separator_normalization` is the peak the separator scaled the mix to before
    inference, when its architecture does that. The stem it returns then carries
    the same `threshold / peak` factor, while the deck subtracts it from the
    untouched source; undoing the factor here keeps the two in one gain domain.
    Measuring rather than assuming covers the sources that decode above full
    scale, which are exactly the ones the separator rescales.
    """
    if sample_format not in FORMATS:
        raise ValueError(f"Unsupported sample format: {sample_format}")
    format_id, ffmpeg_format, frame_size = FORMATS[sample_format]

    with tempfile.TemporaryDirectory(prefix="rx3-sidecar-") as directory:
        workspace = pathlib.Path(directory)
        target_frames: int | None = None
        gain = 1.0
        if match_full is not None:
            full_raw = workspace / "full.s16le"
            # Measured after the resample, which is where librosa measures it,
            # and before the s16 conversion, which would clamp the overshoot.
            measured = _decode(ffmpeg, [
                "-i", str(match_full), "-map", "0:a:0", "-vn",
                "-af", f"aresample={SAMPLE_RATE},{MEASURE}",
                "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
                "-f", "s16le", str(full_raw),
            ], report=True)
            full_size = full_raw.stat().st_size
            if not full_size or full_size % 4:
                raise ValueError("full track decodes to empty or unaligned stereo PCM")
            target_frames = full_size // 4

            peak = _peak_amplitude(measured)
            # An unreadable report leaves the stem alone: a wrong correction is
            # worse than the one the pinned 1.0 threshold already avoids.
            if separator_normalization and peak and peak > separator_normalization:
                gain = peak / separator_normalization

        raw = workspace / f"vocal.{ffmpeg_format}"
        arguments = ["-i", str(vocals), "-map", "0:a:0", "-vn"]
        chain = [] if gain == 1.0 else [f"volume={gain:.9f}:precision=float"]
        if target_frames is not None:
            chain.extend([
                f"aresample={SAMPLE_RATE}", "apad", f"atrim=end_sample={target_frames}",
            ])
            arguments.extend(["-ac", str(CHANNELS)])
        else:
            arguments.extend(["-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS)])
        if chain:
            chain.append(MEASURE)
            arguments.extend(["-af", ",".join(chain)])
        arguments.extend(["-f", ffmpeg_format, str(raw)])
        measured = _decode(ffmpeg, arguments, report=bool(chain))
        # Only the samples where the vocal alone exceeds full scale are lost,
        # against every sample being wrong without the correction.
        clipped = max(
            (int(value) for value in CLIPPED_SAMPLES.findall(measured)), default=0
        )

        size = raw.stat().st_size
        if not size or size % frame_size:
            raise ValueError("empty or unaligned stereo payload")
        frames = size // frame_size
        if target_frames is not None and frames != target_frames:
            raise ValueError(
                f"vocal length mismatch after conversion: {frames} != {target_frames} frames"
            )
        header = HEADER.pack(
            MAGIC, SAMPLE_RATE, CHANNELS, format_id, HEADER.size, frames, b"\0" * 32
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as destination, raw.open("rb") as payload:
            destination.write(header)
            while chunk := payload.read(1024 * 1024):
                destination.write(chunk)

    return SidecarResult(
        output=output,
        frames=frames,
        seconds=frames / SAMPLE_RATE,
        payload_bytes=size,
        gain=gain,
        clipped=clipped,
    )
