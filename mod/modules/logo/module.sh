#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# On-screen logo. Installs the artwork where the performance core can find it:
# the wordmark in the middle of the performance screen, which replaces the
# stock one. The artwork carries its own size in a header, so it is not tied to
# the stock 492x70, and the core centres whatever it is given. DARK and LIGHT
# have separate slots; a drive carrying only the dark one shows it under both
# themes, which is legible.
#
# Volatile and flash-free: everything goes to the RAM copy of /root/pdj, never
# to NAND, and the boot splash is untouched.

module_begin logo logo

LOGO_READY=0
LOGO_SLOTS=0
LOGO_CHANGED=0
LOGO_FILES="
rx3-logo-main.rgb565:/root/pdj/rx3-logo-main.rgb565
rx3-logo-main-light.rgb565:/root/pdj/rx3-logo-main-light.rgb565
"

logo_install_file()
{
    logo_from=$1
    logo_to=$2
    logo_tmp=$logo_to.$$
    [ -r "$logo_from" ] || return 1
    # The core reads the artwork once, in its constructor. New art on the disk
    # with an old rbp still running means the player keeps drawing the previous
    # logo, and if the two are different sizes it reads the new file with the
    # old dimensions and draws a corner of it. So a changed file is a reason to
    # restart, exactly as a changed core object is.
    cmp -s "$logo_from" "$logo_to" 2>/dev/null || LOGO_CHANGED=1
    if cp "$logo_from" "$logo_tmp" 2>/dev/null && chmod 644 "$logo_tmp" &&
       mv -f "$logo_tmp" "$logo_to" 2>/dev/null; then
        return 0
    fi
    rm -f "$logo_tmp"
    return 1
}

logo_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Logo disabled: the performance core is not selected"
        return 1
    }
    module_disabled_by_switch logo && return 0

    for logo_pair in $LOGO_FILES; do
        if logo_install_file "/mnt/iso/modules/logo/${logo_pair%%:*}" \
                             "${logo_pair#*:}"; then
            LOGO_SLOTS=$((LOGO_SLOTS+1))
        fi
    done
    [ "$LOGO_SLOTS" -gt 0 ] || {
        say "Logo disabled: no wordmark artwork in the image"
        return 1
    }

    LOGO_READY=1
    # The core reads the artwork in its constructor, so artwork that changed on
    # this drive is a second reason to restart even when the setting itself has
    # not moved. Without it the player keeps drawing the previous logo, and if
    # the two differ in size it reads the new file with the old dimensions.
    if ! module_export RX3_LOGO 1 Logo && [ "$LOGO_CHANGED" = "1" ]; then
        say "Logo needs a restart: the artwork on this drive is not the one"
        say "the running player loaded"
        request_rbp_restart
    fi
    say "Logo prepared: main screen wordmark ($LOGO_SLOTS/2 slots)"
}

logo_after_launch()
{
    [ "$LOGO_READY" = "1" ] || return 0
    say "Main screen wordmark replaced"
    [ "$LOGO_SLOTS" = "2" ] && say "DARK and LIGHT artwork both installed"
}

register_prepare_hook logo_prepare
register_after_launch_hook logo_after_launch
