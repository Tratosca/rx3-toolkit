#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""List and build versioned RX3 runtime modules."""

import argparse
import pathlib
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools.rx3_runtime.build import build_runtime, discover_patches, repository_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("list", help="list selectable modules")
    command.add_argument("--firmware", default="1.19")

    command = commands.add_parser("build", help="build autoexec.bin")
    command.add_argument("--firmware", default="1.19")
    command.add_argument("--patch", action="append", dest="patches")
    command.add_argument("--key", required=True, type=pathlib.Path)
    command.add_argument("--output", required=True, type=pathlib.Path)
    command.add_argument("--prebuilt-hook", type=pathlib.Path)

    args = parser.parse_args()
    root = repository_root()
    definitions = discover_patches(root, args.firmware)
    if args.command == "list":
        for patch in definitions:
            marker = "default" if patch.default else "optional"
            print(f"{patch.patch_id:24} {marker:8} {patch.name} — {patch.description}")
        return 0

    selected = args.patches or [patch.patch_id for patch in definitions if patch.default]
    result = build_runtime(
        args.firmware,
        selected,
        args.key,
        args.output,
        root=root,
        prebuilt_hook=args.prebuilt_hook,
        progress=print,
    )
    print(f"{result.output}: {result.size:,} bytes")
    print(f"SHA-256: {result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
