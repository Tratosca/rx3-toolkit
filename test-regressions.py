#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Static guards for the now playing module, all of them measured facts."""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
MODULE = (ROOT / "module.sh").read_text()
FEATURE = (ROOT / "rx3_nowplaying_feature.h").read_text()
MANIFEST = json.loads((ROOT / "manifest.json").read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "register_prepare_hook nowplaying_prepare" in MODULE
    and "export RX3_NOWPLAYING=1" in MODULE,
    "the module must announce itself to the core through the environment",
)
require(
    '[ -r "$CORE_OBJECT" ]' in MODULE,
    "the module must decline when the performance core is not selected",
)
require(
    "register_patch" not in MODULE,
    "now playing rides the core dispatch and must not patch any word",
)
require(
    MANIFEST["requires"] == ["core"]
    and "rx3_nowplaying_feature.h" in MANIFEST["build_files"],
    "now playing must declare its core dependency and own its header",
)
require(
    MANIFEST["default"] is False and MANIFEST["namespace"] == "nowplaying",
    "now playing is opt-in and owns the nowplaying namespace",
)
require(
    'getenv("RX3_NOWPLAYING")' in FEATURE
    and "nowplaying_feature_track_did_load" in FEATURE,
    "the feature must gate on its environment flag and take the load hook",
)
require(
    "(const char *)track_info" in FEATURE,
    "the feature reads the loaded path from track_info, like stems",
)
require(
    "sendto" in FEATURE and "50123" in FEATURE,
    "the feature exports over UDP on the documented port",
)

print("Now playing regression guards: OK")