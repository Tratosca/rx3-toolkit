# SPDX-License-Identifier: MPL-2.0
"""Pin the SLIP LOOP stem pads and the one beat echo out."""

import pathlib
import unittest

from tests import test_runtime_transitions as transitions

FEATURE = transitions.MODULES / "stems/rx3_stems_feature.h"

HARNESS = r'''
#include <stdio.h>
typedef struct rx3_stereo Float2;
#include "core/api/rx3_module_api.h"
static int bpm = 12000, bpm_reads, idles, loading;
static int deck_bpm(unsigned int deck) { (void)deck; bpm_reads++; return bpm; }
static const struct rx3_audio_service audio = {.deck_bpm = deck_bpm};
static const struct rx3_services services = {.audio = &audio};
static const struct rx3_services *framework = &services;
#include "stems/rx3_stems_decl.h"
#define TAB_IMAGE_STEMS 0x1601u
static int blink_phase_is_on(void) { return 1; }
static int stems_any_deck_loading(void) { return loading; }
static void stems_blink_idle(void) { idles++; }
static void stems_echo_report(unsigned int deck) { (void)deck; }
static unsigned int now_ms(void) { return 0; }
#include "stems/rx3_stems_panel.h"
#include "stems/rx3_stems_echo.h"
''' + "".join(transitions.function(FEATURE, name) + "\n"
              for name in ("block_is_silent", "stems_stream", "stems_pad", "stems_light")) + r'''
#define FRAMES 300000u
#define BEAT 22050u
static Short2 vocal[FRAMES], drums[FRAMES], bass[FRAMES];
static Float2 played[FRAMES];
static struct stems_deck_context *c = &stems_decks[0];
static void *const reader = &stems_decks;

static void fill(unsigned int count) {
    c->payload_count = count; c->selection = count > 1 ? 0xffu : 0x33u;
    c->status = 2; c->armed = 1; c->reader = reader;
    c->payloads[0].data = vocal; c->payloads[1].data = count > 1 ? drums : 0;
    c->payloads[2].data = count > 2 ? bass : 0;
    for (unsigned int i = 0; i < 3; i++) c->payloads[i].frames = i < count ? FRAMES : 0;
    stems_reset_mix(c);
    __atomic_store_n(&stems_callbacks_enabled, 1u, __ATOMIC_SEQ_CST);
    captured_pad_mask[0] = 0;
}
/* Every role changes every frame, so a wrong read cannot pass as a right one. */
static void sources(void) {
    for (unsigned int i = 0; i < FRAMES; i++) {
        vocal[i] = (Short2){(int16_t)(8192 + i % 4096), (int16_t)-(8192 + i % 4096)};
        drums[i] = (Short2){(int16_t)(4096 + i % 1024), (int16_t)-(4096 + i % 1024)};
        bass[i] = (Short2){(int16_t)(1024 + i % 512), (int16_t)-(1024 + i % 512)};
    }
}
static float vocal_at(unsigned int i) { return (float)vocal[i].left * (1.0f / 32768.0f); }
static float drums_at(unsigned int i) { return (float)drums[i].left * (1.0f / 32768.0f); }
static float full_at(unsigned int i) { (void)i; return 0.9f; }
static float inst_at(unsigned int i, unsigned int count) {
    return full_at(i) - vocal_at(i) - (count > 1 ? drums_at(i) : 0.0f);
}
/* The deck's stream for [from, to), in blocks of `block`. */
static void run(unsigned int from, unsigned int to, unsigned int block) {
    for (unsigned int at = from; at < to; at += block) {
        unsigned int frames = to - at < block ? to - at : block;
        for (unsigned int i = 0; i < frames; i++) played[at + i] = (Float2){0.9f, -0.9f};
        stems_stream(0, reader, (int)at, played + at, frames);
    }
}
static void near(float got, float wanted) {
    float gap = got - wanted;
    if (gap < -0.0002f || gap > 0.0002f) {
        printf("got %f wanted %f\n", (double)got, (double)wanted);
        assert(0);
    }
}
static int tap(unsigned int code) {
    struct rx3_pad_event press = {code, 0, 1, 0, 2}, release = {code, 3, 1, 0, 2};
    int taken = stems_pad(&press);
    assert(stems_pad(&release) == taken);
    return taken;
}
'''


