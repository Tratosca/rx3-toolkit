# SPDX-License-Identifier: MPL-2.0
"""Offline counterparts to the on-device guarded byte patches.

The device applies these words from `module.sh` at boot and reverts them on
power cycle. The patchers here rewrite an extracted `rbp` on a workstation
instead, which is how a patch is inspected or bisected without a deck.

`MODULE_ID` binds each patcher to the runtime module holding the same table;
tests/test_module_consistency.py uses it to prove the two agree.
"""
