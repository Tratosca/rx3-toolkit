#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Accent-insensitive browsing. The code lives in the performance core's shared
# object; this module only switches it on.

module_begin search-latin search_latin

SEARCH_LATIN_READY=0

search_latin_prepare()
{
    [ -r "$CORE_OBJECT" ] || {
        say "Accent folding disabled: the performance core is not selected"
        return 1
    }
    module_disabled_by_switch search-latin && return 0
    SEARCH_LATIN_READY=1
    module_export RX3_SEARCH_LATIN 1 "Accent folding"
    say "Accent folding prepared: browse queries are folded before the search"
}

search_latin_after_launch()
{
    [ "$SEARCH_LATIN_READY" = "1" ] || return 0
    say "SEARCH: typing a letter without its accent finds the track anyway"
}

register_prepare_hook search_latin_prepare
register_after_launch_hook search_latin_after_launch
