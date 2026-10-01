#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Registration API sourced by autoexec.sh. It mutates only the orchestrator's
# in-memory tables; device changes belong to registered lifecycle callbacks.

# Where the packaged performance core sits once the ISO is mounted. Feature
# modules refuse to prepare without it, and name it through this one constant
# rather than repeating the path.
CORE_OBJECT=/mnt/iso/modules/core/librx3_core.so

# Core and startup artwork are staged on the same RAM filesystem as their
# destinations. No live resource is replaced during prepare or media deferral.
RUNTIME_STAGE_DIR=${RUNTIME_STAGE_DIR:-/root/pdj/.rx3-stage.$$}
RUNTIME_STAGE_COUNT=0
RUNTIME_STAGE_OWNED=0

ensure_runtime_stage()
{
    [ "$RUNTIME_STAGE_OWNED" = 1 ] && return 0
    mkdir "$RUNTIME_STAGE_DIR" 2>/dev/null || return 1
    RUNTIME_STAGE_OWNED=1
}

stage_runtime_file()
{
    _rx3_source=$1
    _rx3_target=$2
    [ -r "$_rx3_source" ] || return 1
    [ -f "$_rx3_target" ] && [ ! -L "$_rx3_target" ] &&
        cmp -s "$_rx3_source" "$_rx3_target" 2>/dev/null && return 0
    ensure_runtime_stage || return 1
    _rx3_next=$((RUNTIME_STAGE_COUNT + 1))
    cp "$_rx3_source" "$RUNTIME_STAGE_DIR/new$_rx3_next" 2>/dev/null || return 1
    chmod 644 "$RUNTIME_STAGE_DIR/new$_rx3_next" || return 1
    printf '%s\n' "$_rx3_target" > "$RUNTIME_STAGE_DIR/target$_rx3_next" || return 1
    RUNTIME_STAGE_COUNT=$_rx3_next
}

# Fixed native tab slots are a renderer contract; artwork belongs to its module.
# The generic loader reads only paths explicitly published for this launch.
stage_panel_asset()
{
    _rx3_panel_module=$1
    _rx3_panel_slot=$2
    _rx3_panel_name=$3
    _rx3_panel_source=/mnt/iso/modules/$_rx3_panel_module/$_rx3_panel_name.rgb565
    _rx3_panel_target=/root/pdj/rx3-$_rx3_panel_name.rgb565
    _rx3_panel_before=$RUNTIME_STAGE_COUNT
    stage_runtime_file "$_rx3_panel_source" "$_rx3_panel_target" || return 1
    if [ -r "/mnt/iso/modules/$_rx3_panel_module/$_rx3_panel_name-light.rgb565" ]; then
        stage_runtime_file "/mnt/iso/modules/$_rx3_panel_module/$_rx3_panel_name-light.rgb565" "/root/pdj/rx3-$_rx3_panel_name-light.rgb565" || return 1
        module_export "RX3_TAB_LIGHT_$_rx3_panel_slot" "/root/pdj/rx3-$_rx3_panel_name-light.rgb565" "Panel artwork" || :
    else
        module_export "RX3_TAB_LIGHT_$_rx3_panel_slot" "" "Panel artwork" || :
    fi
    module_export "RX3_TAB_DARK_$_rx3_panel_slot" "$_rx3_panel_target" "Panel artwork" || :
    [ "$RUNTIME_STAGE_COUNT" = "$_rx3_panel_before" ] || request_rbp_restart
    return 0
}

stage_runtime_removal()
{
    _rx3_target=$1
    [ -e "$_rx3_target" ] || [ -L "$_rx3_target" ] || return 0
    ensure_runtime_stage || return 1
    _rx3_next=$((RUNTIME_STAGE_COUNT + 1))
    printf '%s\n' "$_rx3_target" > "$RUNTIME_STAGE_DIR/target$_rx3_next" || return 1
    RUNTIME_STAGE_COUNT=$_rx3_next
}

stage_runtime_symlink()
{
    _rx3_link_target=$1
    _rx3_link_path=$2
    [ -L "$_rx3_link_path" ] &&
        [ "$(readlink "$_rx3_link_path")" = "$_rx3_link_target" ] && return 0
    ensure_runtime_stage || return 1
    _rx3_next=$((RUNTIME_STAGE_COUNT + 1))
    ln -s "$_rx3_link_target" "$RUNTIME_STAGE_DIR/new$_rx3_next" || return 1
    printf '%s\n' "$_rx3_link_path" > "$RUNTIME_STAGE_DIR/target$_rx3_next" || return 1
    RUNTIME_STAGE_COUNT=$_rx3_next
}

