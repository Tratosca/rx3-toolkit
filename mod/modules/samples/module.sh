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

samples_bank_generation()
{
    samples_bank=$1
    samples_active=$2
    samples_manifest=$TMP/samples-generation.$$
    printf 'bank %s\n' "$samples_active" > "$samples_manifest" || return 1
    for sample_name in settings.ini 1.wav 2.wav 3.wav 4.wav 5.wav 6.wav 7.wav 8.wav; do
        sample_file=$samples_bank/$sample_name
        if [ -e "$sample_file" ] || [ -L "$sample_file" ]; then
            [ -f "$sample_file" ] && [ -r "$sample_file" ] || {
                rm -f "$samples_manifest"
                return 1
            }
            sample_hash=$(sha1sum "$sample_file" 2>/dev/null | awk '{print $1}')
            case "$sample_hash" in
                ""|*[!0-9a-f]*) rm -f "$samples_manifest"; return 1 ;;
            esac
            [ "${#sample_hash}" = 40 ] || { rm -f "$samples_manifest"; return 1; }
            printf '%s %s\n' "$sample_name" "$sample_hash" >> "$samples_manifest" || return 1
        else
            printf '%s absent\n' "$sample_name" >> "$samples_manifest" || return 1
        fi
    done
    samples_generation=$(sha1sum "$samples_manifest" 2>/dev/null | awk '{print $1}')
    rm -f "$samples_manifest"
    [ "${#samples_generation}" = 40 ] || return 1
    printf '%s' "$samples_generation"
}

samples_disable()
{
    module_export RX3_SAMPLES_DIR "" "Sample pads" || :
    module_export RX3_SAMPLES_GENERATION "" "Sample pads" || :
    if [ -L "$SAMPLES_LINK" ]; then
        stage_runtime_removal "$SAMPLES_LINK" || return 1
    fi
}

samples_repoint_live_link()
{
    samples_next=$SAMPLES_LINK.$$
    rm -f "$samples_next"
    ln -s "$1" "$samples_next" || return 1
    samples_previous=$(readlink "$SAMPLES_LINK") || return 1
    rm -f "$SAMPLES_LINK" || return 1
    mv -f "$samples_next" "$SAMPLES_LINK" || {
        rm -f "$samples_next"
        ln -s "$samples_previous" "$SAMPLES_LINK"
        return 1
    }
}

samples_prepare()
{

    [ -r "$CORE_OBJECT" ] || {
        say "Sample pads disabled: the performance core is not selected"
        return 1
    }
    if [ -e "$(module_switch_path samples)" ]; then
        samples_disable || say "Sample pads: disabled link could not be staged"
    fi
    module_disabled_by_switch samples && return 0
    stage_panel_asset samples 04 samples-selected || return 1
    stage_panel_asset samples 05 samples-none-selected || return 1
    stage_panel_asset samples 06 samples-beatfx-selected || return 1

    # A drive with no banks on it is the ordinary case, not a failure. A
    # prepare hook that returns non-zero stops the whole session and no
    # guarded word is written, so a module with nothing to do says so and
    # steps aside.
    [ -d "$SAMPLES_DIR" ] || {
        say "Sample pads: no samples directory on this drive, nothing to load"
        samples_disable || return 1
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
            samples_disable || return 1
            return 0
            ;;
    esac
    bank_dir="$SAMPLES_DIR/banks/$active"
    [ -d "$bank_dir" ] || {
        say "Sample pads: the active bank is missing, nothing to load"
        samples_disable || return 1
        return 0
    }
    generation=$(samples_bank_generation "$bank_dir" "$active") || {
        say "Sample pads: bank contents could not be verified"
        return 1
    }
    published=$bank_dir
    if [ -L "$SAMPLES_LINK" ] &&
       [ "$(readlink "$SAMPLES_LINK")" = "$bank_dir" ]; then
        published=$SAMPLES_LINK
    elif [ ! -e "$SAMPLES_LINK" ] || [ -L "$SAMPLES_LINK" ]; then
        if [ "$(rbp_environment_value RX3_SAMPLES_GENERATION)" = "$generation" ] &&
           [ "$(rbp_environment_value RX3_SAMPLES_DIR)" = "$SAMPLES_LINK" ] &&
           [ -L "$SAMPLES_LINK" ]; then
            samples_repoint_live_link "$bank_dir" || return 1
        else
            stage_runtime_symlink "$bank_dir" "$SAMPLES_LINK" || return 1
        fi
        published=$SAMPLES_LINK
    fi

    export RX3_SAMPLES_CONFIG="$published/settings.ini"
    SAMPLES_READY=1
    module_export RX3_SAMPLES_DIR "$published" "Sample pads"
    module_export RX3_SAMPLES_GENERATION "$generation" "Sample pads" || :
    say "Sample pads prepared: $count bank(s) at $SAMPLES_DIR"
}

samples_after_launch()
{
    [ "$SAMPLES_READY" = "1" ] || return 0
    say "SAMPLE: touch SAMPLES to use the pads; touch it again to return to STATUS; playback hardware validation pending"
    # What this build of the pads can do, so the computer can offer exactly
    # that rather than offering a setting a deck would ignore. Read back from
    # the session file the player leaves on the drive.
    say "SAMPLE pad modes: once hold loop latch"
    say "SAMPLE shift.silence: stops every pad"
}

register_prepare_hook samples_prepare
register_after_launch_hook samples_after_launch
