#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Configures the optional sync action supplied by Key Shift.
module_begin key-sync key_sync
key_sync_prepare()
{
    [ -r "$CORE_OBJECT" ] || return 1
    module_disabled_by_switch key-sync && return 0
    # Plain data, never sourced as shell code; absent files keep the default.
    KEY_SYNC_RANGE=1
    if [ -r /mnt/iso/modules/key-sync/sync-range.txt ]; then
        IFS= read -r KEY_SYNC_RANGE < /mnt/iso/modules/key-sync/sync-range.txt
    fi
    case "$KEY_SYNC_RANGE" in
        [1-9]|10|11|12) ;;
        *) KEY_SYNC_RANGE=1 ;;
    esac
    module_export RX3_KEY_SYNC_RANGE "$KEY_SYNC_RANGE" "Key sync range"
    KEY_SYNC_MODE=identical
    if [ -r /mnt/iso/modules/key-sync/sync-mode.txt ]; then
        IFS= read -r KEY_SYNC_MODE < /mnt/iso/modules/key-sync/sync-mode.txt
    fi
    case "$KEY_SYNC_MODE" in
        identical|harmonic) ;;
        *) KEY_SYNC_MODE=identical ;;
    esac
    module_export RX3_KEY_SYNC_MODE "$KEY_SYNC_MODE" "Key sync mode"
    say "Key Sync prepared"
    return 0
}
register_prepare_hook key_sync_prepare