commit_runtime_stage()
{
    _rx3_index=1
    while [ "$_rx3_index" -le "$RUNTIME_STAGE_COUNT" ]; do
        _rx3_target=$(cat "$RUNTIME_STAGE_DIR/target$_rx3_index") || return 1
        [ ! -d "$_rx3_target" ] || [ -L "$_rx3_target" ] || return 1
        # Mark before the first rename so even a partial commit can be undone.
        : > "$RUNTIME_STAGE_DIR/started$_rx3_index" || return 1
        if [ -e "$_rx3_target" ] || [ -L "$_rx3_target" ]; then
            : > "$RUNTIME_STAGE_DIR/had$_rx3_index" || return 1
            mv -f "$_rx3_target" "$RUNTIME_STAGE_DIR/old$_rx3_index" || return 1
        fi
        if [ -e "$RUNTIME_STAGE_DIR/new$_rx3_index" ] ||
           [ -L "$RUNTIME_STAGE_DIR/new$_rx3_index" ]; then
            mv -f "$RUNTIME_STAGE_DIR/new$_rx3_index" "$_rx3_target" || return 1
        fi
        _rx3_index=$((_rx3_index + 1))
    done
}

restore_runtime_stage()
{
    _rx3_index=$RUNTIME_STAGE_COUNT
    _rx3_failed=0
    while [ "$_rx3_index" -gt 0 ]; do
        if [ -f "$RUNTIME_STAGE_DIR/started$_rx3_index" ]; then
            _rx3_target=$(cat "$RUNTIME_STAGE_DIR/target$_rx3_index") || return 1
            if [ -e "$RUNTIME_STAGE_DIR/old$_rx3_index" ] ||
               [ -L "$RUNTIME_STAGE_DIR/old$_rx3_index" ]; then
                if [ -d "$_rx3_target" ] && [ ! -L "$_rx3_target" ]; then
                    _rx3_failed=1
                elif rm -f "$_rx3_target"; then
                    mv -f "$RUNTIME_STAGE_DIR/old$_rx3_index" "$_rx3_target" || _rx3_failed=1
                else
                    _rx3_failed=1
                fi
            elif [ ! -f "$RUNTIME_STAGE_DIR/had$_rx3_index" ]; then
                rm -f "$_rx3_target" || _rx3_failed=1
            fi
        fi
        _rx3_index=$((_rx3_index - 1))
    done
    [ "$_rx3_failed" = 0 ]
}

discard_runtime_stage()
{
    [ "$RUNTIME_STAGE_OWNED" = 0 ] || rm -rf "$RUNTIME_STAGE_DIR"
    RUNTIME_STAGE_OWNED=0
    RUNTIME_STAGE_COUNT=0
}

module_begin()
{
    _rx3_module_id=$1
    _rx3_module_namespace=$2
    case "$_rx3_module_id" in
        ""|*[!a-z0-9-]*)
            say "FAILED: invalid module id [$_rx3_module_id]"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
    case "$_rx3_module_namespace" in
        ""|*[!a-z0-9_]*)
            say "FAILED: invalid namespace [$_rx3_module_namespace] for $_rx3_module_id"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
    case " $LOADED_MODULES " in
        *" $_rx3_module_id "*)
            say "FAILED: duplicate runtime module $_rx3_module_id"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
    LOADED_MODULES="$LOADED_MODULES $_rx3_module_id"
    CURRENT_MODULE=$_rx3_module_id
    CURRENT_NAMESPACE=$_rx3_module_namespace
}

