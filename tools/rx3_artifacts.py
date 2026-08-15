#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Resolve local analysis inputs by the role they play.

Some tools in `tools/` read a file the repository does not contain and will
never contain. Those files belong to whoever is running the tool, live wherever
that person keeps them, and are named here only by the role they fill — never by
where they came from. A path is a place on a disk; it is not a provenance
record, and this module deliberately has nowhere to write one.

Resolution order, first hit wins:

1. the role's environment variable, e.g. `RX3_IMAGE_DATA`;
2. the `[artifacts]` table of `artifacts.toml` at the root of the checkout,
   which is gitignored because it is the one file that says anything about how
   an operator has arranged their own machine;
3. `local/artifacts/<profile>/<role>`, the default layout.

The profile groups artifacts belonging to one device and firmware. It comes from
`RX3_PROFILE`, or from `profile` in `artifacts.toml`, or falls back to
`DEFAULT_PROFILE`.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIGURATION = ROOT / "artifacts.toml"
DEFAULT_PROFILE = "xdj-rx3-1.19"
DOCUMENTATION = "docs/artifacts.md"

# Every role carries what the file has to be, so that a missing one produces an
# error a reader can act on without going to look for the calling code, and its
# environment variable, spelled out rather than derived: the two differ often
# enough that deriving one from the other silently stops honouring overrides.
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


def _environment_variable(role):
    return ROLES[role]["variable"]


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


def profile():
    """The artifact grouping in force, without touching the filesystem twice."""
    from_environment = os.environ.get("RX3_PROFILE")
    if from_environment:
        return from_environment
    return _configuration().get("profile") or DEFAULT_PROFILE


def locate(role):
    """Return the configured path for `role`, whether or not anything is there."""
    if role not in ROLES:
        raise KeyError(
            f"unknown artifact role {role!r}; known roles: "
            + ", ".join(sorted(ROLES))
        )
    override = os.environ.get(_environment_variable(role))
    if override:
        return Path(override).expanduser()
    configured = _configuration().get("artifacts", {}).get(role)
    if configured:
        return Path(configured).expanduser()
    return ROOT / "local" / "artifacts" / profile() / role


def resolve(role):
    """Return a readable path for `role`, or explain what is missing.

    The explanation names the role, says what the file has to be, and points at
    the documentation. It does not, and must not, suggest where to obtain one.
    """
    path = locate(role)
    if path.is_file():
        return path
    raise ArtifactMissing(
        f"No file is available for the artifact role {role!r} "
        f"({ROLES[role]['description']}).\n"
        f"Looked at: {path}\n"
        f"Set it in the [artifacts] table of {CONFIGURATION.name}, or in the "
        f"{_environment_variable(role)} environment variable. "
        f"Both are described in {DOCUMENTATION}."
    )


def read_bytes(role):
    """Read the artifact for `role`, raising the same explained error if absent."""
    return resolve(role).read_bytes()
