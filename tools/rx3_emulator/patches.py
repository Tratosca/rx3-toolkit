#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Emulator-only guarded patches for rbp. These must never reach a deck.

Deliberately outside `tools/rx3_patcher/`, whose every member is required by
tests/test_module_consistency.py to have a matching `register_patch` in some
module.sh -- the invariant that keeps the device and the offline patcher in
step. A patch that exists only under QEMU has no device counterpart by
definition, so it lives here instead of being granted an exemption there, and
tests/test_rx3_emulator.py asserts none of these offsets appears in a module.sh.

The container applies the same words in shell (container/run.sh) against its
own writable copy of rbp; this module is the offline counterpart used to
inspect or bisect a patched binary on a workstation.

File offset = virtual address - 0x8000, the ELF's single PT_LOAD (off=0,
vaddr=0x8000), confirmed against the loaded image base in the Ghidra project.
"""

from tools.rx3_patcher.patchlib import run


# ui::IReceptionForMAIN::startUp() is reached from main only when r0 is
# non-zero after the preceding call:
#
#   000104c8  bl 0x002bb888   ; IReceptionForMAIN::initialize_()
#   000104cc  cmp r0,#0x0
#   000104d0  bne 0x00010584  ; -> bl IReceptionForMAIN::startUp()
#
# initialize_() returns void, so that `cmp` reads whatever the call left behind
# -- UiObjectManager::init()'s result, since init(this) sits in tail position.
# Forcing the branch is safe: startUp() re-checks its own state word first, bit
# 1 meaning "already started" and bit 0 "already initialised", and calls init()
# itself when bit 0 is clear.
#
# MEASURED RESULT: applying this changes nothing. A 60 s keyshift run with it
# on is indistinguishable from one with it off -- same nine checks, same
# probes, and /dev/subucom_* and /dev/tsc2007_* still never open (the shim
# creates each fake node lazily on first open, so their absence is proof). The
# only reading left is that execution never reaches 0x000104d0: init() does not
# return, which confirms the hang ANALYSE.md 19.10 diagnosed rather than the
# "returns 0 and main skips startUp" alternative this patch was written to test.
#
# It is kept, off by default, because it is the cheap discriminator to re-run
# once the wait inside init() is found and removed: at that point this branch
# is what carries execution into startUp().
UNBLOCK_STARTUP = (
    0x0084D0,
    "2b00001a",
    "2b0000ea",
    "main: bne startUp -> b startUp (no effect until init() returns)",
)

PATCHES = [UNBLOCK_STARTUP]


if __name__ == "__main__":
    raise SystemExit(run(__doc__.splitlines()[0], PATCHES))
