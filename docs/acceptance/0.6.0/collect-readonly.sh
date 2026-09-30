#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# One diagnostic snapshot. Run over a qualified Telnet session; save on host.
# No credentials, environment dump, /dev/mem, panel reads or device writes.
export LC_ALL=C
printf 'RX3_ACCEPTANCE_SNAPSHOT\n'
date -u 2>/dev/null
uname -a 2>/dev/null
for item in /proc/uptime /proc/loadavg /proc/meminfo /proc/stat /tmp/rx3-performance.ready; do
    printf '\nFILE %s\n' "$item"
    if [ -r "$item" ]; then cat "$item"; else printf 'UNAVAILABLE\n'; fi
done
pids=$(pidof rbp 2>/dev/null)
if [ -z "$pids" ]; then printf '\nRBP_NOT_FOUND_OR_PIDOF_UNAVAILABLE\n'; fi
for pid in $pids; do
    case "$pid" in *[!0-9]*|'') continue;; esac
    printf '\nRBP_PID %s\n' "$pid"
    readlink "/proc/$pid/exe" 2>/dev/null
    for item in stat status maps; do
        printf '\nPROCESS_FILE %s\n' "$item"
        cat "/proc/$pid/$item" 2>/dev/null
    done
    printf '\nFD_COUNT\n'
    ls "/proc/$pid/fd" 2>/dev/null | wc -l
    printf '\nFD_TARGETS_FIRST_80\n'
    ls -l "/proc/$pid/fd" 2>/dev/null | head -n 80
done
for item in /root/pdj/librx3_core.so /root/pdj/rbp; do
    if [ -r "$item" ]; then
        printf '\nDISK_FILE_HASH %s\n' "$item"
        if command -v sha256sum >/dev/null 2>&1; then sha256sum "$item";
        elif command -v sha1sum >/dev/null 2>&1; then sha1sum "$item";
        else printf 'HASH_TOOL_UNAVAILABLE\n'; fi
    fi
done
printf '\nSOCKETS_TCP_UDP\n'
cat /proc/net/tcp /proc/net/udp 2>/dev/null
printf '\nCORE_LOG_TAIL\n'
if [ -r /tmp/rx3-stems.log ]; then tail -n 80 /tmp/rx3-stems.log; fi
printf '\nKERNEL_LOG_TAIL\n'
dmesg 2>/dev/null | tail -n 80
printf '\nEND_RX3_ACCEPTANCE_SNAPSHOT\n'