class PadTests(unittest.TestCase):
    run_c = transitions.RuntimeTransitionTests.run_c

    def test_top_row_toggles_bottom_row_echoes_last_column_stays_native(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    for (unsigned int bit = 1; bit <= 4; bit <<= 1) {
        unsigned int pad = bit == 1 ? 0x4117u : bit == 2 ? 0x4118u : 0x4119u;
        assert(tap(pad) && !(stems_selected(c) & bit));
        assert(tap(pad) && (stems_selected(c) & bit));
        assert(!c->echo_request);
    }
    /* Native on both rows, in any other mode, and for a role not prepared. */
    assert(!tap(0x411au) && !tap(0x411eu));
    struct rx3_pad_event other = {0x4117u, 0, 1, 0, 1};
    assert(!stems_pad(&other) && stems_selected(c) == 7u);
    fill(1);
    assert(!tap(0x4119u) && !tap(0x411du));
    assert(tap(0x4118u) && tap(0x4118u));
    /* The gesture is the deck's: a release without our press stays native. */
    struct rx3_pad_event alone = {0x411bu, 3, 1, 0, 2};
    assert(!stems_pad(&alone));
    /* An echo pad cuts its role and asks for one beat, once. */
    fill(2); bpm_reads = 0;
    assert(tap(0x411bu) && !(stems_selected(c) & 1u));
    assert(c->echo_request == 1u && c->echo_frames == BEAT && bpm_reads == 1);
    /* Nothing is left to echo: the gesture is still taken. */
    assert(tap(0x411bu) && c->echo_request == 1u && bpm_reads == 2);
    return 0;
}
''')

    def test_lights_of_both_rows(self):
        self.run_c(HARNESS + r'''
static struct rx3_light look(unsigned int control) {
    struct rx3_light light = {RX3_LIGHT_NATIVE, 0u};
    stems_light(0, control, &light);
    return light;
}
int main(void) {
    sources(); fill(2);
    /* Ready: the top row lit, the bottom row dimmed in the same colours. */
    assert(look(0).state == RX3_LIGHT_ON && look(0).rgb == 0xff0000u);
    assert(look(1).state == RX3_LIGHT_ON && look(1).rgb == 0x00ff00u);
    assert(look(2).state == RX3_LIGHT_ON && look(2).rgb == 0x78c8ffu);
    assert(look(4).state == RX3_LIGHT_DIM && look(4).rgb == 0xff0000u);
    assert(look(6).state == RX3_LIGHT_DIM && look(6).rgb == 0x78c8ffu);
    assert(look(3).state == RX3_LIGHT_NATIVE && look(7).state == RX3_LIGHT_NATIVE);
    /* Ringing: the top pad dims, the echo pad blinks in its colour. */
    assert(tap(0x411cu));
    assert(look(1).state == RX3_LIGHT_DIM && look(5).state == RX3_LIGHT_BLINK);
    assert(look(5).rgb == 0x00ff00u && look(4).state == RX3_LIGHT_DIM);
    run(0, BEAT * 5, 512);
    /* Rung out: nothing left to echo, so the pad goes dark. */
    assert(!stems_echo_running(c, 7u));
    assert(look(5).state == RX3_LIGHT_DIM && !look(5).rgb);
    /* A role not prepared stays native; loading blinks both rows. */
    fill(1);
    assert(look(2).state == RX3_LIGHT_NATIVE && look(6).state == RX3_LIGHT_NATIVE);
    c->payloads[0].data = 0; loading = 1;
    assert(look(0).state == RX3_LIGHT_BLINK && look(4).state == RX3_LIGHT_BLINK);
    return 0;
}
''')


class EchoTests(unittest.TestCase):
    run_c = transitions.RuntimeTransitionTests.run_c

    def test_beat_length_from_the_player(self):
        self.run_c(HARNESS + r'''
