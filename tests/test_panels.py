# SPDX-License-Identifier: MPL-2.0
"""Framework clients and shared stem volume semantics, without firmware calls."""
import unittest
from tests import test_framework as framework
from tests import test_runtime_transitions as transitions


class PanelTests(unittest.TestCase):
    run_units = framework.FrameworkTests.run_units
    run_c = transitions.RuntimeTransitionTests.run_c

    def test_public_client_registration_and_ownership(self):
        self.run_units('''
#include "core/api/rx3_module_api.h"
#include "core/services/rx3_panels.h"
static unsigned level;
static unsigned status_kind(unsigned d,unsigned w){(void)d;(void)w;return RX3_PAD_STATUS;}
static unsigned get(unsigned d,unsigned w){(void)d;(void)w;return level;}
static void set(unsigned d,unsigned w,unsigned v,unsigned c){(void)d;(void)w;(void)c;level=v;}
static const struct rx3_pad_widget widgets[]={{RX3_PAD_BUTTON,1},{RX3_PAD_SLIDER,3}};
static const struct rx3_pad_row row={.panel_id=7,.scope=RX3_PAD_SCOPE_DECK,.count=2,
    .widgets=widgets,.slider_get=get,.slider_set=set};
static const struct rx3_services *api;
static int start(const struct rx3_services *s){api=s;return api->panels->register_row(&row);}
static void stop(void){api->panels->unregister_row(&row);}
int main(void){
    struct rx3_services services={.panels=&rx3_panels};
    assert(start(&services)); assert(rx3_panel_count()==1);
    assert(rx3_panel_find(7)==&row); assert(start(&services));
    struct rx3_pad_row other=row;
    assert(!services.panels->register_row(&other));
    services.panels->unregister_row(&other);assert(rx3_panel_find(7)==&row);
    assert(services.panels->open(7));assert(rx3_panel_take_open()==7);
    assert(rx3_panel_take_open()==0);assert(!services.panels->open(8));
    row.slider_set(0,1,37,0);assert(row.slider_get(1,1)==37);
    assert(services.panels->open(7));stop();assert(rx3_panel_take_open()==0);
    other.panel_id=8;other.slider_set=0;
    assert(!services.panels->register_row(&other));
    const struct rx3_pad_widget status={RX3_PAD_STATUS,1};
    other.widgets=&status;other.count=1;other.kind=status_kind;other.slider_get=0;
    assert(services.panels->register_row(&other));
    services.panels->unregister_row(&other);
    other=row;other.count=9;assert(!services.panels->register_row(&other));
    assert(!rx3_panel_count());return 0;
}
''', ['core/services/rx3_panels.c'])

    def test_stem_hybrid_and_pcm_share_one_volume(self):
        self.run_c('''
typedef struct rx3_stereo Float2;
#include "core/api/rx3_panel_api.h"
#include "stems/rx3_stems_decl.h"
#define TAB_IMAGE_STEMS 0x1601u
static int blink_phase_is_on(void){return 1;}
static int stems_any_deck_loading(void){return 0;}
static void stems_blink_idle(void){}
static unsigned int tick;
static unsigned int now_ms(void){return tick;}
#include "stems/rx3_stems_panel.h"
int main(void){
    struct stems_deck_context *c=&stems_decks[0];
    c->selection=0xff;c->status=2;c->reader=c;c->armed=1;c->payload_count=3;
    stems_reset_mix(c);
    assert(stems_live_count(0)==3 && stems_widget_kind(0,0)==RX3_PAD_TOGGLE_SLIDER);
    assert(stems_widget_kind(1,0)==RX3_PAD_BUTTON);
    c->payloads[0].data=c;
    assert(stems_widget_colour(0,0)==0xf800);
    assert(stems_widget_colour(0,1)==0x07e0);
    assert(stems_widget_colour(0,2)==0x001f);
    assert(stems_control_bit(15,3)==0);
    assert(stems_control_bit(3,0)==1 && stems_control_bit(3,1)==2);
    assert(stems_control_bit(7,2)==4 && stems_control_bit(7,3)==0);
    stems_fire(0,0,0);assert(stems_slider_get(0,0)==0 && !(stems_selected(c)&1));
    assert(!stems_slider_visible(0,0));
    stems_slider_set(0,0,37,1);assert(stems_slider_get(0,0)==37 && stems_is_on(0,0,0));
    tick=9000;assert(stems_slider_visible(0,0));
    stems_slider_set(0,0,100,1);assert(stems_slider_visible(0,0));
    tick=10999;assert(stems_slider_visible(0,0));
    tick=11000;assert(!stems_slider_visible(0,0));
    stems_slider_set(0,0,0,1);assert(!stems_is_on(0,0,0) && !stems_slider_visible(0,0));
    stems_fire(0,0,0);assert(stems_slider_get(0,0)==100 && !stems_slider_visible(0,0));
    stems_slider_set(0,0,1000,1);assert(stems_slider_get(0,0)==100);
    /* Settled 50% on each role reconstructs exactly half of the original. */
    Short2 pcm[300];Float2 out[300];
    for(unsigned i=0;i<300;i++){pcm[i]=(Short2){4096,-4096};out[i]=(Float2){1,-1};}
    for(unsigned j=0;j<3;j++){c->payloads[j].data=pcm;c->payloads[j].frames=300;}
    stems_set_level(c,15,50);stems_mix(c,0,out,300);
    assert(out[299].left==0.5f && out[299].right==-0.5f);
    assert(c->transition_cursor==256);
    /* Resetting one deck does not change the other deck's settings. */
    stems_decks[1].selection=0xff;stems_set_mask(&stems_decks[1],15);
    stems_set_level(&stems_decks[1],2,23);stems_reset_mix(c);
    assert(stems_level(&stems_decks[1],2)==23);
    return 0;
}
''')

    def test_fixed_step_labels_and_current_or_adjacent_key_colours(self):
        panel = transitions.MODULES / "keyshift/rx3_keyshift_panel.h"
        self.run_c(r"""
#include "keyshift/rx3_keyshift_text.h"

#include "core/api/rx3_module_api.h"
static int keyshift_current_key(unsigned int deck);
static struct rx3_harmonic_reference reference(void) {
    int key=keyshift_current_key(1);unsigned mask=0;
    for(int i=0;i<24;i++)if(rx3_camelot_compatible(key,i))mask|=1u<<i;
    return (struct rx3_harmonic_reference){1,key,mask};
}
static const struct rx3_browse_service browse={.reference=reference};
static const struct rx3_services services={.browse=&browse};
static const struct rx3_services *framework=&services;
static int keyshift_track_key[2], shifts[2];
static unsigned int keyshift_sync_enabled=1;
static unsigned int keyshift_sync_range=1;
static unsigned int keyshift_sync_harmonic;
static unsigned int keyshift_match_rules;
static int rx3_keyshift_semitones(unsigned d) { return shifts[d]; }
""" + transitions.function(panel, "keyshift_base_key") + transitions.function(panel, "keyshift_current_key")
            + transitions.function(panel, "keyshift_reference")
            + transitions.function(panel, "keyshift_sync_compatible")
            + transitions.function(panel, "keyshift_match_delta")
            + transitions.function(panel, "keyshift_part_colour") + r"""
int main(void) {
    assert(rx3_camelot_colour(0)==0xb7fc);   /* 1A: mint */
    assert(rx3_camelot_colour(14)==0xe57d);  /* 8A: pink */
    assert(rx3_camelot_colour(23)==0x7fff);  /* 12B: cyan */
    for (int key=0;key<24;key++) for(int shift=-12;shift<=12;shift++) {
        keyshift_track_key[0]=key;shifts[0]=shift;
        uint16_t labels[3][12];keyshift_format_labels(labels,key,shift);
        assert(labels[0][0]=='-' && labels[0][1]=='1' && !labels[0][2]);
        assert(labels[2][0]=='+' && labels[2][1]=='1' && !labels[2][2]);
        for(unsigned part=0;part<3;part++) {
            int delta=part==0?-1:part==2?1:0;
            int unavailable=(part==0 && shift==-12) || (part==2 && shift==12);
            assert(keyshift_part_colour(0,0,part)==(unavailable ? 0 :
                rx3_camelot_colour(rx3_camelot_shifted(key,shift+delta))));
        }
    }
    keyshift_track_key[0]=-1;
    for(unsigned part=0;part<3;part++) assert(!keyshift_part_colour(0,0,part));
    assert(!keyshift_part_colour(2,0,0));assert(!keyshift_part_colour(0,0,3));
    assert(!rx3_camelot_colour(-1));assert(!rx3_camelot_colour(24));
    return 0;
}
""")

    def test_native_fill_keeps_all_three_components(self):
        core = transitions.MODULES / "core/rx3_core_hook.c"
        self.run_c(transitions.function(core, "pad_native_fill_colour") + r"""
int main(void) {
    assert(pad_native_fill_colour(0xff0000)==0x00001f);
    assert(pad_native_fill_colour(0x00ff00)==0x003f00);
    assert(pad_native_fill_colour(0x0000ff)==0x1f0000);
    assert(pad_native_fill_colour(0xffffff)==0x1f3f1f);
    assert(pad_native_fill_colour(0)==0);
    return 0;
}
""")

    def test_weighted_controls_fill_the_row(self):
        self.run_c('''
#include "core/ui/rx3_pad_layout.h"
int main(void){
    unsigned char weights[5]={1,2,2,2,2};struct rx3_pad_cell cells[8];
    for(int span=100;span<1300;span++){
        assert(rx3_pad_solve(weights,5,19,span,cells)==5);
        assert(cells[0].x1==19 && cells[4].x2==19+span-1);
        for(int i=0;i<5;i++){
            assert(rx3_pad_slider_value(cells[i],cells[i].x1,100)==0);
            assert(rx3_pad_slider_value(cells[i],cells[i].x2,100)==100);
        }
    }return 0;
}
''')
