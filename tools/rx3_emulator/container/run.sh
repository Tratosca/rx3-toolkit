#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
set -eu

PROFILE=${RX3EMU_PROFILE:-all}
DURATION=${RX3EMU_DURATION:-60}
RBP=/rx3/root/pdj/rbp
OUT=/rx3/tmp/rx3emu
PDJ=/work/pdj

case "$PROFILE" in
    stock|keyshift|stems|all) ;;
    *) echo "unsupported emulator profile: $PROFILE" >&2; exit 64 ;;
esac

mkdir -p /work "$PDJ" /rx3/tmp "$OUT" /rx3/media/usb/RX3_STEMS
mount --bind /output "$OUT"
mount -t proc proc /rx3/proc
mount --rbind /dev /rx3/dev

# rbp and its fixed-path assets live in a 7 MiB private copy. The 4.6 GiB
# laboratory sysroot remains mounted read-only on the host.
cp -a /rx3/root/pdj/. "$PDJ"/
mount --bind "$PDJ" /rx3/root/pdj
cp /opt/rx3emu/fbshim.so /rx3/root/pdj/rx3emu-fbshim.so

# Rewrite one 32-bit word in the private copy of rbp, refusing anything that is
# neither the stock word nor the word we would write. Same contract as
# register_patch on the deck and as tools/rx3_patcher/patchlib.py offline: a
# firmware that does not match is a reason to stop, never to guess.
read_word()
{
    dd if="$RBP" bs=1 skip="$1" count=4 2>/dev/null | od -An -tx1 | tr -d ' \n'
}

# Hex string to a printf format of octal escapes. /bin/sh here is dash, whose
# printf has no \xHH -- it emits the six literal characters instead, which is
# how this function first wrote sixteen bytes of garbage into rbp and earned
# rbp a SIGILL. Octal is the POSIX escape, and is why the original image-table
# patch was written '\314\065\001\343' rather than in hex.
octal_escapes()
{
    value=$1
    escapes=""
    index=1
    while [ "$index" -lt "${#value}" ]; do
        byte=$(printf '%s' "$value" | cut -c"$index"-$((index + 1)))
        escapes="$escapes$(printf '\\%03o' "0x$byte")"
        index=$((index + 2))
    done
    printf '%s' "$escapes"
}

# Rewrite one 32-bit word in the private copy of rbp, refusing anything that is
# neither the stock word nor the word we would write, and reading the word back
# afterwards. Same contract as register_patch on the deck and as
# tools/rx3_patcher/patchlib.py offline: a firmware that does not match is a
# reason to stop, never to guess -- and neither is a write we did not confirm.
patch_word()
{
    offset=$1
    stock=$2
    patched=$3
    label=$4
    found=$(read_word "$offset")
    case "$found" in
        "$patched") echo "already patched: $label"; return ;;
        "$stock") ;;
        *) echo "$label guard rejected: $found" >&2; exit 65 ;;
    esac
    printf "$(octal_escapes "$patched")" |
        dd of="$RBP" bs=1 seek="$offset" conv=notrunc 2>/dev/null
    written=$(read_word "$offset")
    if [ "$written" != "$patched" ]; then
        echo "$label write failed: wrote $written, wanted $patched" >&2
        exit 65
    fi
    echo "patched $label"
}

PRELOAD=/root/pdj/rx3emu-fbshim.so
if [ "$PROFILE" != stock ]; then
    test -r /repo/build/librx3_core_emulator.so
    cp /repo/build/librx3_core_emulator.so /rx3/root/pdj/librx3_core.so
    cp /repo/mod/modules/core/1.19/assets/key-selected.rgb565 \
       /rx3/root/pdj/rx3-key-selected.rgb565
    cp /repo/mod/modules/core/1.19/assets/stems-selected.rgb565 \
       /rx3/root/pdj/rx3-stems-selected.rgb565
    cp /repo/mod/modules/core/1.19/assets/none-selected.rgb565 \
       /rx3/root/pdj/rx3-none-selected.rgb565
    cp /repo/mod/modules/core/1.19/assets/status-none-selected.rgb565 \
       /rx3/root/pdj/rx3-status-none-selected.rgb565

    # NS_GetImageInfoByID: movw r3,#0x15cc -> movw r3,#0x1603. This is the
    # same guarded pre-launch patch registered by core/module.sh.
    patch_word 1874220 cc3501e3 033601e3 image-table
    PRELOAD="$PRELOAD:/root/pdj/librx3_core.so"
fi

# main: bne startUp -> b startUp. Emulator-only and off by default, because it
# is measurably inert until the wait inside UiObjectManager::init() is removed
# -- see tools/rx3_emulator/patches.py for the measurement.
if [ "${RX3EMU_UNBLOCK_INIT:-0}" = "1" ]; then
    patch_word 34000 2b00001a 2b0000ea unblock-startup
fi

case "$PROFILE" in
    keyshift|all) KEYSHIFT=1 ;;
    *) KEYSHIFT=0 ;;
esac
case "$PROFILE" in
    stems|all) STEMS=/media/usb/RX3_STEMS ;;
    *) STEMS= ;;
