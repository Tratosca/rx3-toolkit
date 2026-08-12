#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Create a ZIP or tar.gz release archive while preserving file modes."""

import argparse
import os
import pathlib
import stat
import tarfile
import zipfile


def zip_target(target: pathlib.Path, output: pathlib.Path, includes: list[pathlib.Path]) -> None:
    paths = [target] if target.is_file() else [target, *sorted(target.rglob("*"))]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            relative = pathlib.Path(target.name) / path.relative_to(target) if path != target else pathlib.Path(target.name)
            if path.is_symlink():
                info = zipfile.ZipInfo(relative.as_posix())
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, os.readlink(path).encode("utf-8"))
                continue
            if path.is_dir():
                info = zipfile.ZipInfo(relative.as_posix().rstrip("/") + "/")
                info.external_attr = (0o40755 << 16) | 0x10
                archive.writestr(info, b"")
                continue
            info = zipfile.ZipInfo.from_file(path, relative.as_posix())
            info.external_attr = path.stat().st_mode << 16
            with path.open("rb") as source:
                archive.writestr(info, source.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        for path in includes:
            archive.write(path, path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--include", action="append", default=[], type=pathlib.Path)
    args = parser.parse_args()
    if not args.target.exists():
        parser.error(f"target does not exist: {args.target}")
    for path in args.include:
        if not path.is_file():
            parser.error(f"included notice does not exist: {path}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.name.endswith(".tar.gz"):
        with tarfile.open(args.output, "w:gz") as archive:
            archive.add(args.target, arcname=args.target.name)
            for path in args.include:
                archive.add(path, arcname=path.name)
    elif args.output.suffix == ".zip":
        zip_target(args.target, args.output, args.include)
    else:
        parser.error("output must end in .zip or .tar.gz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
