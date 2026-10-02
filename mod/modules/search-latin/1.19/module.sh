#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Accent-insensitive SEARCH for XDJ-RX3 firmware 1.19.
# Reproduces the hardware-validated V14 shape() Latin-1 folding patch.

module_begin search-latin search_latin
register_patch 1426684 '\030\320\115\342' '\060\100\055\351' shape_latin_word_00
register_patch 1426688 '\014\000\215\345' '\134\100\217\342' shape_latin_word_01
register_patch 1426692 '\010\020\215\345' '\000\060\240\343' shape_latin_word_02
register_patch 1426696 '\004\040\215\345' '\002\000\123\341' shape_latin_word_03
register_patch 1426700 '\000\060\240\343' '\022\000\000\052' shape_latin_word_04
register_patch 1426704 '\024\060\215\345' '\203\300\201\340' shape_latin_word_05
register_patch 1426708 '\000\060\240\343' '\260\120\334\341' shape_latin_word_06
register_patch 1426712 '\020\060\215\345' '\000\000\125\343' shape_latin_word_07
register_patch 1426716 '\014\060\235\345' '\016\000\000\012' shape_latin_word_08
register_patch 1426720 '\000\000\123\343' '\141\000\125\343' shape_latin_word_09
register_patch 1426724 '\002\000\000\012' '\002\000\000\072' shape_latin_word_10
register_patch 1426728 '\010\060\235\345' '\172\000\125\343' shape_latin_word_11
register_patch 1426732 '\000\000\123\343' '\040\120\105\222' shape_latin_word_12
register_patch 1426736 '\001\000\000\032' '\005\000\000\232' shape_latin_word_13
register_patch 1426740 '\020\060\235\345' '\300\000\125\343' shape_latin_word_14
register_patch 1426744 '\073\000\000\352' '\003\000\000\072' shape_latin_word_15
register_patch 1426748 '\000\060\240\343' '\377\000\125\343' shape_latin_word_16
register_patch 1426752 '\024\060\215\345' '\001\000\000\212' shape_latin_word_17
register_patch 1426756 '\061\000\000\352' '\300\120\105\342' shape_latin_word_18
register_patch 1426760 '\024\060\235\345' '\005\120\324\347' shape_latin_word_19
register_patch 1426764 '\203\060\240\341' '\203\300\200\340' shape_latin_word_20
register_patch 1426768 '\010\040\235\345' '\260\120\314\341' shape_latin_word_21
register_patch 1426772 '\003\060\202\340' '\001\060\203\342' shape_latin_word_22
register_patch 1426776 '\260\060\323\341' '\352\377\377\352' shape_latin_word_23
register_patch 1426780 '\000\000\123\343' '\003\000\240\341' shape_latin_word_24
register_patch 1426784 '\057\000\000\012' '\060\200\275\350' shape_latin_word_25
register_patch 1426788 '\024\060\235\345' '\101\101\101\101' shape_latin_word_26
register_patch 1426792 '\203\060\240\341' '\101\101\101\103' shape_latin_word_27
register_patch 1426796 '\010\040\235\345' '\105\105\105\105' shape_latin_word_28
register_patch 1426800 '\003\060\202\340' '\111\111\111\111' shape_latin_word_29
register_patch 1426804 '\260\060\323\341' '\104\116\117\117' shape_latin_word_30
register_patch 1426808 '\140\000\123\343' '\117\117\117\327' shape_latin_word_31
register_patch 1426812 '\023\000\000\232' '\117\125\125\125' shape_latin_word_32
register_patch 1426816 '\024\060\235\345' '\125\131\124\123' shape_latin_word_33
register_patch 1426820 '\203\060\240\341' '\101\101\101\101' shape_latin_word_34
register_patch 1426824 '\010\040\235\345' '\101\101\101\103' shape_latin_word_35
register_patch 1426828 '\003\060\202\340' '\105\105\105\105' shape_latin_word_36
register_patch 1426832 '\260\060\323\341' '\111\111\111\111' shape_latin_word_37
register_patch 1426836 '\172\000\123\343' '\104\116\117\117' shape_latin_word_38
register_patch 1426840 '\014\000\000\212' '\117\117\117\367' shape_latin_word_39
register_patch 1426844 '\024\060\235\345' '\117\125\125\125' shape_latin_word_40
register_patch 1426848 '\203\060\240\341' '\125\131\124\131' shape_latin_word_41
register_patch 1426852 '\014\040\235\345' '\000\000\240\341' shape_latin_word_42
register_patch 1426856 '\003\060\202\340' '\000\000\240\341' shape_latin_word_43
register_patch 1426860 '\024\040\235\345' '\000\000\240\341' shape_latin_word_44
register_patch 1426864 '\202\040\240\341' '\000\000\240\341' shape_latin_word_45
register_patch 1426868 '\010\020\235\345' '\000\000\240\341' shape_latin_word_46
register_patch 1426872 '\002\040\201\340' '\000\000\240\341' shape_latin_word_47
register_patch 1426876 '\260\040\322\341' '\000\000\240\341' shape_latin_word_48
register_patch 1426880 '\040\040\102\342' '\000\000\240\341' shape_latin_word_49
register_patch 1426884 '\162\040\377\346' '\000\000\240\341' shape_latin_word_50
register_patch 1426888 '\260\040\303\341' '\000\000\240\341' shape_latin_word_51
register_patch 1426892 '\011\000\000\352' '\000\000\240\341' shape_latin_word_52
register_patch 1426896 '\024\060\235\345' '\000\000\240\341' shape_latin_word_53
register_patch 1426900 '\203\060\240\341' '\000\000\240\341' shape_latin_word_54
register_patch 1426904 '\014\040\235\345' '\000\000\240\341' shape_latin_word_55
register_patch 1426908 '\003\060\202\340' '\000\000\240\341' shape_latin_word_56
register_patch 1426912 '\024\040\235\345' '\000\000\240\341' shape_latin_word_57
register_patch 1426916 '\202\040\240\341' '\000\000\240\341' shape_latin_word_58
register_patch 1426920 '\010\020\235\345' '\000\000\240\341' shape_latin_word_59
register_patch 1426924 '\002\040\201\340' '\000\000\240\341' shape_latin_word_60
register_patch 1426928 '\260\040\322\341' '\000\000\240\341' shape_latin_word_61
register_patch 1426932 '\260\040\303\341' '\000\000\240\341' shape_latin_word_62
register_patch 1426936 '\020\060\235\345' '\000\000\240\341' shape_latin_word_63
register_patch 1426940 '\001\060\203\342' '\000\000\240\341' shape_latin_word_64
register_patch 1426944 '\020\060\215\345' '\000\000\240\341' shape_latin_word_65
register_patch 1426948 '\024\060\235\345' '\000\000\240\341' shape_latin_word_66
register_patch 1426952 '\001\060\203\342' '\000\000\240\341' shape_latin_word_67
register_patch 1426956 '\024\060\215\345' '\000\000\240\341' shape_latin_word_68
register_patch 1426960 '\024\040\235\345' '\000\000\240\341' shape_latin_word_69
register_patch 1426964 '\004\060\235\345' '\000\000\240\341' shape_latin_word_70
register_patch 1426968 '\003\000\122\341' '\000\000\240\341' shape_latin_word_71
register_patch 1426972 '\311\377\377\072' '\000\000\240\341' shape_latin_word_72
register_patch 1426976 '\000\000\000\352' '\000\000\240\341' shape_latin_word_73
register_patch 1426984 '\020\060\235\345' '\000\000\240\341' shape_latin_word_74
register_patch 1426988 '\003\000\240\341' '\000\000\240\341' shape_latin_word_75
register_patch 1426992 '\030\320\215\342' '\000\000\240\341' shape_latin_word_76
register_patch 1426996 '\036\377\057\341' '\000\000\240\341' shape_latin_word_77

search_latin_report()
{
    say "SEARCH ignores common Latin accents and Ñ (NINO matches NIÑO)."
    say "Displayed track metadata is unchanged."
}

register_report_hook search_latin_report
