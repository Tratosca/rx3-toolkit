#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Now Playing export. The code lives in the performance core's shared object;
# this module only decides whether it runs.

module_begin nowplaying nowplaying

NOWPLAYING_READY=0

nowplaying_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Now Playing disabled: the performance core is not selected"
        return 1
    }
    export RX3_NOWPLAYING=1
    NOWPLAYING_READY=1
    running=$(rbp_environment_value RX3_NOWPLAYING)
    if [ "$running" != "1" ]; then
        say "Now Playing needs a restart: running rbp carries RX3_NOWPLAYING=[${running:-none}]"
        request_rbp_restart
    fi
    say "Now Playing prepared: exporting /tmp/rx3-nowplaying.txt on each load"
}

nowplaying_after_launch()
{
    [ "$NOWPLAYING_READY" = "1" ] || return 0
    say "Now Playing active: per-deck track path in /tmp/rx3-nowplaying.txt"
}

register_prepare_hook nowplaying_prepare
register_after_launch_hook nowplaying_after_launch
