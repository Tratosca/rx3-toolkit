#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Registration API sourced by autoexec.sh. It mutates only the orchestrator's
# in-memory tables; device changes belong to registered lifecycle callbacks.

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

request_rbp_restart() { NEED_RBP_RESTART=1; }

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

run_hooks()
{
    _rx3_hooks=$1
    _rx3_hook_failed=0
    for _rx3_hook in $_rx3_hooks; do
        "$_rx3_hook" || {
            say "FAILED: lifecycle hook $_rx3_hook"
            _rx3_hook_failed=1
        }
    done
    return "$_rx3_hook_failed"
}
