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
SOURCE = HOOK + FEATURE + PANEL


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "register_prepare_hook stems_prepare" in MODULE
    and "register_after_launch_hook stems_after_launch" in MODULE
    and "export RX3_STEMS_DIR" in MODULE,
    "stem lifecycle logic must remain owned by the stems module",
)
require(
    MANIFEST["requires"] == ["core"] and MANIFEST["conflicts"] == [],
    "the stems dependency must be expressed by its manifest",
)
require(
    set(MANIFEST["build_files"]) == {
        "rx3_stems_decl.h", "rx3_stems_feature.h", "rx3_stems_panel.h"
    },
    "the module must own and publish its lifecycle and panel sources",
)
require(
    "librx3_core.so" in MODULE,
    "the module must decline when the performance core is not selected",
)
require(
    "librx3" not in MODULE.replace("librx3_core.so", ""),
    "the stems module must no longer install a shared object of its own",
)
require(
    "uint32_t channel = *(const uint32_t *)(led + 4u);" in FEATURE
    and "if (channel != deck_channel)" in FEATURE,
    "LED writes must be filtered by the channel embedded in each uif::Led",
)
require(
    'memcmp(header.magic, "RX3STM1", 7)' in HOOK
    and "header.sample_rate != 44100" in HOOK,
    "the sidecar must be validated against PcmReader's own time domain",
)
require(
    "(void)mprotect(block, payload, PROT_READ);" in HOOK,
    "a resident stem must be read-only so an audio-thread write fails loudly",
)
require(
    "if (output[i].left == 0.0f && output[i].right == 0.0f)" in HOOK,
    "a partially zero-filled block must never become inverted vocal audio",
)
require(
    "key_code < 0x411du || key_code > 0x411eu" in FEATURE,
    "only Slip Loop pads 7 and 8 may be captured",
)
stream_body = FEATURE.split("static unsigned long hooked_get_stream", 1)[1].split(
    "\nstatic ", 1
)[0]
require(
    "apply_mix(context, position, output, frames, selected)" in stream_body,
    "stems must be mixed inside getStreamAt, where the read is addressed by "
    "position and therefore indifferent to the reader's out-of-order access",
)
require(
    '#include "../../stems/1.19/rx3_stems_feature.h"' in HOOK
    and "stems_feature_install" in FEATURE
    and "keyshift" not in FEATURE.lower(),
    "stems must implement only its own core lifecycle and hook group",
)

print("Stems regression guards: OK")
