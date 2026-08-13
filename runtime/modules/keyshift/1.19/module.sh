#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Per-deck key shift. The code lives in the performance core's shared object;
# this module decides whether it runs, and owns its documentation and tests.

module_begin keyshift keyshift

KEYSHIFT_READY=0

keyshift_prepare()
{
    [ -r /mnt/iso/modules/core/librx3_core.so ] || {
        say "Key shift disabled: the performance core is not selected"
        return 1
    }
    export RX3_KEYSHIFT=1
    KEYSHIFT_READY=1
    if [ "$(rbp_environment_value RX3_KEYSHIFT)" != "1" ]; then
        request_rbp_restart
    fi
    say "Key shift prepared: -12..+12 semitones per deck"
}

keyshift_after_launch()
{
    [ "$KEYSHIFT_READY" = "1" ] || return 0
    say "KEY tab: down, reset and up per deck, -12..+12 semitones"
    say "raising pitch uses the runtime's own shifter, lowering uses rbp's"
}

register_prepare_hook keyshift_prepare
register_after_launch_hook keyshift_after_launch
