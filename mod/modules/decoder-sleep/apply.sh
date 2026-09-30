#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Set the decoder sleep interval through the rbp debug console.

NANOSECONDS=${1:-100000}
LOG=${2:-/tmp/rx3-decoder-sleep.log}
DEBUG_PORT_HEX=4E20
HELPER=/tmp/rx3-debug-command.$$

log()
{
    echo "$@" >> "$LOG" 2>&1
}

case "$NANOSECONDS" in
    ''|*[!0-9]*)
        log "decoder sleep rejected: interval must be a positive integer"
        exit 2
        ;;
    0)
        log "decoder sleep rejected: zero interval is not supported"
        exit 2
        ;;
esac

i=0
while [ "$i" -lt 20 ] && ! grep -qi ":$DEBUG_PORT_HEX" /proc/net/udp 2>/dev/null; do
    sleep 1
    i=$((i+1))
done

if ! grep -qi ":$DEBUG_PORT_HEX" /proc/net/udp 2>/dev/null; then
    log "decoder sleep not applied: rbp debug console is unavailable"
    exit 1
fi
if [ ! -x /bin/bash ]; then
    log "decoder sleep not applied: /bin/bash is unavailable"
    exit 1
fi

cat > "$HELPER" <<'DEBUG_HELPER'
#!/bin/bash
exec 3<>/dev/udp/127.0.0.1/20000 || exit 1
printf '%s\n' "$*" >&3 || exit 1
# Bash read consumes one byte at a time; on UDP that discards the rest of the
# datagram. Receive one whole packet, with a bounded wait and owned child.
umask 077
reply=${TMPDIR:-/tmp}/rx3-debug-reply.$$
receiver=
cleanup_reply()
{
    if [ -n "$receiver" ]; then
        kill "$receiver" 2>/dev/null || :
        wait "$receiver" 2>/dev/null || :
    fi
    rm -f "$reply"
}
trap cleanup_reply EXIT
trap 'exit 1' HUP INT TERM
dd bs=4096 count=1 <&3 > "$reply" 2>/dev/null &
receiver=$!
attempt=0
while kill -0 "$receiver" 2>/dev/null && [ "$attempt" -lt 5 ]; do
    sleep 1
    attempt=$((attempt+1))
done
kill -0 "$receiver" 2>/dev/null && exit 1
wait "$receiver" || exit 1
receiver=
response=$(tr -d '\000' < "$reply")
[ -n "$response" ] || exit 1
printf '%s\n' "$response"
DEBUG_HELPER
chmod 700 "$HELPER"
trap 'rm -f "$HELPER"' EXIT HUP INT TERM

log "--- decoder sleep: $NANOSECONDS ns ---"
failed=0
for deck in 0 1; do
    if ! "$HELPER" bufsleep "$deck" "$NANOSECONDS" >> "$LOG" 2>&1; then
        log "decoder sleep failed on deck $deck"
        failed=1
    fi
done

[ "$failed" -eq 0 ] || exit 1
log "decoder sleep: responses received for both decks; setting not verified"
