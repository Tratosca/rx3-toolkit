#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Per-deck key shift. The code lives in the performance core's shared object;
# this module decides whether it runs, and owns its documentation and tests.

module_begin keyshift keyshift

KEYSHIFT_READY=0

keyshift_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Key shift disabled: the performance core is not selected"
        return 1
    }
    module_disabled_by_switch keyshift && return 0
    KEYSHIFT_SYNC_ENABLED=0
    case " $LOADED_MODULES " in *" key-sync "*) KEYSHIFT_SYNC_ENABLED=1 ;; esac
    if module_disabled_by_switch key-sync; then KEYSHIFT_SYNC_ENABLED=0; fi
    if module_disabled_by_switch key-match; then KEYSHIFT_SYNC_ENABLED=0; fi
    module_export RX3_KEY_SYNC "$KEYSHIFT_SYNC_ENABLED" "Key Sync"
    KEYSHIFT_READY=1
    module_export RX3_KEYSHIFT 1 "Key shift"
    say "Key shift prepared: -12..+12 semitones per deck"
}

keyshift_after_launch()
{
    [ "$KEYSHIFT_READY" = "1" ] || return 0
    say "KEY tab: down, reset, up"
    say "raising pitch uses the runtime's own shifter, lowering uses rbp's"
}

register_prepare_hook keyshift_prepare
register_after_launch_hook keyshift_after_launch
