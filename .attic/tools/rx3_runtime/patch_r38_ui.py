#!/usr/bin/env python3
"""Apply the minimal dual-tab UI experiment to the hardware-proven r38 hook."""

from __future__ import annotations

import argparse
from pathlib import Path


PATCHES = {
    # Reuse the now-disabled PLEASE WAIT buffer for a longer, combined label.
    0x0D20: (
        "50004c004500410053004500200057004100490054000000",
        "4b00450059002000200020005300540045004d0053000000",
    ),
    # Active ZOOM/GRID state: left edge 102 -> 10, width 87 -> 179.
    0x2E9C: ("6620a0e3", "0a20a0e3"),
    0x2EA8: ("573082e2", "b33082e2"),
    # text_stems (0xd14) -> combined label buffer (0xd20).
    0x2F78: ("78defeff", "84defeff"),
    # The stock header stops redrawing after startup. Do not expire the custom
    # touch zones 500 ms after its last draw; patch_state still gates them.
    0x30C0: ("096098e1", "080000ea"),
    # After selecting either half, continue through rbp's stock ZOOM/GRID
    # handler so it invalidates and redraws the affected windows immediately.
    0x3184: ("360000ea", "a8ffffea"),
    0x3238: ("090000ea", "7bffffea"),
    # Native caution workers are disabled; invoking that path froze rbp.
    0x4584: ("00482de9", "1eff2fe1"),
    0x45E8: ("30482de9", "1eff2fe1"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    image = bytearray(args.input.read_bytes())
    for offset, (expected_hex, replacement_hex) in PATCHES.items():
        expected = bytes.fromhex(expected_hex)
        replacement = bytes.fromhex(replacement_hex)
        if len(expected) != len(replacement):
            raise SystemExit(f"invalid patch size at 0x{offset:x}")
        actual = bytes(image[offset : offset + len(expected)])
        if actual != expected:
            raise SystemExit(
                f"guard mismatch at 0x{offset:x}: {actual.hex()} != {expected.hex()}"
            )
        image[offset : offset + len(expected)] = replacement

    args.output.write_bytes(image)


if __name__ == "__main__":
    main()
