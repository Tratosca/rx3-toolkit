#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Session diagnostics on the drive. The orchestrator has already answered this
# module's only question - is it in the image? - before the first line could be
# written, so what is left here is to say what having said yes costs.

module_begin logging logging

# The performance core writes its own diagnostics, and by default it writes them
# to /tmp, which on this device is RAM: they die with the power and nobody can
# read them. Point it at the drive, beside the session log already kept here.
MOD_LOG="$USB/RX3_RUNTIME/mod.txt"

logging_prepare()
{
    mkdir -p "$USB/RX3_RUNTIME" 2>/dev/null
    # One generation back, like the session log: the run worth reading is
    # usually the one before the operator reinserted the drive to check.
    [ -f "$MOD_LOG" ] && mv -f "$MOD_LOG" "$USB/RX3_RUNTIME/mod-previous.txt" 2>/dev/null
    module_export RX3_LOG_FILE "$MOD_LOG" "Logging"
    # stdout is inherited at launch, not updated by exporting an environment
    # variable. Switching between RAM and USB must replace the old descriptor.
    if [ -n "$PID" ]; then
        current_output=$(readlink "${PROC_ROOT:-/proc}/$PID/fd/1" 2>/dev/null)
        [ "$current_output" = "$RBP_OUTPUT" ] || request_rbp_restart
    fi
    # An unchanged setting needs no restart; it is not a prepare failure.
    return 0
}

logging_report()
{
    say ""
    say "Session logs: RX3_RUNTIME/session.txt and mod.txt (closed after each line)."
    say "Player output stays in RAM unless verbose USB logging is selected."
}

register_prepare_hook logging_prepare
register_report_hook logging_report
