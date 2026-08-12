#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Remove the RX3 Beat Jump grid reservation without changing global Quantize."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from patchlib import run  # noqa: E402


PATCHES = [
    (0x0A9DD4, "3d00000a", "0000a0e1", "quantized branch -> ARM NOP"),
]


if __name__ == "__main__":
    raise SystemExit(run(__doc__.splitlines()[0], PATCHES))
