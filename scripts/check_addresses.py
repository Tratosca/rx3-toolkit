#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Does a player binary still hold what the mod expects at every address?

The mod refuses rather than guesses: each inline hook compares eight bytes of
prologue before it writes, and each byte patch states the word it expects to
find. That is the check the deck performs on itself. This runs the same check on
the computer, against a binary given on the command line, which is what turns
"does the mod support this firmware" from an afternoon into a minute.

It reads the addresses and the guards out of the core's own sources, so it
cannot drift from what the deck will do. It ships no firmware and embeds no
binary: point it at an rbp you already have.

    python3 scripts/check_addresses.py path/to/rbp

Exit status is zero when every address holds what is expected.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import struct
import sys

REPOSITORY = pathlib.Path(__file__).resolve().parent.parent


def loadable_segments(binary: bytes) -> list[tuple[int, int, int]]:
    """(vaddr, offset, size) for each PT_LOAD, so an address can be read."""
    if binary[:4] != b"\x7fELF" or binary[4] != 1:
        raise SystemExit("not a 32-bit ELF")
    phoff, = struct.unpack_from("<I", binary, 0x1C)
    entry_size, count = struct.unpack_from("<HH", binary, 0x2A)
    segments = []
    for index in range(count):
        base = phoff + index * entry_size
        kind, offset, vaddr, _, size, _, _, _ = struct.unpack_from("<IIIIIIII", binary, base)
        if kind == 1:
            segments.append((vaddr, offset, size))
    return segments


def read_at(binary: bytes, segments, vaddr: int, length: int = 8) -> bytes | None:
    for start, offset, size in segments:
        if start <= vaddr < start + size:
            at = offset + (vaddr - start)
            return binary[at:at + length]
    return None


def sources() -> str:
    directory = REPOSITORY / "mod/modules"
    parts = [
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(directory.glob("*/*.h")) + sorted(directory.glob("*/*.c"))
    ]
    if not parts:
        raise SystemExit("no module sources found under mod/modules")
    return "\n".join(parts)


def guarded_hooks(text: str) -> list[tuple[str, int, bytes]]:
    """Every (symbol, address, expected prologue) the core installs a hook at."""
    defines = {
        match.group(1): int(match.group(2), 16)
        for match in re.finditer(
            r"#define\s+([A-Z_0-9]+)\s+\(\(unsigned long\)\s*(0x[0-9a-fA-F]+)[uUlL]*\s*\)", text
        )
    }
    guards = {
        match.group(1): bytes(int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]+)", match.group(2)))
        for match in re.finditer(
            r"static const uint8_t (\w+_guard)\[8\]\s*=\s*\{\s*([^}]+)\}", text
        )
    }
    found, seen = [], set()
    for match in re.finditer(
        r"install_(?:pc_ldr_)?hook\(\s*&(\w+),\s*([A-Za-z_0-9]+),\s*(\w+_guard)", text
    ):
        where, guard = match.group(2), match.group(3)
        literal = where.strip().rstrip("uUlL")
        address = defines.get(where)
        if address is None and literal.lower().startswith("0x"):
            address = int(literal, 16)
        if address is None or guard not in guards or (address, guard) in seen:
            continue
        seen.add((address, guard))
        found.append((where, address, guards[guard]))
    return sorted(found, key=lambda row: row[1])


def guarded_calls(text: str) -> list[tuple[str, int, bytes]]:
    """Addresses called directly rather than hooked, but guarded all the same.

    A hook records its guard in the install_hook call. A direct call has nowhere
    to put it, so the convention is a `#define NAME` beside a
    `static const uint8_t name_guard[8]`. This pairs them by that name, which is
    also what keeps the convention honest: a guard nobody can pair with an
    address is reported rather than ignored.
    """
    defines = {
        match.group(1): int(match.group(2), 16)
        for match in re.finditer(
            r"#define\s+([A-Z_0-9]+)\s+\(\(unsigned long\)\s*(0x[0-9a-fA-F]+)[uUlL]*\s*\)", text
        )
    }
    guards = {
        match.group(1): bytes(int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]+)", match.group(2)))
        for match in re.finditer(
            r"static const uint8_t (\w+_guard)\[8\]\s*=\s*\{\s*([^}]+)\}", text
        )
    }
    hooked = {match.group(1) for match in re.finditer(
        r"install_(?:pc_ldr_)?hook\([^)]*?(\w+_guard)", text, re.S)}
    found = []
    for name, expected in sorted(guards.items()):
        if name in hooked:
            continue
        symbol = name[:-len("_guard")].upper()
        if symbol in defines:
            found.append((symbol, defines[symbol], expected))
    return found


def registered_patches() -> list[tuple[str, int, bytes]]:
    """Every (module, file offset, stock word) a module.sh expects to find."""
    rows = []
    for script in sorted((REPOSITORY / "mod/modules").glob("*/module.sh")):
        for match in re.finditer(
            r"register_patch\s+(\d+)\s+'([^']+)'\s+'([^']+)'\s+(\S+)",
            script.read_text(encoding="utf-8"),
        ):
            stock = bytes(int(part, 8) for part in match.group(2).split("\\") if part)
            rows.append((script.parent.name, int(match.group(1)), stock))
    return sorted(rows, key=lambda row: row[1])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("binary", type=pathlib.Path, help="the player binary to check")
    parser.add_argument("--quiet", action="store_true", help="only report what differs")
    arguments = parser.parse_args(argv)

    binary = arguments.binary.read_bytes()
    segments = loadable_segments(binary)
    text = sources()

    intact = differ = 0
    # Several guards at one address are alternatives, not separate checks. The
    # image-table lookup is hooked with the word the launch patch writes, and
    # again with the stock word underneath it, so an unpatched binary matches the
    # second and a patched one the first. Either is the address holding its own.
    by_address: dict[int, list[tuple[str, bytes]]] = {}
    for where, address, expected in guarded_hooks(text):
        by_address.setdefault(address, []).append((where, expected))

    for address, alternatives in sorted(by_address.items()):
        found = read_at(binary, segments, address)
        where = alternatives[0][0]
        if any(found == expected for _, expected in alternatives):
            intact += 1
            if not arguments.quiet:
                note = "" if len(alternatives) == 1 else f"  ({len(alternatives)} accepted forms)"
                print(f"  holds    {where:<24}{address:#010x}{note}")
        else:
            differ += 1
            print(f"  DIFFERS  {where:<24}{address:#010x}")
            for _, expected in alternatives:
                print(f"           expected {expected.hex(' ')}")
            print(f"           found    {found.hex(' ') if found else '(outside any loaded segment)'}")

    for where, address, expected in guarded_calls(text):
        found = read_at(binary, segments, address)
        if found == expected:
            intact += 1
            if not arguments.quiet:
                print(f"  holds    {where:<24}{address:#010x}  (called, not hooked)")
        else:
            differ += 1
            print(f"  DIFFERS  {where:<24}{address:#010x}  (called, not hooked)")
            print(f"           expected {expected.hex(' ')}")
            print(f"           found    {found.hex(' ') if found else '(outside any loaded segment)'}")

    for module, offset, stock in registered_patches():
        found = binary[offset:offset + len(stock)]
        if found == stock:
            intact += 1
            if not arguments.quiet:
                print(f"  holds    {module:<24}offset {offset}")
        else:
            differ += 1
            print(f"  DIFFERS  {module:<24}offset {offset}")
            print(f"           expected {stock.hex(' ')}")
            print(f"           found    {found.hex(' ')}")

    print(f"\n{intact} intact, {differ} different")
    if differ:
        print("An address that moved means this binary needs work before it is claimed.")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
