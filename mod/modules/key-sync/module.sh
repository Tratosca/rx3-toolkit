#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Configures the optional sync action supplied by Key Shift.
module_begin key-sync key_sync
key_sync_prepare()
{
    [ -r "$CORE_OBJECT" ] || return 1
    module_disabled_by_switch key-sync && return 0
    KEY_SYNC_RANGE=$(module_setting key-sync.range 1)
    case "$KEY_SYNC_RANGE" in
        [1-9]|10|11|12) ;;
        *) KEY_SYNC_RANGE=1 ;;
    esac
    module_export RX3_KEY_SYNC_RANGE "$KEY_SYNC_RANGE" "Key sync range"
    # Same default as the Toolkit.
    KEY_SYNC_MODE=$(module_setting key-sync.mode harmonic)
    case "$KEY_SYNC_MODE" in
        identical|harmonic) ;;
        *) KEY_SYNC_MODE=harmonic ;;
    esac
    module_export RX3_KEY_SYNC_MODE "$KEY_SYNC_MODE" "Key sync mode"
    say "Key Sync prepared"
    return 0
}
register_prepare_hook key_sync_prepare
