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
# An mp3 or AAC file declares the samples its encoder prepended, and ffmpeg
# drops them. The deck does not: `PcmReader` position zero is the first sample
# its own decoder emits, padding included. A stem cut on ffmpeg's grid
# therefore sits ahead of the mix the deck plays, and 25 ms of offset is enough
# for the subtraction to leave the whole vocal audible while the vocal alone
# still sounds correct. `skip_manual` hands the decoder's output over untouched,
# which is the grid every frame index here is expressed in.
UNTRIMMED = ("-flags2", "+skip_manual")
# No encoder prepends anything close to a second; a larger apparent offset is a
# measurement gone wrong rather than padding.
MAX_ENCODER_DELAY = SAMPLE_RATE
# Long enough that the pattern cannot repeat by chance, short enough to read.
PROBE_FRAMES = 4096
# Positions in the trimmed decode to take that pattern from. Silence matches
# everywhere, so a probe that is not unique is abandoned for the next one.
PROBE_POSITIONS = (0.5, 0.25, 0.75, 0.1)


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
    # Encoder padding the stem was pushed back by to sit on the deck's grid.
    delay: int = 0
    # False when that padding could not be measured and the stem was left on
    # the separator's own grid, which is only correct for a source without any.
    aligned: bool = True


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


def _encoder_delay(trimmed: pathlib.Path, untrimmed: pathlib.Path) -> int | None:
    """Frames ffmpeg dropped from the head of `trimmed`, or None if unreadable.

    Both files hold the same decoder output, one with the declared padding
    removed and one without, so the offset is found by locating a stretch of the
    trimmed decode inside the untrimmed one rather than by trusting a timestamp.
    The first frames differ either way, which is why the pattern is taken from
    further in.
    """
    trimmed_frames = trimmed.stat().st_size // 4
    extra = untrimmed.stat().st_size // 4 - trimmed_frames
    if extra == 0:
        return 0
    if extra < 0:
        return None
    limit = min(extra, MAX_ENCODER_DELAY)
    with trimmed.open("rb") as source, untrimmed.open("rb") as reference:
        for fraction in PROBE_POSITIONS:
            position = int(trimmed_frames * fraction)
            if position + PROBE_FRAMES > trimmed_frames:
                continue
            source.seek(position * 4)
            probe = source.read(PROBE_FRAMES * 4)
            reference.seek(position * 4)
            window = reference.read((limit + PROBE_FRAMES) * 4)
            offset = window.find(probe)
            # An offset off the frame grid, or a pattern that repeats, means the
            # match says nothing; silence is the usual reason for both.
            if offset < 0 or offset % 4 or window.find(probe, offset + 4) >= 0:
                continue
            return offset // 4
    return None


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

    `match_full` aligns the stem to the full track as the deck's own decoder
    emits it, rather than trusting the separator output duration: the frame
    count comes from that decode, and any encoder padding ffmpeg dropped on the
    way into the separator is put back at the head of the stem.

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
        delay = 0
        aligned = True
        if match_full is not None:
            def decode_full(name: str, *, untrimmed: bool) -> tuple[pathlib.Path, str]:
                raw_path = workspace / name
                # Measured after the resample, which is where librosa measures
                # it, and before the s16 conversion, which would clamp the
                # overshoot.
                report = _decode(ffmpeg, [
                    *(UNTRIMMED if untrimmed else ()),
                    "-i", str(match_full), "-map", "0:a:0", "-vn",
                    "-af", f"aresample={SAMPLE_RATE},{MEASURE}",
                    "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
                    "-f", "s16le", str(raw_path),
                ], report=True)
                size = raw_path.stat().st_size
                if not size or size % 4:
                    raise ValueError("full track decodes to empty or unaligned stereo PCM")
                return raw_path, report

            # The separator's grid, which its stem comes back on, and the deck's
            # grid, which the sidecar is indexed against.
            trimmed_raw, trimmed_report = decode_full("trimmed.s16le", untrimmed=False)
            offset: int | None = None
            try:
                untrimmed_raw, untrimmed_report = decode_full("full.s16le", untrimmed=True)
            except (RuntimeError, ValueError):
                # An ffmpeg too old to know the flag, rather than a broken file:
                # the same decode already succeeded without it.
                untrimmed_raw = None
            else:
                offset = _encoder_delay(trimmed_raw, untrimmed_raw)
            if offset is None:
                # Staying on the separator's grid is what every release before
                # this did, and it is right for a source declaring no padding.
                aligned = False
                full_raw, measured = trimmed_raw, trimmed_report
                if untrimmed_raw is not None:
                    untrimmed_raw.unlink()
            else:
                delay = offset
                full_raw, measured = untrimmed_raw, untrimmed_report
                trimmed_raw.unlink()
            target_frames = full_raw.stat().st_size // 4

            peak = _peak_amplitude(measured)
            # An unreadable report leaves the stem alone: a wrong correction is
            # worse than the one the pinned 1.0 threshold already avoids.
            if separator_normalization and peak and peak > separator_normalization:
                gain = peak / separator_normalization

        raw = workspace / f"vocal.{ffmpeg_format}"
        arguments = ["-i", str(vocals), "-map", "0:a:0", "-vn"]
        chain = [] if gain == 1.0 else [f"volume={gain:.9f}:precision=float"]
        if target_frames is not None:
            chain.append(f"aresample={SAMPLE_RATE}")
            # Silence for exactly the padding the deck's decoder will play
            # before the first sample the separator ever saw.
            if delay:
                chain.append(f"adelay=delays={delay}S:all=1")
            chain.extend(["apad", f"atrim=end_sample={target_frames}"])
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
        delay=delay,
        aligned=aligned,
    )
