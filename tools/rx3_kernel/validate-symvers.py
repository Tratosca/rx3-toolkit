#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
import hashlib
import re
import sys
from pathlib import Path


SYMVERS_LINE = re.compile(
    r"^(0x[0-9a-f]{8})\t([A-Za-z_][A-Za-z0-9_]*)\t"
    r"vmlinux\t(EXPORT_SYMBOL(?:_GPL)?)$"
)


def read_profile(path, checksum_path=None):
    profile_path = Path(path)
    if checksum_path is not None:
        checksum = Path(checksum_path).read_text()
        match = re.fullmatch(
            r"([0-9a-f]{64})  production\.symvers\n", checksum
        )
        if match is None:
            raise SystemExit("invalid production.symvers.sha256")

        actual = hashlib.sha256(profile_path.read_bytes()).hexdigest()
        if actual != match.group(1):
            raise SystemExit("production.symvers checksum mismatch")

    entries = {}

    for number, line in enumerate(profile_path.read_text().splitlines(), 1):
        match = SYMVERS_LINE.fullmatch(line)
        if match is None:
            raise SystemExit(f"invalid production.symvers line {number}: {line}")

        crc, symbol, _export = match.groups()
        if symbol in entries:
            raise SystemExit(f"duplicate production symbol: {symbol}")
        entries[symbol] = int(crc, 16)

    if not entries:
        raise SystemExit("production.symvers is empty")

    return entries


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "profile":
        read_profile(sys.argv[2], sys.argv[3])
        return

    raise SystemExit("usage: validate-symvers.py profile PROFILE CHECKSUM")


if __name__ == "__main__":
    main()
