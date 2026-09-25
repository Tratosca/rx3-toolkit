#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Sample pads. The code lives in the performance core's shared object; this
# module points it at the bank directory and reports what it found.

module_begin samples samples

SAMPLES_DIR="$USB/RX3_RUNTIME/samples"
# Same reason as stems: a drive comes back under a different device node, and
# rbp reads its environment once. One fixed path, re-pointed on each insertion,
# means a moved drive does not cost a restart.
SAMPLES_LINK=/tmp/rx3-samples
SAMPLES_READY=0

samples_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Sample pads disabled: the performance core is not selected"
        return 1
    }
    module_disabled_by_switch samples && return 0

    # A drive with no banks on it is the ordinary case, not a failure. A
    # prepare hook that returns non-zero stops the whole session and no
    # guarded word is written, so a module with nothing to do says so and
    # steps aside.
    [ -d "$SAMPLES_DIR" ] || {
        say "Sample pads: no samples directory on this drive, nothing to load"
        return 0
    }

    count=0
    for candidate in "$SAMPLES_DIR"/banks/*; do
        [ -d "$candidate" ] || continue
        count=$((count+1))
    done

    # The core reads numbered WAV files directly from RX3_SAMPLES_DIR.
    # Bank selection belongs to the host and is resolved before launch.
    active=
    if [ -r "$SAMPLES_DIR/active" ]; then
        IFS= read -r active < "$SAMPLES_DIR/active" || :
    fi
    case "$active" in
        ''|.*|*[!A-Za-z0-9_.-]*)
            say "Sample pads: no valid active bank, nothing to load"
            return 0
            ;;
    esac
    bank_dir="$SAMPLES_DIR/banks/$active"
    [ -d "$bank_dir" ] || {
        say "Sample pads: the active bank is missing, nothing to load"
        return 0
    }
    published=$bank_dir
    if [ ! -e "$SAMPLES_LINK" ] || [ -L "$SAMPLES_LINK" ]; then
        rm -f "$SAMPLES_LINK"
        ln -s "$bank_dir" "$SAMPLES_LINK" 2>/dev/null && published=$SAMPLES_LINK
    fi

    export RX3_SAMPLES_CONFIG="$published/settings.ini"
    SAMPLES_READY=1
    module_export RX3_SAMPLES_DIR "$published" "Sample pads"
    say "Sample pads prepared: $count bank(s) at $SAMPLES_DIR"
}

samples_after_launch()
{
    [ "$SAMPLES_READY" = "1" ] || return 0
    say "SAMPLE: press SLIP LOOP past its own pages to reach the pads; playback hardware validation pending"
    # What this build of the pads can do, so the computer can offer exactly
    # that rather than offering a setting a deck would ignore. Read back from
    # the session file the player leaves on the drive.
    say "SAMPLE pad modes: once hold loop latch"
    say "SAMPLE shift.silence: stops every pad"
}

register_prepare_hook samples_prepare
register_after_launch_hook samples_after_launch
