#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Installs the performance core: the shared object that carries the hook
# installer and the on-screen additions. Features -- stems, key shift -- are
# separate modules that switch themselves on through the environment; this one
# owns the binary and decides when rbp has to be restarted for it.

module_begin core core

CORE_SRC=/mnt/iso/modules/core/librx3_core.so
CORE_LIB=/root/pdj/librx3_core.so
CORE_TMP=/root/pdj/.librx3_core.so.$$
CORE_READY=/tmp/rx3-performance.ready
CORE_LOG=/tmp/rx3-stems.log
CORE_INSTALLED=0
CORE_RESIDENT=0
CORE_TAB_KEY_SRC=/mnt/iso/modules/core/key-selected.rgb565
CORE_TAB_STEMS_SRC=/mnt/iso/modules/core/stems-selected.rgb565
CORE_TAB_NONE_SRC=/mnt/iso/modules/core/none-selected.rgb565
CORE_STATUS_NONE_SRC=/mnt/iso/modules/core/status-none-selected.rgb565
CORE_TAB_KEY=/root/pdj/rx3-key-selected.rgb565
CORE_TAB_STEMS=/root/pdj/rx3-stems-selected.rgb565
CORE_TAB_NONE=/root/pdj/rx3-none-selected.rgb565
CORE_STATUS_NONE=/root/pdj/rx3-status-none-selected.rgb565

register_ready_file "$CORE_READY"
register_diagnostic_file "$CORE_LOG"

# NS_GetImageInfoByID: movw r3,#0x15cc -> movw r3,#0x1603. This guarded
# pre-launch word admits four private IDs in the secondary table without
# hot-patching the renderer function.
register_patch 1874220 '\314\065\001\343' '\003\066\001\343' image-table-private-ids

core_install_asset()
{
    source_file=$1
    target_file=$2
    temporary_file=$target_file.$$
    [ -r "$source_file" ] || return 1
    cp "$source_file" "$temporary_file" 2>/dev/null || return 1
    chmod 644 "$temporary_file"
    mv -f "$temporary_file" "$target_file" 2>/dev/null || {
        rm -f "$temporary_file"
        return 1
    }
}

core_normalize_preload()
{
    # Keep exactly one entry for the core, at the front, however many earlier
    # insertions left behind.
    pending=$RBP_PRELOAD
    cleaned=""
    while [ -n "$pending" ]; do
        case "$pending" in
            *:*) entry=${pending%%:*}; pending=${pending#*:} ;;
            *)   entry=$pending; pending="" ;;
        esac
        [ -n "$entry" ] || continue
        [ "$entry" = "$CORE_LIB" ] && continue
        # The pre-split name, so an older runtime is superseded cleanly.
        [ "$entry" = "/root/pdj/librx3_stems.so" ] && continue
        if [ -n "$cleaned" ]; then
            cleaned="$cleaned:$entry"
        else
            cleaned=$entry
        fi
    done
    if [ -n "$cleaned" ]; then
        RBP_PRELOAD="$CORE_LIB:$cleaned"
    else
        RBP_PRELOAD=$CORE_LIB
    fi
}

core_prepare()
{
    [ -r "$CORE_SRC" ] || {
        say "Performance core disabled: shared object is missing"
        return 1
    }
    core_install_asset "$CORE_TAB_KEY_SRC" "$CORE_TAB_KEY" &&
    core_install_asset "$CORE_TAB_STEMS_SRC" "$CORE_TAB_STEMS" &&
    core_install_asset "$CORE_TAB_NONE_SRC" "$CORE_TAB_NONE" &&
    core_install_asset "$CORE_STATUS_NONE_SRC" "$CORE_STATUS_NONE" || {
        say "Performance core disabled: custom tab assets cannot be installed"
        return 1
    }

    previous_preload=$RBP_PRELOAD
    core_normalize_preload
    preload_changed=0
    [ "$RBP_PRELOAD" = "$previous_preload" ] || preload_changed=1

    CORE_INSTALLED=1

    # Already resident and identical: leave rbp alone. Reapplying costs a frozen
    # screen and a fresh USB rescan for no change, so the drive can be
    # reinserted freely.
    if preload_contains "$CORE_LIB" && cmp -s "$CORE_SRC" "$CORE_LIB" &&
       [ "$preload_changed" = "0" ] && [ "$NEED_RBP_RESTART" = "0" ]; then
        CORE_RESIDENT=1
        say "Performance core already active, rbp left untouched"
        return
    fi

    rm -f "$CORE_LOG" "$CORE_READY" "$CORE_TMP"
    cp "$CORE_SRC" "$CORE_TMP" 2>/dev/null || {
        say "Performance core disabled: cannot copy shared object"
        CORE_INSTALLED=0
        return 1
    }
    chmod 644 "$CORE_TMP"
    mv -f "$CORE_TMP" "$CORE_LIB" 2>/dev/null || {
        rm -f "$CORE_TMP"
        say "Performance core disabled: cannot install shared object atomically"
        CORE_INSTALLED=0
        return 1
    }
    request_rbp_restart
    say "Performance core prepared: native overlay and touch"
}

core_after_launch()
{
    [ "$CORE_INSTALLED" = "1" ] || return 0
    if [ "$CORE_RESIDENT" = "1" ]; then
        say "OK: performance core still active from the previous insertion"
        return 0
    fi
    if [ -s "$CORE_READY" ] &&
       grep -q 'RX3 performance hook active' "$CORE_LOG" 2>/dev/null; then
        say "OK: performance core active"
    else
        say "WARNING: rbp is active but the performance core is inactive"
    fi
    cat "$CORE_LOG" >> "$LOG" 2>/dev/null
}

register_prepare_hook core_prepare
register_after_launch_hook core_after_launch
