#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Runtime registration for the firmware 1.19 Beat Jump +/-32 patch.

register_patch 393376 '\310\212\267\356' '\310\212\260\356' guard_vcvt_f64_to_vabs_f32
register_patch 393380 '\010\213\070\356' '\010\172\170\356' guard_vadd_f64_to_vadd_f32
register_patch 393384 '\310\173\374\356' '\347\172\374\356' guard_vcvt_u32_f64_to_f32
register_patch 393600 '\000\212\262\356' '\302\124\240\343' negative_jump_-32.0f
register_patch 393604 '\301\124\240\343' '\020\132\010\356' negative_guard_32
register_patch 393612 '\000\212\262\356' '\102\124\240\343' positive_jump_+32.0f
register_patch 393616 '\020\132\030\356' '\020\132\010\356' positive_guard_32
register_patch 5016772 '\020\000\000\000' '\100\000\000\000' LED_threshold_16_to_64_half-beats
register_patch 5367248 '\362\023\000\000' '\003\024\000\000' PAD7_off_image_5106_to_5123
register_patch 5367224 '\363\023\000\000' '\004\024\000\000' PAD7_on_image_5107_to_5124
register_patch 5367188 '\364\023\000\000' '\003\024\000\000' PAD8_off_image_5108_to_5123
register_patch 5367164 '\365\023\000\000' '\004\024\000\000' PAD8_on_image_5109_to_5124

beatjump_32bars_report()
{
    say "Beat Jump pads 7 and 8: -32 and +32"
    say "The jog display remains at 8; its glyph is outside rbp."
}

register_report_hook beatjump_32bars_report
