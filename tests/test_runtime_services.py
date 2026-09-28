# SPDX-License-Identifier: MPL-2.0
"""Exercise shared services without firmware addresses or a connected player."""
import unittest
from tests import test_framework as harness


class RuntimeServiceTests(unittest.TestCase):
    run_units = harness.FrameworkTests.run_units

    def test_notices_copy_replace_preempt_expire_and_cancel(self):
        self.run_units(r'''
#include "core/services/rx3_notice.h"
static int a,b,shows,hides;
static const uint16_t *retained;
static unsigned int deck_seen;
static void render(unsigned int deck,const uint16_t *text,int show) {
    if(show) { assert(!retained);retained=text;deck_seen=deck;shows++; }
    else { assert(retained && deck==deck_seen);retained=0;hides++; }
    /* A native renderer may synchronously trigger another draw. */
    rx3_notice_pump(10,1,render);
}
int main(void) {
    uint16_t text[]={'A',0}, other[]={'B',0};
    struct rx3_notice n={&a,1,0,RX3_NOTICE_INFO,100,text};
    assert(!rx3_notices.available());assert(rx3_notices.post(&n)==RX3_NOTICE_OK);
    text[0]='X';rx3_notice_pump(10,1,render);
    assert(rx3_notices.available() && shows==1 && retained[0]=='A');
    n.owner=&b;n.text=other;n.deck=1;n.priority=RX3_NOTICE_ERROR;n.duration_ms=20;
    assert(rx3_notices.post(&n)==RX3_NOTICE_OK);
    assert(retained[0]=='A');rx3_notice_pump(20,1,render);
    assert(shows==2 && hides==1 && retained[0]=='B' && deck_seen==1);
    rx3_notice_pump(40,1,render);assert(shows==3 && retained[0]=='A');
    rx3_notice_pump(110,1,render);assert(!retained && hides==3);
    n.owner=&a;n.deck=0;n.text=text;n.duration_ms=50;
    assert(rx3_notices.post(&n)==RX3_NOTICE_OK);rx3_notice_pump(200,1,render);
    text[0]='Y';assert(rx3_notices.post(&n)==RX3_NOTICE_OK);assert(retained[0]=='X');
    rx3_notice_pump(210,1,render);assert(retained[0]=='Y');
    assert(rx3_notices.cancel(&b,1)==RX3_NOTICE_OK);rx3_notice_pump(220,1,render);assert(retained);
    assert(rx3_notices.cancel(&a,1)==RX3_NOTICE_OK);rx3_notice_pump(230,1,render);assert(!retained);
    n.deck=RX3_NOTICE_GLOBAL;assert(rx3_notices.post(&n)==RX3_NOTICE_INVALID);
    n.deck=0;n.duration_ms=0;assert(rx3_notices.post(&n)==RX3_NOTICE_INVALID);
    n.duration_ms=20;
    for(unsigned int i=0;i<RX3_NOTICE_CAPACITY;i++){n.id=i;assert(rx3_notices.post(&n)==RX3_NOTICE_OK);}
    n.id=99;assert(rx3_notices.post(&n)==RX3_NOTICE_FULL);
    n.id=0;assert(rx3_notices.post(&n)==RX3_NOTICE_OK);
    rx3_notice_pump(240,0,render);assert(!rx3_notices.available());
    rx3_notice_pump(250,1,render);assert(!retained);
    uint16_t long_text[RX3_NOTICE_TEXT_UNITS+1];
    for(unsigned int i=0;i<RX3_NOTICE_TEXT_UNITS;i++)long_text[i]='L';
    long_text[RX3_NOTICE_TEXT_UNITS]=0;n.text=long_text;
    assert(rx3_notices.post(&n)==RX3_NOTICE_INVALID);
    return 0;
}
''', ['core/services/rx3_notice.c'])

    def test_concurrent_notice_producers_never_mix_deck_and_text(self):
        self.run_units(r'''
#include <sched.h>
#include "core/services/rx3_notice.h"
static int owners[2];static unsigned int done,shown;
static void *producer(void *arg) {
    unsigned int deck=(unsigned int)(uintptr_t)arg;
    uint16_t text[]={(uint16_t)('A'+deck),0};
    struct rx3_notice n={&owners[deck],1,deck,0,2,text};
    for(unsigned int i=0;i<10000;i++) {
        enum rx3_notice_result r;
        do {r=rx3_notices.post(&n);if(r==RX3_NOTICE_BUSY)sched_yield();}while(r==RX3_NOTICE_BUSY);
        assert(r==RX3_NOTICE_OK);
    }
    __atomic_add_fetch(&done,1,__ATOMIC_SEQ_CST);return 0;
}
static void render(unsigned int deck,const uint16_t *text,int show) {
    if(show){assert(deck<2 && text[0]=='A'+deck && !text[1]);shown++;}
}
int main(void) {
    pthread_t a,b;assert(!pthread_create(&a,0,producer,(void *)0));
    assert(!pthread_create(&b,0,producer,(void *)1));
    uint64_t now=0;
    while(__atomic_load_n(&done,__ATOMIC_SEQ_CST)!=2){rx3_notice_pump(now++,1,render);sched_yield();}
    pthread_join(a,0);pthread_join(b,0);rx3_notice_pump(now,1,render);assert(shown);return 0;
}
''', ['core/services/rx3_notice.c'], ['-pthread'])

    def test_dsp_scaling_block_boundaries_levels_and_time(self):
        self.run_units(r'''
#include "core/api/rx3_dsp.h"
int main(void) {
    int16_t pcm[]={-32768,32767,0,16384};float out[4];
    rx3_dsp.pcm16_to_float(out,pcm,2);
    assert(out[0]==-1 && out[1]==32767.0f/32768 && out[2]==0 && out[3]==0.5f);
    float whole[16],split[16];for(unsigned int i=0;i<16;i++)whole[i]=split[i]=1;
    struct rx3_gain_ramp a={0,1,0,4},b=a;
    rx3_dsp.gain(whole,8,&a);rx3_dsp.gain(split,1,&b);rx3_dsp.gain(split+2,2,&b);rx3_dsp.gain(split+6,5,&b);
    assert(!memcmp(whole,split,sizeof whole) && a.cursor==4 && b.cursor==4);
    assert(whole[0]==0.25f && whole[1]==0.25f && whole[6]==1 && whole[15]==1);
    struct rx3_gain_ramp immediate={1,0.5f,0,0};rx3_dsp.gain(whole,8,&immediate);
    assert(whole[15]==0.5f);
    float signal[]={-1,1,-0.5f,0.5f};
    struct rx3_audio_level level=rx3_dsp.level(signal,2);
    assert(level.peak==1 && level.mean_square==0.625f);
    rx3_dsp.mix(signal,signal,2,-1);for(unsigned int i=0;i<4;i++)assert(signal[i]==0);
    assert(rx3_dsp.frames_from_ms(1000,48000)==48000);
    assert(rx3_dsp.frames_from_ms(1,44100)==44);
    assert(rx3_dsp.frames_from_ms(0xffffffffu,192000)==824633720640ULL);
    assert(rx3_dsp_loop_edge(0,128)==1.0f/32 && rx3_dsp_loop_edge(127,128)==1.0f/32);
    assert(rx3_dsp_loop_edge(0,32)==1 && rx3_dsp_loop_edge(32,128)==1);
    return 0;
}
''', ['core/services/rx3_dsp.c'])
