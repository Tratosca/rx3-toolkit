# SPDX-License-Identifier: MPL-2.0
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.services import browse_columns
from app.localization import LocalizedError
from app.ui.bridge import Bridge
from app.runtime import build
from tests import test_framework

class BrowseColumnsTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_added_and_preserved_fields_share_one_metadata_request(self):
        self.run_units(r'''
#include "core/services/rx3_browse.c"
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)h;(void)a;(void)g;(void)r;(void)o;return 0;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
static unsigned requests,streams,position,freed;
static int meta(void *db,unsigned kind,unsigned id){assert(db && kind==2 && id==42);requests++;return 2;}
static int rec(void *db,unsigned k,unsigned *f,unsigned n,unsigned x,unsigned y,unsigned z) {
    (void)db;assert(k==2 && *f==0 && n==2 && !x && y==2 && !z);streams++;position=0;return 1;
}
static int next(void *db,uint32_t *r,int a,void *b){(void)db;assert(!a && !b);r[2]=position++?7:13;return 1;}
static uint16_t *fmt(uint32_t a,uint32_t b,unsigned kind,unsigned flags) {
    (void)a;(void)b;assert(flags==65535);
    static uint16_t bpm[]={'1','2','8','.','0',' ','b','p','m',0},artist[]={'D','J',0};
    return kind==13?bpm:artist;
}
static void done(void *db){assert(db);}
static void drop(void *p){assert(p);freed++;}
int main(void) {
    assert(semantic_field(52,7)==7 && semantic_field(120,13)==13);
    assert(semantic_field(52,0)==15 && semantic_field(15,7)==15);
    uint32_t db[8]={0};uint16_t bpm[128],artist[128];
    metadata=meta;records=rec;next_record=next;format=fmt;skip=done;free_text=drop;
    values_for(db,42,1,13,bpm,7,artist);
    assert(requests==1 && streams==1 && freed==2);
    assert(bpm[4]=='0' && !bpm[5] && artist[0]=='D' && artist[1]=='J');
    values_for(db,42,1,15,bpm,0,artist);assert(requests==1 && bpm[0]=='1' && bpm[1]=='A');
    values_for(db,42,1,13,bpm,13,artist);
    assert(requests==2 && freed==3 && !memcmp(bpm,artist,12));
    return 0;
}
''', [], flags=('-Wno-unused-function',))

    def test_setting_is_data_and_reaches_the_packaged_module(self):
        self.assertEqual(browse_columns.files(), {'column.txt': b'13\n'})
        for value in (None, True, 0, 14, '15', '$(id)'):
            with self.assertRaises(LocalizedError): browse_columns.files(value)
        result=SimpleNamespace(output='autoexec.bin',size=1,sha256='x',patches=('browse-columns',))
        bridge=Bridge()
        with patch('app.ui.bridge.build_module.build_runtime',return_value=result) as writer, patch.object(bridge,'_settle'):
            bridge._build('1.19',['browse-columns'],pathlib.Path('key'),pathlib.Path('.'),None,build.Cancellation(),1,'identical',3,15)
        supplied=writer.call_args.kwargs['supplied_files']
        self.assertEqual(supplied,{'browse-columns':{'column.txt':b'15\n'}})
        selected=build.resolve_patches(build.discover_patches(None,'1.19'),['browse-columns'])
        self.assertEqual(build._validate_supplied_files(supplied,selected),supplied)

    def test_row_extension_survives_native_utf16_strings_and_capacity(self):
        self.run_units(r'''
#include "core/services/rx3_browse.c"
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)h;(void)a;(void)g;(void)r;(void)o;return 0;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
int main(void) {
    uint8_t source[600]={0},dest[600]={0};uint16_t value[128]={0};
    put_half(source,7);put_half(source+20,255);
    for(unsigned i=0;i<255;i++)put_half(source+22+i*2,'a');
    for(unsigned n=0;n<=127;n++) {
        for(unsigned i=0;i<128;i++)value[i]=i<n?'x':0;
        unsigned bytes=append(dest,source,value,0),length=half(dest+20);
        assert(bytes==532 && length==255 && half(dest)==7);
        for(unsigned i=0;i<length;i++)assert(half(dest+22+i*2)!=0);
        assert(half(dest+22+(length-2)*2)==END);
        assert(half(dest+22+(length-1)*2)==SEP);
        assert(half(dest+22+(length-n-3)*2)==1); /* absent badge is not NUL */
    }
    key_text(1,value);assert(value[0]=='1' && value[1]=='A');
    key_text(24,value);assert(value[0]=='1'&&value[1]=='2'&&value[2]=='B');
    key_text(0,value);assert(!value[0]);
    /* A surrogate pair is truncated as a unit, never split across columns. */
    put_half(source+22+249*2,0xd83d);put_half(source+22+250*2,0xde00);
    value[0]='x';value[1]=0;append(dest,source,value,42);
    assert(half(dest+20)==254 && half(dest+22+248*2)==0x2026);
    assert(!rx3_browse.column(0,0) && !rx3_browse.marker(0,0));
    return 0;
}
''',[])

    def test_preserved_column_keeps_filter_header_and_native_green(self):
        self.run_units(r'''
#include "core/services/rx3_browse.c"
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)h;(void)a;(void)g;(void)r;(void)o;return 0;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
int main(void){
    uint8_t entry[532]={0},replacement[532]={0};
    const uint16_t artist[]={'A','r','t',0};
    put_half(entry,98);put_half(entry+20,1);put_half(entry+22,'F');
    unsigned category=98;
    assert(replace_row_field(entry,replacement,artist,7,0,&category)==entry);
    assert(category==98 && half(entry+22)=='F');
    category=52;
    assert(replace_row_field(entry,replacement,artist,7,1,&category)==replacement);
    assert(category==52 && half(replacement+20)==3 && half(replacement+22)=='A');
    category=13;replace_row_field(entry,replacement,artist,7,1,&category);
    assert(category==7);
    return 0;
}
''', [])

    def test_shared_hook_keeps_the_other_provider_registered(self):
        self.run_units(r'''
static int firmware_guard(const void *a,const void *b,size_t n){(void)a;(void)b;assert(n==8);return 0;}
#define memcmp firmware_guard
#include "core/services/rx3_browse.c"
#undef memcmp
static unsigned installed,detached,released,paints,loads;
static int native_load(unsigned event){loads++;return (int)event;}
static void paint(void *render,void *model){
    (void)render;const uint8_t *m=model;paints++;
    assert(half(m+0x10)==0x0801 && word(m+8)==123);
    assert(half(m+0x18)==1126 && half(m+0x1c)==1258);
    assert(m[0x38]==3 && word(m+0x28)==0);
}
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)g;assert((a==ROW_HOOK||a==0x20805cu||a==0x207dd0u||a==0x11d9b0u||a==0x11d83cu||a==0x2596ccu||a==0x104edcu||a==0x171780u||a==0x153530u||a==0x2995c8u||a==0x2955d8u||a==0x29992cu)&&r);h->record=(void *)1;installed++;void *original=a==ROW_HOOK?(void *)1:(void *)native_load;memcpy(o,&original,sizeof(original));return 1;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;detached++;return 1;}
int release_hook(struct installed_hook *h){h->record=0;released++;return 1;}
static unsigned category(unsigned a,unsigned b,unsigned c){(void)a;(void)b;return c;}
static unsigned image(unsigned c){(void)c;return 0;}
int main(void){
    const unsigned char a=1,b=2,other=3;static const uint16_t caption[]={'B','P','M',0};
    const struct rx3_browse_column col={13,caption};const struct rx3_browse_marker mark={category,image};
    assert(rx3_browse.column(&a,&col) && rx3_browse.marker(&b,&mark));
    assert(installed==12 && rx3_browse_count());
    assert(list_load1(42)==0 && list_load2(42)==0 && loads==0);
    column=0;assert(list_load1(42)==42 && list_load2(42)==42 && loads==2);column=&col;
    uint32_t heading[21]={0};heading[2]=123;heading[4]=0x0801;
    unsigned root=0;root_pointer=&root;
    uint8_t context[0x18000]={0};unsigned count=1;memcpy(context+0x17ea8,&count,4);
    put_half(context+0x17eb0,4);list_context=context;
    caption_object=heading;caption_ready=1;track_list=1;
    assert(native_track_layout());
    rx3_browse_caption(0,heading,paint);assert(paints==1);
    rx3_browse_caption(0,caption_model,paint);assert(paints==1);
    track_list=0;rx3_browse_caption(0,heading,paint);assert(paints==1);
    track_list=1;put_half(context+0x17eb0,7);assert(!native_track_layout());
    rx3_browse_caption(0,heading,paint);assert(paints==1);
    assert(!rx3_browse.column(&other,&col) && !rx3_browse.marker(&other,&mark));
    rx3_browse.unregister_owner(&other);assert(column==&col && marker==&mark);
    rx3_browse.unregister_owner(&a);assert(!column && marker==&mark && detached==9);
    rx3_browse.unregister_owner(&b);assert(!rx3_browse_count() && detached==12 && released==12);
    assert(rx3_browse.column(&a,&col) && installed==24);
    rx3_browse.unregister_owner(&a);assert(detached==24 && released==24);
    return 0;
}
''',[])

    def test_failed_touch_hook_leaves_marker_and_no_partial_column(self):
        self.run_units(r'''
static int firmware_guard(const void *a,const void *b,size_t n){(void)a;(void)b;(void)n;return 0;}
#define memcmp firmware_guard
#include "core/services/rx3_browse.c"
#undef memcmp
static unsigned detached,released;
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)g;(void)r;if(a==0x11d83cu){void *empty=0;memcpy(o,&empty,sizeof(empty));return 0;}h->record=(void *)1;void *original=(void *)1;memcpy(o,&original,sizeof(original));return 1;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;detached++;return 1;}
int release_hook(struct installed_hook *h){h->record=0;released++;return 1;}
static unsigned category(unsigned a,unsigned b,unsigned c){(void)a;(void)b;return c;}
static unsigned image(unsigned c){(void)c;return 0;}
int main(void){
    unsigned a=1,b=2;const uint16_t caption[]={'B',0};
    const struct rx3_browse_marker mark={category,image};
    const struct rx3_browse_column col={13,caption};
    assert(rx3_browse.marker(&a,&mark));
    assert(!rx3_browse.column(&b,&col));
    assert(!column && marker==&mark && original_rows);
    assert(!original_load[0] && !original_load[1] && detached==1 && released==1);
    rx3_browse.unregister_owner(&b);assert(marker==&mark && detached==1);
    rx3_browse.unregister_owner(&a);assert(!rx3_browse_count() && detached==4 && released==4);
    return 0;
}
''',[])

    def test_failed_sort_hook_rolls_back_without_stopping_key_match(self):
        self.run_units(r'''
static int firmware_guard(const void *a,const void *b,size_t n){(void)a;(void)b;(void)n;return 0;}
#define memcmp firmware_guard
#include "core/services/rx3_browse.c"
#undef memcmp
static unsigned detached,released,fail_at;
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)g;(void)r;if(a==fail_at){void *empty=0;memcpy(o,&empty,sizeof(empty));return 0;}h->record=(void *)1;void *original=(void *)1;memcpy(o,&original,sizeof(original));return 1;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;detached++;return 1;}
int release_hook(struct installed_hook *h){h->record=0;released++;return 1;}
static unsigned category(unsigned a,unsigned b,unsigned c){(void)a;(void)b;return c;}
static unsigned image(unsigned c){(void)c;return 0;}
int main(void){
    unsigned a=1,b=2;const uint16_t caption[]={'B',0};
    const struct rx3_browse_marker mark={category,image};
    const struct rx3_browse_column col={13,caption};
    unsigned failures[]={0x104edcu,0x171780u,0x153530u,0x2995c8u,0x2955d8u,0x29992cu};
    for(unsigned i=0;i<sizeof(failures)/sizeof(*failures);i++){
    fail_at=failures[i];detached=released=0;unsigned expected=3+i;
    assert(rx3_browse.marker(&a,&mark));
    assert(!rx3_browse.column(&b,&col));
    assert(!column && marker==&mark && original_rows);
    assert(!original_load[0] && !original_load[1] && detached==expected && released==expected);
    rx3_browse.unregister_owner(&b);assert(marker==&mark && detached==expected);
    rx3_browse.unregister_owner(&a);assert(!rx3_browse_count() && detached==expected+3 && released==expected+3);
    }
    return 0;
}
''',[])

    def test_sort_gestures_and_native_request_handoff(self):
        self.run_units(r'''
#include "core/services/rx3_browse.c"
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)h;(void)a;(void)g;(void)r;(void)o;return 0;}
int hook_is_installed(const struct installed_hook *h){(void)h;return 0;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
static int visible=1,menu=0,requests,commands,forwarded;
static unsigned task_id(void){return 1;}
static unsigned selector,compare_flags,compare_second,compare_third,stock_keys;
static int comparator(void *g,unsigned n,unsigned f,unsigned b,unsigned c){assert(g==(void *)0x032c682cu && n==9);compare_flags=f;compare_second=b;compare_third=c;return 0;}
static void native_keys(unsigned n,unsigned c,int g){assert(n==9 && c==4 && g==0);stock_keys++;}
static int is_visible(void){return visible;}
static int is_menu(void){return menu;}
static int enter(void){commands++;return 1;}
static int request(void *c,unsigned item,unsigned device){(void)c;assert(device==7);requests++;selector=item;return 0;}
static int sorted(void *c,void *r,void *q,int code,const uint16_t *label){(void)c;(void)r;(void)q;assert(code==0xc004 && !label[0]);return 42;}
static int validate(void *c,void *m){(void)c;(void)m;return 1;}
static int passthrough(void *c,void *r,void *q){(void)c;(void)r;(void)q;forwarded++;return 9;}
int main(void){
    const uint16_t label[]={'B',0};const struct rx3_browse_column col={13,label};
    assert(observed_sort(8)==136 && observed_sort(0x4008)==8 && observed_sort(0xc004)==132 && observed_sort(2)==2);
    native_task=task_id;
    original_sort_keys=native_keys;set_sort_type=comparator;
    sort_keys(9,4,0);assert(stock_keys==1);
    sort_keys(9,0x4004,0);assert(compare_flags==4 && compare_second==1 && compare_third==3);
    task_sort[1]=0xc004;sort_keys(9,4,0);assert(compare_flags==0x84);task_sort[1]=0;
    sort_keys(9,0x4008,0);assert(compare_flags==4);
    sort_keys(9,0xc002,1);assert(compare_flags==0xc2);
    sort_keys(9,0xc001,0);assert(compare_flags==0x81 && compare_second==3 && !compare_third);
    primary_field=4;secondary_field=7;
    column=&col;track_list=1;browse_visible=is_visible;track_layout=is_visible;menu_visible=is_menu;post_sort=enter;
    assert(header_at(434,50)==1 && header_at(855,75)==2 && header_at(1118,99)==3);
    assert(!header_at(1200,100) && !header_at(433,75));
    assert(rx3_browse_touch(1200,75,1) && !commands);
    assert(rx3_browse_touch(1200,75,1) && !commands);
    assert(rx3_browse_touch(1200,75,0) && commands==1 && sort_pending==4);
    sort_pending=0;sort_observed=4;
    rx3_browse_touch(1200,75,1);rx3_browse_touch(1200,75,0);assert(sort_pending==132);
    uint8_t context[0x7000]={0},message[128]={0};unsigned command=0x10fe,magic=0x52583353,device=7;
    memcpy(message+0x24,&command,4);memcpy(message+0x28,&magic,4);memcpy(message+0x68,&device,4);
    native_sort_request=request;original_sort_validate=validate;
    assert(sort_validate(context,message)==0 && requests==1 && selector==0x7e84);
    put_half(message+0x78,selector);
    send_sorted=sorted;original_sort_select=passthrough;
    assert(sort_select(context,0,message)==42 && !sort_pending && context[0x15]==1);
    put_half(message+0x78,3);assert(sort_select(context,0,message)==9 && forwarded==1);
    rx3_browse_touch(900,75,1);rx3_browse_touch(1200,75,1);rx3_browse_touch(900,75,0);assert(!sort_pending);
    assert(!rx3_browse_touch(1200,120,1));assert(!rx3_browse_touch(1200,75,1));assert(!rx3_browse_touch(1200,75,0));assert(!sort_pending);
    visible=0;assert(!rx3_browse_touch(1200,75,1));visible=1;menu=1;assert(!rx3_browse_touch(1200,75,1));
    menu=0;track_list=0;assert(!rx3_browse_touch(1200,75,1));track_list=1;column=0;assert(!rx3_browse_touch(1200,75,1));
    assert(sort_for_field(7)==2 && sort_for_field(15)==12 && sort_for_field(11)==8 && !sort_for_field(255));
    return 0;
}
''',[])

    def test_native_scroll_resets_at_end_and_reuses_native_timers(self):
        self.run_units(r'''
#include "core/services/rx3_browse.c"
int install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r,void *o){(void)h;(void)a;(void)g;(void)r;(void)o;return 0;}
int hook_is_installed(const struct installed_hook *h){(void)h;return 0;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
static unsigned timer_delay,timer_calls,steps,shown;
static uint8_t states[512],strings[0x4000],ids[512],glyph[84];
static int layout(void){return 1;}
static void *object(void *root,int id){assert(root==(void *)1 && id==9);return glyph;}
static void kill(unsigned w,unsigned id){assert(w==0x82a && id==4);}
static void timer(unsigned w,unsigned id,unsigned delay){assert(w==0x82a && id==4);timer_delay=delay;timer_calls++;}
static void prepare(unsigned lane,unsigned row){
    assert(lane==1 && !row && half(glyph+0x1c)==1110);
    const uint16_t *s=(void *)(strings+0x1ce4+0x238);assert(s[0]=='L' && s[1]=='o' && !s[4]);
    put_word(states+0x74+0x38,4);
}
static void start(const uint16_t *s,void *g,unsigned lane){assert(s==scroll_text[1] && g==glyph && lane==1);}
static void show(void *g,unsigned value){assert(g==glyph && value==1);shown++;}
static void run(unsigned lane){assert(lane==1);uint8_t *s=states+0x74;int x=(int)word(s+0x58)-3;put_word(s+0x58,(unsigned)x);assert(x>=-134);assert(word(s+0x48)==234);steps++;}
int main(void){
    const uint16_t caption[]={'B',0};const struct rx3_browse_column col={13,caption};column=&col;
    scroll_state=states;scroll_strings=strings;scroll_ids=ids;track_layout=layout;
    unsigned root=1;root_pointer=&root;object_by_id=object;put_half(ids+0x118,9);put_half(glyph+0x1c,1020);
    const uint16_t full[]={'L','o','n','g',SEP,1,'1','2','8',END,SEP,0};
    memcpy(strings+0x1ce4+0x238,full,sizeof(full));
    original_scroll_prepare=prepare;original_scroll_start=start;original_scroll_run=run;
    scroll_kill=kill;scroll_timer=timer;scroll_show=show;
    scroll_prepare(1,0);assert(scroll_owned[1] && timer_delay==2000 && timer_calls==1);
    assert(!memcmp(strings+0x1ce4+0x238,full,sizeof(full)) && half(glyph+0x1c)==1020);
    put_word(states+0x74+0x10,4);
    scroll_start(scroll_text[1],glyph,1);assert(shown==1 && timer_delay==60);
    uint8_t *s=states+0x74;put_word(s+0x24,1);put_word(s+0x48,110);put_word(s+0x2c,100);put_word(s+0x10,4);
    put_word(s+0x58,(unsigned)-129);
    scroll_run(1);assert((int)word(s+0x58)==-132 && !scroll_phase[1]);
    scroll_run(1);assert((int)word(s+0x58)==-134 && scroll_phase[1]==1);
    scroll_run(1);assert(!word(s+0x58) && scroll_phase[1]==2 && timer_delay==2000);
    scroll_run(1);assert((int)word(s+0x58)==-3 && !scroll_phase[1] && timer_delay==60);
    for(unsigned i=0;i<100;i++)scroll_run(1);
    assert(steps==104 && timer_calls>=6 && word(s+0x48)==110);
    return 0;
}
''',[])

    def test_feature_owns_only_the_selected_field(self):
        self.run_units(r'''
#include "core/api/rx3_module_api.h"
extern const struct rx3_module rx3_browse_columns_module;
static unsigned expected,registered,removed;
static int add(const void *owner,const struct rx3_browse_column *c){assert(owner&&c&&c->caption&&c->field==expected);registered++;return 1;}
static void remove_owner(const void *owner){assert(owner);removed++;}
static const struct rx3_browse_service browse={.column=add,.unregister_owner=remove_owner};
static const struct rx3_services api={.browse=&browse};
int main(void){
    unsetenv("RX3_BROWSE_COLUMNS");assert(!rx3_browse_columns_module.configured());
    setenv("RX3_BROWSE_COLUMNS","1",1);assert(rx3_browse_columns_module.configured());
    const char *choices[]={"13","15","7","11","14","15junk"};unsigned fields[]={13,15,7,11,13,13};
    for(unsigned i=0;i<6;i++) {
        setenv("RX3_BROWSE_FIELD",choices[i],1);expected=fields[i];
        assert(rx3_browse_columns_module.start(&api));rx3_browse_columns_module.stop();
    }
    assert(registered==6&&removed==6);return 0;
}
''',['browse-columns/rx3_browse_columns_module.c'])

    def test_usb_setting_is_never_executed(self):
        import subprocess
        import tempfile
        script=pathlib.Path('mod/modules/browse-columns/module.sh').read_text()
        with tempfile.TemporaryDirectory() as temp:
            config=pathlib.Path(temp)/'column.txt'
            core=pathlib.Path(temp)/'core';core.write_bytes(b'x')
            script=script.replace('/mnt/iso/modules/browse-columns/column.txt',str(config))
            prefix=f'CORE_OBJECT="{core}"\n'+'''module_begin(){ :; }
register_prepare_hook(){ :; }
module_disabled_by_switch(){ return 1; }
module_export(){ printf '%s=%s\\n' "$1" "$2"; }
'''
            for raw,expected in ((None,13),('15\n',15),('7\n',7),('11\n',11),('14\n',13),('$(touch injected)\n',13)):
                if raw is not None: config.write_text(raw)
                result=subprocess.run(['sh'],input=prefix+script+'\nbrowse_columns_prepare\n',text=True,capture_output=True,check=True,cwd=temp)
                self.assertIn(f'RX3_BROWSE_FIELD={expected}\n',result.stdout)
                self.assertFalse((pathlib.Path(temp)/'injected').exists())
