#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# RX3 volatile runtime orchestrator. Feature logic lives in module directories.

USB="$1"
OUT="$USB/RX3_RUNTIME"
LOG="$OUT/session.txt"
RBP=/root/pdj/rbp
TMP=/tmp/rx3-runtime
PATCH_TABLE=""
PATCH_OFFSETS=""
SUPPORTED_SHA1=""
PREPARE_HOOKS=""
AFTER_LAUNCH_HOOKS=""
POST_LAUNCH_HOOKS=""
REPORT_HOOKS=""
RBP_PRELOAD=""
RBP_READY_FILES=""
RBP_DIAGNOSTIC_FILES=""
PREVIOUS_PRELOAD=""
NEED_RBP_RESTART=0
LOADED_MODULES=""
CURRENT_MODULE=""
CURRENT_NAMESPACE=""
MODULE_LOAD_FAILED=0

mkdir -p "$OUT" 2>/dev/null
: > "$LOG"

say()
{
    echo "$@" >> "$LOG" 2>&1
}

MODULE_API=/mnt/iso/lib/module-api.sh
[ -r "$MODULE_API" ] || {
    say "STOP: runtime module API is missing."
    sync; exit 1
}
. "$MODULE_API" || {
    say "STOP: runtime module API could not be loaded."
    sync; exit 1
}

load_module()
{
    runtime_directory=$1
    case "$runtime_directory" in
        ""|*[!a-z0-9-]*)
            say "FAILED: unsafe runtime module directory [$runtime_directory]"
            MODULE_LOAD_FAILED=1
            return
            ;;
    esac
    module=/mnt/iso/modules/$runtime_directory/module.sh
    [ -r "$module" ] || {
        say "FAILED: indexed module is missing: $runtime_directory"
        MODULE_LOAD_FAILED=1
        return
    }
    CURRENT_MODULE=""
    CURRENT_NAMESPACE=""
    . "$module" || MODULE_LOAD_FAILED=1
    [ -n "$CURRENT_MODULE" ] || {
        say "FAILED: $runtime_directory did not declare a module contract"
        MODULE_LOAD_FAILED=1
    }
}

if [ -r /mnt/iso/modules/index ]; then
    while IFS= read -r runtime_directory; do
        [ -n "$runtime_directory" ] || continue
        load_module "$runtime_directory"
    done < /mnt/iso/modules/index
else
    say "FAILED: deterministic module index is missing"
    MODULE_LOAD_FAILED=1
fi

[ "$MODULE_LOAD_FAILED" = "0" ] || {
    say "STOP: one or more runtime modules violate their contract."
    sync; exit 1
}
say "loaded modules:${LOADED_MODULES:- none}"

say "=== RX3 volatile runtime, uid $(id -u) ==="
say "firmware revision: $(cat /tmp/smdj2.rev 2>/dev/null || cat /tmp/smdj.rev 2>/dev/null)"
say ""
say "--- mounts ---"; cat /proc/mounts >> "$LOG" 2>&1
say ""
say "--- disk space ---"; df >> "$LOG" 2>&1
say ""

ROOTFS=$(awk '$2=="/" {print $3}' /proc/mounts | tail -1)
say "effective root type: ${ROOTFS:-unknown}"
if [ "$ROOTFS" != "tmpfs" ] && [ "$ROOTFS" != "ramfs" ] && [ "$ROOTFS" != "rootfs" ]; then
    say "STOP: effective root is not RAM-backed (${ROOTFS})."
    say "      Modification could be persistent; nothing was changed."
    sync; exit 1
fi
if awk '$2=="/root/pdj"' /proc/mounts | grep -q .; then
    say "STOP: /root/pdj is a separate mount; nothing was changed."
    sync; exit 1
fi
[ -x "$RBP" ] || { say "FAILED: $RBP is missing"; sync; exit 1; }

RBP_SHA1=$(sha1sum "$RBP" 2>/dev/null | awk '{print $1}')
case " $SUPPORTED_SHA1 " in
    *" $RBP_SHA1 "*) ;;
    *)
        say "STOP: unsupported rbp SHA-1: ${RBP_SHA1:-unavailable}"
        say "      No module was applied."
        sync; exit 1
        ;;
esac
say "accepted rbp SHA-1: $RBP_SHA1"
say "volatile root confirmed: changes will be lost on power-off"

