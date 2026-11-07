/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_KEYSHIFT_EFFECTIVE_H
#define RX3_KEYSHIFT_EFFECTIVE_H
/* The key a deck is heard in. With MASTER TEMPO off the tempo fader moves the
 * pitch too, so the heard key is the analysed key moved by the nearest whole
 * number of semitones, 12*log2(1+tempo). A tempo more than 25 cents away from
 * that semitone is shown with a "~".
 *
 * The native deck line is left alone: Ui_CycleTask copies it into the GUI
 * buffer through ConvertPlayTitle2Gui whenever the per-deck flag
 * Ui_MemoryCueCommentUpdate is set, and only that copy is rewritten here.
 * Firmware 1.19 addresses; every entry is guarded. */
#define EFFECTIVE_TITLE_TO_GUI ((unsigned long)0x0027b0e8u)
#define EFFECTIVE_TEMPO_RATE ((unsigned long)0x000fd2dcu)
#define EFFECTIVE_TEMPO_RANGE ((unsigned long)0x000fd2b4u)
#define EFFECTIVE_MASTER_TEMPO ((unsigned long)0x000fd30cu)
#define EFFECTIVE_GUI_KEY_LINE 0x03268bf0u
#define EFFECTIVE_TITLE_REFRESH 0x0326f8a8u
#define EFFECTIVE_LINE_STRIDE 0x238u
static const uint8_t effective_title_to_gui_guard[8]={0xf0,0x47,0x2d,0xe9,0x00,0x40,0xa0,0xe1};
static const uint8_t effective_tempo_rate_guard[8]={0x24,0x30,0x9f,0xe5,0x00,0x10,0xa0,0xe1};
static const uint8_t effective_tempo_range_guard[8]={0x1c,0x30,0x9f,0xe5,0x00,0x10,0xa0,0xe1};
static const uint8_t effective_master_tempo_guard[8]={0x08,0x40,0x2d,0xe9,0x00,0x10,0xa0,0xe1};
static int (*effective_tempo_rate)(int)=(void *)EFFECTIVE_TEMPO_RATE;
static int (*effective_master_tempo)(int)=(void *)EFFECTIVE_MASTER_TEMPO;
static void (*effective_original_gui)(int);
static struct installed_hook effective_gui_hook;
static unsigned effective_callbacks,effective_enabled;
/* Heard shift per deck: tempo semitones in bits 0-7 (signed), "~" in bit 8,
 * and the KEY shift in bits 9-13 so a KEY change also refreshes the line. */
static unsigned effective_state[2];
static uint64_t effective_polled;

/* Tempo in 0.01 % where the heard pitch crosses each quarter semitone, from
 * -24.5 to +12.5 semitones (the WIDE range reaches -100 % and +100 %). */
static const int16_t effective_quarters[149]={
    -7571,-7536,-7500,-7464,-7427,-7389,-7351,-7313,-7274,-7234,-7194,-7153,
    -7112,-7070,-7027,-6984,-6940,-6895,-6850,-6804,-6758,-6711,-6663,-6614,
    -6565,-6515,-6464,-6413,-6361,-6308,-6254,-6200,-6145,-6088,-6031,-5974,
    -5915,-5856,-5795,-5734,-5672,-5609,-5545,-5481,-5415,-5348,-5281,-5212,
    -5142,-5072,-5000,-4927,-4854,-4779,-4703,-4626,-4548,-4468,-4388,-4306,
    -4223,-4139,-4054,-3967,-3880,-3791,-3700,-3609,-3516,-3421,-3326,-3229,
    -3130,-3030,-2929,-2826,-2722,-2616,-2509,-2399,-2289,-2177,-2063,-1948,
    -1831,-1712,-1591,-1469,-1345,-1219,-1091,-961,-830,-697,-561,-424,
    -285,-143,0,145,293,443,595,749,906,1064,1225,1388,
    1554,1722,1892,2065,2240,2419,2599,2782,2968,3157,3348,3543,
    3740,3939,4142,4348,4557,4768,4983,5201,5422,5646,5874,6105,
    6339,6577,6818,7063,7311,7563,7818,8077,8340,8607,8877,9152,
    9431,9713,10000,10291,10586
};
/* Nearest semitone for a tempo in 0.01 %, with bit 8 set more than 25 cents off. */
static unsigned keyshift_effective_shift(int rate)
{
    unsigned count=sizeof(effective_quarters)/sizeof(effective_quarters[0]);
    if(rate<effective_quarters[0])return (unsigned)(-24 & 0xff)|0x100u;
    unsigned q=0;
    while(q+1u<count && effective_quarters[q+1u]<=rate)q++;
    /* Quarter q spans [-24.5 + q/4, -24.5 + (q+1)/4) semitones. */
    int quarter=(int)q-98;
    int semitone=quarter>=-2?(quarter+2)/4:-((-quarter+1)/4);
    int offset=quarter-4*semitone;
    unsigned off=offset!=-1 && offset!=0;
    return ((unsigned)semitone&0xffu)|(off?0x100u:0u);
}
static int keyshift_tempo_semitones(unsigned deck)
{
    if(deck>1 || !effective_enabled)return 0;
    int semitones=(int)(__atomic_load_n(&effective_state[deck],__ATOMIC_SEQ_CST)&0xffu);
    return semitones>=128?semitones-256:semitones;
}
static int keyshift_effective_marked(unsigned deck)
{
    return deck<2 && effective_enabled &&
        (__atomic_load_n(&effective_state[deck],__ATOMIC_SEQ_CST)&0x100u);
}
/* Rewrite the GUI copy of the deck's key line in the notation it already uses. */
static void keyshift_effective_gui(int deck)
{
    __atomic_add_fetch(&effective_callbacks,1u,__ATOMIC_SEQ_CST);
    effective_original_gui(deck);
    int shift=deck>=0 && deck<2?keyshift_tempo_semitones((unsigned)deck)+rx3_keyshift_semitones((unsigned)deck):0;
    if(deck>=0 && deck<2 && (shift || keyshift_effective_marked((unsigned)deck))) {
        uint8_t *line=(uint8_t *)(unsigned long)(EFFECTIVE_GUI_KEY_LINE+(unsigned)deck*EFFECTIVE_LINE_STRIDE);
        uint16_t kind,length,text[16];
        memcpy(&kind,line+8,2);memcpy(&length,line+32,2);
        if(kind==15 && length>0 && length<=13) {
            memcpy(text,line+34,length*2u);
            int key=keyshift_key_from_glyph_text(text,length);
            int heard=rx3_camelot_shifted(key,shift);
            if(heard>=0) {
                uint16_t *out=text;
                if(text[0]>='0' && text[0]<='9')out=keyshift_put_camelot(out,heard);
                else for(const char *name=rx3_camelot_classic[heard];*name;name++)*out++=(uint16_t)*name;
                if(keyshift_effective_marked((unsigned)deck))*out++='~';
                length=(uint16_t)(out-text);
                memcpy(line+34,text,length*2u);memset(line+34+length*2u,0,2);
                memcpy(line+32,&length,2);
            }
        }
    }
    __atomic_sub_fetch(&effective_callbacks,1u,__ATOMIC_SEQ_CST);
}
/* Core watcher thread: a still HOME draws no text, so the render path cannot
 * drive this. Reads the tempo ten times a second at most. */
