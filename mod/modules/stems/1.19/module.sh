#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Stem controls. The code lives in the performance core's shared object; this
# module points it at the sidecar directory and reports what it found.

module_begin stems stems

STEMS_DIR="$USB/RX3_STEMS"
# A drive does not come back under the same device node: pulled out as sda and
# pushed back in as sdb, it mounts somewhere else, and the absolute path handed
# to rbp on the first insertion goes stale. rbp reads this once at load time, so
# a moved path used to mean stopping and relaunching the player - which freezes
# the screen and empties the media list, the very thing that made the drive get
# pulled again. One fixed path, re-pointed on each insertion, makes the loop go
# away: the running player keeps resolving it, and nothing has to restart.
STEMS_LINK=/tmp/rx3-stems
STEMS_READY=0

stems_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Stems disabled: the performance core is not selected"
        return 1
    }

    count=0
    for candidate in "$STEMS_DIR"/*.rx3stem; do
        [ -f "$candidate" ] || continue
        count=$((count+1))
    done

    published=$STEMS_DIR
    if [ ! -e "$STEMS_LINK" ] || [ -L "$STEMS_LINK" ]; then
        rm -f "$STEMS_LINK"
        ln -s "$STEMS_DIR" "$STEMS_LINK" 2>/dev/null && published=$STEMS_LINK
    fi
    [ "$published" = "$STEMS_LINK" ] || \
        say "Stems: $STEMS_LINK cannot be published, falling back to the mount path"

    export RX3_STEMS_DIR="$published"
    STEMS_READY=1
    # Only a change of the published directory needs a restart; the core decides
    # for itself whether the binary changed.
    running=$(rbp_environment_value RX3_STEMS_DIR)
    if [ "$running" != "$published" ]; then
        say "Stems needs a restart: running rbp carries [${running:-none}], this drive is [$published]"
        request_rbp_restart
    fi
    say "Stems prepared: $count sidecar(s) at $STEMS_DIR, asynchronous basename lookup"
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
