#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Command-line front end for the RX3 Stems vocal sidecar encoder."""

from __future__ import annotations

import argparse
import pathlib
import sys


if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools.rx3_stems.sidecar import write_sidecar


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an RX3 Stems vocal sidecar")
    parser.add_argument("vocals", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument(
        "--format", choices=("s16", "f32"), default="s16",
        help="s16 uses half the RAM; f32 preserves the exact floating-point stem",
    )
    parser.add_argument(
        "--match-full", type=pathlib.Path,
        help="trim/pad validation against the exact 44.1 kHz full track",
    )
    parser.add_argument(
        "--separator-normalization", type=float, metavar="PEAK",
        help="peak the separator scaled the mix to before inference (MDX and "
             "MDXC); the same factor is undone here so the deck can subtract "
             "the stem from the untouched source. Requires --match-full",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg", help="path to the ffmpeg binary")
    args = parser.parse_args()
    if args.separator_normalization is not None and args.match_full is None:
        parser.error("--separator-normalization needs --match-full to measure against")

    result = write_sidecar(
        args.vocals,
        args.output,
        ffmpeg=args.ffmpeg,
        sample_format=args.format,
        match_full=args.match_full,
        separator_normalization=args.separator_normalization,
    )
    mib = result.payload_bytes / (1024 * 1024)
    print(
        f"created {result.output}: {result.frames} frames, {result.seconds:.3f} s, "
        f"44.1 kHz stereo {args.format}, {mib:.2f} MiB payload"
    )
    if result.gain != 1.0:
        print(f"gain restored by x{result.gain:.5f}")
    if result.clipped:
        print(f"warning: {result.clipped} sample(s) exceeded full scale and were clipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