register_lifecycle_hook()
{
    _rx3_phase=$1
    _rx3_hook=$2
    [ -n "$CURRENT_MODULE" ] || {
        say "FAILED: lifecycle hook registered outside a module"
        MODULE_LOAD_FAILED=1
        return 1
    }
    case "$_rx3_hook" in
        "${CURRENT_NAMESPACE}_"*) ;;
        *)
            say "FAILED: $CURRENT_MODULE hook [$_rx3_hook] escapes namespace $CURRENT_NAMESPACE"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
    case "$_rx3_phase" in
        prepare) PREPARE_HOOKS="$PREPARE_HOOKS $_rx3_hook" ;;
        stopped) STOPPED_HOOKS="$STOPPED_HOOKS $_rx3_hook" ;;
        rollback) ROLLBACK_HOOKS="$ROLLBACK_HOOKS $_rx3_hook" ;;
        after)   AFTER_LAUNCH_HOOKS="$AFTER_LAUNCH_HOOKS $_rx3_hook" ;;
        post)    POST_LAUNCH_HOOKS="$POST_LAUNCH_HOOKS $_rx3_hook" ;;
        report)  REPORT_HOOKS="$REPORT_HOOKS $_rx3_hook" ;;
        *)
            say "FAILED: unknown lifecycle phase [$_rx3_phase] for $CURRENT_MODULE"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
}

register_patch()
{
    [ -n "$CURRENT_MODULE" ] || {
        say "FAILED: binary patch registered outside a module"
        MODULE_LOAD_FAILED=1
        return 1
    }
    case "$1" in
        ""|*[!0-9]*)
            say "FAILED: $CURRENT_MODULE registered invalid patch offset [$1]"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
    if patch_span_conflicts "$1" 4; then
        say "FAILED: modules share guarded patch bytes at $1"
        MODULE_LOAD_FAILED=1
        return 1
    fi
    PATCH_OFFSETS="$PATCH_OFFSETS $1"
    PATCH_SPANS="${PATCH_SPANS}
$1 4 $CURRENT_MODULE:$4"
    PATCH_TABLE="${PATCH_TABLE}
$1 $2 $3 $CURRENT_MODULE:$4"
}

patch_span_conflicts()
{
    _rx3_start=$1
    _rx3_length=$2
    printf '%s\n' "$PATCH_SPANS" | awk \
        -v start="$_rx3_start" -v finish="$((_rx3_start + _rx3_length))" '
        NF >= 2 && start < $1 + $2 && $1 < finish { conflict = 1 }
        END { exit conflict ? 0 : 1 }
    '
}

patch_file_path_valid()
{
    case "$1" in
        /mnt/iso/modules/*|/tmp/*)
            case "$1" in
                *[!A-Za-z0-9_./-]*|*/../*|*/..|*/./*|*/.) return 1 ;;
                *) return 0 ;;
            esac
            ;;
        *) return 1 ;;
    esac
}

# Register a contiguous, aligned file-backed replacement. Both files are
# copied into the orchestrator workspace before rbp is inspected, so generated
# /tmp inputs can be cleaned after launch without weakening rollback.
register_patch_file()
{
    [ -n "$CURRENT_MODULE" ] || {
        say "FAILED: binary patch registered outside a module"
        MODULE_LOAD_FAILED=1
        return 1
    }
    case "$1:$2" in
        *[!0-9:]*|:*|*:|*:0)
            say "FAILED: $CURRENT_MODULE registered invalid patch range [$1,$2]"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
    [ $(( $1 % 4 )) -eq 0 ] && [ $(( $2 % 4 )) -eq 0 ] || {
        say "FAILED: $CURRENT_MODULE registered unaligned patch range [$1,$2]"
        MODULE_LOAD_FAILED=1
        return 1
    }
    patch_file_path_valid "$3" && patch_file_path_valid "$4" || {
        say "FAILED: $CURRENT_MODULE registered an unsafe patch file"
        MODULE_LOAD_FAILED=1
        return 1
    }
    [ -r "$3" ] && [ -r "$4" ] &&
        [ "$(wc -c < "$3" 2>/dev/null)" = "$2" ] &&
        [ "$(wc -c < "$4" 2>/dev/null)" = "$2" ] || {
        say "FAILED: $CURRENT_MODULE registered an incomplete patch range [$1,$2]"
        MODULE_LOAD_FAILED=1
        return 1
    }
    if patch_span_conflicts "$1" "$2"; then
        say "FAILED: modules share guarded patch bytes at $1"
        MODULE_LOAD_FAILED=1
        return 1
    fi
    PATCH_SPANS="${PATCH_SPANS}
$1 $2 $CURRENT_MODULE:$5"
    PATCH_FILE_TABLE="${PATCH_FILE_TABLE}
$1 $2 $3 $4 $CURRENT_MODULE:$5"
}

