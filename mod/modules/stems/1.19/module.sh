#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Stem controls. The code lives in the performance core's shared object; this
# module points it at the sidecar directory and reports what it found.

module_begin stems stems

STEMS_DIR="$USB/RX3_STEMS"
STEMS_READY=0

stems_prepare()
{
    [ -r /mnt/iso/modules/core/librx3_core.so ] || {
        say "Stems disabled: the performance core is not selected"
        return 1
    }

    count=0
    for candidate in "$STEMS_DIR"/*.rx3stem; do
        [ -f "$candidate" ] || continue
        count=$((count+1))
    done

    export RX3_STEMS_DIR="$STEMS_DIR"
    STEMS_READY=1
    # Only a change of directory needs a restart; the core decides for itself
    # whether the binary changed.
    if [ "$(rbp_environment_value RX3_STEMS_DIR)" != "$STEMS_DIR" ]; then
        request_rbp_restart
    fi
    say "Stems prepared: $count sidecar(s), asynchronous basename lookup"
}

stems_after_launch()
{
    [ "$STEMS_READY" = "1" ] || return 0
    say "SLIP LOOP: pad 7=instrumental, pad 8=vocal, independent toggles"
    say "STEMS tab: on-screen instrumental and vocal per deck"
    say "both pads blink while a sidecar loads and hold once it is resident"
    say "without a matching sidecar, audio and pads remain stock"
}

register_prepare_hook stems_prepare
register_after_launch_hook stems_after_launch
