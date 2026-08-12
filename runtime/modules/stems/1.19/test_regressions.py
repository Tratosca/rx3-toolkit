#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Static guards for hardware-confirmed runtime behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[3]
AUTOEXEC = (REPOSITORY / "runtime/autoexec.sh").read_text()
HOOK = (ROOT / "rx3_stems_hook.c").read_text()
STEMS_MODULE = (ROOT / "module.sh").read_text()
PATCH_32_BARS = (REPOSITORY / "runtime/modules/beatjump/beatjump-32bars/1.19/patch.py").read_text()
PATCH_32_BARS_MODULE = (REPOSITORY / "runtime/modules/beatjump/beatjump-32bars/1.19/module.sh").read_text()
PATCH_NO_QUANTIZE = (REPOSITORY / "runtime/modules/beatjump/beatjump-no-quantize/1.19/patch.py").read_text()
PATCH_NO_QUANTIZE_MODULE = (REPOSITORY / "runtime/modules/beatjump/beatjump-no-quantize/1.19/module.sh").read_text()
DECODER_SLEEP = (REPOSITORY / "runtime/modules/buffer/decoder-sleep/1.19/apply.sh").read_text()
DECODER_SLEEP_MODULE = (REPOSITORY / "runtime/modules/buffer/decoder-sleep/1.19/module.sh").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "for module in /mnt/iso/modules/*/module.sh" in AUTOEXEC,
    "autoexec must discover packaged modules instead of embedding features",
)
require(
    "register_patch" in AUTOEXEC and "write_words patched" in AUTOEXEC,
    "the runtime orchestrator must apply guarded module registrations",
)
require(
    "uint32_t channel = *(const uint32_t *)(led + 4u);" in HOOK
    and "if (channel != deck_channel)" in HOOK,
    "LED writes must be filtered by the channel embedded in each uif::Led",
)
require(
    "register_patch 695764" in PATCH_NO_QUANTIZE_MODULE,
    "the no-quantize runtime module must register its ARM NOP",
)
require(
    len(PATCH_32_BARS.split("(0x")) - 1 == 12,
    "the +/-32 offline patch must contain exactly twelve guarded words",
)
require(
    '(0x0A9DD4, "3d00000a", "0000a0e1"' in PATCH_NO_QUANTIZE,
    "the no-quantize patch must include the direct Beat Jump path",
)
require(
    PATCH_32_BARS_MODULE.count("register_patch ") == 12,
    "the +/-32 runtime module must register exactly twelve guarded words",
)
require(
    "register_prepare_hook stems_prepare" in STEMS_MODULE
    and "register_after_launch_hook stems_after_launch" in STEMS_MODULE,
    "stem lifecycle logic must remain owned by the stems module",
)
require(
    "register_post_launch_hook decoder_sleep_apply" in DECODER_SLEEP_MODULE,
    "the decoder-sleep adapter must register its post-launch hook",
)
require(
    'bufsleep "$deck" "$NANOSECONDS"' in DECODER_SLEEP,
    "the decoder-sleep patch must apply the interval independently to each deck",
)

print("Runtime regression guards: OK")
