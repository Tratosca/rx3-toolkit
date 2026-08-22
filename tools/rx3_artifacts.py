#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Resolve local analysis inputs by the role they play.

Some tools in `tools/` read a file the repository does not contain and will
never contain. Those files belong to whoever is running the tool, live wherever
that person keeps them, and are named here only by the role they fill, never by
where they came from. A path is a place on a disk. It is not a provenance
record, and this module deliberately has nowhere to write one.

A role is looked up in the environment first, then in `artifacts.toml` at the
root of the checkout. That file is gitignored: it is the one file that says
anything about how an operator has arranged their own machine.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIGURATION = ROOT / "artifacts.toml"
DOCUMENTATION = "docs/artifacts.md"

# Each role carries what the file has to be, so a missing one produces an error
# the reader can act on without going to look at the calling code.
ROLES = {
    "imagedata": {
        "variable": "RX3_IMAGE_DATA",
        "description": "the flat record array the player indexes to find a bitmap",
    },
    "rbp": {
        "variable": "RX3_RBP",
        "description": "the player application binary, as an ELF file",
    },
}


class ArtifactMissing(FileNotFoundError):
    """Raised when a role has no readable file behind it."""


def _configuration():
    if not CONFIGURATION.is_file():
        return {}
    try:
        with CONFIGURATION.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ArtifactMissing(
            f"{CONFIGURATION.name} could not be read: {error}. "
            f"Its format is described in {DOCUMENTATION}."
        ) from error


def locate(role):
    """Return the configured path for `role`, or None if nothing points at one."""
    if role not in ROLES:
        raise KeyError(
            f"unknown artifact role {role!r}; known roles: "
            + ", ".join(sorted(ROLES))
        )
    override = os.environ.get(ROLES[role]["variable"])
    if override:
        return Path(override).expanduser()
    configured = _configuration().get("artifacts", {}).get(role)
    if configured:
        return Path(configured).expanduser()
    return None


def resolve(role):
    """Return a readable path for `role`, or explain what is missing.

    The explanation names the role, says what the file has to be, and points at
    the documentation. It does not, and must not, suggest where to obtain one.
    """
    path = locate(role)
    if path is not None and path.is_file():
        return path
    raise ArtifactMissing(
        f"No file is available for the artifact role {role!r} "
        f"({ROLES[role]['description']}).\n"
        f"Looked at: {path if path is not None else 'nothing is configured'}\n"
        f"Set it in the [artifacts] table of {CONFIGURATION.name}, or in the "
        f"{ROLES[role]['variable']} environment variable. "
        f"Both are described in {DOCUMENTATION}."
    )
