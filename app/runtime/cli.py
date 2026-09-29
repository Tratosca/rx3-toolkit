#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""List and build versioned RX3 runtime modules."""

import argparse
import pathlib
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.runtime.build import build_runtime, discover_patches, repository_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("list", help="list selectable modules")
    command.add_argument("--firmware", default="1.19")

    command = commands.add_parser("build", help="build autoexec.bin")
    command.add_argument("--firmware", default="1.19")
    command.add_argument("--patch", action="append", dest="patches")
    command.add_argument(
        "--profile", action="append", default=[], metavar="MODULE=PROFILE",
        help="select a hardware profile for a module that requires one",
    )
    command.add_argument("--key", required=True, type=pathlib.Path)
    command.add_argument("--output", required=True, type=pathlib.Path)
    command.add_argument("--prebuilt-hook", type=pathlib.Path)

    args = parser.parse_args()
    root = repository_root()
    definitions = discover_patches(root, args.firmware)
    if args.command == "list":
        for patch in definitions:
            if not patch.selectable:
                continue
            marker = "default" if patch.default else "optional"
            dependencies = f" (requires: {', '.join(patch.requires)})" if patch.requires else ""
            profiles = f" (profiles: {', '.join(patch.profiles)})" if patch.profiles else ""
            print(
                f"{patch.patch_id:24} {marker:8} {patch.name} — "
                f"{patch.description}{dependencies}{profiles}"
            )
        return 0

    selected = args.patches or [
        patch.patch_id for patch in definitions if patch.selectable and patch.default
    ]
    profiles = {}
    for value in args.profile:
        module, separator, profile = value.partition("=")
        if not separator or not module or not profile:
            parser.error("--profile must use MODULE=PROFILE")
        if module in profiles:
            parser.error(f"profile for {module} was supplied more than once")
        profiles[module] = profile

    try:
        result = build_runtime(
            args.firmware,
            selected,
            args.key,
            args.output,
            root=root,
            profiles=profiles,
            prebuilt_hook=args.prebuilt_hook,
            progress=print,
        )
    except ValueError as error:
        parser.error(str(error))
    print(f"{result.output}: {result.size:,} bytes")
    print(f"SHA-256: {result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