rm -rf "$TMP"
mkdir -p "$TMP" || { say "FAILED: /tmp is unavailable"; sync; exit 1; }

i=0
printf '%s\n' "$PATCH_TABLE" | while read -r OFF STOCK PATCHED LABEL; do
    [ -n "$OFF" ] || continue
    i=$((i+1))
    printf "$STOCK" > "$TMP/stock$i"
    printf "$PATCHED" > "$TMP/patched$i"
done
PATCH_COUNT=$(printf '%s\n' "$PATCH_TABLE" | awk '/^[0-9]/ {count++} END {print count+0}')
say "$PATCH_COUNT guarded words registered"

read_word()
{
    dd if="$RBP" bs=1 skip="$1" count=4 2>/dev/null
}

i=0
printf '%s\n' "$PATCH_TABLE" | while read -r OFF STOCK PATCHED LABEL; do
    [ -n "$OFF" ] || continue
    i=$((i+1))
    if read_word "$OFF" | cmp -s - "$TMP/stock$i"; then
        echo stock >> "$TMP/state"
        cp "$TMP/stock$i" "$TMP/previous$i"
    elif read_word "$OFF" | cmp -s - "$TMP/patched$i"; then
        echo patched >> "$TMP/state"
        cp "$TMP/patched$i" "$TMP/previous$i"
    else
        echo "unknown $OFF $LABEL" >> "$TMP/state"
    fi
done
UNKNOWN=$(grep -c '^unknown ' "$TMP/state" 2>/dev/null); [ -n "$UNKNOWN" ] || UNKNOWN=0
if [ "$UNKNOWN" != "0" ]; then
    say "STOP: $UNKNOWN unexpected patch word(s); nothing was changed."
    grep '^unknown ' "$TMP/state" >> "$LOG" 2>&1
    rm -rf "$TMP"; sync; exit 1
fi

# Reinserting the drive on an already-patched session must not disturb it. Only
# a word that still holds its stock value makes an rbp restart necessary.
STOCK_WORDS=$(grep -c '^stock$' "$TMP/state" 2>/dev/null); [ -n "$STOCK_WORDS" ] || STOCK_WORDS=0
if [ "$STOCK_WORDS" != "0" ]; then
    say "$STOCK_WORDS of $PATCH_COUNT word(s) still hold the stock value"
    request_rbp_restart
elif [ "$PATCH_COUNT" != "0" ]; then
    say "all $PATCH_COUNT word(s) already carry the patched value"
fi

