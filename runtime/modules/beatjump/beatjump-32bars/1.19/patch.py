#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Change the RX3 Beat Jump outer pads from +/-8 to +/-32 beats."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from patchlib import run  # noqa: E402


PATCHES = [
    # Negative-path magnitude conversion in single precision.
    (0x0600A0, "c88ab7ee", "c88ab0ee", "vcvt.f64.f32 d8,s16 -> vabs.f32 s16,s16"),
    (0x0600A4, "088b38ee", "087a78ee", "vadd.f64 d8,d8,d8 -> vadd.f32 s15,s16,s16"),
    (0x0600A8, "c87bfcee", "e77afcee", "vcvt.u32.f64 s15,d8 -> vcvt.u32.f32 s15,s15"),
    # Negative and positive jump values.
    (0x060180, "008ab2ee", "c254a0e3", "load -32.0f through r5"),
    (0x060184, "c154a0e3", "105a08ee", "move negative guard magnitude to s16"),
    (0x06018C, "008ab2ee", "4254a0e3", "load +32.0f through r5"),
    (0x060190, "105a18ee", "105a08ee", "move positive guard magnitude to s16"),
    # Availability LED threshold. The adjacent Loop Move table is unchanged.
    (0x4C8CC4, "10000000", "40000000", "LED threshold: 16 -> 64 half-beats"),
    # Reuse the non-directional 32 images from the Beat Loop page.
    (0x51E5D0, "f2130000", "03140000", "pad 7 off image: 5106 -> 5123"),
    (0x51E5B8, "f3130000", "04140000", "pad 7 on image: 5107 -> 5124"),
    (0x51E594, "f4130000", "03140000", "pad 8 off image: 5108 -> 5123"),
    (0x51E57C, "f5130000", "04140000", "pad 8 on image: 5109 -> 5124"),
]


if __name__ == "__main__":
    raise SystemExit(run(__doc__.splitlines()[0], PATCHES))
