#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Set the firmware 1.19 decoder sleep interval through the rbp debug console.

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
printf '%s\n' "$*" >&3
IFS= read -r -d '' -t 5 -u 3 response || true
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
log "decoder sleep applied to both decks"