PID=""
for process in /proc/[0-9]*; do
    [ "$(cat "$process/comm" 2>/dev/null)" = "rbp" ] && PID=${process#/proc/}
done
[ -n "$PID" ] || { say "FAILED: running rbp process not found"; rm -rf "$TMP"; sync; exit 1; }
ARGS=$(tr '\0' ' ' < "/proc/$PID/cmdline" | cut -d' ' -f2-)
CWD=$(readlink "/proc/$PID/cwd" 2>/dev/null)
PREVIOUS_PRELOAD=$(tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null | sed -n 's/^LD_PRELOAD=//p' | head -1)
RBP_PRELOAD=$PREVIOUS_PRELOAD
say "rbp pid=$PID options=[$ARGS] cwd=$CWD"
say "existing preload: ${PREVIOUS_PRELOAD:-none}"

run_hooks "$PREPARE_HOOKS" || {
    say "STOP: a prepare hook failed; no guarded word was written."
    rm -rf "$TMP"; sync; exit 1
}

if [ "$NEED_RBP_RESTART" = "0" ]; then
    echo patched > /tmp/rx3-patch.state
    say "nothing to apply: rbp already runs every selected module"
    NEW=$PID
    run_hooks "$AFTER_LAUNCH_HOOKS" || say "WARNING: an after-launch hook failed"
    run_hooks "$POST_LAUNCH_HOOKS" || say "WARNING: a post-launch hook failed"
    run_hooks "$REPORT_HOOKS" || say "WARNING: a report hook failed"
    rm -rf "$TMP"
    sync
    say "=== complete ==="
    exit 0
fi

echo applying > /tmp/rx3-patch.state
say "stopping rbp"
kill "$PID" 2>/dev/null
i=0
while [ "$i" -lt 10 ] && [ -d "/proc/$PID" ]; do sleep 1; i=$((i+1)); done
[ -d "/proc/$PID" ] && { kill -9 "$PID" 2>/dev/null; sleep 2; }
say "rbp stopped after ${i}s"

write_words()
{
    source_prefix=$1
    i=0
    printf '%s\n' "$PATCH_TABLE" | while read -r OFF STOCK PATCHED LABEL; do
        [ -n "$OFF" ] || continue
        i=$((i+1))
        dd if="$TMP/$source_prefix$i" of="$RBP" bs=1 seek="$OFF" conv=notrunc 2>/dev/null
    done
}

verify_words()
{
    source_prefix=$1
    rm -f "$TMP/failed"
    i=0
    printf '%s\n' "$PATCH_TABLE" | while read -r OFF STOCK PATCHED LABEL; do
        [ -n "$OFF" ] || continue
        i=$((i+1))
        read_word "$OFF" | cmp -s - "$TMP/$source_prefix$i" || echo "$OFF $LABEL" >> "$TMP/failed"
    done
    failures=$(grep -c . "$TMP/failed" 2>/dev/null); [ -n "$failures" ] || failures=0
    echo "$failures"
}

launch_rbp()
{
    target_log=$1
    cd "${CWD:-/root/pdj}" 2>/dev/null
    if [ -n "$RBP_PRELOAD" ]; then
        LD_PRELOAD="$RBP_PRELOAD" "$RBP" $ARGS >> "$target_log" 2>&1 &
    else
        "$RBP" $ARGS >> "$target_log" 2>&1 &
    fi
    NEW=$!
}

append_diagnostics()
{
    for diagnostic_file in $RBP_DIAGNOSTIC_FILES; do
        [ -r "$diagnostic_file" ] || continue
        say "--- diagnostic $diagnostic_file before rollback ---"
        cat "$diagnostic_file" >> "$LOG" 2>&1
    done
}

write_words patched
FAILED=$(verify_words patched)
if [ "$FAILED" != "0" ]; then
    say "FAILED: $FAILED patch word write(s); restoring previous bytes"
    cat "$TMP/failed" >> "$LOG" 2>&1
    write_words previous
    RBP_PRELOAD=$PREVIOUS_PRELOAD
    echo patched > /tmp/rx3-patch.state
    launch_rbp "$OUT/rbp_restore.txt"
    say "previous rbp restarted, pid=$NEW"
    rm -rf "$TMP"; sync; exit 1
fi
say "write verified: $PATCH_COUNT/$PATCH_COUNT words"

launch_rbp "$OUT/rbp_stdout.txt"
sleep 8
if [ ! -d "/proc/$NEW" ]; then
    say "FAILED: replacement rbp exited; restoring previous bytes"
    append_diagnostics
    write_words previous
    RBP_PRELOAD=$PREVIOUS_PRELOAD
    echo patched > /tmp/rx3-patch.state
    launch_rbp "$OUT/rbp_restore.txt"
    say "previous rbp restarted, pid=$NEW"
    rm -rf "$TMP"; sync; exit 1
fi
MISSING_READY=""
for ready_file in $RBP_READY_FILES; do
    [ -s "$ready_file" ] || MISSING_READY="$MISSING_READY $ready_file"
done
if [ -n "$MISSING_READY" ]; then
    say "FAILED: replacement rbp missed readiness:${MISSING_READY}; restoring previous bytes"
    append_diagnostics
    kill "$NEW" 2>/dev/null
    write_words previous
    RBP_PRELOAD=$PREVIOUS_PRELOAD
    echo patched > /tmp/rx3-patch.state
    launch_rbp "$OUT/rbp_restore.txt"
    say "previous rbp restarted, pid=$NEW"
    rm -rf "$TMP"; sync; exit 1
fi
say "OK: rbp active, pid=$NEW"
echo patched > /tmp/rx3-patch.state

run_hooks "$AFTER_LAUNCH_HOOKS" || say "WARNING: an after-launch hook failed"
run_hooks "$POST_LAUNCH_HOOKS" || say "WARNING: a post-launch hook failed"
run_hooks "$REPORT_HOOKS" || say "WARNING: a report hook failed"

rm -rf "$TMP"
sync
say "=== complete ==="
exit 0
