#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
module_begin key-match key_match
key_match_prepare()
{
    [ -r "$CORE_OBJECT" ] || return 1
    module_disabled_by_switch key-match && return 0
    key_match_rules=2
    if [ -r /mnt/iso/modules/key-match/rules.txt ]; then
        read -r key_match_rules < /mnt/iso/modules/key-match/rules.txt
    fi
    case "$key_match_rules" in
        [0-9]|1[0-5]) ;; *) key_match_rules=2 ;;
    esac
    key_match_rules=$((key_match_rules & 14))
    module_export RX3_KEY_MATCH 1 "Key Match"
    module_export RX3_KEY_MATCH_RULES "$key_match_rules" "Key Match rules"
    return 0
}
register_prepare_hook key_match_prepare
