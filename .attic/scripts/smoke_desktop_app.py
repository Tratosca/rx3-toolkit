#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run a packaged desktop application's non-interactive self-test."""

import argparse
import pathlib
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=pathlib.Path)
    args = parser.parse_args()
    if not args.executable.is_file():
        parser.error(f"executable does not exist: {args.executable}")
    subprocess.run([str(args.executable), "--self-test"], check=True, timeout=120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