# Restarting rbp costs a frozen screen and a fresh media rescan, so a session
# that asks for one has to say which hook asked and why.
request_rbp_restart()
{
    NEED_RBP_RESTART=1
    _rx3_requester=${RUNNING_HOOK:-runtime}
    case " $RESTART_REQUESTED_BY " in
        *" $_rx3_requester "*) ;;
        *) RESTART_REQUESTED_BY="$RESTART_REQUESTED_BY $_rx3_requester" ;;
    esac
}

# A shared object this runtime injects. Rolling back to a stock binary has to
# take these out of LD_PRELOAD: stock bytes under our hook is neither state.
register_runtime_preload()
{
    [ -n "$CURRENT_MODULE" ] || {
        say "FAILED: preload entry registered outside a module"
        MODULE_LOAD_FAILED=1
        return 1
    }
    case " $RUNTIME_PRELOAD_ENTRIES " in
        *" $1 "*) ;;
        *) RUNTIME_PRELOAD_ENTRIES="$RUNTIME_PRELOAD_ENTRIES $1" ;;
    esac
}

# Keep a preload at its first position, collapse its duplicates, or append it.
# Separately packaged modules must not reorder each other's interposers.
ensure_preload_entry()
{
    _rx3_target=$1
    [ -n "$_rx3_target" ] || return 1
    _rx3_pending=$RBP_PRELOAD
    _rx3_cleaned=""
    _rx3_seen=0
    while [ -n "$_rx3_pending" ]; do
        case "$_rx3_pending" in
            *:*) _rx3_entry=${_rx3_pending%%:*}; _rx3_pending=${_rx3_pending#*:} ;;
            *)   _rx3_entry=$_rx3_pending; _rx3_pending="" ;;
        esac
        [ -n "$_rx3_entry" ] || continue
        if [ "$_rx3_entry" = "$_rx3_target" ]; then
            [ "$_rx3_seen" = 0 ] || continue
            _rx3_seen=1
        fi
        if [ -n "$_rx3_cleaned" ]; then
            _rx3_cleaned="$_rx3_cleaned:$_rx3_entry"
        else
            _rx3_cleaned=$_rx3_entry
        fi
    done
    if [ "$_rx3_seen" = 0 ]; then
        if [ -n "$_rx3_cleaned" ]; then
            _rx3_cleaned="$_rx3_cleaned:$_rx3_target"
        else
            _rx3_cleaned=$_rx3_target
        fi
    fi
    RBP_PRELOAD=$_rx3_cleaned
}

preload_without_runtime()
{
    _rx3_pending=$1
    _rx3_cleaned=""
    while [ -n "$_rx3_pending" ]; do
        case "$_rx3_pending" in
            *:*) _rx3_entry=${_rx3_pending%%:*}; _rx3_pending=${_rx3_pending#*:} ;;
            *)   _rx3_entry=$_rx3_pending; _rx3_pending="" ;;
        esac
        [ -n "$_rx3_entry" ] || continue
        case " $RUNTIME_PRELOAD_ENTRIES " in
            *" $_rx3_entry "*) continue ;;
        esac
        if [ -n "$_rx3_cleaned" ]; then
            _rx3_cleaned="$_rx3_cleaned:$_rx3_entry"
        else
            _rx3_cleaned=$_rx3_entry
        fi
    done
    printf '%s' "$_rx3_cleaned"
}

# Materialise every guarded patch in `directory`, plus an index sorted by file
# offset. Range inputs are copied now so later validation and rollback do not
# depend on their original paths.
extract_guarded_words()
{
    _rx3_directory=$1
    _rx3_index=0
    printf '%s\n' "$PATCH_TABLE" | while read -r _rx3_offset _rx3_stock _rx3_patched _rx3_label; do
        [ -n "$_rx3_offset" ] || continue
        _rx3_index=$((_rx3_index + 1))
        printf "$_rx3_stock" > "$_rx3_directory/stock$_rx3_index"
        printf "$_rx3_patched" > "$_rx3_directory/patched$_rx3_index"
    done
    _rx3_index=0
    printf '%s\n' "$PATCH_FILE_TABLE" | while read -r _rx3_offset _rx3_length _rx3_stock _rx3_patched _rx3_label; do
        [ -n "$_rx3_offset" ] || continue
        _rx3_index=$((_rx3_index + 1))
        cp "$_rx3_stock" "$_rx3_directory/stock-file$_rx3_index" || exit 1
        cp "$_rx3_patched" "$_rx3_directory/patched-file$_rx3_index" || exit 1
    done || return 1
    {
        printf '%s\n' "$PATCH_TABLE" | awk '/^[0-9]/ {print $1, 4, "word", ++n}'
        printf '%s\n' "$PATCH_FILE_TABLE" | awk '/^[0-9]/ {print $1, $2, "file", ++n}'
    } | sort -n > "$_rx3_directory/order"
}

