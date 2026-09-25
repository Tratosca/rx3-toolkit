#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
module_begin logging-verbose logging_verbose
logging_verbose_report()
{
    say "Verbose player output is on USB. Stop the player before removing the drive."
}
register_report_hook logging_verbose_report
