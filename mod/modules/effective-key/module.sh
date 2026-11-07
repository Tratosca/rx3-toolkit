#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Heard key: with MASTER TEMPO off, the deck's key follows the tempo fader.
# The code lives in Key Shift; this module only switches it on.

module_begin effective-key effective_key

effective_key_prepare()
{
    [ -r "$CORE_OBJECT" ] || return 1
    module_disabled_by_switch effective-key && return 0
    module_export RX3_EFFECTIVE_KEY 1 "Heard key"
    say "Heard key prepared: MASTER TEMPO off moves the shown key with the tempo fader"
}

register_prepare_hook effective_key_prepare
