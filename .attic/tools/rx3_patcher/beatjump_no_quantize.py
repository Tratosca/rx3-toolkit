#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Remove the RX3 Beat Jump grid reservation without changing global Quantize."""

from tools.rx3_patcher.patchlib import run

MODULE_ID = "beatjump-no-quantize"

PATCHES = [
    (0x0A9DD4, "3d00000a", "0000a0e1", "quantized branch -> ARM NOP"),
]


if __name__ == "__main__":
    raise SystemExit(run(__doc__.splitlines()[0], PATCHES))