# SHA-1 of `binary` with every guarded patch put back to its stock value.
#
# The identity check hashes the whole file, so a session this runtime already
# patched no longer matches the state it started from and reinserting the drive
# stops. Normalising first asks the question the check means to ask - is this
# the binary I know? - without being fooled by our own writes. A guarded patch
# holding neither value survives normalisation, but the state audit that follows
# rejects it before anything is written.
#
# Words are 32-bit instructions at aligned offsets, which is what lets the
# untouched spans stream back out of dd. An unaligned registration would need a
# byte-at-a-time pass over a multi-megabyte binary, so it is refused rather than
# served slowly. /tmp is half a megabyte on this device, so the stream is piped
# rather than staged as a patched copy.

# Copy `from`..`to` of the binary to stdout, in whole pages wherever the span
# allows it. A page holds 1024 guarded-word slots, so reading the whole file at
# word granularity would cost three orders of magnitude more read calls than the
# deck needs to spend here.
_rx3_emit_span()
{
    _rx3_from=$1
    _rx3_to=$2
    while [ "$_rx3_from" -lt "$_rx3_to" ]; do
        if [ $((_rx3_from % 4096)) -eq 0 ] && [ $((_rx3_to - _rx3_from)) -ge 4096 ]; then
            _rx3_count=$(((_rx3_to - _rx3_from) / 4096))
            dd if="$_rx3_binary" bs=4096 skip=$((_rx3_from / 4096)) \
                count="$_rx3_count" 2>/dev/null
            _rx3_from=$((_rx3_from + _rx3_count * 4096))
        else
            _rx3_limit=$(((_rx3_from / 4096 + 1) * 4096))
            [ "$_rx3_limit" -gt "$_rx3_to" ] && _rx3_limit=$_rx3_to
            _rx3_count=$(((_rx3_limit - _rx3_from) / 4))
            dd if="$_rx3_binary" bs=4 skip=$((_rx3_from / 4)) \
                count="$_rx3_count" 2>/dev/null
            _rx3_from=$_rx3_limit
        fi
    done
}

normalized_rbp_sha1()
{
    _rx3_binary=$1
    _rx3_directory=$2
    awk '$1 % 4 != 0 || $2 % 4 != 0 { unaligned = 1 } END { exit !unaligned }' \
        "$_rx3_directory/order" && return 1
    _rx3_size=$(wc -c < "$_rx3_binary" 2>/dev/null)
    [ -n "$_rx3_size" ] || return 1
    {
        _rx3_previous=0
        while read -r _rx3_offset _rx3_length _rx3_kind _rx3_index; do
            _rx3_emit_span "$_rx3_previous" "$_rx3_offset"
            if [ "$_rx3_kind" = "word" ]; then
                cat "$_rx3_directory/stock$_rx3_index"
            else
                cat "$_rx3_directory/stock-file$_rx3_index"
            fi
            _rx3_previous=$((_rx3_offset + _rx3_length))
        done < "$_rx3_directory/order"
        _rx3_emit_span "$_rx3_previous" $((_rx3_size - _rx3_size % 4))
        [ $((_rx3_size % 4)) -gt 0 ] && dd if="$_rx3_binary" bs=1 \
            skip=$((_rx3_size - _rx3_size % 4)) 2>/dev/null
    } | sha1sum | awk '{print $1}'
}

guarded_patch_file_state()
{
    _rx3_binary=$1
    _rx3_offset=$2
    _rx3_length=$3
    _rx3_stock=$4
    _rx3_patched=$5
    if guarded_patch_file_matches "$_rx3_binary" "$_rx3_offset" \
        "$_rx3_length" "$_rx3_stock"; then
        printf '%s\n' stock
    elif guarded_patch_file_matches "$_rx3_binary" "$_rx3_offset" \
        "$_rx3_length" "$_rx3_patched"; then
        printf '%s\n' patched
    else
        printf '%s\n' unknown
    fi
}

