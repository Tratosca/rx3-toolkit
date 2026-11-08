# SPDX-License-Identifier: MPL-2.0
"""BEAT FX frequency bands: keys, LEDs and the band split, against fake services."""
import unittest

from tests import test_framework

HARNESS = r'''
#include <math.h>
#include "beatfx-eq/rx3_beatfx_eq_module.c"
static rx3_key_handler key_handler; static rx3_light_fn mixer_lights;
static const struct rx3_beat_fx_client *fx; static unsigned refuse, released, unregistered;
static int reg_key(const void *o, unsigned p, rx3_key_handler h) { (void)o; (void)p; key_handler = h; return refuse != 1; }
static int reg_lights(const void *o, unsigned r, rx3_light_fn f) {
    (void)o; assert(r == RX3_LIGHTS_MIXER); mixer_lights = f; return refuse != 2;
}
static void unreg(const void *o) { (void)o; unregistered++; key_handler = 0; mixer_lights = 0; }
static int claim(const void *o, const struct rx3_beat_fx_client *c) { (void)o; fx = c; return refuse != 3; }
static void release(const void *o) { (void)o; released++; fx = 0; }
static const struct rx3_input_service fake_input = {.register_key = reg_key,
    .register_lights = reg_lights, .unregister_owner = unreg};
static const struct rx3_audio_service fake_audio = {.claim_beat_fx = claim, .release_beat_fx = release};
static const struct rx3_services services = {.input = &fake_input, .audio = &fake_audio};

static int press(unsigned key, unsigned channel) {
    struct rx3_key_event e = {key, 0, channel}; int a = key_handler(&e);
    e.operation = 2; int b = key_handler(&e); assert(a == b); return a;
}
static unsigned lit(unsigned control) {
    struct rx3_light l = {RX3_LIGHT_NATIVE, 0}; mixer_lights(RX3_NO_DECK, control, &l); return l.state;
}
/* The effect under test: kills its input, so only the dry bands are heard. */
static void killer(struct rx3_stereo *b, unsigned n) { for (unsigned i = 0; i < n; i++) b[i].left = b[i].right = 0; }
#define BLOCK 256u
#define BLOCKS 400u
/* Steady-state peak of a sine through send, the effect and ret. */
static float through(double hz, void (*effect)(struct rx3_stereo *, unsigned)) {
    static struct rx3_stereo b[BLOCK]; float peak = 0; unsigned t = 0;
    for (unsigned k = 0; k < BLOCKS; k++) {
        for (unsigned i = 0; i < BLOCK; i++, t++) b[i].left = b[i].right = (float)sin(2 * M_PI * hz * t / 44100.0);
        fx->send(b, BLOCK); if (effect) effect(b, BLOCK); fx->ret(b, BLOCK);
        if (k > BLOCKS / 2) for (unsigned i = 0; i < BLOCK; i++) if (fabsf(b[i].left) > peak) peak = fabsf(b[i].left);
    }
    return peak;
}
'''


class BeatFxEqTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_keys_lights_and_start_failure(self):
        self.run_units(HARNESS + r'''
int main(void) {
    setenv("RX3_BEATFX_EQ", "1", 1); assert(rx3_beatfx_eq_module.configured());
    setenv("RX3_BEATFX_EQ", "11", 1); assert(!rx3_beatfx_eq_module.configured());
    /* A refused service undoes the rest. */
    for (refuse = 1; refuse <= 3; refuse++) {
        assert(!rx3_beatfx_eq_module.start(&services));
        assert(!input && !audio);
    }
    refuse = 0; unregistered = released = 0;
    assert(rx3_beatfx_eq_module.start(&services));
    /* All three lit at start; NOISE, CRUSH, FILTER stay native. */
    for (unsigned c = 0; c < 3; c++) assert(lit(c) == RX3_LIGHT_ON);
    for (unsigned c = 3; c < 6; c++) assert(lit(c) == RX3_LIGHT_NATIVE);
    /* Channel 1 toggles, channel 2 is the same press: both consumed. */
    assert(press(RX3_KEY_COLOR_FX_SPACE, 1) && press(RX3_KEY_COLOR_FX_SPACE, 2));
    assert(lit(RX3_LIGHT_COLOR_FX_SPACE) == RX3_LIGHT_OFF && lit(RX3_LIGHT_COLOR_FX_DUB_ECHO) == RX3_LIGHT_ON);
    assert(press(RX3_KEY_COLOR_FX_SWEEP, 1) && press(RX3_KEY_COLOR_FX_SWEEP, 2));
    assert(bands == BAND_MID);
    assert(press(RX3_KEY_COLOR_FX_SPACE, 1) && press(RX3_KEY_COLOR_FX_SPACE, 2) && bands == (BAND_LOW | BAND_MID));
    /* Other COLOR FX keys reach the player. */
    assert(!press(0x50a4u, 1) && !press(0x50a6u, 1));
    rx3_beatfx_eq_module.stop(); assert(unregistered == 1 && released == 1);
    return 0;
}
''', [], ['-Wno-unused-function'])

    def test_all_bands_lit_is_the_stock_effect_exactly(self):
        self.run_units(HARNESS + r'''
static void doubler(struct rx3_stereo *b, unsigned n) { for (unsigned i = 0; i < n; i++) b[i].left *= 2; }
int main(void) {
    assert(rx3_beatfx_eq_module.start(&services));
    struct rx3_stereo b[64], r[64];
    for (unsigned k = 0; k < 10; k++) {
        for (unsigned i = 0; i < 64; i++) b[i].left = b[i].right = r[i].left = r[i].right = (float)sin(i * 0.37 + k);
        memcpy(r, b, sizeof(b)); fx->capture(r, 64);
        assert(!memcmp(r, b, sizeof(b)));
        fx->send(b, 64); doubler(b, 64); fx->ret(b, 64);
        for (unsigned i = 0; i < 64; i++) assert(b[i].left == 2 * (float)sin(i * 0.37 + k) && b[i].right == (float)sin(i * 0.37 + k));
    }
    return 0;
}
''', [], ['-Wno-unused-function'])

    def test_a_dark_band_bypasses_the_effect(self):
        self.run_units(HARNESS + r'''
int main(void) {
    assert(rx3_beatfx_eq_module.start(&services));
    /* An effect that changes nothing: every combination sums back flat. */
    for (unsigned mask = 0; mask < 8; mask++) {
        bands = mask;
        for (double hz = 40; hz < 16000; hz *= 3.1) {
            float peak = through(hz, 0);
            assert(peak > 0.99f && peak < 1.01f);
        }
    }
    /* With the effect killing its input, only the dark bands are left. */
    bands = BAND_MID | BAND_HIGH;  /* SPACE dark: LOW stays dry */
    assert(through(50, killer) > 0.95f && through(1000, killer) < 0.05f && through(12000, killer) < 0.01f);
    bands = BAND_LOW | BAND_HIGH;  /* DUB ECHO dark: MID stays dry */
    assert(through(50, killer) < 0.05f && through(1150, killer) > 0.9f && through(16000, killer) < 0.05f);
    bands = BAND_LOW | BAND_MID;   /* SWEEP dark: HIGH stays dry */
    assert(through(50, killer) < 0.01f && through(1000, killer) < 0.05f && through(15000, killer) > 0.95f);
    bands = BAND_ALL;
    assert(through(1000, killer) == 0.0f);
    /* The Roll pre-capture receives the same split as the effect. */
    bands = BAND_MID | BAND_HIGH;
    static struct rx3_stereo b[BLOCK]; float peak = 0; unsigned t = 0;
    for (unsigned k = 0; k < BLOCKS; k++) {
        for (unsigned i = 0; i < BLOCK; i++, t++) b[i].left = b[i].right = (float)sin(2 * M_PI * 50 * t / 44100.0);
        fx->capture(b, BLOCK);
        if (k > BLOCKS / 2) for (unsigned i = 0; i < BLOCK; i++) if (fabsf(b[i].left) > peak) peak = fabsf(b[i].left);
    }
    assert(peak < 0.05f);
    return 0;
}
''', [], ['-Wno-unused-function'])

    def test_a_band_change_is_ramped(self):
        self.run_units(HARNESS + r'''
int main(void) {
    assert(rx3_beatfx_eq_module.start(&services));
    struct rx3_stereo b[1];
    float last = 0;
    for (unsigned t = 0; t < 2000; t++) {
        if (t == 1000) bands = BAND_MID | BAND_HIGH;
        b[0].left = b[0].right = 1.0f;  /* DC: all LOW */
        fx->send(b, 1); killer(b, 1); fx->ret(b, 1);
        /* split and the band gain ramp together: at most two increments a frame. */
        if (t > 1000) assert(fabsf(b[0].left - last) < 2.0f / RAMP_FRAMES + 1e-4f);
        last = b[0].left;
    }
    assert(last > 0.99f);
    return 0;
}
''', [], ['-Wno-unused-function'])


if __name__ == '__main__':
    unittest.main()
