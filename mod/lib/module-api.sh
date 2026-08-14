#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Registration API sourced by autoexec.sh. It mutates only the orchestrator's
# in-memory tables; device changes belong to registered lifecycle callbacks.

# Where the packaged performance core sits once the ISO is mounted. Feature
# modules refuse to prepare without it, and name it through this one constant
# rather than repeating the path.
CORE_OBJECT=/mnt/iso/modules/core/librx3_core.so

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
    case " $PATCH_OFFSETS " in
        *" $1 "*)
            say "FAILED: modules share guarded patch offset $1"
            MODULE_LOAD_FAILED=1
            return 1
            ;;
    esac
    PATCH_OFFSETS="$PATCH_OFFSETS $1"
    PATCH_TABLE="${PATCH_TABLE}
$1 $2 $3 $CURRENT_MODULE:$4"
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

# Write every guarded word into `directory`, one file per word, numbered by its
# position in PATCH_TABLE, plus an `order` index sorted by offset.
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
    printf '%s\n' "$PATCH_TABLE" | awk '/^[0-9]/ {print $1, ++n}' | sort -n \
        > "$_rx3_directory/order"
}

# SHA-1 of `binary` with every guarded word put back to its stock value.
#
# The identity check hashes the whole file, so a session this runtime already
# patched no longer matches the state it started from and reinserting the drive
# stops. Normalising first asks the question the check means to ask - is this
# the binary I know? - without being fooled by our own writes. A guarded word
# holding neither value survives normalisation, but the word-by-word audit that
# follows rejects it before anything is written.
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
    awk '$1 % 4 != 0 { unaligned = 1 } END { exit !unaligned }' \
        "$_rx3_directory/order" && return 1
    _rx3_size=$(wc -c < "$_rx3_binary" 2>/dev/null)
    [ -n "$_rx3_size" ] || return 1
    {
        _rx3_previous=0
        while read -r _rx3_offset _rx3_index; do
            _rx3_emit_span "$_rx3_previous" "$_rx3_offset"
            cat "$_rx3_directory/stock$_rx3_index"
            _rx3_previous=$((_rx3_offset + 4))
        done < "$_rx3_directory/order"
        _rx3_emit_span "$_rx3_previous" $((_rx3_size - _rx3_size % 4))
        [ $((_rx3_size % 4)) -gt 0 ] && dd if="$_rx3_binary" bs=1 \
            skip=$((_rx3_size - _rx3_size % 4)) 2>/dev/null
    } | sha1sum | awk '{print $1}'
}

# Read one variable out of the running rbp environment. A module uses this to
# distinguish an active runtime from one that still has to be installed.
rbp_environment_value()
{
    [ -n "$PID" ] || return 1
    tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null | sed -n "s/^$1=//p" | head -1
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
                [ -s "$_rx3_ready" ] || _rx3_pending=1
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
