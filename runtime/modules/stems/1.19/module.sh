#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Runtime setup and validation for the firmware 1.19 stems hook.

STEMS_SRC=/mnt/iso/modules/stems/librx3_stems.so
STEMS_LIB=/root/pdj/librx3_stems.so
STEMS_DIR="$USB/RX3_STEMS"
STEMS_READY=0
STEMS_RESIDENT=0

stems_prepare()
{
    [ -r "$STEMS_SRC" ] || { say "Stems disabled: shared object is missing"; return; }

    count=0
    for candidate in "$STEMS_DIR"/*.rx3stem; do
        [ -f "$candidate" ] || continue
        count=$((count+1))
    done
    if [ "$count" = "0" ]; then
        say "Stems disabled: no sidecar in $STEMS_DIR"
        return
    fi

    # The same hook, already preloaded against the same sidecar directory, is
    # the state this module wants. Reapplying it would cost a frozen screen and
    # a fresh USB rescan for no change, so the drive can be reinserted freely.
    if preload_contains "$STEMS_LIB" && cmp -s "$STEMS_SRC" "$STEMS_LIB" &&
       [ "$(rbp_environment_value RX3_STEMS_DIR)" = "$STEMS_DIR" ]; then
        export RX3_STEMS_DIR="$STEMS_DIR"
        STEMS_READY=1
        STEMS_RESIDENT=1
        say "Stems already active: $count sidecar(s), rbp left untouched"
        return
    fi

    rm -f /tmp/rx3-stems.log
    cp "$STEMS_SRC" "$STEMS_LIB" 2>/dev/null || {
        say "Stems disabled: cannot copy shared object"; return;
    }
    chmod 644 "$STEMS_LIB"
    if [ -n "$RBP_PRELOAD" ]; then
        RBP_PRELOAD="$STEMS_LIB:$RBP_PRELOAD"
    else
        RBP_PRELOAD=$STEMS_LIB
    fi
    export RX3_STEMS_DIR="$STEMS_DIR"
    STEMS_READY=1
    request_rbp_restart
    say "Stems prepared: $count sidecar(s), asynchronous basename lookup"
}

stems_after_launch()
{
    [ "$STEMS_READY" = "1" ] || return 0
    if [ "$STEMS_RESIDENT" = "1" ]; then
        say "OK: RX3 stems hook still active from the previous insertion"
        return 0
    fi
    if grep -q 'RX3 stems hook active' /tmp/rx3-stems.log 2>/dev/null; then
        say "OK: RX3 stems hook active"
        say "SLIP LOOP: pad 7=instrumental, pad 8=vocal, independent toggles"
        say "both pads blink while a sidecar loads and hold once it is resident"
        say "without a matching sidecar, audio and pads remain stock"
    else
        say "WARNING: rbp is active but the stems hook is inactive"
        cat /tmp/rx3-stems.log >> "$LOG" 2>/dev/null
    fi
}

register_prepare_hook stems_prepare
register_after_launch_hook stems_after_launch