esac
case "$PROFILE" in
    keyshift|all) PANEL=1 ;;
    stems) PANEL=2 ;;
    *) PANEL=0 ;;
esac
# Lets the hook load without forcing a feature panel open. The forced panel is
# what makes the mod's own rendering observable, but it also pins the display,
# so isolating "does rbp still change screens" needs a way to switch it off
# while keeping the injector.
PANEL=${RX3EMU_PANEL:-$PANEL}

rm -f "$OUT/framebuffer.raw" "$OUT/framebuffer.json" \
      "$OUT/rbp.log" "$OUT/hook.log" "$OUT/ready" "$OUT/status"
rm -f "$OUT/touch.fifo" "$OUT/touch.command"
printf '0 0 0\n' > "$OUT/touch.command"
rm -f /rx3/tmp/rx3emu-touch.fifo
mkfifo /rx3/tmp/rx3emu-touch.fifo

cleanup()
{
    trap - EXIT INT TERM
    for process in ${RBP_PID:-} ${STDIN_WRITER_PID:-} ${DB_WRITER_PID:-} ${DB_PID:-}; do
        [ -n "$process" ] && kill "$process" 2>/dev/null || true
    done
    [ -n "${RBP_PID:-}" ] && wait "$RBP_PID" 2>/dev/null || true
    cp /rx3/tmp/rx3-stems.log "$OUT/hook.log" 2>/dev/null || true
    cp /rx3/tmp/rx3-performance.ready "$OUT/ready" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

chroot /rx3 /bin/sh -c '/usr/bin/edb_streamd' > "$OUT/edb.log" 2>&1 &
DB_PID=$!

# Wait for edb_streamd to be listening rather than guessing at it. rbp polls
# that socket during startup, and a fixed sleep is a race: under QEMU the
# database server sometimes needs longer than two seconds to bind, and when it
# does, rbp stalls before DirectFB ever opens /dev/fb0 -- no framebuffer, no
# image table, nothing. Port 12523 is 0x30EB in /proc/net/tcp, which is shared
# with the chroot because the network namespace is.
DB_WAIT=0
while [ "$DB_WAIT" -lt 150 ]; do
    if grep -qi ':30EB' /proc/net/tcp 2>/dev/null; then
        echo "edb_streamd listening after ${DB_WAIT}00ms"
        break
    fi
    kill -0 "$DB_PID" 2>/dev/null || { echo "edb_streamd exited early" >&2; break; }
    DB_WAIT=$((DB_WAIT + 1))
    sleep 0.1
done
[ "$DB_WAIT" -lt 150 ] || echo "edb_streamd did not listen within 15s" >&2

# Keep both FIFOs open without making them perpetually readable. rbp otherwise
# spins on stdin or blocks the LocalDBServer initialization path.
( sleep 100000 > /rx3/tmp/req_LocalDBServer ) &
DB_WRITER_PID=$!
mkfifo /rx3/tmp/stdin.fifo 2>/dev/null || true
( sleep 100000 > /rx3/tmp/stdin.fifo ) &
STDIN_WRITER_PID=$!

chroot /rx3 /bin/sh -c \
    "LD_PRELOAD='$PRELOAD' RX3_KEYSHIFT='$KEYSHIFT' RX3_STEMS_DIR='$STEMS' \
     RX3_EMULATOR_PANEL='$PANEL' \
     RX3_EMULATOR_TRACE_INIT='${RX3EMU_TRACE_INIT:-0}' \
     RX3_EMULATOR_PUMP='${RX3EMU_PUMP:-}' \
     RX3_EMULATOR_TRACE_LAYERS='${RX3EMU_TRACE_LAYERS:-0}' \
     RX3_EMULATOR_FONT_DONOR='${RX3EMU_FONT_DONOR:-0}' \
     RX3_EMULATOR_FONT_MAXH='${RX3EMU_FONT_MAXH:-0}' \
     RX3EMU_OUTPUT=/tmp/rx3emu RX3EMU_TRACE_READS='${RX3EMU_TRACE_READS:-0}' \
     DFBARGS='system=fbdev,no-vt,no-sighandler,no-cursor,no-hardware,disable-module=keyboard,disable-module=linux_input,disable-module=gal,mode=1280x720,depth=32' \
     /root/pdj/rbp -a < /tmp/stdin.fifo" > "$OUT/rbp.log" 2>&1 &
RBP_PID=$!

# Duration 0 means "run until the host stops us", which the window path does by
# terminating the container when it is closed. The trap still runs, so hook.log
# and the ready file are collected either way.
if [ "$DURATION" -eq 0 ]; then
    echo "running profile=$PROFILE pid=$RBP_PID duration=unlimited"
else
    echo "running profile=$PROFILE pid=$RBP_PID duration=${DURATION}s"
fi
ELAPSED=0
while kill -0 "$RBP_PID" 2>/dev/null; do
    [ "$DURATION" -eq 0 ] || [ "$ELAPSED" -lt "$DURATION" ] || break
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

if kill -0 "$RBP_PID" 2>/dev/null; then
    printf 'timeout\n' > "$OUT/status"
else
    wait "$RBP_PID" || true
    printf 'rbp-exited\n' > "$OUT/status"
fi
