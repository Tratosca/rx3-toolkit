# SPDX-License-Identifier: MPL-2.0
"""The DJ's settings file on the drive, read by the deck at every insertion.

`RX3_RUNTIME/settings.cfg`: a `version = 1` line, then `<module>.<key> = <value>`
lines. The deck reads it as data (mod/lib/module-api.sh, module_setting). This
writer changes only the keys it is given and keeps every other line as it is,
so keys written by the deck or by hand survive a rebuild.
"""
from __future__ import annotations

import os
import pathlib
from collections.abc import Mapping

from app.localization import LocalizedError

RELATIVE_PATH = pathlib.Path("RX3_RUNTIME") / "settings.cfg"
MAX_BYTES = 65536  # the deck ignores a larger file


def _key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def update(drive: pathlib.Path, values: Mapping[str, str]) -> pathlib.Path:
    """Write `values` into the drive's settings file, keeping everything else."""
    path = drive / RELATIVE_PATH
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        lines = ["version = 1"]
    else:
        try:
            text = raw.decode("utf-8") if len(raw) <= MAX_BYTES else ""
        except UnicodeDecodeError:
            text = ""
        lines = text.replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        versions = [line.split("=", 1)[1].strip() for line in lines if _key(line) == "version"]
        # Not ours to rewrite: an unknown format or version is left untouched.
        if not versions or versions[-1] != "1":
            raise LocalizedError("error.settingsFile", path=str(path))
    pending = dict(values)
    kept = []
    for line in lines:
        key = _key(line)
        if key in values:
            if key not in pending:
                continue  # an older duplicate: one line per key, in its place
            line = f"{key} = {pending.pop(key)}"
        kept.append(line)
    kept.extend(f"{key} = {value}" for key, value in pending.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(kept) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return path
