# SPDX-License-Identifier: MPL-2.0
"""Each feature module builds, links and runs against the public API alone."""
import json
import pathlib
import tempfile
import unittest

from app.runtime.build import compile_arm_hook
from tests import test_framework
from tests.test_hook_symbols import ALLOWED, undefined_symbols

MODULES = test_framework.MODULES
EXTRACTED = ('logo/rx3_logo_module.c', 'theme-white/rx3_theme_module.c',
             'samples/rx3_samples_module.c', 'stems/rx3_stems_module.c')

# Services a module may be handed, as mocks that record what they are asked.
MOCKS = r'''
#include "core/api/rx3_module_api.h"
static unsigned installs, removals, rows, unrows, pads, keys, leds, modes, unregisters;
static unsigned masters, streams, releases, mixes, waves, withdrawals, fail_at, calls;
static const struct rx3_pad_row *row;
static rx3_pad_handler pad;
static rx3_key_handler key;
static rx3_deck_stream_fn stream;
static rx3_master_fn master;
static struct rx3_mix_state (*mix)(unsigned);
static unsigned (*wave)(unsigned, unsigned, unsigned, uint8_t *, unsigned);
static int step(void) { return ++calls != fail_at; }
static int register_row(const struct rx3_pad_row *r) { if (!step()) return 0; rows++; row = r; return 1; }
static void unregister_row(const struct rx3_pad_row *r) { if (r == row) row = 0; unrows++; }
static int register_pad(const void *o, unsigned p, rx3_pad_handler h) { assert(o && h && p); if (!step()) return 0; pads++; pad = h; return 1; }
static int register_key(const void *o, unsigned p, rx3_key_handler h) { assert(o && h && p); if (!step()) return 0; keys++; key = h; return 1; }
static rx3_light_fn lights[2];
static int register_lights(const void *o, unsigned r, rx3_light_fn f) { assert(o && f && r <= 1); if (!step()) return 0; leds++; lights[r] = f; return 1; }
static int blink_on(void) { return 1; }
static void blink_restart(void) {}
static int claim_modes(const void *o) { assert(o); if (!step()) return 0; modes++; return 1; }
static void unregister_owner(const void *o) { assert(o); unregisters++; pad = 0; key = 0; }
static int shift_held(unsigned c) { (void)c; return 0; }
static int claim_stream(const void *o, rx3_deck_stream_fn f) { assert(o && f); if (!step()) return 0; streams++; stream = f; return 1; }
static void release_stream(const void *o) { assert(o); releases++; stream = 0; }
static int claim_master(const void *o, rx3_master_fn f) { assert(o && f); if (!step()) return 0; masters++; master = f; return 1; }
static void release_master(const void *o) { assert(o); releases++; master = 0; }
static int provide_mix(struct rx3_mix_state (*f)(unsigned)) { if (!step()) return 0; mixes++; mix = f; return 1; }
static void withdraw_mix(struct rx3_mix_state (*f)(unsigned)) { if (f == mix) mix = 0; withdrawals++; }
static int provide_wave(unsigned (*f)(unsigned, unsigned, unsigned, uint8_t *, unsigned)) { if (!step()) return 0; waves++; wave = f; return 1; }
static void withdraw_wave(unsigned (*f)(unsigned, unsigned, unsigned, uint8_t *, unsigned)) { if (f == wave) wave = 0; withdrawals++; }
static unsigned jobs, loader_releases;
static int loader_claim(const void *o) { assert(o); return step(); }
/* Jobs run where they are submitted: the order a worker would give them. */
static int loader_submit(const void *o, const struct rx3_load_job *j) {
    assert(o && j && j->run); if (!step()) return 0; jobs++; j->run(j->context); return 1;
}
static int loader_stopping(const void *o) { (void)o; return 0; }
static void loader_release(const void *o) { assert(o); loader_releases++; }
static const struct rx3_loader_service loader = {loader_claim, loader_submit, loader_stopping, loader_release};
static void quiet(const char *s) { assert(s); }
static void quiet_number(const char *s, unsigned long n) { (void)n; assert(s); }
static unsigned long plenty(void) { return 1u << 30; }
static int mock_reserve(const void *o, unsigned long bytes, unsigned long floor_kb) {
    (void)o; unsigned long kb = bytes / 1024u + (bytes % 1024u != 0u), have = plenty();
    return !floor_kb || (have > floor_kb && have - floor_kb >= kb);
}
static void mock_move(const void *o, unsigned long b) { (void)o; (void)b; }
static unsigned long mock_held(void) { return 0; }
static const struct rx3_memory_service memory_mock={mock_reserve,mock_move,mock_move,mock_move,plenty,mock_held};
static const struct rx3_panel_service panels = {.register_row = register_row, .unregister_row = unregister_row};
static const struct rx3_input_service input = {.register_pad = register_pad, .register_key = register_key,
    .register_lights = register_lights, .claim_mode_keys = claim_modes,
    .unregister_owner = unregister_owner, .shift_held = shift_held,
    .blink_on = blink_on, .blink_restart = blink_restart};
static const struct rx3_audio_service audio = {claim_stream, release_stream, claim_master, release_master};
static const struct rx3_services services = {.log_line = quiet, .log_number = quiet_number,
    .panels = &panels, .input = &input, .audio = &audio, .memory = &memory_mock,
    .provide_mix = provide_mix, .withdraw_mix = withdraw_mix,
    .provide_waveform = provide_wave, .withdraw_waveform = withdraw_wave, .loader = &loader};
'''


class ModuleUnitTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_every_module_unit_imports_libc_only(self):
        """No core or sibling symbol can be reached: each unit links alone."""
        manifest = json.loads((MODULES / 'core/manifest.json').read_text())
        units = [unit for unit in manifest['arm_hook']['sources'] if not unit.startswith('core/')]
        self.assertTrue(set(EXTRACTED) <= set(units))
        with tempfile.TemporaryDirectory() as temporary:
            for unit in units:
                with self.subTest(unit=unit):
                    output = pathlib.Path(temporary) / (pathlib.Path(unit).stem + '.so')
                    compile_arm_hook(MODULES / unit, output)
                    self.assertEqual(undefined_symbols(output) - ALLOWED, set())

    def test_logo_and_theme_link_against_mock_services(self):
        # Their start reads firmware addresses, so the host checks the descriptor
        # and the link; their policies are exercised by their own tests.
        self.run_units(MOCKS + r'''
extern const struct rx3_module rx3_logo_module, rx3_theme_module;
int main(void) {
    const struct rx3_module *modules[] = {&rx3_logo_module, &rx3_theme_module};
    for (unsigned i = 0; i < 2; i++) {
        assert(modules[i]->version == RX3_MODULE_API_VERSION);
        assert(modules[i]->size == sizeof(struct rx3_module));
        assert(!modules[i]->configured());
        modules[i]->stop(); /* never started: touches nothing */
    }
    (void)services;
    return 0;
}
''', ['logo/rx3_logo_module.c', 'theme-white/rx3_theme_module.c'],
            ['-Wno-unused-function', '-Wno-unused-variable', '-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE'])

    def test_samples_runs_on_mock_services_and_cleans_partial_starts(self):
        self.run_units(MOCKS + r'''
extern const struct rx3_module rx3_samples_module;
int main(void) {
    setenv("RX3_SAMPLES_DIR", "/nonexistent-samples", 1);
    assert(rx3_samples_module.configured());
    assert(rx3_samples_module.start(&services));
    assert(modes == 1 && masters == 1 && pads == 1 && keys == 1 && leds == 1 && rows == 1);
    assert(row && row->panel_id == 3 && row->activate);
    /* The pads belong to the player until the panel is shown. */
    struct rx3_pad_event press = {0x4117, 0, 1, 0, 0};
    assert(!pad(&press));
    struct rx3_light light = {RX3_LIGHT_NATIVE, 0};
    lights[RX3_LIGHTS_PADS](0, 0, &light); assert(light.state == RX3_LIGHT_NATIVE);
    row->activate(1); assert(pad(&press));
    /* Its pads are lit in the bank colours, SHIFT red; no LED ID in sight. */
    lights[RX3_LIGHTS_PADS](RX3_NO_DECK, RX3_LIGHT_SHIFT, &light);
    assert(light.state == RX3_LIGHT_ON && light.rgb == 0xff0000u);
    lights[RX3_LIGHTS_PADS](0, 0, &light); assert(light.state == RX3_LIGHT_DIM && light.rgb == 0xff2828u);
    row->activate(0); assert(!pad(&press));
    struct rx3_key_event shift = {RX3_KEY_SHIFT, 0, 1};
    assert(!key(&shift)); /* SHIFT is watched, never taken */
    struct rx3_stereo bus[4] = {{0, 0}};
    master(bus, 4);
    rx3_samples_module.stop();
    assert(!row && releases == 1 && unregisters == 1);
    /* Each required service refused in turn: start fails, stop cleans up.
       The pad LEDs (the fifth request) stay optional, as they always were:
       the bank plays without its colours. */
    assert(jobs == 1 && loader_releases == 1);
    for (unsigned at = 1; at <= 8; at++) {
        calls = 0; fail_at = at; releases = unregisters = 0;
        assert(!rx3_samples_module.start(&services) == (at != 5));
        rx3_samples_module.stop();
        assert(!row && releases == 1 && unregisters == 1);
    }
    return 0;
}
''', ['samples/rx3_samples_module.c'],
            ['-Wno-unused-function', '-Wno-unused-variable', '-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE'])

    def test_stems_runs_on_mock_services_and_cleans_partial_starts(self):
        self.run_units(MOCKS + r'''
extern const struct rx3_module rx3_stems_module;
int main(void) {
    setenv("RX3_STEMS_DIR", "/nonexistent-stems", 1);
    assert(rx3_stems_module.configured());
    assert(rx3_stems_module.start(&services));
    assert(streams == 1 && pads == 1 && leds == 1 && mixes == 1 && waves == 1 && rows == 1);
    assert(row && row->panel_id == 2);
    /* No stem files: the deck stays stock, its pads stay native. */
    rx3_stems_module.track_will_load(0, (void *)1, "/usb/Contents/track.wav");
    rx3_stems_module.track_did_load(0, (void *)1, "/usb/Contents/track.wav");
    struct rx3_mix_state state = mix(0);
    assert(!state.available && !state.ready);
    struct rx3_pad_event press = {0x411b, 0, 1, 0, 2};
    assert(!pad(&press));
    struct rx3_stereo out[2] = {{1, -1}, {1, -1}};
    stream(0, (void *)1, 0, out, 2);
    assert(out[0].left == 1 && out[1].right == -1);
    rx3_stems_module.stop();
    assert(!row && !mix && !wave && releases == 1 && unregisters == 1);
    assert(loader_releases == 1);
    for (unsigned at = 1; at <= 7; at++) {
        calls = 0; fail_at = at; releases = unregisters = 0;
        assert(!rx3_stems_module.start(&services));
        rx3_stems_module.stop();
        assert(!row && !mix && !wave && releases == 1 && unregisters == 1);
    }
    return 0;
}
''', ['stems/rx3_stems_module.c'],
            ['-Wno-unused-function', '-Wno-unused-variable', '-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE'])


if __name__ == '__main__':
    unittest.main()