guarded_patch_file_matches()
{
    dd if="$1" bs=1 skip="$2" count="$3" 2>/dev/null | cmp -s - "$4"
}

write_guarded_patch_file()
{
    [ "$(wc -c < "$4" 2>/dev/null)" = "$3" ] || return 1
    dd if="$4" of="$1" bs=1 seek="$2" conv=notrunc 2>/dev/null
}

# Read one variable out of the running rbp environment. A module uses this to
# distinguish an active runtime from one that still has to be installed.
rbp_environment_value()
{
    [ -n "$PID" ] || return 1
    tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null | sed -n "s/^$1=//p" | head -1
}

# A process named rbp may still be running an old or unrelated executable.
# Guarded writes target the file at RBP, so its live executable mapping must
# refer to that exact file before a transition is planned.
rbp_executable_matches()
{
    _rx3_exe="$PROC_ROOT/$PID/exe"
    [ "$(readlink "$_rx3_exe" 2>/dev/null)" = "$RBP" ] || return 1
    _rx3_live_inode=$(ls -iL "$_rx3_exe" 2>/dev/null | awk '{print $1}')
    _rx3_file_inode=$(ls -i "$RBP" 2>/dev/null | awk '{print $1}')
    [ -n "$_rx3_live_inode" ] && [ "$_rx3_live_inode" = "$_rx3_file_inode" ]
}

# Export one setting for the core, and ask for a restart when the running player
# does not already carry it.
#
# rbp reads its environment once, at load. A module that only exports leaves a
# player started without the variable running exactly as before, which is
# indistinguishable from a module that did nothing: the file changed, the deck
# did not. Every module that configures the core needs this comparison, so it
# lives here instead of being written out five times.
#
# Returns 0 when a restart was asked for, 1 when the running player is already
# carrying the value. Modules that have a second reason to restart, such as
# artwork that changed on the drive, test the result.
module_export()
{
    _rx3_setting=$1
    _rx3_wanted=$2
    _rx3_owner=$3
    export "$_rx3_setting=$_rx3_wanted"
    _rx3_running=$(rbp_environment_value "$_rx3_setting")
    [ "$_rx3_running" = "$_rx3_wanted" ] && return 1
    say "$_rx3_owner needs a restart: running rbp carries $_rx3_setting=[${_rx3_running:-none}]"
    request_rbp_restart
    return 0
}

# An absent module has no prepare hook to retract its old environment setting.
# Record the ordered image selection and runtime switches as one startup value
# so removing or disabling a module asks for a safe restart of the old player.
reconcile_module_set()
{
    case " $LOADED_MODULES " in
        *" core "*) ;;
        *) return 0 ;;
    esac
    _rx3_selection="${LOADED_MODULES# }|${DISABLED_MODULES# }"
    RUNNING_HOOK=module-set
    module_export RX3_RUNTIME_MODULE_SET "$_rx3_selection" "Module set" || :
}

# Where a module's kill switch lives. One shape for every module, so an operator
# who has learned one has learned them all.
module_switch_path() { printf '/tmp/rx3-%s.off' "$1"; }

# Whether the operator has turned this module off from the deck itself.
#
# Creating the file takes a shell on the player and no computer at all, and the
# switch is gone at the next power cycle. During a set that is the difference
# between a feature misbehaving for one track and a feature misbehaving until
# there is time to rebuild the drive.
#
# The path is built here from the module id, which module_begin has already
# constrained to lower case, digits and dashes, so no module can name a switch
# outside /tmp or diverge from the shape.
#
# The caller must step aside with `return 0`, never `return 1`. A prepare hook
# that returns non-zero stops the session and no guarded word is written at
# all, so a switch meant to take out one module would take out every one of
# them. That is the opposite of what it is for, and it is not hypothetical: it
# shipped that way once and cost a session on hardware.
module_disabled_by_switch()
{
    _rx3_switch=$(module_switch_path "$1")
    [ -e "$_rx3_switch" ] || return 1
    case " $DISABLED_MODULES " in
        *" $1 "*) ;;
        *) DISABLED_MODULES="$DISABLED_MODULES $1" ;;
    esac
    say "$1 disabled: $_rx3_switch exists"
    return 0
}

