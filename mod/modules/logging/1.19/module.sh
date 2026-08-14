#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Session diagnostics on the drive. The orchestrator has already answered this
# module's only question - is it in the image? - before the first line could be
# written, so what is left here is to say what having said yes costs.

module_begin logging logging

logging_report()
{
    say ""
    say "Session logging is on. Eject the drive from the RX3 rather than"
    say "pulling it out: rbp keeps this file open for as long as it plays."
}

register_report_hook logging_report
