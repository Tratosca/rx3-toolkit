#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Installs the performance core: the shared object that carries the hook
# installer and the on-screen additions. Features -- stems, key shift -- are
# separate modules that switch themselves on through the environment; this one
# owns the binary and decides when rbp has to be restarted for it.

module_begin core core

CORE_SRC=/mnt/iso/modules/core/librx3_core.so
CORE_LIB=/root/pdj/librx3_core.so
CORE_READY=/tmp/rx3-performance.ready
CORE_LOG=/tmp/rx3-stems.log
CORE_INSTALLED=0
CORE_RESIDENT=0
CORE_GLYPHS_SRC=/mnt/iso/modules/core/glyph-atlas-dark.rgb565
CORE_GLYPHS=/root/pdj/rx3-glyph-atlas-dark.rgb565

register_pid_ready_file "$CORE_READY"
register_diagnostic_file "$CORE_LOG"
register_runtime_preload "$CORE_LIB"

# NS_GetImageInfoByID: movw r3,#0x15cc -> movw r3,#0x16a5. This guarded
# pre-launch word admits the private IDs in the secondary table without
# hot-patching the renderer function: seven for the tab strip and a reserve for
# the pad row's glyph atlas. The stock word is left as it is, because the
# orchestrator accepts only the stock or the patched value here and stops the
# session on anything else, so a drive carrying an older mod is refused loudly.
register_patch 1874220 '\314\065\001\343' '\245\066\001\343' image-table-private-ids

core_install_asset()
{
    stage_runtime_file "$1" "$2"
}

core_optional_asset()
{
    if [ -r "$1" ]; then
        core_install_asset "$1" "$2"
    else
        stage_runtime_removal "$2"
    fi
}

core_normalize_preload()
{
    ensure_preload_entry "$CORE_LIB"
}

core_running_ready()
{
    [ -n "$PID" ] && [ -r "$PROC_ROOT/$PID/maps" ] || return 1
    [ "$(cat "$CORE_READY" 2>/dev/null)" = "$PID" ] || return 1
    # The path alone is insufficient: a replaced .so leaves the old inode
    # mapped, often shown as '(deleted)', while the path names new bytes.
    core_inode=$(ls -i "$CORE_LIB" 2>/dev/null | awk '{print $1}')
    [ -n "$core_inode" ] || return 1
    awk -v path="$CORE_LIB" -v inode="$core_inode" \
        'NF == 6 && $6 == path && $5 == inode && $2 ~ /x/ { found = 1 } END { exit !found }' \
        "$PROC_ROOT/$PID/maps" 2>/dev/null
}

core_prepare()
{
    [ -r "$CORE_SRC" ] || {
        say "Performance core disabled: shared object is missing"
        return 1
    }
    core_stage_start=$RUNTIME_STAGE_COUNT
    stage_panel_asset core 02 status-none-selected || return 1

    # The pad row letters its controls from this, one image per character. The
    # core keeps its stock text if it is missing, so the row is legible rather
    # than blank, but it will be lettered in the wrong face and size.
    core_optional_asset "$CORE_GLYPHS_SRC" "$CORE_GLYPHS" || return 1

    # The light glyphs are optional in the same way the light tabs are: the
    # core repoints the same image IDs at them only when they are there.
    target=/root/pdj/rx3-glyph-atlas-light.rgb565
    core_optional_asset /mnt/iso/modules/core/glyph-atlas-light.rgb565 "$target" || return 1

    core_install_asset "$CORE_SRC" "$CORE_LIB" || {
        say "Performance core disabled: shared object cannot be staged"
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
    if preload_contains "$CORE_LIB" &&
       [ "$RUNTIME_STAGE_COUNT" = "$core_stage_start" ] &&
       core_running_ready &&
       [ "$preload_changed" = "0" ] && [ "$NEED_RBP_RESTART" = "0" ]; then
        CORE_RESIDENT=1
        say "Performance core already active, rbp left untouched"
        return
    fi

    say "Performance core restart required: resident readiness or generation differs"
    request_rbp_restart
    say "Performance core staged: native overlay and touch"
}

core_after_launch()
{
    [ "$CORE_INSTALLED" = "1" ] || return 0
    if [ "$CORE_RESIDENT" = "1" ] && [ "$NEW" = "$PID" ]; then
        say "OK: performance core still active from the previous insertion"
        return 0
    fi
    if ready_file_matches_pid "$CORE_READY" "$NEW" &&
       grep -q 'RX3 performance hook active' "$CORE_LOG" 2>/dev/null; then
        say "OK: performance core active"
    else
        say "WARNING: rbp is active but the performance core is inactive"
    fi
    cat "$CORE_LOG" >> "$LOG" 2>/dev/null
}

register_prepare_hook core_prepare
register_after_launch_hook core_after_launch
