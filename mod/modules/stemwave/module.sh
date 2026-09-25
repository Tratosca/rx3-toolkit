#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Stem waveform tint. The code lives in the performance core's shared object;
# this module only switches it on and says what it needs to be visible.

module_begin stemwave stemwave

STEMWAVE_READY=0

stemwave_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Stem waveform disabled: the performance core is not selected"
        return 1
    }
    module_disabled_by_switch stemwave && return 0
    STEMWAVE_READY=1
    module_export RX3_STEMWAVE 1 "Stem waveform"
    say "Stem waveform prepared: the waveform follows the stem toggles"
}

stemwave_after_launch()
{
    [ "$STEMWAVE_READY" = "1" ] || return 0
    say "STEM WAVEFORM: the waveform takes the colour of the soloed stem"
    say "Stem waveform render port: hardware validation pending"
}

register_prepare_hook stemwave_prepare
register_after_launch_hook stemwave_after_launch