int main(void) {
    assert(stems_beat_frames(12000) == 22050u);
    assert(stems_beat_frames(6000) == 44100u);
    /* Slower than the history holds: the beat halves and stays on the grid. */
    assert(stems_beat_frames(5900) == 22423u);
    assert(stems_beat_frames(14000) == 18900u);
    assert(stems_beat_frames(0) == 0u && stems_beat_frames(-1) == 0u);
    return 0;
}
''')

    def test_echo_repeats_the_last_beat_quieter_and_ends_after_four(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411du));                /* DRUMS */
    run(cut, cut + BEAT * 4 + 2048, 512);
    static const float levels[4] = {0.71f, 0.35f, 0.18f, 0.09f};
    /* Past the crossfade and the loop edges the deck plays everything but the
       drums, plus the drums of the beat before the cut at the repeat's level. */
    for (unsigned int repeat = 0; repeat < 4; repeat++)
        for (unsigned int at = 512; at < BEAT - 64; at += 97) {
            unsigned int i = cut + repeat * BEAT + at;
            near(played[i].left, full_at(i) - drums_at(i) + drums_at(cut - BEAT + at) * levels[repeat]);
        }
    /* Then silence: only the dry roles are left. */
    for (unsigned int i = cut + BEAT * 4; i < cut + BEAT * 4 + 2048; i += 13)
        near(played[i].left, full_at(i) - drums_at(i));
    assert(!stems_echo_running(c, 7u));
    return 0;
}
''')

    def test_inst_echo_is_the_mix_without_the_stems_and_keeps_legacy_bass(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(3);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411bu));
    run(cut, cut + BEAT, 512);
    /* INST contains the bass, so its dry part is vocal plus drums only. */
    for (unsigned int at = 512; at < BEAT - 64; at += 97) {
        unsigned int i = cut + at;
        near(played[i].left, vocal_at(i) + drums_at(i) + inst_at(cut - BEAT + at, 2) * 0.71f);
    }
    return 0;
}
''')

    def test_roles_ring_independently(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411cu));                /* VOCAL */
    run(cut, cut + BEAT, 512);
    assert(tap(0x411du));                /* DRUMS, one beat later */
    run(cut + BEAT, cut + BEAT * 2, 512);
    for (unsigned int at = 512; at < BEAT - 64; at += 97) {
        unsigned int i = cut + BEAT + at;
        float inst = full_at(i) - vocal_at(i) - drums_at(i);
        near(played[i].left, inst + vocal_at(cut - BEAT + at) * 0.35f +
                             drums_at(cut + at) * 0.71f);
    }
    return 0;
}
''')

    def test_reads_that_overlap_and_step_back_hear_the_same_echo(self):
        # The stage is random-access: on hardware 13.6% of its calls continue
        # where the last one stopped, two thirds re-read and a fifth step back.
        # A read that repeats a frame must get that frame's samples again.
        self.run_c(HARNESS + r'''
static Float2 straight[FRAMES];
/* The next read starts `hop` frames on from this one, as the measured mix does. */
static int hop_of(unsigned int call) {
    unsigned int roll = (call * 2654435761u) >> 24;
    if (roll < 35) return 512;                 /* continues: 13.6% */
    if (roll < 205) return 128 + (int)(roll % 256);  /* re-reads an overlap */
    return -64 - (int)(roll % 64);             /* steps back */
}
static void wander(unsigned int from, unsigned int to) {
    unsigned int call = 0;
    int at = (int)from;
    while (at < (int)to) {
        for (unsigned int i = 0; i < 512; i++) played[(unsigned int)at + i] = (Float2){0.9f, -0.9f};
        stems_stream(0, reader, at, played + (unsigned int)at, 512);
        at += hop_of(call++);
        if (at < (int)from) at = (int)from;
    }
}
int main(void) {
    sources(); fill(2);
    unsigned int cut = BEAT * 2;
    run(0, cut, 512); assert(tap(0x411du)); run(cut, cut + BEAT * 4, 512);
    memcpy(straight, played, sizeof(straight));
    fill(2);
    wander(0, cut); assert(tap(0x411du)); wander(cut, cut + BEAT * 4);
    /* Past the cut's own fade, every frame matches a straight read. */
    unsigned int wrong = 0;
    for (unsigned int i = cut + 2048; i < cut + BEAT * 4 - 2048; i++) {
        float gap = played[i].left - straight[i].left;
        if (gap < -0.0002f || gap > 0.0002f) wrong++;
    }
    printf("frames off the straight read: %u of %u\n", wrong, BEAT * 4 - 4096);
    fflush(stdout);
    assert(!wrong);
    return 0;
}
''')

    def test_block_size_does_not_change_a_single_frame(self):
        self.run_c(HARNESS + r'''
static Float2 first[FRAMES];
int main(void) {
    sources(); fill(2);
    unsigned int cut = BEAT + 1000u;
    run(0, cut, 512); assert(tap(0x411cu)); run(cut, cut + BEAT * 5, 512);
    memcpy(first, played, sizeof(first));
    fill(2);
    /* The press must land on a block boundary of both runs. */
    run(0, cut, 64); assert(tap(0x411cu)); run(cut, cut + BEAT * 5, 64);
    assert(!memcmp(first, played, (cut + BEAT * 5) * sizeof(Float2)));
    return 0;
}
''')

    def test_no_echo_leaves_the_stream_as_it_was(self):
        self.run_c(HARNESS + r'''
static Float2 mixed[FRAMES];
int main(void) {
    sources(); fill(2);
    stems_toggle(c, 2u);
    run(0, 8192, 512);
    memcpy(mixed, played, 8192 * sizeof(Float2));
    fill(2);
    stems_toggle(c, 2u);
    for (unsigned int at = 0; at < 8192; at += 512) {
        for (unsigned int i = 0; i < 512; i++) played[at + i] = (Float2){0.9f, -0.9f};
        stems_mix(c, (int)at, played + at, 512);
    }
    assert(!memcmp(mixed, played, 8192 * sizeof(Float2)));
    return 0;
}
''')

    def test_the_echo_rings_through_silent_blocks(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411du));
    run(cut, cut + 1024, 512);
    Float2 quiet[512];
    memset(quiet, 0, sizeof(quiet));
    stems_stream(0, reader, (int)(cut + 1024), quiet, 512);
    near(quiet[100].left, drums_at(cut - BEAT + 1024 + 100) * 0.71f);
    return 0;
}
''')

    def test_a_role_turned_back_on_ends_its_echo_within_a_crossfade(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411du));
    run(cut, cut + 2048, 512);
    assert(tap(0x4119u));                /* back on from the top row */
    run(cut + 2048, cut + 2048 + 512, 512);
    assert(!stems_echo_running(c, 7u));
    run(cut + 2560, cut + 4096, 512);
    for (unsigned int i = cut + 2560; i < cut + 4096; i += 13) near(played[i].left, 0.9f);
    /* The echo pad works again at once, with what was captured since. */
    run(cut + 4096, cut + 4096 + BEAT, 512);
    assert(tap(0x411du) && c->echo_request == 4u);
    run(cut + 4096 + BEAT, cut + 4096 + BEAT + 2048, 512);
    assert(stems_echo_running(c, 4u));
    return 0;
}
''')

    def test_a_quick_second_inst_echo_never_repeats_the_frozen_beat(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411bu));
    run(cut, cut + 2048, 512);
    assert(tap(0x4117u));
    run(cut + 2048, cut + 2560, 512);
    assert(!stems_echo_running(c, 7u));
    /* Half a beat later the history holds only that half. */
    unsigned int press = cut + 2560 + BEAT / 2;
    run(cut + 2560, press, 512);
    assert(tap(0x411bu));
    run(press, press + BEAT, 512);
    for (unsigned int at = 512; at < BEAT / 2 - 64; at += 97)
        near(played[press + at].left, vocal_at(press + at) + drums_at(press + at));
    for (unsigned int at = BEAT / 2 + 512; at < BEAT - 64; at += 97)
        near(played[press + at].left, vocal_at(press + at) + drums_at(press + at) +
             inst_at(press - BEAT + at, 2) * 0.71f);
    return 0;
}
''')

    def test_a_jump_keeps_the_echo_in_time(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411bu) && tap(0x411du));
    run(cut, cut + 1024, 512);
    /* A hot cue: the repeats go on from where they were, with what they froze. */
    unsigned int cue = cut + 60000u;
    run(cue, cue + 1024, 512);
    near(played[cue + 512].left, vocal_at(cue + 512) +
         inst_at(cut - BEAT + 1024 + 512, 2) * 0.71f + drums_at(cut - BEAT + 1024 + 512) * 0.71f);
    run(cue + 1024, cue + BEAT * 4, 512);
    assert(!stems_echo_running(c, 7u));
    return 0;
}
''')

    def test_a_stopped_deck_holds_the_echo(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411du));
    run(cut, cut + 1024, 512);
    /* Paused, the stage keeps asking for one place and gets silence back. */
    Float2 quiet[512];
    for (unsigned int i = 0; i < 200; i++) {
        memset(quiet, 0, sizeof(quiet));
        stems_stream(0, reader, (int)(cut + 512), quiet, 512);
        assert(quiet[100].left == 0.0f && quiet[511].right == 0.0f);
    }
    assert(stems_echo_running(c, 4u));
    run(cut + 1024, cut + 2048, 512);
    near(played[cut + 1536].left, full_at(cut + 1536) - drums_at(cut + 1536) +
         drums_at(cut - BEAT + 1536) * 0.71f);
    return 0;
}
''')

    def test_slider_level_scales_the_echo(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    stems_set_level(c, 4u, 50u);
    run(0, BEAT * 2, 512);
    unsigned int cut = BEAT * 2;
    assert(tap(0x411du));
    run(cut, cut + 2048, 512);
    near(played[cut + 1024].left, full_at(cut + 1024) - drums_at(cut + 1024) +
         drums_at(cut - BEAT + 1024) * 0.5f * 0.71f);
    return 0;
}
''')

    def test_no_bpm_mutes_without_an_echo(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2); bpm = 0;
    run(0, BEAT * 2, 512);
    assert(tap(0x411du) && !(stems_selected(c) & 4u));
    assert(!c->echo_request);
    unsigned int cut = BEAT * 2;
    run(cut, cut + 2048, 512);
    assert(!stems_echo_running(c, 7u));
    near(played[cut + 1024].left, full_at(cut + 1024) - drums_at(cut + 1024));
    return 0;
}
''')

    def test_a_short_history_rings_silence_never_an_older_track(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    /* A new track: half a beat in, the press has half a beat to repeat. */
    fill(2);
    run(0, BEAT / 2, 512);
    unsigned int cut = BEAT / 2;
    assert(tap(0x411bu) && tap(0x411du));
    run(cut, cut + BEAT, 512);
    for (unsigned int at = 512; at < BEAT / 2 - 64; at += 97)
        near(played[cut + at].left, vocal_at(cut + at));
    for (unsigned int at = BEAT / 2 + 512; at < BEAT - 64; at += 97)
        near(played[cut + at].left, vocal_at(cut + at) +
             (inst_at(cut - BEAT + at, 2) + drums_at(cut - BEAT + at)) * 0.71f);
    return 0;
}
''')

    def test_a_new_track_ends_the_echo(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    assert(tap(0x411du));
    run(BEAT * 2, BEAT * 2 + 1024, 512);
    assert(stems_echo_running(c, 4u));
    stems_reset_mix(c);
    assert(!stems_echo_running(c, 7u));
    run(0, 1024, 512);
    near(played[512].left, 0.9f);
    return 0;
}
''')

    def test_decks_keep_separate_histories(self):
        self.run_c(HARNESS + r'''
int main(void) {
    sources(); fill(2);
    run(0, BEAT * 2, 512);
    assert(stems_echo_history[1][1000].left == 0.0f);
    assert(stems_echo_history[0][1000].left != 0.0f);
    return 0;
}
''')


class SourceTests(unittest.TestCase):
    def test_bpm_is_read_where_the_contract_allows(self):
        """Audio callbacks must not call into the player."""
        echo = (transitions.MODULES / "stems/rx3_stems_echo.h").read_text()
        self.assertNotIn("deck_bpm", echo)
        self.assertNotIn("deck_bpm", transitions.function(FEATURE, "stems_stream"))

    def test_the_history_stays_out_of_the_file(self):
        echo = (transitions.MODULES / "stems/rx3_stems_echo.h").read_text()
        self.assertRegex(echo, r"static struct rx3_stereo stems_echo_history\[2\]\[STEMS_ECHO_FRAMES\];")
        decl = pathlib.Path(transitions.MODULES / "stems/rx3_stems_decl.h").read_text()
        self.assertNotIn("stems_echo_history", decl)


if __name__ == "__main__":
    unittest.main()