preload_contains()
{
    case ":$PREVIOUS_PRELOAD:" in
        *":$1:"*) return 0 ;;
        *) return 1 ;;
    esac
}

register_rbp_sha1()
{
    case " $SUPPORTED_SHA1 " in
        *" $1 "*) ;;
        *) SUPPORTED_SHA1="$SUPPORTED_SHA1 $1" ;;
    esac
}

register_prepare_hook()      { register_lifecycle_hook prepare "$1"; }
register_stopped_hook()      { register_lifecycle_hook stopped "$1"; }
register_rollback_hook()     { register_lifecycle_hook rollback "$1"; }
register_after_launch_hook() { register_lifecycle_hook after "$1"; }
register_post_launch_hook()  { register_lifecycle_hook post "$1"; }
register_report_hook()       { register_lifecycle_hook report "$1"; }

validate_tmp_contract_path()
{
    case "$1" in
        /tmp/*)
            case "$1" in
                *[!A-Za-z0-9_./-]*|*/../*|*/..|*/./*|*/.) return 1 ;;
                *) return 0 ;;
            esac
            ;;
        *) return 1 ;;
    esac
}

register_ready_file()
{
    validate_tmp_contract_path "$1" || {
        say "FAILED: $CURRENT_MODULE registered unsafe readiness path [$1]"
        MODULE_LOAD_FAILED=1
        return 1
    }
    RBP_READY_FILES="$RBP_READY_FILES $1"
}

register_pid_ready_file()
{
    register_ready_file "$1" || return 1
    RBP_PID_READY_FILES="$RBP_PID_READY_FILES $1"
}

ready_file_matches_pid()
{
    _rx3_ready_file=$1
    _rx3_ready_pid=$2
    [ -s "$_rx3_ready_file" ] || return 1
    case " $RBP_PID_READY_FILES " in
        *" $_rx3_ready_file "*)
            [ "$(cat "$_rx3_ready_file" 2>/dev/null)" = "$_rx3_ready_pid" ] ;;
        *) return 0 ;;
    esac
}

register_diagnostic_file()
{
    validate_tmp_contract_path "$1" || {
        say "FAILED: $CURRENT_MODULE registered unsafe diagnostic path [$1]"
        MODULE_LOAD_FAILED=1
        return 1
    }
    RBP_DIAGNOSTIC_FILES="$RBP_DIAGNOSTIC_FILES $1"
}

# How long a relaunched rbp is given to come up.
RBP_LAUNCH_TIMEOUT=8

# The one place that reads the device's process table.
rbp_is_running() { [ -d "/proc/$1" ]; }

# Wait for the process to be up, and no longer than it takes.
#
# Sitting out the whole window costs the operator the media list: a restarted
# player knows nothing of a drive that is already mounted, and nothing is
# announced to it until it has been declared up. A registered readiness file is
# written from inside the hook's own constructor, so seeing it is at once proof
# that the launch did not crash and a reason to stop waiting. Without one there
# is no signal to wait for, and the full window is the only guard left.
wait_for_rbp()
{
    _rx3_pid=$1
    RBP_SETTLED_AFTER=0
    while [ "$RBP_SETTLED_AFTER" -lt "$RBP_LAUNCH_TIMEOUT" ]; do
        rbp_is_running "$_rx3_pid" || break
        if [ -n "$RBP_READY_FILES" ]; then
            _rx3_pending=0
            for _rx3_ready in $RBP_READY_FILES; do
                ready_file_matches_pid "$_rx3_ready" "$_rx3_pid" || _rx3_pending=1
            done
            [ "$_rx3_pending" = "0" ] && break
        fi
        sleep 1
        RBP_SETTLED_AFTER=$((RBP_SETTLED_AFTER + 1))
    done
    say "rbp settled after ${RBP_SETTLED_AFTER}s"
}

run_hooks()
{
    _rx3_hooks=$1
    _rx3_hook_failed=0
    for _rx3_hook in $_rx3_hooks; do
        RUNNING_HOOK=$_rx3_hook
        "$_rx3_hook" || {
            say "FAILED: lifecycle hook $_rx3_hook"
            _rx3_hook_failed=1
        }
    done
    RUNNING_HOOK=""
    return "$_rx3_hook_failed"
}
