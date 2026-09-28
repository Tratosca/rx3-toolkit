#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
import hashlib
import re
import struct
import subprocess
import sys
import tempfile
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


def run(*arguments):
    return subprocess.run(
        arguments, check=True, text=True, stdout=subprocess.PIPE
    ).stdout


def module_versions(path):
    with tempfile.NamedTemporaryFile() as section:
        run(
            "arm-linux-gnueabi-objcopy",
            "--dump-section",
            f"__versions={section.name}",
            str(path),
            "/dev/null",
        )
        data = Path(section.name).read_bytes()

    if len(data) % 64:
        raise SystemExit(f"malformed __versions section: {path}")

    versions = {}
    for offset in range(0, len(data), 64):
        crc = struct.unpack_from("<I", data, offset)[0]
        symbol = data[offset + 4 : offset + 64].split(b"\0", 1)[0].decode()
        versions[symbol] = crc

    return versions


def module_exports(path):
    exports = set()
    for line in run("arm-linux-gnueabi-nm", str(path)).splitlines():
        symbol = line.split()[-1]
        if symbol.startswith("__ksymtab_"):
            exports.add(symbol.removeprefix("__ksymtab_"))
    return exports


def validate_modules(profile_path, modules_path, output_directory):
    profile = read_profile(profile_path)
    output = Path(output_directory)
    modules = [
        line
        for raw in Path(modules_path).read_text().splitlines()
        if (line := raw.strip()) and not line.startswith("#")
    ]
    paths = [output / module for module in modules]
    exports = set().union(*(module_exports(path) for path in paths))
    versions = {}

    for path in paths:
        for symbol, crc in module_versions(path).items():
            previous = versions.setdefault(symbol, crc)
            if previous != crc:
                raise SystemExit(f"inconsistent module CRC for {symbol}")

    required = {symbol: crc for symbol, crc in versions.items() if symbol not in exports}
    missing = sorted(required.keys() - profile.keys())
    extra = sorted(profile.keys() - required.keys())
    mismatched = sorted(
        symbol
        for symbol in required.keys() & profile.keys()
        if required[symbol] != profile[symbol]
    )

    if missing:
        raise SystemExit("production symbols missing from profile: " + ", ".join(missing))
    if extra:
        raise SystemExit("unused production symbols in profile: " + ", ".join(extra))
    if mismatched:
        raise SystemExit("production symbol CRC mismatch: " + ", ".join(mismatched))


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "profile":
        read_profile(sys.argv[2], sys.argv[3])
        return

    if len(sys.argv) == 5 and sys.argv[1] == "modules":
        validate_modules(*sys.argv[2:])
        return

    raise SystemExit(
        "usage: validate-symvers.py profile PROFILE CHECKSUM\n"
        "       validate-symvers.py modules PROFILE MODULES OUTPUT"
    )


if __name__ == "__main__":
    main()
