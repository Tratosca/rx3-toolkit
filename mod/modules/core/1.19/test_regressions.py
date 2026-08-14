#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Static guards for the performance core and the runtime orchestrator."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[3]
AUTOEXEC = (REPOSITORY / "mod/autoexec.sh").read_text()
MODULE_API = (REPOSITORY / "mod/lib/module-api.sh").read_text()
HOOK = (ROOT / "rx3_core_hook.c").read_text()
CORE_MODULE = (ROOT / "module.sh").read_text()
CORE_MANIFEST = (ROOT / "manifest.json").read_text()
FEATURE_API = (ROOT / "rx3_feature_api.h").read_text()
STEMS_PANEL = (
    REPOSITORY / "mod/modules/stems/1.19/rx3_stems_panel.h"
).read_text()
STEMS_FEATURE = (
    REPOSITORY / "mod/modules/stems/1.19/rx3_stems_feature.h"
).read_text()
KEYSHIFT_FEATURE = (
    REPOSITORY / "mod/modules/keyshift/1.19/rx3_keyshift_feature.h"
).read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "while IFS= read -r runtime_directory" in AUTOEXEC
    and "/mnt/iso/modules/index" in AUTOEXEC
    and "load_module" in AUTOEXEC,
    "autoexec must use the build's deterministic module index",
)
require(
    'MODULE_API=/mnt/iso/lib/module-api.sh' in AUTOEXEC
    and "module_begin" in MODULE_API
    and "register_lifecycle_hook" in MODULE_API
    and "escapes namespace" in MODULE_API,
    "runtime modules must declare an id and keep lifecycle hooks namespaced",
)
require(
    "register_patch" in MODULE_API and "write_words patched" in AUTOEXEC,
    "the runtime orchestrator must apply guarded module registrations",
)
require(
    "PATCH_OFFSETS" in AUTOEXEC
    and "modules share guarded patch offset" in MODULE_API
    and "a prepare hook failed; no guarded word was written" in AUTOEXEC,
    "module collisions and failed preparation must stop before executable writes",
)
# The beat jump tables and the decoder-sleep hook used to be asserted here.
# They belong to those modules, not to the core: see
# tests/test_module_consistency.py, which compares the offline and on-device
# tables word by word, and tests/test_decoder_sleep_patch.py.

# -- the core owns the binary, and only the binary ----------------------------

require(
    "register_prepare_hook core_prepare" in CORE_MODULE
    and "register_after_launch_hook core_after_launch" in CORE_MODULE
    and "librx3_core.so" in CORE_MODULE,
    "the core module must own the shared object's lifecycle",
)
require(
    'entry" = "/root/pdj/librx3_stems.so" ] && continue' in CORE_MODULE,
    "reinsertion must retire the pre-split preload entry",
)
require(
    "core_normalize_preload" in CORE_MODULE
    and 'entry=${pending%%:*}' in CORE_MODULE,
    "reinsertion must collapse duplicate core entries in LD_PRELOAD",
)
require(
    'RX3_KEYSHIFT' in HOOK and 'RX3_STEMS_DIR' in HOOK
    and "if (!configure_features())" in HOOK,
    "each feature must announce itself through its own module's environment",
)
require(
    "PAL_DRAW_TEXT  ((unsigned long)0x001d23e4)" in HOOK
    and "SOLVE_TOUCH    ((unsigned long)0x002dc104)" in HOOK,
    "the on-screen controls must use the guarded native rbp text and touch paths",
)
require(
    "stock_tab_backing" in HOOK and "draw_custom_tabs(render, image)" in HOOK
    and "x = x * 1280 / 4096" in HOOK and "y = y * 720 / 4096" in HOOK,
    "the tab strip must reuse the stock artwork and scale raw touch coordinates",
)
require(
    "TAB_IMAGE_KEY   0x1600u" in HOOK
    and "TAB_IMAGE_STEMS 0x1601u" in HOOK
    and "TAB_IMAGE_STATUS_NONE 0x1602u" in HOOK
    and "TAB_IMAGE_KEY_NONE 0x1603u" in HOOK
    and "extended private KEY/STEMS image table installed" in HOOK
    and "3452u" not in HOOK and "3460u" not in HOOK,
    "custom tabs must use private IDs, never live SOURCE colour resources",
)
for asset in (
    "key-selected.rgb565",
    "stems-selected.rgb565",
    "none-selected.rgb565",
    "status-none-selected.rgb565",
):
    require(
        (ROOT / "assets" / asset).stat().st_size == 18000,
        f"{asset} must be an exact 180x50 RGB565 bitmap",
    )
    require(asset in CORE_MANIFEST, f"{asset} must be packaged in autoexec")
