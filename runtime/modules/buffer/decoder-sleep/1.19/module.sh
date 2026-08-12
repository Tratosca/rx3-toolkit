#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Runtime adapter for the firmware 1.19 decoder sleep setting.

DECODER_SLEEP_NS=${DECODER_SLEEP_NS:-100000}
DECODER_SLEEP_SCRIPT=/mnt/iso/modules/decoder-sleep/apply.sh

decoder_sleep_apply()
{
    if [ -x "$DECODER_SLEEP_SCRIPT" ]; then
        "$DECODER_SLEEP_SCRIPT" "$DECODER_SLEEP_NS" "$LOG" || \
            say "WARNING: decoder sleep setting failed"
    else
        say "WARNING: decoder sleep module is incomplete"
    fi
}

register_post_launch_hook decoder_sleep_apply
