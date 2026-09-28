# SPDX-License-Identifier: MPL-2.0
"""Pin audio transitions and input ownership that compilation cannot check."""

import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULES = ROOT / "mod/modules"


def function(path, name):
    source = path.read_text()
    # The caller names a definition, not a prototype or a call site.
    start = re.search(r"(?m)^.*\bstatic\b[^\n]*\b" + name + r"\s*\(", source).start()
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class RuntimeTransitionTests(unittest.TestCase):
    def run_c(self, body):
        compiler = shutil.which("clang") or shutil.which("cc")
        if not compiler:
            self.skipTest("a native C compiler is required")
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "transitions.c"
            source.write_text('#define RX3_PLATFORM_H\n#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n'
                              '#include <assert.h>\n#include <pthread.h>\n' + body)
            binary = source.with_suffix("")
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-function", "-Wno-unused-variable", "-pthread",
                            "-I", str(MODULES), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_track_path_never_selects_appledouble_for_an_audio_file(self):
        core = MODULES / "core/rx3_core_hook.c"
        self.run_c(r'''
static const char *stems_dir = "/usb/RX3_STEMS";
static size_t str_length(const char *s) { return strlen(s); }
''' + function(core, "path_in_stems") + function(core, "stem_path_for_track") + r'''
int main(void) {
    char path[1024];
    assert(!stem_path_for_track("/usb/Contents/track.wav",path,sizeof(path)));
    assert(!strcmp(path,"/usb/RX3_STEMS/track.rx3stem"));
    assert(strcmp(path,"/usb/RX3_STEMS/._track.rx3stem"));
    return 0;
}
''')

    def test_host_reconstruction_matches_c_for_every_float_sample(self):
        import array
        import random
        import struct
        from app.stems import mixing
        randomizer = random.Random(43)
        pcm = [array.array("h", [randomizer.randint(-32768, 32767) for _ in range(1400)]) for _ in range(3)]
        full = array.array("f", [randomizer.uniform(-1.2, 1.2) for _ in range(1400)])
        for frame in range(0, 700, 17):
            full[2 * frame] = full[2 * frame + 1] = 0
        state = mixing.MixState()
        expected = array.array("f")
        segments = [(0, 128, 1), (128, 1, 3), (129, 300, 2), (429, 271, 15)]
        for start, count, selection in segments:
            expected.extend(mixing.reconstruct(full[start * 2:(start + count) * 2],
                            [part[start * 2:(start + count) * 2] for part in pcm], selection, state))
        def floats(values):
            return ",".join(float(value).hex() + "f" for value in values)
        vectors = "Float2 output[700]={" + ",".join("{" + floats(full[i:i + 2]) + "}" for i in range(0, 1400, 2)) + "};\n"
        vectors += "Float2 expected[700]={" + ",".join("{" + floats(expected[i:i + 2]) + "}" for i in range(0, 1400, 2)) + "};\n"
        for index, part in enumerate(pcm):
            vectors += "Short2 role%d[700]={" % index + ",".join("{%d,%d}" % tuple(part[i:i + 2]) for i in range(0, 1400, 2)) + "};\n"
        setup = "".join("c->payloads[%d].data=role%d;c->payloads[%d].frames=700;" % (i, i, i) for i in range(3))
        calls = "".join("stems_set_mask(c,%du);stems_mix(c,%d,output+%d,%d);" % (selection, start, start, count) for start, count, selection in segments)
        self.run_c('''
#pragma STDC FP_CONTRACT OFF
typedef struct { float left, right; } Float2;
typedef struct { int16_t left, right; } Short2;
#include "stems/rx3_stems_decl.h"
#include "stems/rx3_stems_audio.h"
int main(void) {
''' + vectors + "struct stems_deck_context *c=&stems_decks[0]; c->payload_count=3; stems_reset_mix(c);" + setup + calls + '''
assert(!memcmp(output,expected,sizeof(output)));
return 0;
}
''')

    def test_legacy_bass_follows_inst_and_concurrent_selection(self):
        self.run_c(r'''
typedef struct { float left, right; } Float2;
typedef struct { int16_t left, right; } Short2;
#include "stems/rx3_stems_decl.h"
#include "stems/rx3_stems_audio.h"
static void *toggle_many(void *argument) {
    for (unsigned i=0; i<20001; i++) stems_toggle(&stems_decks[0], (unsigned)(uintptr_t)argument);
    return 0;
}
int main(void) {
    struct stems_deck_context *c = &stems_decks[0];
    c->selection=0xff; c->payload_count=3; stems_reset_mix(c);
    Short2 vocals[300], drums[300], bass[300];
    Float2 output[300];
    for (unsigned i=0; i<300; i++) {
        vocals[i]=(Short2){8192,-8192}; drums[i]=(Short2){4096,-4096};
        bass[i]=(Short2){2048,-2048}; output[i]=(Float2){1,-1};
    }
    c->payloads[0].data=vocals; c->payloads[1].data=drums; c->payloads[2].data=bass;
    for(unsigned i=0;i<3;i++) c->payloads[i].frames=300;
    stems_mix(c,0,output,300); assert(output[299].left==1);
    /* INST retains legacy bass and subtracts vocals and drums. */
    stems_toggle(c,14); stems_mix(c,0,output,128);
    assert(c->transition_cursor==128 && c->gain[1]==0.5f);
    assert(output[127].left==0.8125f);
    /* A toggle halfway through starts at the audible gains, not at the old mask. */
    stems_toggle(c,2); stems_mix(c,128,output+128,1);
    assert(c->from[1]==0.5f && c->gain[1]==0.5f+0.5f/256);
    assert(c->from[2]==0.5f && c->gain[2]==0.5f-0.5f/256);
    output[0]=(Float2){0,0}; unsigned cursor=c->transition_cursor;
    stems_mix(c,0,output,1); assert(c->transition_cursor==cursor);
    output[0]=(Float2){1,-1}; stems_mix(c,-1,output,1);
    assert(output[0].left==1 && c->transition_cursor==cursor);
    stems_mix(c,300,output,1); assert(output[0].left==1);
    c->selection=0xf2; stems_reset_mix(c);
    for(unsigned i=0;i<300;i++) output[i]=(Float2){1,-1};
    stems_mix(c,0,output,300); assert(output[299].left==0.25f && output[299].right==-0.25f);
    stems_set_mask(c,0); stems_mix(c,0,output,300); assert(output[299].left==0);
    for(unsigned count=1;count<=3;count++) {
        c->payload_count=count; c->selection=1u; stems_reset_mix(c);
        for(unsigned i=0;i<300;i++) output[i]=(Float2){1,-1};
        stems_mix(c,0,output,255);
        assert(c->transition_cursor==255 && c->gain[1]==1.0f/256.0f);
        stems_mix(c,255,output+255,1);
        float rest=1.0f-0.25f-(count>=2?0.125f:0);
        assert(c->transition_cursor==256 && c->gain[1]==0);
        assert(output[255].left==rest && output[255].right==-rest);
    }
    c->selection=0xff; stems_set_mask(c,15); pthread_t a,b;
    assert(!pthread_create(&a,0,toggle_many,(void *)2));
    assert(!pthread_create(&b,0,toggle_many,(void *)4));
    pthread_join(a,0); pthread_join(b,0);
    assert(stems_selected(c)==1);
    c->selection=0x33; stems_toggle(c,4); assert(c->selection==0x33);
    assert(stems_available(c)==3);
    return 0;
}
''')

    def test_key_labels_and_transport_resets(self):
        key = MODULES / "keyshift/rx3_keyshift.h"
        self.run_c(r'''
#include "keyshift/rx3_keyshift_text.h"
struct rx3_keyshift_deck {
    unsigned request, reset_generation, seen_reset, was_silent;
    uint32_t last_position;
    unsigned last_frames;
    int last_direction, position_valid;
};
static struct rx3_keyshift_deck keyshift_decks[2]={{.request=12},{.request=12}};
static void log_number(const char *s, unsigned long n) { (void)s; (void)n; }
''' + function(key, "change_key") + function(key, "keyshift_transport_reset") + r'''
static void equal(const uint16_t *text, const char *wanted) {
    while (*wanted) assert(*text++==(unsigned char)*wanted++);
    assert(!*text);
}
int main(void) {
    uint16_t text[20], labels[3][12];
    for(unsigned key=0;key<24;key++) {
        unsigned n=0; while(rx3_camelot_classic[key][n]) {
            text[n]=(uint16_t)rx3_camelot_classic[key][n]; n++;
        }
        assert(rx3_camelot_index_from_text(text,n)==(int)key);
        keyshift_format_labels(labels,(int)key,0);
        assert(rx3_camelot_index_from_text(labels[1],key>=18?3:2)==(int)key);
    }
    const uint16_t padded[]={'\t',' ','1','2','b',' ',0};
    assert(keyshift_key_from_glyph_text(padded,255)==23);
    const uint16_t invalid[]={'1','3','A',0};
    assert(rx3_camelot_index_from_text(invalid,3)==-1);
    assert(rx3_camelot_index_from_text(0,2)==-1);
    keyshift_format_labels(labels,14,1); equal(labels[0],"-1"); equal(labels[1],"3A (+1)"); equal(labels[2],"+1");
    keyshift_format_labels(labels,18,-2); equal(labels[1],"8A (-2)");
    keyshift_format_labels(labels,14,0); equal(labels[1],"8A");
    keyshift_format_labels(labels,23,12); equal(labels[1],"12B (+12)");
    keyshift_format_labels(labels,-1,0); equal(labels[0],"-1"); equal(labels[1],"KEY --"); equal(labels[2],"+1");
    keyshift_format_labels(labels,14,-12); equal(labels[0],"-1"); equal(labels[1],"8A (-12)");
    keyshift_format_labels(labels,-1,12); equal(labels[1],"KEY +12"); equal(labels[2],"+1");
    assert(keyshift_text_deck(0x1101,10,78,122,104)==0);
    assert(keyshift_text_deck(0x1101,10,339,138,375)==1);
    assert(keyshift_text_deck(0x1102,10,78,122,104)==-1);
    assert(keyshift_text_deck(0x1101,10,119,122,145)==-1);
    struct rx3_keyshift_deck *c=&keyshift_decks[0];
    change_key(0,50); assert((c->request&255)==24 && (c->request>>8)==1);
    change_key(0,1); assert(c->request==(256|24));
    change_key(0,-100); assert(c->request==512);
    assert(!keyshift_transport_reset(c,0,64,0));
    assert(!keyshift_transport_reset(c,64,64,0));
    assert(!keyshift_transport_reset(c,320,64,0));
    assert(keyshift_transport_reset(c,577,64,0));
    assert(keyshift_transport_reset(c,513,64,0));
    assert(!keyshift_transport_reset(c,449,64,1));
    assert(keyshift_transport_reset(c,385,64,0));
    c->reset_generation++; assert(keyshift_transport_reset(c,321,64,0));
    assert(!keyshift_transport_reset(c,257,64,0));
    return 0;
}
''')

    def test_sample_pad_modes_ownership_and_master_order(self):
        samples = MODULES / "samples/rx3_samples_feature.h"
        self.run_c(r"""
typedef struct { float left, right; } Float2;
#include "samples/rx3_samples_decl.h"
#include "samples/rx3_samples_state.h"
#include "samples/rx3_samples_audio.h"
static unsigned pad_callbacks_active, stock_calls, master_calls;
static uint8_t theme_shift_held[3];
static int stems_on_key_pad(void *self, const void *input) {
    assert(self==(void *)1 && input); stock_calls++; return 42;
}
static void original_mic_talkover_attenuate(void *self, void *state, Float2 *out, int frames) {
    assert(self==(void *)1 && state==(void *)2 && frames==1);
    assert(out[0].left==0.125f && samples_audio_active==1); master_calls++;
}
""" + function(samples, "samples_stop") + function(samples, "samples_leave_mode") + function(samples, "samples_shift_pressed") + function(samples, "samples_active_voices") + function(samples, "hooked_on_key_pad") + function(samples, "hooked_mic_talkover_attenuate") + r"""
static void press(uint8_t *event, unsigned pad, int down) {
    event[8]=(uint8_t)(0x17u+pad); event[9]=0x41; event[11]=down?0:3;
}
int main(void) {
    uint8_t event[12]={0}; press(event,0,1);
    int16_t pcm[]={32767,0};
    for(unsigned i=0;i<8;i++){ samples_bank[i].frames=pcm; samples_bank[i].length=1; }
    /* What samples_feature_install leaves behind: nothing is sounding. */
    for(unsigned i=0;i<8;i++) samples_slots[i].position=SAMPLE_SLOT_IDLE;
    assert(hooked_on_key_pad((void *)1,event)==42 && stock_calls==1);
    samples_callbacks_enabled=1; samples_mode=1;

    /* Once: the mode every pad had before the modes existed. */
    assert(hooked_on_key_pad((void *)1,event)==1 && samples_slots[0].position==0);
    samples_slots[0].position=1; press(event,0,0);
    assert(hooked_on_key_pad((void *)1,event)==1 && samples_slots[0].position==1);
    press(event,0,1); hooked_on_key_pad((void *)1,event);
    assert(samples_slots[0].position==0);

    /* The trim rides with the sound: half the level, half the sample. */
    samples_config.gain[0]=50u; press(event,0,1); hooked_on_key_pad((void *)1,event);
    assert(samples_slots[0].gain==50u);
    samples_config.gain[0]=SAMPLES_GAIN_UNITY;

    /* Hold: the release is what stops it, and only for this mode. */
    samples_config.mode[1]=SAMPLE_MODE_HOLD; press(event,1,1);
    assert(hooked_on_key_pad((void *)1,event)==1);
    assert(samples_slots[1].position==0 && samples_slots[1].mode==SAMPLE_MODE_HOLD);
    press(event,1,0); hooked_on_key_pad((void *)1,event);
    assert(samples_slots[1].position==SAMPLE_SLOT_IDLE);

    /* A shared hold is released by its last deck, not by repeats or by the
       first deck to lift a finger. */
    press(event,1,1); event[10]=1; hooked_on_key_pad((void *)1,event);
    event[10]=2; hooked_on_key_pad((void *)1,event);
    event[11]=1; hooked_on_key_pad((void *)1,event);
    assert(samples_slots[1].position==0);
    press(event,1,0); event[10]=1; hooked_on_key_pad((void *)1,event);
    assert(samples_slots[1].position==0);
    event[10]=2; hooked_on_key_pad((void *)1,event);
    assert(samples_slots[1].position==SAMPLE_SLOT_IDLE);
    event[10]=0;

    /* Loop: the pad that started it stops it. */
    samples_config.mode[2]=SAMPLE_MODE_LOOP; press(event,2,1);
    hooked_on_key_pad((void *)1,event);
    assert(samples_slots[2].position==0 && samples_slots[2].mode==SAMPLE_MODE_LOOP);
    press(event,2,0); hooked_on_key_pad((void *)1,event);
    assert(samples_slots[2].position==0);
    press(event,2,1); hooked_on_key_pad((void *)1,event);
    assert(samples_slots[2].position==SAMPLE_SLOT_IDLE);

    /* Latch: the same pad stops it, and it never wraps.
       This is what a long sound needed. Once ignores the release, so a bed
       fired by mistake could only be taken back by SHIFT, which takes the other
       seven with it. */
    samples_config.mode[3]=SAMPLE_MODE_LATCH; press(event,3,1);
    hooked_on_key_pad((void *)1,event);
    assert(samples_slots[3].position==0 && samples_slots[3].mode==SAMPLE_MODE_LATCH);
    press(event,3,0); hooked_on_key_pad((void *)1,event);
    assert(samples_slots[3].position==0);          /* the release is not it */
    press(event,3,1); hooked_on_key_pad((void *)1,event);
    assert(samples_slots[3].position==SAMPLE_SLOT_IDLE);
    samples_config.mode[3]=SAMPLE_MODE_ONCE;

    /* A latch runs out where a loop wraps: one sample long, mixed twice. */
    {
        Float2 out[1];
        samples_slots[4].frames=pcm; samples_slots[4].length=1;
        samples_slots[4].gain=SAMPLES_GAIN_UNITY;
        samples_slots[4].mode=SAMPLE_MODE_LATCH; samples_slots[4].position=0;
        samples_slots[5].frames=pcm; samples_slots[5].length=1;
        samples_slots[5].gain=SAMPLES_GAIN_UNITY;
        samples_slots[5].mode=SAMPLE_MODE_LOOP; samples_slots[5].position=0;
        out[0].left=0.0f; out[0].right=0.0f;
        samples_mix(samples_slots,out,1,100u);
        assert(samples_slots[4].position==SAMPLE_SLOT_IDLE);
        assert(samples_slots[5].position==0);
        samples_slots[4].position=SAMPLE_SLOT_IDLE;
        samples_slots[5].position=SAMPLE_SLOT_IDLE;
    }

    /* Four voices of mixed modes share both decks' budget. A refused fifth leaves all
       sounding voices intact; stopping one immediately frees a place. */
    for(unsigned i=0;i<8;i++) samples_slots[i].position=SAMPLE_SLOT_IDLE;
    for(unsigned i=0;i<5;i++) {
        samples_config.mode[i]=i < 4 ? i : SAMPLE_MODE_LOOP; press(event,i,1);
        event[10]=(uint8_t)(1+i%2); hooked_on_key_pad((void *)1,event);
    }
    assert(samples_active_voices()==4 && samples_slots[4].position==SAMPLE_SLOT_IDLE);
    for(unsigned i=0;i<4;i++) assert(samples_slots[i].position==0);
    /* Retriggering an occupied one-shot needs no extra slot. */
    press(event,0,1); hooked_on_key_pad((void *)1,event);
    assert(samples_active_voices()==4 && samples_slots[0].position==0);
    press(event,2,1); hooked_on_key_pad((void *)1,event);
    assert(samples_active_voices()==3);
    press(event,4,1); hooked_on_key_pad((void *)1,event);
    assert(samples_active_voices()==4 && samples_slots[4].position==0);
    samples_stop(1);

    /* Shift silences everything and starts nothing. */
    samples_config.shift_silence=1u; theme_shift_held[1]=1u;
    samples_slots[0].position=0; samples_slots[1].position=0;
    press(event,3,1); assert(hooked_on_key_pad((void *)1,event)==1);
    for(unsigned i=0;i<8;i++) assert(samples_slots[i].position==SAMPLE_SLOT_IDLE);
    samples_config.shift_silence=0u; theme_shift_held[1]=0u;

    samples_config.shift_silence=1u;
    samples_slots[0].position=0; samples_slots[1].position=0;
    samples_shift_pressed();
    for(unsigned i=0;i<8;i++) assert(samples_slots[i].position==SAMPLE_SLOT_IDLE);
    samples_config.shift_silence=0u;
    for(unsigned i=0;i<4;i++) {
        samples_slots[i].mode=i; samples_slots[i].position=0; samples_pad_hold[i]=6;
    }
    samples_leave_mode();
    assert(!samples_mode && samples_slots[0].position==0);
    for(unsigned i=0;i<4;i++) assert(samples_slots[i].position==0 && samples_pad_hold[i]==6);
    /* Both deck releases remain owned after leaving; loops/latches keep playing. */
    press(event,1,1); event[11]=2; assert(hooked_on_key_pad((void *)1,event)==1);
    assert(samples_slots[1].position==0 && samples_pad_hold[1]==4);
    event[10]=2; assert(hooked_on_key_pad((void *)1,event)==1);
    assert(samples_slots[1].position==SAMPLE_SLOT_IDLE && !samples_pad_hold[1]);
    assert(samples_slots[2].position==0 && samples_slots[3].position==0);
    press(event,0,1);
    assert(hooked_on_key_pad((void *)1,event)==42);
    assert(stock_calls==2 && !pad_callbacks_active);

    /* A loop wraps where a one-shot would fall silent. */
    for(unsigned i=0;i<8;i++) samples_slots[i]=(struct sample_slot){0,0,SAMPLE_SLOT_IDLE,0,SAMPLES_GAIN_UNITY};
    int16_t full[]={-32768,0};
    samples_slots[0]=(struct sample_slot){full,1,0,SAMPLE_MODE_LOOP,SAMPLES_GAIN_UNITY};
    Float2 pair[2]={{0,0},{0,0}};
    samples_mix(samples_slots,pair,2,50);
    assert(pair[0].left==-0.125f && pair[1].left==-0.125f);
    assert(samples_slots[0].position==0);

    /* The ramp applies at each wrap, including a wrap inside an audio block. */
    int16_t long_pcm[256]; for(unsigned i=0;i<256;i++) long_pcm[i]=-32768;
    samples_slots[0]=(struct sample_slot){long_pcm,128,127,SAMPLE_MODE_LOOP,SAMPLES_GAIN_UNITY};
    Float2 edges[3]={{0,0},{0,0},{0,0}};
    samples_mix(samples_slots,edges,3,100);
    assert(edges[0].left==-0.5f/32 && edges[1].left==-0.5f/32);
    assert(edges[2].left==-0.5f*2/32 && samples_slots[0].position==2);
    samples_slots[0]=(struct sample_slot){long_pcm,128,0,SAMPLE_MODE_ONCE,SAMPLES_GAIN_UNITY};
    Float2 untouched={0,0}; samples_mix(samples_slots,&untouched,1,100);
    assert(untouched.left==-0.5f);

    /* And the mixer spends it: half the trim is half the sample, so a loud pad
       can be brought down to sit with the others. */
    samples_slots[0]=(struct sample_slot){full,1,0,SAMPLE_MODE_LOOP,50u};
    Float2 quiet[2]={{0,0},{0,0}};
    samples_mix(samples_slots,quiet,2,50);
    assert(quiet[0].left==-0.0625f && quiet[1].left==-0.0625f);
    samples_slots[0]=(struct sample_slot){full,1,0,SAMPLE_MODE_LOOP,0u};
    Float2 muted={0,0};
    samples_mix(samples_slots,&muted,1,50);
    assert(muted.left==0.0f);

    samples_slots[0]=(struct sample_slot){full,1,0,SAMPLE_MODE_ONCE,SAMPLES_GAIN_UNITY};
    samples_volume=50; Float2 out={0.25f,0};
    hooked_mic_talkover_attenuate((void *)1,(void *)2,&out,1);
    assert(master_calls==1 && !samples_audio_active && samples_slots[0].position==SAMPLE_SLOT_IDLE);
    samples_callbacks_enabled=0; samples_slots[0].position=0;
    hooked_mic_talkover_attenuate((void *)1,(void *)2,&out,1);
    assert(samples_slots[0].position==0 && master_calls==2);
    return 0;
}
""")

    def test_key_sync_is_bounded_and_tracks_both_transposed_decks(self):
        panel = MODULES / "keyshift/rx3_keyshift_panel.h"
        self.run_c(r"""
#include "keyshift/rx3_keyshift_text.h"

#include "core/api/rx3_module_api.h"
static int keyshift_current_key(unsigned int deck);
static unsigned int master_deck=1;
static struct rx3_harmonic_reference reference(void) {
    int key=keyshift_current_key(master_deck);unsigned mask=0;
    for(int i=0;i<24;i++)if(rx3_camelot_compatible(key,i))mask|=1u<<i;
    return (struct rx3_harmonic_reference){(int)master_deck,key,mask};
}
static const struct rx3_browse_service browse={.reference=reference};
static const struct rx3_services services={.browse=&browse};
static const struct rx3_services *framework=&services;
#include "core/api/rx3_panel_api.h"
static uint16_t keyshift_labels[2][3][12];
static int keyshift_track_key[2], shifts[2];
static unsigned int keyshift_sync_enabled=1;
static unsigned int keyshift_sync_range=1;
static unsigned int keyshift_sync_harmonic;
static unsigned int keyshift_match_rules;
static int rx3_keyshift_semitones(unsigned d){return shifts[d];}
static void rx3_keyshift_change(unsigned d,int delta){shifts[d]+=delta;}
""" + function(panel,"keyshift_base_key") + function(panel,"keyshift_current_key")
            + function(panel,"keyshift_reference")
            + function(panel,"keyshift_sync_compatible")
            + function(panel,"keyshift_match_delta")
            + function(panel,"keyshift_live_count")
            + function(panel,"keyshift_widget_kind")
            + function(panel,"keyshift_caption")
            + function(panel,"keyshift_fire") + r"""
int main(void) {
    assert(keyshift_parse_sync_range(0)==1);
    assert(keyshift_parse_sync_range("12")==12);
    assert(keyshift_parse_sync_range("2")==2);
    const char *bad[]={"","0","13","-1","1.5","1x","999"," 2"};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) assert(keyshift_parse_sync_range(bad[i])==1);
    /* Same source, but the other deck is already shifted. */
    keyshift_track_key[0]=keyshift_track_key[1]=0;
    shifts[1]=1;
    keyshift_sync_enabled=0;
    assert(keyshift_live_count(0)==1 && keyshift_match_delta(0)==0);
    keyshift_fire(0,1,0);assert(shifts[0]==0);
    keyshift_fire(0,0,2);assert(shifts[0]==1);
    keyshift_fire(0,0,1);assert(shifts[0]==0);
    keyshift_sync_enabled=1;
    assert(keyshift_match_delta(0)==1 && keyshift_match_delta(1)==0);
    assert(keyshift_live_count(0)==2);
    keyshift_fire(0,1,0);assert(shifts[0]==1 && shifts[1]==1);
    assert(keyshift_live_count(0)==2 && keyshift_live_count(1)==1);
    assert(keyshift_caption(1,1,0)[0]==0); /* no MASTER caption on the reference deck */
    assert(keyshift_widget_kind(0,1)==RX3_PAD_STATUS);
    assert(keyshift_caption(0,1,0)[0]=='I'); /* IDENTIQUE */
    /* The centre is reset only, even while a sync offer exists. */
    shifts[1]=2;keyshift_fire(0,0,1);assert(shifts[0]==0);
    assert(!keyshift_match_delta(0));
    assert(keyshift_live_count(0)==2 && keyshift_widget_kind(0,1)==RX3_PAD_STATUS);
    assert(keyshift_caption(0,1,0)[0]=='P'); /* PAS DE SYNC */
    keyshift_sync_range=2;assert(keyshift_match_delta(0)==2);
    /* Releasing after the target has moved beyond the threshold does nothing. */
    shifts[1]=3;keyshift_fire(0,1,0);assert(shifts[0]==0);
    shifts[1]=-2;assert(keyshift_match_delta(0)==-2);
    keyshift_fire(0,1,0);assert(shifts[0]==-2);
    keyshift_track_key[1]=-1;assert(!keyshift_match_delta(0));
    keyshift_track_key[1]=1;assert(!keyshift_match_delta(0)); /* different A/B mode */
    /* Every offered action obeys the configured distance and absolute range. */
    for(int k=0;k<24;k++) for(int j=0;j<24;j++) for(int n=-12;n<=12;n++) {
        keyshift_track_key[0]=k;keyshift_track_key[1]=j;shifts[0]=n;shifts[1]=2;
        int delta=keyshift_match_delta(0);
        if(delta) {
            assert(delta>=-2 && delta<=2 && n+delta>=-12 && n+delta<=12);
            assert(rx3_camelot_shifted(k,n+delta)==keyshift_current_key(1));
        }
    }
    keyshift_sync_harmonic=1; keyshift_sync_range=1;
    shifts[0]=shifts[1]=0;
    keyshift_track_key[0]=16;keyshift_track_key[1]=14; /* 9A / 8A */
    assert(keyshift_sync_compatible(0) && keyshift_live_count(0)==2);
    assert(keyshift_widget_kind(0,1)==RX3_PAD_STATUS);
    assert(keyshift_caption(0,1,0)[0]=='K' && keyshift_caption(0,1,0)[4]=='M'); /* KEY MATCH */
    keyshift_fire(0,1,0);assert(shifts[0]==0);
    keyshift_track_key[0]=18; /* 10A */
    assert(!keyshift_sync_compatible(0) && !keyshift_match_delta(0));
    keyshift_sync_range=2;assert(keyshift_match_delta(0)==-2);
    assert(keyshift_widget_kind(0,1)==RX3_PAD_OUTLINE_BUTTON);
    assert(keyshift_caption(0,1,0)[0]=='K'); /* KEY SYNC */
    keyshift_fire(0,1,0);assert(shifts[0]==-2 && keyshift_sync_compatible(0));
    shifts[0]=0;keyshift_track_key[0]=15; /* relative 8B / 8A */
    assert(keyshift_sync_compatible(0) && !keyshift_match_delta(0));
    keyshift_track_key[0]=-1;assert(!keyshift_sync_compatible(0) && !keyshift_match_delta(0));
    /* Exhaustive compatibility, minimality and pitch bounds, both decks shifted. */
    for(int k=0;k<24;k++) for(int j=0;j<24;j++) for(int n=-12;n<=12;n++)
    for(int other=-2;other<=2;other++) {
        keyshift_track_key[0]=k;keyshift_track_key[1]=j;shifts[0]=n;shifts[1]=other;
        int delta=keyshift_match_delta(0), best=99;
        for(int move=-2;move<=2;move++) {
            if(n+move < -12 || n+move > 12) continue;
            if(rx3_camelot_compatible(rx3_camelot_shifted(k,n+move),keyshift_current_key(1))) {
                int distance=move<0?-move:move;if(distance<best)best=distance;
            }
        }
        if(best==0 || best==99) assert(delta==0);
        else {
            assert((delta<0?-delta:delta)==best);
            assert(rx3_camelot_compatible(rx3_camelot_shifted(k,n+delta),keyshift_current_key(1)));
        }
    }
    /* The other deck is the reference: 8A -> 10A is +2, not the reverse. */
    shifts[0]=shifts[1]=0;keyshift_track_key[0]=18;keyshift_track_key[1]=14;
    keyshift_match_rules=RX3_MATCH_BOOST_TWO;
    assert(keyshift_sync_compatible(0) && !keyshift_sync_compatible(1));
    assert(!keyshift_match_delta(0));
    keyshift_sync_harmonic=0;assert(!keyshift_sync_compatible(0));
    assert(keyshift_match_delta(0)==-2);
    /* All rule combinations, both modes, pitch edges and transposed references. */
    for(unsigned mask=0;mask<16;mask+=2) for(unsigned mode=0;mode<2;mode++)
    for(int k=0;k<24;k++) for(int j=0;j<24;j++) for(int n=-12;n<=12;n+=3)
    for(int other=-1;other<=1;other++) {
        keyshift_match_rules=mask;keyshift_sync_harmonic=mode;keyshift_sync_range=3;
        keyshift_track_key[0]=k;keyshift_track_key[1]=j;shifts[0]=n;shifts[1]=other;
        int reference=keyshift_current_key(1),best=99;
        int delta=keyshift_match_delta(0);
        for(int move=-3;move<=3;move++) {
            if(n+move < -12 || n+move > 12) continue;
            int candidate=rx3_camelot_shifted(k,n+move);
            int accepted=candidate==reference || (mode &&
                (rx3_camelot_compatible(reference,candidate) ||
                 rx3_camelot_extended(reference,candidate,mask)));
            if(accepted) {int distance=move<0?-move:move;if(distance<best)best=distance;}
        }
        if(best==0 || best==99) assert(delta==0);
        else {
            assert((delta<0?-delta:delta)==best);
            int target=rx3_camelot_shifted(k,n+delta);
            assert(target==reference || (mode && rx3_camelot_matches(reference,target,mask)));
        }
    }
    /* Switching MASTER swaps the single-key and match/sync layouts. */
    master_deck=0;keyshift_sync_harmonic=1;keyshift_match_rules=0;
    shifts[0]=shifts[1]=0;keyshift_track_key[0]=14;keyshift_track_key[1]=16;
    assert(keyshift_live_count(0)==1 && keyshift_caption(0,1,0)[0]==0);
    assert(keyshift_live_count(1)==2 && keyshift_caption(1,1,0)[0]=='K');
    return 0;
}
""")

    def test_settings_file_means_the_same_to_the_deck_and_to_the_computer(self):
        """The deck's parser and the computer's reader agree, case by case.

        The computer decides what to write and tells the operator what a drive
        already says. The deck decides what to play. Those are two parsers for
        one file, and a bank that reads one way here and another way there is a
        set with the wrong sounds on the wrong pads.
        """
        from app.samples import bank as bank_module

        default = bank_module.PAD_COLOURS
        cases = [
            # text, then the deck's answer: None for refused, or the values.
            ("version=1\n", (50, 0, default, (0,) * 8, (100,) * 8)),
            ("version=1\nvolume_default=100\n", (100, 0, default, (0,) * 8, (100,) * 8)),
            ("version=1\nvolume_default=101\n", None),
            ("version=1\nvolume_default=0\n", (0, 0, default, (0,) * 8, (100,) * 8)),
            ("volume_default=20\n", None),
            ("version=2\n", None),
            ("version=1\nversion=1\n", None),
            ("version=1\nnonsense\n", None),
            ("version=1\n# a comment\n\n", (50, 0, default, (0,) * 8, (100,) * 8)),
            ("version=1\nwhat.ever=42\n", (50, 0, default, (0,) * 8, (100,) * 8)),
            # A pad name shares a key length with a pad mode and must be passed
            # over rather than mistaken for one.
            ("version=1\npad1.name=Kick\n", (50, 0, default, (0,) * 8, (100,) * 8)),
            ("version=1\npad1.color=#0a0B0c\n",
             (50, 0, (0x0A0B0C,) + default[1:], (0,) * 8, (100,) * 8)),
            ("version=1\npad1.color=0A0B0C\n", None),
            ("version=1\npad1.color=#0A0B0\n", None),
            ("version=1\npad1.color=#00FF00\npad1.color=#00FF00\n", None),
            ("version=1\npad8.mode=2\n", (50, 0, default, (0,) * 7 + (2,), (100,) * 8)),
            ("version=1\npad1.mode=0\n", (50, 0, default, (0,) * 8, (100,) * 8)),
            ("version=1\npad1.mode=3\n", (50, 0, default, (3,) + (0,) * 7, (100,) * 8)),
            ("version=1\npad1.mode=4\n", None),
            ("version=1\npad1.mode=1\npad1.mode=1\n", None),
            ("version=1\nshift.silence=1\n", (50, 1, default, (0,) * 8, (100,) * 8)),
            ("version=1\nshift.silence=2\n", None),
            ("version=1\nshift.silence=0\nshift.silence=0\n", None),
            # The deck strips one carriage return per line and nothing else.
            ("version=1\r\nvolume_default=30\r\n", (30, 0, default, (0,) * 8, (100,) * 8)),
        ]

        checks = []
        for text, expected in cases:
            literal = text.replace("\\", "\\\\").replace('"', '\\"')
            literal = literal.replace("\r", "\\r").replace("\n", "\\n")
            body = [
                "    {",
                f'        static const char text[] = "{literal}";',
                "        struct samples_config c;",
                "        int ok = samples_parse_config(text, sizeof(text) - 1u, &c);",
                f"        assert(ok == {0 if expected is None else 1});",
            ]
            if expected is not None:
                volume, silence, colours, modes, gains = expected
                body.append(f"        assert(c.volume == {volume}u);")
                body.append(f"        assert(c.shift_silence == {silence}u);")
                for index, colour in enumerate(colours):
                    body.append(f"        assert(c.colour[{index}] == 0x{colour:06x}u);")
                for index, mode in enumerate(modes):
                    body.append(f"        assert(c.mode[{index}] == {mode}u);")
                for index, level in enumerate(gains):
                    body.append(f"        assert(c.gain[{index}] == {level}u);")
            body.append("    }")
            checks.append("\n".join(body))

        self.run_c(
            '#include "samples/rx3_samples_decl.h"\n'
            '#include "samples/rx3_samples_config.h"\n'
            "int main(void) {\n" + "\n".join(checks) + "\n    return 0;\n}\n"
        )

        # The same files, read by the computer, have to mean the same thing.
        with tempfile.TemporaryDirectory() as directory:
            bank = pathlib.Path(directory) / "bank"
            bank.mkdir()
            for text, expected in cases:
                (bank / "settings.ini").write_text(text, encoding="ascii")
                read = bank_module.read_settings(bank)
                if expected is None:
                    self.assertIsNone(read, f"the computer accepted {text!r}")
                    continue
                volume, silence, colours, modes, gains = expected
                self.assertIsNotNone(read, f"the computer refused {text!r}")
                self.assertEqual(read.volume, volume, text)
                self.assertEqual(read.shift_silence, bool(silence), text)
                self.assertEqual(
                    tuple(pad.colour for pad in read.padded()), colours, text)
                self.assertEqual(tuple(pad.mode for pad in read.padded()), modes, text)
                self.assertEqual(tuple(pad.gain for pad in read.padded()), gains, text)

    def test_sample_slider_crosses_decks_and_resets_to_bank_volume(self):
        """The level is one control across both halves, and a press that lands
        outside it is declined so the player still gets the touch.

        This drives the row's own touch machine rather than a handler of the
        module's, because the module no longer has one: a panel declares a
        slider and the core maps the finger to a value.
        """
        self.run_c(r"""
#include "core/api/rx3_feature_api.h"
#include "core/ui/rx3_pad_layout.h"
#include "samples/rx3_samples_decl.h"
#include "samples/rx3_samples_state.h"
#define TAB_IMAGE_KEY_NONE 0x1603
#define PAD_COLOUR_INHERIT 0u
static const uint16_t text_empty[]={0};
static volatile unsigned int performance_refresh_pending;
/* Any non-null model will do: the row only asks whether it has one to cut
   a box from, and this test is about where the boxes land. */
static uint8_t face_model[0x54];
static const void *pad_button_face(void) { return face_model; }
static void log_number(const char *s, unsigned n) { (void)s; (void)n; }

/* The atlas is artwork, and this test is about arithmetic: stand it down and
   the captions draw nothing, which is what a deck with no artwork does too. */
static int theme_light_active;
static unsigned int pad_atlas_ready;
static struct { uint16_t cell_height, ink_left; } pad_atlas;
static unsigned int pad_atlas_cell_width(unsigned int c) { (void)c; return 0; }
static unsigned int pad_atlas_advance(unsigned int c) { (void)c; return 0; }
static unsigned int pad_atlas_text_width(const uint16_t *t) { (void)t; return 0; }
static unsigned int pad_atlas_image_id(unsigned int c, unsigned int i) { (void)c; (void)i; return 0; }
static uint32_t pad_atlas_ground_colour(unsigned int ink) { (void)ink; return 0; }
#define RX3_PAD_INK_INACTIVE 0u
#define RX3_PAD_INK_PRESSED  1u
#define RX3_PAD_INK_SELECTED 2u

/* A box is placed in the coordinates of the deck window it is drawn into, so
   every one of them has to land inside 0..639 whichever half is being painted.
   The level spans the screen, and this is the clipping that keeps deck two's
   half of it off deck one's window. */
static unsigned int boxes_drawn;
static void draw_native_box_local(void *r, const void *face, const void *m, uint8_t w,
    int x1, int y1, int x2, int y2, const uint16_t *s, uint32_t a, uint32_t b) {
    (void)r; (void)face; (void)m; (void)w; (void)y1; (void)y2; (void)s; (void)a; (void)b;
    assert(x1 <= x2);
    assert(x1 >= 0 && x2 <= 639);
    boxes_drawn++;
}
static void draw_native_image_local(void *r, const void *m, uint8_t w,
    int x1, int y1, int x2, int y2, uint32_t id) {
    (void)r; (void)m; (void)w; (void)x1; (void)y1; (void)x2; (void)y2; (void)id;
}
static unsigned int tick;
static unsigned int now_ms(void) { return tick; }
#include "core/ui/rx3_pad_widgets.h"
#include "samples/rx3_samples_panel.h"
static void hybrid_fire(unsigned d,unsigned w,unsigned p) { (void)w; samples_fire(d,1,p); }

static unsigned int status_kind=RX3_PAD_STATUS;
static unsigned int status_test_kind(unsigned d,unsigned w){(void)d;(void)w;return status_kind;}

static int touch(unsigned int deck, int x, unsigned int phase) {
    return pad_row_touch(&samples_row, deck, x - (int)deck * 640, phase);
}

int main(void) {
    struct rx3_pad_cell cells[RX3_PAD_CELL_MAX];
    int count = pad_row_cells(&samples_row, 0u, cells);
    assert(count == 2);
    int track_left = cells[0].x1, track_right = cells[0].x2;
    int readout_left = cells[1].x1;

    samples_config.volume=37; samples_volume=50;

    /* Left of the track is nobody's: the row declines and the player keeps it. */
    assert(!touch(0, track_left - 2, 1u));

    /* A tap is the first event of a drag, so the value follows at once. */
    assert(touch(0, track_left, 1u) && samples_volume==0);
    /* Across the boundary between the halves, because it is one control. */
    assert(touch(0, 640, 2u) && samples_volume > 50 && samples_volume < 60);
    assert(touch(0, track_right, 2u) && samples_volume==100);
    assert(samples_volume_touched);
    /* The release commits, and nothing follows the finger afterwards. */
    /* The firmware clears coordinates on release; preserve the last drag. */
    assert(touch(0, 0, 0u));
    assert(!touch(0, track_left + 10, 2u) && samples_volume==100);

    /* The readout is on deck two's half, and tapping it restores the bank. */
    unsigned int deck = (unsigned int)(readout_left >= 640);
    assert(touch(deck, readout_left + 4, 1u));
    assert(samples_volume==100);          /* a press alone changes nothing */
    assert(touch(deck, readout_left + 4, 0u) && samples_volume==37);

    /* Sliding off a control before releasing must not fire it. */
    samples_volume=70;
    assert(touch(deck, readout_left + 4, 1u));
    assert(touch(deck, readout_left - 40, 2u));
    assert(touch(deck, readout_left - 40, 0u) && samples_volume==70);

    assert(samples_panel_needs_refresh()); assert(!samples_panel_needs_refresh());

    /* Every level, painted into both halves, stays inside the half it is in. */
    for(unsigned volume=0;volume<=100;volume++) {
        samples_volume=volume;
        boxes_drawn = 0;
        pad_row_paint(0, 0, 0, 0u, &samples_row);
        pad_row_paint(0, 0, 1, 1u, &samples_row);
        /* Both halves paint something at every level, so a track that vanished
           into one window would be caught rather than merely not crashing. */
        assert(boxes_drawn >= 4);
    }
    /* Hybrid: tap fires, a held drag changes volume without a release toggle.
       Dragging is relative to the initial gain, never jumps to the touch point. */
    struct rx3_pad_widget hybrid_widget={RX3_PAD_TOGGLE_SLIDER,1};
    struct rx3_pad_row hybrid=samples_row;
    hybrid.fire=hybrid_fire;hybrid.widgets=&hybrid_widget;hybrid.count=1;hybrid.scope=RX3_PAD_SCOPE_DECK;
    samples_volume=100;tick=0;
    pad_row_touch(&hybrid,0,200,1);
    tick=100;pad_row_touch(&hybrid,0,200,0);
    assert(samples_volume==37); /* sample fire resets to the configured volume */
    samples_volume=100;tick=1000;
    pad_row_touch(&hybrid,0,300,1);
    tick=1200;pad_row_touch(&hybrid,0,299,2);assert(samples_volume==100);
    tick=1400;pad_row_touch(&hybrid,0,150,2);
    assert(samples_volume>70 && samples_volume<80);
    unsigned held=samples_volume;
    pad_row_touch(&hybrid,0,0,0);assert(samples_volume==held);
    tick=2000;pad_row_touch(&hybrid,0,300,1);
    tick=2400;pad_row_touch(&hybrid,0,-600,2);assert(samples_volume==0);
    pad_row_touch(&hybrid,0,0,0);assert(samples_volume==0);
    tick=3000;pad_row_touch(&hybrid,0,100,1);
    tick=3400;pad_row_touch(&hybrid,0,1000,2);assert(samples_volume==100);
    pad_row_touch(&hybrid,0,0,0);assert(samples_volume==100);
    /* Passive statuses consume complete gestures without action or repaint,
       even when the underlying state changes while the finger is down. */
    struct rx3_pad_row status=hybrid;
    struct rx3_pad_widget status_widget={RX3_PAD_STATUS,1};
    status.widgets=&status_widget;status.kind=status_test_kind;
    samples_volume=80;performance_refresh_pending=0;
    assert(pad_row_touch(&status,0,200,1));
    assert(pad_row_touch(&status,0,220,2));
    assert(pad_row_touch(&status,0,0,0));
    assert(samples_volume==80 && !performance_refresh_pending);
    assert(pad_press_deck==-1);
    assert(pad_row_touch(&status,0,200,1));status_kind=RX3_PAD_BUTTON;
    assert(pad_row_touch(&status,0,0,0));assert(samples_volume==80);
    assert(pad_row_touch(&status,0,200,1));status_kind=RX3_PAD_STATUS;
    assert(pad_row_touch(&status,0,0,0));assert(samples_volume==80);
    return 0;
}
""")

    def test_physical_modes_close_panels_before_native_dispatch(self):
        core = MODULES / "core/rx3_core_hook.c"
        functions = "\n".join(function(core, name) for name in (
            "restore_status", "leave_performance_panel", "pad_mode_key_pressed",
            "hooked_on_key_hot_cue", "hooked_on_key_beat_loop", "hooked_on_key_slip_loop",
            "hooked_on_key_beat_jump", "hooked_on_physical_key"))
        self.run_c(r'''
static unsigned samples_mode, calls, overlay_panel, native_beatfx_selected;
static unsigned beatfx_reselect_pending,beatfx_reselect_generation,refreshes,parked;
static unsigned playing_loop=1,muted_vocal=1,held_sample=1,must_be_closed;
static void samples_leave_mode(void){samples_mode=0;}
static void pad_row_clear_press(void){}
static void park_native_performance_touches(int p){parked=p;}
static void set_native(int p){native_beatfx_selected=p;}
static void (*original_set_beatfx_selected)(int)=set_native;
static void refresh_performance_ui(void){refreshes++;}
static int native(void *p,const void *i) {
 assert(p && i);calls++;
 if(must_be_closed) assert(!overlay_panel&&!native_beatfx_selected&&!beatfx_reselect_pending&&!samples_mode&&!parked);
 assert(playing_loop && muted_vocal && held_sample);
 return 7;
}
static int (*original_on_key_hot_cue)(void *,const void *)=native;
static int (*original_on_key_beat_loop)(void *,const void *)=native;
static int (*original_on_key_slip_loop)(void *,const void *)=native;
static int (*original_on_key_beat_jump)(void *,const void *)=native;
static int (*original_on_physical_key)(void *,const void *)=native;
''' + functions + r'''
int main(void) {
 uint32_t players[2][64]={{0}};uint8_t event[12]={0};event[9]=0x41;
 int (*hooks[4])(void *,const void *)={hooked_on_key_hot_cue,hooked_on_key_beat_loop,hooked_on_key_slip_loop,hooked_on_key_beat_jump};
 for(unsigned deck=0;deck<2;deck++) for(unsigned panel=1;panel<=5;panel++)
 for(unsigned key=0;key<4;key++) for(unsigned dispatch=0;dispatch<2;dispatch++) {
   overlay_panel=panel<4?panel:0;native_beatfx_selected=panel==4;
   beatfx_reselect_pending=panel==5;samples_mode=1;parked=1;
   event[8]=0x13+key;event[11]=2;must_be_closed=0;
   int (*hook)(void *,const void *)=dispatch?hooked_on_physical_key:hooks[key];
   unsigned before=refreshes,gen=beatfx_reselect_generation;
   assert(hook(players[deck],event)==7 && samples_mode);
   assert(overlay_panel==(panel<4?panel:0) && native_beatfx_selected==(panel==4));
   assert(beatfx_reselect_pending==(panel==5) && refreshes==before);
   event[11]=0;must_be_closed=1;
   assert(hook(players[deck],event)==7);
   assert(refreshes==before+1 && beatfx_reselect_generation==gen+1);
   /* Nested native dispatch must not clear and refresh a second time. */
   assert(hooks[key](players[deck],event)==7 && refreshes==before+1);
 }
 overlay_panel=3;samples_mode=1;event[8]=0x17;must_be_closed=0;
 assert(hooked_on_physical_key(players[0],event)==7 && samples_mode && overlay_panel==3);
 assert(calls==2*5*4*2*3+1);
 return 0;
}
''')

    def test_touchscreen_tabs_toggle_to_status_without_resetting_audio(self):
        core = MODULES / "core/rx3_core_hook.c"
        self.run_c(r'''
#define CUSTOM_TAB_OFFSET_Y 21u
#define CUSTOM_TAB_TOUCH_BOTTOM 431
static unsigned overlay_panel, native_beatfx_selected, beatfx_reselect_pending;
static unsigned samples_callbacks_enabled=1,tab_assets_ready=1,samples_mode;
static unsigned beatfx_reselect_generation,refreshes,parked;
static unsigned playing_loop=1,muted_vocal=1;
struct rx3_pad_row {unsigned panel_id;};
static struct rx3_pad_row rows[2]={{1},{2}};
static unsigned available=3;
static const struct rx3_pad_row *row_for_slot(unsigned i){return available&(1u<<i)?&rows[i]:0;}
static int point_in_rect(int x,int y,int l,int t,int r,int b){return x>=l&&x<=r&&y>=t&&y<=b;}
static void samples_leave_mode(void){samples_mode=0;}
static void pad_row_clear_press(void){}
static void park_native_performance_touches(int p){parked=p;}
static void set_native(int p){native_beatfx_selected=p;}
static void (*original_set_beatfx_selected)(int)=set_native;
static void refresh_performance_ui(void){refreshes++;}
static void log_line(const char *s){(void)s;}
static void select_custom_panel(unsigned p){overlay_panel=p;samples_mode=p==3;}
static int samples_enter_mode(void){select_custom_panel(3);return 1;}
static void hooked_set_beatfx_selected(int p){overlay_panel=0;samples_mode=0;native_beatfx_selected=p;}
''' + function(core, "restore_status") + function(core, "performance_tab_touch") + r'''
int main(void){
 int x[]={1135,1225,1135,1225},y[]={409,409,457,457};
 for(unsigned i=0;i<4;i++){
   assert(performance_tab_touch(x[i],y[i]));
   assert(i==3?native_beatfx_selected:overlay_panel==i+1);
   unsigned gen=beatfx_reselect_generation;
   assert(performance_tab_touch(x[i],y[i]));
   assert(!overlay_panel&&!native_beatfx_selected&&!samples_mode&&!parked);
   assert(beatfx_reselect_generation==gen+1 && playing_loop && muted_vocal);
 }
 assert(!performance_tab_touch(1135,383)); /* gap below QUANTIZE */
 assert(performance_tab_touch(1135,431)&&overlay_panel==1);
 assert(performance_tab_touch(1135,431)&&!overlay_panel);
 assert(performance_tab_touch(1135,409)&&overlay_panel==1);
 assert(performance_tab_touch(1225,409)&&overlay_panel==2);
 assert(performance_tab_touch(1135,457)&&overlay_panel==3);
 assert(performance_tab_touch(1225,457)&&!overlay_panel&&native_beatfx_selected);
 beatfx_reselect_pending=1;assert(performance_tab_touch(1225,457));
 assert(!beatfx_reselect_pending&&!native_beatfx_selected);
 samples_callbacks_enabled=0;assert(performance_tab_touch(1135,457));
 assert(!overlay_panel && !native_beatfx_selected);
 samples_callbacks_enabled=1;tab_assets_ready=0;assert(!performance_tab_touch(1135,457));
 available=1;
 assert(performance_tab_touch(1135,409)&&overlay_panel==1);
 assert(performance_tab_touch(1225,409)&&!overlay_panel);
 assert(performance_tab_touch(1180,409)&&overlay_panel==1);
 available=2;
 assert(performance_tab_touch(1135,409)&&overlay_panel==2);
 assert(performance_tab_touch(1225,409)&&!overlay_panel);
 assert(performance_tab_touch(1180,409)&&overlay_panel==2);
 available=0;
 assert(!performance_tab_touch(1135,409));
 assert(!performance_tab_touch(1180,457));assert(!performance_tab_touch(10,10));
 return 0;
}
''')

    def test_all_feature_selection_tab_combinations(self):
        core = MODULES / "core/rx3_core_hook.c"
        self.run_c(r'''
#include <stdint.h>
#define TAB_IMAGE_KEY 0x1600u
#define TAB_IMAGE_STEMS 0x1601u
#define TAB_IMAGE_STATUS_NONE 0x1602u
#define TAB_IMAGE_KEY_NONE 0x1603u
#define TAB_IMAGE_SAMPLES 0x1604u
#define TAB_IMAGE_SAMPLES_NONE 0x1605u
#define TAB_IMAGE_SAMPLES_BEATFX 0x1606u
#define TAB_IMAGE_SINGLE_KEY_NONE 0x1607u
#define TAB_IMAGE_SINGLE_KEY_SELECTED 0x1608u
#define TAB_IMAGE_SINGLE_STEMS_NONE 0x1609u
#define TAB_IMAGE_SINGLE_STEMS_SELECTED 0x160au
struct rx3_pad_row {unsigned panel_id,tab_image;};
''' + function(core, "performance_tab_image") +
            function(core, "performance_status_image") + r'''
int main(void) {
    struct rx3_pad_row key={1,TAB_IMAGE_KEY},stems={2,TAB_IMAGE_STEMS};
    const unsigned none[]={0,TAB_IMAGE_SINGLE_KEY_NONE,
                            TAB_IMAGE_SINGLE_STEMS_NONE,TAB_IMAGE_KEY_NONE};
    for(unsigned key_on=0;key_on<2;key_on++)
      for(unsigned stems_on=0;stems_on<2;stems_on++)
        for(unsigned samples_on=0;samples_on<2;samples_on++) {
          unsigned mask=key_on|stems_on<<1;
          const struct rx3_pad_row *left=key_on?&key:0,*right=stems_on?&stems:0;
          assert(performance_tab_image(left,right,0)==none[mask]);
          if(key_on)assert(performance_tab_image(left,right,1)==
                            (stems_on?TAB_IMAGE_KEY:TAB_IMAGE_SINGLE_KEY_SELECTED));
          if(stems_on)assert(performance_tab_image(left,right,2)==
                              (key_on?TAB_IMAGE_STEMS:TAB_IMAGE_SINGLE_STEMS_SELECTED));
          assert(performance_status_image(samples_on,0,0x1599u)==
                 (samples_on?TAB_IMAGE_SAMPLES_NONE:0x1599u));
          assert(performance_status_image(samples_on,1,0x1599u)==
                 (samples_on?TAB_IMAGE_SAMPLES_NONE:TAB_IMAGE_STATUS_NONE));
          if(samples_on) {
            assert(performance_status_image(1,3,0x1599u)==TAB_IMAGE_SAMPLES);
            assert(performance_status_image(1,0,0x1598u)==TAB_IMAGE_SAMPLES_BEATFX);
          }
        }
    return 0;
}
''')

    def test_stem_loader_rejects_bad_headers_and_keeps_memory_reserve(self):
        loader = MODULES / "stems/rx3_stems_loader.h"
        self.run_c(r'''
#include <stdio.h>
#include <unistd.h>
#include <sys/mman.h>
typedef struct { float left, right; } Float2;
#include "stems/rx3_stems_decl.h"
static unsigned long available=0x4b001;
static unsigned long memory_available_kb(void) { return available; }
static int read_exactly(int fd, void *p, size_t n) { return read(fd,p,n)==(ssize_t)n?0:-1; }
''' + function(MODULES / "core/rx3_core_hook.c", "release_payload") + function(loader, "stems_load_payload") + function(loader, "stems_load_set") + r'''
static void write_fixture(FILE *f, const struct stem_header *h, unsigned bytes) {
    int16_t pcm[4]={1234,-1234,2345,-2345};
    rewind(f); assert(fwrite(h,1,sizeof(*h),f)==sizeof(*h));
    assert(fwrite(pcm,1,bytes,f)==bytes); fflush(f); assert(!ftruncate(fileno(f),64+bytes));
}
int main(void) {
    FILE *f=tmpfile(); assert(f);
    struct stem_header h={.magic="RX3STM1",.sample_rate=44100,.channels=2,
        .format=FORMAT_S16,.header_size=64,.frames=2};
    struct stem_payload p={0}; write_fixture(f,&h,8);
    assert(stems_load_payload(fileno(f),&p,0)); assert(p.frames==2 && p.block_size==8);
    assert(((int16_t *)p.data)[0]==1234); munmap(p.block,p.block_size); memset(&p,0,sizeof(p));
    available=0x4b000; assert(!stems_load_payload(fileno(f),&p,0));
    available=0; assert(!stems_load_payload(fileno(f),&p,0)); available=0x4b001;
    assert(!stems_load_payload(fileno(f),&p,0x20000000));
    h.magic[7]=1; write_fixture(f,&h,8); assert(!stems_load_payload(fileno(f),&p,0)); h.magic[7]=0;
    h.reserved[31]=1; write_fixture(f,&h,8); assert(!stems_load_payload(fileno(f),&p,0)); h.reserved[31]=0;
    h.format=FORMAT_F32; write_fixture(f,&h,8); assert(!stems_load_payload(fileno(f),&p,0)); h.format=FORMAT_S16;
    h.frames=0; write_fixture(f,&h,8); assert(!stems_load_payload(fileno(f),&p,0)); h.frames=2;
    write_fixture(f,&h,4); assert(!stems_load_payload(fileno(f),&p,0));
    h.frames=1; write_fixture(f,&h,8); assert(!stems_load_payload(fileno(f),&p,0));
    assert(!p.data);
    h.frames=2; write_fixture(f,&h,8);
    FILE *shorter=tmpfile(); assert(shorter);
    h.frames=1; write_fixture(shorter,&h,4);
    struct stem_payload next[3]={0};
    int fds[3]={-1,fileno(f),fileno(f)};
    assert(!stems_load_set(fds,next,0));
    fds[0]=fileno(f); fds[1]=-1;
    assert(stems_load_set(fds,next,0)==1 && !next[1].data && !next[2].data);
    release_payload(&next[0]);
    fds[1]=fileno(shorter);
    assert(stems_load_set(fds,next,0)==1 && !next[1].data && !next[2].data);
    release_payload(&next[0]);
    fds[1]=fileno(f);
    assert(stems_load_set(fds,next,0)==3);
    for(unsigned i=0;i<3;i++) release_payload(&next[i]);
    /* Together with the other deck, only two eight-byte roles fit. */
    assert(stems_load_set(fds,next,0x20000000u-16u)==2 && !next[2].data);
    for(unsigned i=0;i<3;i++) release_payload(&next[i]);
    assert(!stems_load_set(fds,next,0x20000001u));
    fclose(shorter); fclose(f); return 0;
}
''')

    def test_theme_pixels_and_utility_choice_are_bounded(self):
        utility = MODULES / "theme-white/rx3_theme_utility.h"
        self.run_c(r'''
#include "theme-white/rx3_theme_decl.h"
#include "theme-white/rx3_theme_pixels.h"
static uint8_t table[0x774];
static uint8_t *utility_theme_table=table;
static int theme_toggle_pending;
''' + function(utility, "utility_copy_line") + function(utility, "utility_poll_theme_row") + r'''
int main(void) {
    assert(theme_pixel_light_for_image(0xa3f,0x3907,1)==0xce59);
    assert(theme_pixel_light_for_image(0xa82,0x28e6,0)==0xdedb);
    assert(theme_pixel_light_for_image(0,0xf81f,0)==0xf81f);
    assert(theme_pixel_light_for_image(0,0,0)==0xe71c);
    assert(theme_pixel_light_for_image(0,0,1)==0);
    for(unsigned pixel=0;pixel<65536;pixel++)
        if(pixel!=0xf81f) assert(theme_pixel_light_for_image(0,(uint16_t)pixel,0)!=0xf81f);
    /* The dark conversion: the transparent key and anything with real colour
       in it are left alone, and what is already grey comes down to about a
       third. The four values are computed from the reference's own shifts. */
    assert(theme_pixel_dark(0xf81f)==0xf81f);
    assert(theme_pixel_dark(0xf800)==0xf800);
    assert(theme_pixel_dark(0x0000)==0x0000);
    assert(theme_pixel_dark(0xffff)==0x52ca);
    assert(theme_pixel_dark(0x8410)==0x2965);
    assert(theme_pixel_dark(0x4208)==0x10a2);
    for(unsigned pixel=0;pixel<65536;pixel++)
        assert(theme_pixel_dark((uint16_t)pixel)!=0xf81f||pixel==0xf81f);
    uint32_t *row=(uint32_t *)(table+0x624); row[2]=2; row[4]=1;
    utility_poll_theme_row(); assert(row[4]==0xffffffff && row[3]==1 && theme_toggle_pending==2);
    utility_poll_theme_row(); assert(theme_toggle_pending==2);
    theme_toggle_pending=3; row[4]=1; utility_poll_theme_row(); assert(theme_toggle_pending==3);
    theme_toggle_pending=0; theme_light_active=1; row[4]=1; utility_poll_theme_row(); assert(!theme_toggle_pending);
    row[4]=2; utility_poll_theme_row(); assert(row[4]==2 && !theme_toggle_pending);
    uint8_t line[0x222]; memset(line,0xff,sizeof(line));
    uint16_t title[]={'D','A','R','K',0}; utility_copy_line(line,title);
    uint16_t length; memcpy(&length,line+0x20,2); assert(length==4);
    assert(!memcmp(line+0x22,title,8) && line[0x221]==0 && line[0x1f]==0xff);
    return 0;
}
''')

    def test_theme_request_during_a_draw_waits_for_the_next_render_pass(self):
        core = MODULES / "core/rx3_core_hook.c"
        theme = MODULES / "theme-white/rx3_theme_feature.h"
        self.run_c(r'''
static unsigned performance_refresh_pending, performance_refresh_reported;
static uint64_t performance_refresh_until_us, performance_refresh_next_us;
static int render_probe_enabled, drawing, pending, theme_light_active, switches, passes, invalidations, window_dirty, header_pending, header_visible;
#define PERFORMANCE_REFRESH_WINDOW_US 1000000u
#define PERFORMANCE_REFRESH_EVERY_US 100000u
static uint64_t monotonic_enough_us(void) { return 100; }
static void refresh_performance_ui(void) {}
static void log_line(const char *s) { (void)s; }
static void rx3_message_run_pending(void) {}
static unsigned int rx3_panel_take_open(void) { return 0; }
static void select_custom_panel(unsigned int id) { (void)id; }
static void theme_run_pending_toggle(void) {
    assert(!drawing);
    if(pending) { theme_light_active=!theme_light_active; pending=0; switches++; }
}
''' + function(core, "run_pending_ui") + r'''
static void native_render(void *manager) {
    assert(manager==(void *)123);
    int frame_light=theme_light_active;
    if(passes==1) { assert(window_dirty); header_visible=0; }
    if(passes==2) { assert(header_pending); header_pending=0; header_visible=1; }
    window_dirty=0;
    drawing=1;
    for(unsigned i=0;i<20;i++) {
        if(i==5 && !passes) pending=1;
        run_pending_ui();
        assert(theme_light_active==frame_light);
    }
    drawing=0; passes++;
}
static unsigned int theme_refresh_header(void) { assert(!drawing && passes==2); header_pending=1; return 1; }
static int dirty_windows(void) { assert(!drawing); invalidations++; window_dirty=1; return 1; }
#define THEME_DIRTY_WINDOWS dirty_windows
static void (*original_theme_render_pass)(void *)=native_render;
''' + function(theme, "hooked_theme_render_pass") + r'''
int main(void) {
    hooked_theme_render_pass((void *)123);
    assert(pending && !switches && !theme_light_active);
    hooked_theme_render_pass((void *)123);
    assert(!pending && switches==1 && theme_light_active && invalidations==1 && header_visible);
    hooked_theme_render_pass((void *)123);
    assert(switches==1 && passes==4 && invalidations==1 && header_visible && !header_pending);
    return 0;
}
''')

    def test_theme_refresh_queues_native_children_without_object_ids(self):
        theme = MODULES / "theme-white/rx3_theme_feature.h"
        self.run_c(r'''
#define THEME_LIST_FIRST_SLOT 20u
#define THEME_LIST_NEXT_SLOT 18u
#define THEME_CHILD_REFRESH_LIMIT 64u
struct native_list { void **vtable; unsigned index, length, cycling; void *items[3]; };
static unsigned queued;
static void *seen[64];
static void *native_first(void *p) {
    struct native_list *list=p; list->index=0;
    return list->length ? list->items[0] : 0;
}
static void *native_next(void *p) {
    struct native_list *list=p;
    if(list->cycling) return list->items[0];
    return ++list->index < list->length ? list->items[list->index] : 0;
}
static void *get_manager(void) { return (void *)123; }
static void queue_child(void *manager, int layer, void *child) {
    assert(manager==(void *)123 && layer==-1 && queued<64);
    seen[queued++]=child;
}
#define GET_HMI_MANAGER get_manager
#define REFRESH_GLYPH queue_child
''' + function(theme, "theme_queue_children") + r'''
int main(void) {
    void *vtable[21]={0};
    vtable[20]=(void *)native_first; vtable[18]=(void *)native_next;
    struct native_list list={vtable,0,3,0,{(void *)400,(void *)200,(void *)700}};
    assert(theme_queue_children(0)==0);
    assert(theme_queue_children(&list)==3 && queued==3);
    for(unsigned i=0;i<3;i++) assert(seen[i]==list.items[i]);
    list.length=0; queued=0;
    assert(theme_queue_children(&list)==0 && queued==0);
    list.length=1; list.cycling=1;
    assert(theme_queue_children(&list)==64 && queued==64);
    return 0;
}
''')

    def test_image_lookup_retries_only_after_table_exists(self):
        core = MODULES / "core/rx3_core_hook.c"
        self.run_c(r'''
static uint8_t *table;
#define IMAGE_TABLE_POINTER ((uintptr_t)&table)
static unsigned tab_assets_ready, tab_asset_attempts, installs, succeeds, lookups;
static void install_tab_assets(const char *route) { assert(route); installs++; if(succeeds) tab_assets_ready=1; }
static void *rx3_image_resolve(unsigned id,void *(*lookup)(unsigned),const void *base) {(void)id;(void)lookup;(void)base;return 0;}
static void *original_image_info(unsigned id) { assert(id==0x1600); lookups++; return (void *)123; }
''' + function(core, "hooked_image_info") + r'''
int main(void) {
    for(unsigned i=0;i<10;i++) assert(hooked_image_info(0x1600)==(void *)123);
    assert(installs==10 && tab_asset_attempts==0);
    table=(void *)1;
    for(unsigned i=0;i<7;i++) hooked_image_info(0x1600);
    assert(tab_asset_attempts==7 && installs==17);
    succeeds=1; hooked_image_info(0x1600);
    assert(tab_assets_ready && tab_asset_attempts==8 && installs==18);
    hooked_image_info(0x1600); assert(installs==18 && lookups==19);
    tab_assets_ready=0; hooked_image_info(0x1600); assert(installs==18 && lookups==20);
    return 0;
}
''')

    def test_image_lookup_uses_runtime_address_not_file_offset(self):
        core = (MODULES / "core/rx3_core_hook.c").read_text()
        def verify(source):
            self.assertEqual(source.count("&image_info_hook, 0x001d192c,"), 2)
            self.assertNotIn("&image_info_hook, 0x001c992c,", source)
        verify(core)
        with self.assertRaises(AssertionError):
            verify(core.replace("&image_info_hook, 0x001d192c,", "&image_info_hook, 0x001c992c,"))

    def test_watcher_finishes_before_feature_cleanup(self):
        core = MODULES / "core/rx3_core_hook.c"
        finalizer = function(core, "finalize").replace('__attribute__((destructor)) ', '')
        self.run_c(r'''
#include <sched.h>
static int player_process_initialized=1;
static volatile int state_thread_running=1;
static pthread_t state_thread;
static int state_thread_started=1, stopped, removed, destroyed;
#define RUNTIME_FEATURE_COUNT 1u
static void *watcher(void *unused) {
    (void)unused;
    while(__atomic_load_n(&state_thread_running,__ATOMIC_SEQ_CST)) sched_yield();
    stopped=1; return 0;
}
static void rx3_modules_stop(void) {}
static void uninstall_performance_hooks(void) { assert(stopped && !state_thread_started); removed=1; }
static void destroy(unsigned deck) { assert(removed && deck<2); destroyed++; }
static struct {void (*destroy_deck)(unsigned);} runtime_features[1]={{destroy}};
''' + finalizer + r'''
int main(void) {
    assert(!pthread_create(&state_thread,0,watcher,0));
    finalize(); assert(destroyed==2 && !state_thread_running);
    return 0;
}
''')
