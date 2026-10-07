#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Light theme. The code lives in the performance core's shared object; this
# module only announces the mode.

module_begin theme-white theme_white

THEME_WHITE_READY=0

theme_white_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Light theme disabled: the performance core is not selected"
        return 1
    }
    module_disabled_by_switch theme-white && return 0

    # Which mode the deck starts in is the operator's, not ours, and a drive is
    # the only thing that reaches the player. One word in one file, written by
    # the computer beside the mod it built; a drive without it behaves as every
    # drive did before this existed.
    mode=
    if [ -r "$USB/RX3_RUNTIME/display" ]; then
        IFS= read -r mode < "$USB/RX3_RUNTIME/display" || :
    fi
    # Choosing the module is asking for the light display, so a drive that
    # names no mode starts light. SHIFT + SHORTCUT and Utility switch it either
    # way afterwards; switch is the word for starting dark.
    case "$mode" in
        dark)   letter=d; described="dark, and it stays dark" ;;
        ''|light) letter=l; described="light from the first frame, switchable" ;;
        wait)   letter=w; described="light, once the player has painted once" ;;
        switch) letter=s; described="dark, switchable from Utility" ;;
        *)
            letter=l
            described="light from the first frame, switchable"
            say "Display mode: '$mode' is not a mode; starting light and switchable"
            ;;
    esac

    THEME_WHITE_READY=1
    module_export RX3_THEME "$letter" "Light theme"
    say "Display mode prepared: $described"
}

theme_white_after_launch()
{
    [ "$THEME_WHITE_READY" = "1" ] || return 0
    say "DISPLAY MODE: Utility or SHIFT + SHORTCUT switches between DARK and LIGHT"
    say "Light images, waveform palette and Utility port: hardware validation pending"
}

register_prepare_hook theme_white_prepare
register_after_launch_hook theme_white_after_launch
