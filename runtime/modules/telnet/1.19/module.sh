#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Volatile firmware 1.19 diagnostic access for manual runtime inspection.

module_begin telnet telnet

telnet_start()
{
    if [ -f /etc/securetty ] && ! grep -q '^pts/0$' /etc/securetty 2>/dev/null; then
        tty_index=0
        while [ "$tty_index" -lt 10 ]; do
            echo "pts/$tty_index" >> /etc/securetty
            tty_index=$((tty_index+1))
        done
    fi

    if grep -qi ':0017 ' /proc/net/tcp 2>/dev/null; then
        say "telnetd: port 23 already open"
    elif /bin/busybox telnetd -p 23 >/dev/null 2>&1; then
        sleep 1
        IP=$(ifconfig 2>/dev/null | sed -n 's/.*inet addr:\([0-9.]*\).*/\1/p' | grep -v '^127' | head -1)
        say "telnetd active: telnet ${IP:-rx3_address}"
    else
        say "WARNING: telnetd failed to start"
    fi
}

# Start before rbp is replaced. Diagnostic access then survives a guarded
# rollback and exposes the core log when a candidate preload exits early.
register_prepare_hook telnet_start
