#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
module_begin beatfx-eq beatfx_eq
beatfx_eq_prepare()
{
    module_disabled_by_switch beatfx-eq && return 0
    [ -r "$CORE_OBJECT" ] || return 1
    module_export RX3_BEATFX_EQ 1 "BEAT FX frequency bands"
    say "BEAT FX bands: SPACE=LOW, DUB ECHO=MID, SWEEP=HIGH; lit goes through the effect"
}
register_prepare_hook beatfx_eq_prepare
