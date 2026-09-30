#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
module_begin asshole-mode asshole_mode
asshole_mode_prepare()
{
    module_disabled_by_switch asshole-mode && return 0
    [ -r "$CORE_OBJECT" ] || return 1
    module_export RX3_ASSHOLE_MODE 1 "Asshole mode"
    say "Asshole mode: tap each deck's eye to hide or show its title"
}
register_prepare_hook asshole_mode_prepare
