#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
module_begin browse-columns browse_columns
browse_columns_prepare()
{
    [ -r "$CORE_OBJECT" ] || return 1
    module_disabled_by_switch browse-columns && return 0
    browse_field=$(module_setting browse-columns.column 13)
    case "$browse_field" in
        7|11|13|15) ;; *) browse_field=13 ;;
    esac
    module_export RX3_BROWSE_COLUMNS 1 "Browse Columns"
    module_export RX3_BROWSE_FIELD "$browse_field" "Browse third column"
    return 0
}
register_prepare_hook browse_columns_prepare
