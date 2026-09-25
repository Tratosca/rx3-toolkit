#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Static guards for the stems module."""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[3]
MODULE = (ROOT / "module.sh").read_text()
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
HOOK = (REPOSITORY / "mod/modules/core/1.19/rx3_core_hook.c").read_text()
FEATURE = (ROOT / "rx3_stems_feature.h").read_text()
PANEL = (ROOT / "rx3_stems_panel.h").read_text()
AUDIO = (ROOT / "rx3_stems_audio.h").read_text()
LOADER = (ROOT / "rx3_stems_loader.h").read_text()
SOURCE = HOOK + FEATURE + PANEL + AUDIO + LOADER


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "register_prepare_hook stems_prepare" in MODULE
    and "register_after_launch_hook stems_after_launch" in MODULE
    and "module_export RX3_STEMS_DIR" in MODULE,
    "stem lifecycle logic must remain owned by the stems module",
)
require(
    MANIFEST["requires"] == ["core"] and MANIFEST["conflicts"] == [],
    "the stems dependency must be expressed by its manifest",
)
require(
    set(MANIFEST["build_files"]) == {
        "rx3_stems_decl.h", "rx3_stems_feature.h", "rx3_stems_panel.h",
        "rx3_stems_audio.h", "rx3_stems_loader.h"
    },
    "the module must own and publish its lifecycle and panel sources",
)
require(
    '[ -r "$CORE_OBJECT" ]' in MODULE,
    "the module must decline when the performance core is not selected",
)
require(
    "librx3" not in MODULE,
    "the stems module must no longer install a shared object of its own; the "
    "core it depends on is named through CORE_OBJECT, not by path",
)
require(
    "uint32_t channel = *(const uint32_t *)(led + 4u);" in FEATURE
    and "if (channel != deck_channel)" in FEATURE,
    "LED writes must be filtered by the channel embedded in each uif::Led",
)
require(
    'memcmp(header.magic, "RX3STM1\\0", 8u)' in LOADER
    and "header.sample_rate != 44100u" in LOADER,
    "the sidecar must be validated against PcmReader's own time domain",
)
require(
    "mprotect(block, bytes, PROT_READ)" in LOADER,
    "a resident stem must be read-only so an audio-thread write fails loudly",
)
require(
    "if (output[i].left == 0.0f && output[i].right == 0.0f)" in AUDIO,
    "a partially zero-filled block must never become inverted vocal audio",
)
require(
    "code < 0x411bu || code > 0x411eu" in FEATURE,
    "only Slip Loop pads 5 through 8 may be captured",
)
stream_body = FEATURE.split("static unsigned long hooked_get_stream", 1)[1].split(
    "\nstatic ", 1
)[0]
require(
    "stems_mix(context, (int)position, output, frames)" in stream_body,
    "the time-stretch wrapper must preserve the source position for subtraction",
)
require(
    '#include "../../stems/1.19/rx3_stems_feature.h"' in HOOK
    and "stems_feature_install" in FEATURE
    and "keyshift" not in FEATURE.lower(),
    "stems must implement only its own core lifecycle and hook group",
)

print("Stems regression guards: OK")
