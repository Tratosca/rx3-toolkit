#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Guarded binary patch engine shared by RX3 Beat Jump patches."""

import argparse
import pathlib
import shutil


def run(description, patches):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("binary")
    parser.add_argument("-o", "--output")
    parser.add_argument("--check", action="store_true", help="inspect without writing")
    parser.add_argument("--revert", action="store_true", help="restore stock bytes")
    args = parser.parse_args()

    source = pathlib.Path(args.binary)
    data = bytearray(source.read_bytes())

    if args.check:
        for offset, stock, patched, label in patches:
            observed = bytes(data[offset:offset + 4]).hex()
            state = "STOCK" if observed == stock else "PATCHED" if observed == patched else "UNKNOWN"
            print(f"0x{offset:07x} {observed} {state:7} {label}")
        return 0

    for offset, stock, patched, label in patches:
        expected, replacement = (patched, stock) if args.revert else (stock, patched)
        observed = bytes(data[offset:offset + 4]).hex()
        if observed == replacement:
            print(f"0x{offset:07x} already in requested state")
            continue
        if observed != expected:
            parser.error(
                f"0x{offset:07x}: unexpected bytes {observed}; expected {expected}. "
                "Check the rbp firmware build and patch order."
            )
        data[offset:offset + 4] = bytes.fromhex(replacement)
        print(f"0x{offset:07x} {label}")

    destination = pathlib.Path(args.output) if args.output else source.with_name(source.name + ".patched")
    destination.write_bytes(bytes(data))
    shutil.copymode(source, destination)
    unit = "word" if len(patches) == 1 else "words"
    print(f"\n{len(patches)} {unit} modified")
    print(f"Wrote {destination} ({destination.stat().st_size} bytes)")
    return 0