require(
    "register_patch 1874220 '\\314\\065\\001\\343' "
    "'\\003\\066\\001\\343' image-table-private-ids"
        in CORE_MODULE
    and "STOCK_IMAGE_COUNT 0x15cdu" in HOOK
    and "EXTENDED_IMAGE_COUNT 0x1604u" in HOOK
    and "memcpy(table, stock_table, STOCK_IMAGE_COUNT * 44u);" in HOOK
    and "data_offset += relocation;" in HOOK
    and "*(uint8_t **)IMAGE_TABLE_POINTER = table;" in HOOK
    and "hooked_get_image_info" not in HOOK
    and "install_get_image_info_hook" not in HOOK
    and "memcpy(table + offset" not in HOOK
    and "0x0d7eu" not in HOOK,
    "private images must use a secondary table and a guarded pre-launch bound",
)
require(
    "Populate the private image records before their first DirectFB lookup" in HOOK
    and "if (!tab_assets_ready)\n        install_tab_assets();" in HOOK,
    "private tab payloads must be ready before DirectFB caches them",
)
require(
    "initial_performance_refresh_done" in HOOK
    and "initial native performance tabs refreshed" in HOOK
    and "text_template_ready && stock_tab_backing_ready" in HOOK
    and "key_tab_glyph && stems_tab_glyph && stock_status_glyph" in HOOK
    and "REFRESH_GLYPH must run from rbp's UI rendering path" in HOOK
    and HOOK.count("refresh_initial_performance_tabs_if_ready();") == 4
    and "Re-check on every ordinary image" in HOOK,
    "bootstrap ZOOM/GRID controls must receive one native redraw after all "
    "tab dependencies are captured",
)
require(
    "/root/pdj/rx3-key-selected.rgb565" in HOOK
    and "core_install_asset" in CORE_MODULE
    and "custom tab assets cannot be installed" in CORE_MODULE,
    "tab assets must survive the autoexec ISO unmount before rbp starts",
)
require(
    "if (overlay_panel && tab_assets_ready)" in HOOK
    and "set_u32(neutral, 0x44, TAB_IMAGE_STATUS_NONE);" in HOOK,
    "STATUS and BEAT FX must both render inactive under a custom panel",
)
require(
    "stock_status_glyph = image;" in HOOK
    and "key_tab_glyph, stems_tab_glyph, stock_status_glyph" in HOOK,
    "selecting KEY/STEMS must invalidate the previously drawn stock tab row",
)
beatfx_setter = HOOK.split("static void hooked_set_beatfx_selected", 1)[1].split(
    "static void hooked_solve_touch", 1
)[0]
require(
    beatfx_setter.index("overlay_panel = 0;")
    < beatfx_setter.index("if (leaving_custom_panel && selected)")
    < beatfx_setter.index("refresh_performance_ui();"),
    "STATUS/BEAT FX must redraw both performance parents after leaving a "
    "custom panel",
)
require(
    "usleep(60000u);" in HOOK
    and HOOK.count("usleep(30000u);") == 1
    and "The native state-7 rebuild paints Aqua/Default/Yellow" in HOOK
    and "original_set_beatfx_selected(0);" in beatfx_setter
    and "finish_beatfx_reselect" in beatfx_setter
    and "capture_beatfx_left_glyph" not in HOOK,
    "custom-to-Beat-FX must create a two-cycle native state edge without "
    "refreshing glyphs shared by HOT CUES and pad modes",
)
require(
    "if (beatfx_reselect_pending) {" in beatfx_setter
    and "native Beat FX rebuild ignored setter = " in beatfx_setter
    and beatfx_setter.index("if (beatfx_reselect_pending) {")
        < beatfx_setter.index("__sync_add_and_fetch(")
    and "beatfx_reselect_pending = 1u;" in beatfx_setter
    and "Ui_CycleTask can echo the provisional STATUS value" in beatfx_setter,
    "reentrant STATUS/BEAT FX stores must not cancel the pending native edge",
)
require(
    "Only a hardware pad-mode selector restores STATUS" in HOOK
    and "restore_status_after_pad_mode" in HOOK
    and "pad mode selected: custom panel returned to STATUS" in HOOK,
    "custom controls must stay open; hardware pad-mode keys must restore STATUS",
)
require(
    "ON_KEY_HOT_CUE ((unsigned long)0x003030ec)" in HOOK
    and "ON_KEY_BEAT_LOOP ((unsigned long)0x003031cc)" in HOOK
    and "ON_KEY_SLIP_LOOP ((unsigned long)0x00303238)" in HOOK
    and "ON_KEY_BEAT_JUMP ((unsigned long)0x00303294)" in HOOK
    and HOOK.count("restore_status_after_pad_mode();") == 4,
    "HOT CUE, BEAT LOOP, SLIP LOOP and BEAT JUMP must each restore STATUS",
)
require(
    "BEATFX_XPAD_CTOR ((unsigned long)0x0035b0f8)" in HOOK
    and "stock_touch_geometry" in HOOK and "captured_native_touch" in HOOK,
    "on-screen controls must capture, repurpose and restore native touch areas",
)
require(
    'FRAMEBUFFER_FILE "/dev/fb0"' not in HOOK
    and "framebuffer_draw_tabs" not in HOOK,
    "the tabs must stay in rbp's native renderer",
)
require(
    "#define BLINK_PERIOD_MS 500u" in HOOK
    and "blink_origin_ms()" in HOOK
    and "return blink_phase_is_on();" in STEMS_PANEL,
    "the loading indication must be one second on, one second off, and the "
    "on-screen toggles must share the pads' blink origin",
)
require(
    'text_patched[] = {\'P\',\'A\',\'T\',\'C\',\'H\',\'E\',\'D\',0}' in HOOK,
    "the visible patch badge must contain only PATCHED",
)
require(
    'register_ready_file "$CORE_READY"' in CORE_MODULE
    and "for ready_file in $RBP_READY_FILES" in AUTOEXEC
    and 'echo applying > /tmp/rx3-patch.state' in AUTOEXEC
    and 'echo patched > /tmp/rx3-patch.state' in AUTOEXEC,
    "autoexec must expose lifecycle and support readiness from several modules",
)
require(
    '#include "../../keyshift/1.19/rx3_keyshift_feature.h"' in HOOK
    and "rx3_keyshift_install();" in KEYSHIFT_FEATURE
    and "publish_pitch_percent" not in HOOK
    and "rx3_shifter_process" not in HOOK,
    "the core must delegate key shift to its module, not implement it",
)
require(
    '#include "rx3_feature_api.h"' in HOOK
    and "struct rx3_panel_feature" in FEATURE_API
    and "panel_for_id(overlay_panel)" in HOOK
    and "panel->activate(deck, control);" in HOOK,
    "rendering and native touch must dispatch through the feature panel contract",
)
require(
    "struct rx3_runtime_feature" in FEATURE_API
    and "static unsigned int install_features" in HOOK
    and "optional feature disabled: hook guard rejected" in HOOK
    and "feature->remove();" in HOOK,
    "an optional hook failure must disable only its owning feature",
)
require(
    "stems_feature_install" in HOOK
    and "keyshift_feature_install" in HOOK
    and "runtime_features[i].active" in HOOK,
    "feature-only hooks must not be installed when that feature is absent",
)
require(
    "track_will_load" in FEATURE_API
    and "track_did_load" in FEATURE_API
    and "audio_started" in FEATURE_API,
    "feature lifecycle events must cross one explicit core contract",
)
load_body = HOOK.split("static int hooked_load", 1)[1].split(
    "\nstatic unsigned int configure_features", 1
)[0]
require(
    "runtime_features[i].track_will_load" in load_body
    and "runtime_features[i].track_did_load" in load_body
    and "rx3_keyshift_reload" not in load_body
    and "sidecar_path_for_track" not in load_body,
    "the shared load hook must dispatch events without feature logic",
)
require(
    "static int hooked_on_key_pad" not in HOOK
    and "static void hooked_check_slip_led" not in HOOK
    and "static int hooked_on_key_pad" in STEMS_FEATURE
    and "static void hooked_check_slip_led" in STEMS_FEATURE,
    "stems must own its optional pad and LED hooks",
)

print("Core regression guards: OK")