static void keyshift_effective_poll(void)
{
    if(!effective_enabled)return;
    uint64_t now=monotonic_enough_us();
    if(now-effective_polled<100000u)return;
    effective_polled=now;
    for(unsigned deck=0;deck<2;deck++) {
        unsigned state=effective_master_tempo((int)deck)?0u:keyshift_effective_shift(effective_tempo_rate((int)deck));
        state|=((unsigned)(rx3_keyshift_semitones(deck)+12)&0x1fu)<<9;
        if(state==__atomic_exchange_n(&effective_state[deck],state,__ATOMIC_SEQ_CST))continue;
        /* The next Ui_CycleTask pass copies the line again, through our hook. */
        __atomic_store_n((unsigned *)(unsigned long)(EFFECTIVE_TITLE_REFRESH+deck*4u),1u,__ATOMIC_SEQ_CST);
        /* Republish without storing the key: the render and load threads
         * store first, then publish, so a key read before theirs is redone. */
        int key;
        do {
            key=keyshift_base_key(deck);
            if(framework->browse && framework->browse->deck_key)
                framework->browse->deck_key(deck,rx3_camelot_shifted(key,keyshift_tempo_semitones(deck)),
                                            rx3_keyshift_semitones(deck));
        } while(key!=keyshift_base_key(deck));
        __atomic_store_n(&keyshift_refresh_pending,1u,__ATOMIC_SEQ_CST);
    }
}
static void keyshift_effective_remove(void)
{
    int hooked=effective_original_gui && detach_hook(&effective_gui_hook);
    while(__atomic_load_n(&effective_callbacks,__ATOMIC_SEQ_CST))usleep(1000);
    if(hooked){release_hook(&effective_gui_hook);effective_original_gui=0;}
    effective_enabled=0;
    __atomic_store_n(&effective_state[0],0u,__ATOMIC_SEQ_CST);
    __atomic_store_n(&effective_state[1],0u,__ATOMIC_SEQ_CST);
}
static int keyshift_effective_install(void)
{
    const char *value=getenv("RX3_EFFECTIVE_KEY");
    if(!value || value[0]!='1' || value[1])return 0;
#if defined(__arm__)
    if(memcmp((const void *)EFFECTIVE_TEMPO_RATE,effective_tempo_rate_guard,8) ||
       memcmp((const void *)EFFECTIVE_TEMPO_RANGE,effective_tempo_range_guard,8) ||
       memcmp((const void *)EFFECTIVE_MASTER_TEMPO,effective_master_tempo_guard,8))return 0;
    effective_original_gui=(void *)install_hook(&effective_gui_hook,EFFECTIVE_TITLE_TO_GUI,
                                                effective_title_to_gui_guard,(void *)keyshift_effective_gui,
                                                (void **)&effective_original_gui);
    if(!effective_original_gui)return 0;
    effective_enabled=1;
    log_line("keyshift: heard key follows the tempo fader with MASTER TEMPO off");
    return 1;
#else
    return 0;
#endif
}
#endif
