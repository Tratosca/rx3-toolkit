#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Runtime registration for the firmware 1.19 direct Beat Jump execution path.

register_patch 695764 '\075\000\000\012' '\000\000\240\341' quantized_BeatJump_to_direct_path

beatjump_no_quantize_report()
{
    say "Beat Jump uses the direct path without grid reservation."
}

register_report_hook beatjump_no_quantize_report
