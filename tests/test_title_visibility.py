# SPDX-License-Identifier: MPL-2.0
"""Execute title policy and native adapter against fake UI objects, never firmware."""
import unittest
from tests import test_framework

HARNESS = r'''
#define owner service_owner
#define provider service_provider
#include "core/services/rx3_titles.c"
#undef provider
#undef owner
#include "core/services/rx3_images.c"
#include "asshole-mode/rx3_asshole_module.c"
static const struct rx3_services title_services={.titles=&rx3_titles,.images=&rx3_images};
static unsigned pixels,refreshes,lookups;
void log_line(const char *s){(void)s;}
static void log_number(const char *s,unsigned long n){(void)s;(void)n;}
static void draw_native_image_local(void *r,const void *m,uint8_t t,
 int x,int y,int x2,int y2,uint32_t id) {
 (void)r;(void)m;(void)t;
 assert(x==104 && x2==129 && y==15 && y2==38);
 assert(id>=IMAGE_FIRST && id<IMAGE_FIRST+IMAGE_LIMIT);pixels++;
}
#include "core/ui/rx3_title_visibility.h"
static uint8_t roots[2],texts[2][84],icons[2][84],windows[2][84],foreign[84];
static int screen=1,shown=1;
static int is_shown(void *p){assert(p);return shown;}
static void *object(void *root,unsigned id) {
 lookups++;if(!screen)return 0;
 if(!root)return id==2480?&roots[0]:(id==2569?&roots[1]:0);
 unsigned d=root==&roots[1];
 return id==62?texts[d]:(id==61?icons[d]:(id==64?root:0));
}
static void refresh_object(void *root,unsigned id) {
 assert((root==&roots[0] || root==&roots[1]) && id==64);refreshes++;
}
static void position(int *x,int *y){*x=0;*y=-4;}
static const char *client=owner;
static void setup(void) {
 (void)client;
 title_object=object;title_refresh=refresh_object;title_origin=position;title_shown=is_shown;
 title_abi_checked=title_abi_supported=1;
 uint16_t box[]={135,15,599,48};uint32_t icon=0xbf3;
 for(unsigned d=0;d<2;d++) {
  memcpy(texts[d]+24,box,8);memcpy(icons[d]+68,&icon,4);
  windows[d][4]=0x14;int16_t at[]={10+640*d,584};memcpy(windows[d]+24,at,4);
  void *window=windows[d];memcpy(icons[d]+8,&window,sizeof(window));
 }
 memcpy(foreign,texts[0],84);
 assert(start(&title_services));title_refresh_pending();assert(refreshes==2);
}
static void tap(int deck){assert(rx3_titles_touch(deck,1,1));assert(rx3_titles_touch(deck,0,0));}
'''

class TitleVisibilityTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def case(self, body):
        self.run_units(HARNESS + '\nint main(void){setup();\n' + body + '\nreturn 0;}\n',
                       [], flags=('-Wno-unused-function',))

    def test_independent_decks_and_restore_on_release(self):
        self.case(r'''
assert(!rx3_title_hidden(0) && !rx3_title_hidden(1));
assert(!rx3_titles.acquire(client,&provider) && !rx3_titles.acquire(0,&provider));
tap(0);assert(rx3_title_hidden(0) && !rx3_title_hidden(1));
tap(1);assert(rx3_title_hidden(0) && rx3_title_hidden(1));
tap(0);assert(!rx3_title_hidden(0) && rx3_title_hidden(1));
rx3_titles.release("foreign");assert(rx3_titles_enabled());
rx3_titles.release(client);assert(!rx3_title_hidden(1));
stop();assert(start(&title_services));assert(!rx3_title_hidden(0) && !rx3_title_hidden(1));
assert(!rx3_title_hidden(2));
''')

    def test_drag_cancel_release_and_no_capture_from_existing_gesture(self):
        self.case(r'''
assert(!rx3_titles_touch(0,1,0));assert(!rx3_titles_touch(0,0,0));
assert(rx3_titles_touch(0,1,1));assert(rx3_titles_touch(-1,1,0));
assert(rx3_titles_touch(0,0,0));assert(!rx3_title_hidden(0));
assert(rx3_titles_touch(0,1,1));assert(rx3_titles_touch(1,0,0));
assert(!rx3_title_hidden(0) && !rx3_title_hidden(1));
assert(rx3_titles_touch(0,1,1));rx3_titles.release(client);
assert(rx3_titles_touch(0,0,0));assert(!rx3_titles_touch(0,1,1));
''')

    def test_reacquiring_does_not_complete_a_previous_owners_gesture(self):
        self.case(r'''
assert(rx3_titles_touch(0,1,1));stop();assert(start(&title_services));
assert(rx3_titles_touch(0,0,0));assert(!rx3_title_hidden(0));
assert(rx3_image_count()==4);stop();assert(!rx3_image_count());
''')

    def test_only_exact_native_title_is_hidden_without_mutating_metadata(self):
        self.case(r'''
tap(0);assert(title_text_hidden(texts[0]));assert(!title_text_hidden(texts[1]));
assert(!title_text_hidden(foreign));
uint8_t before[84];memcpy(before,texts[0],84);
for(unsigned i=0;i<100;i++) assert(title_text_hidden(texts[0]));
assert(!memcmp(before,texts[0],84));
/* A new title value on this deck must not reset its visibility choice. */
texts[0][56]=14;assert(title_text_hidden(texts[0]));
screen=0;assert(!title_text_hidden(texts[0]));
''')

    def test_native_eye_geometry_theme_and_screen_gating(self):
        self.case(r'''
assert(title_draw_eye(0,icons[0]));rx3_images.select_variant(1);
assert(title_draw_eye(0,icons[1]));assert(pixels);
assert(title_hits[0][0]==106 && title_hits[0][1]==584);
assert(title_touch_hit(110,605,1)==0);assert(title_touch_hit(750,605,1)==1);
assert(title_touch_hit(144,605,1)==-1);assert(title_touch_hit(110,605,0)==-1);
screen=0;assert(title_touch_hit(110,605,1)==-1);screen=1;
shown=0;assert(title_touch_hit(110,605,1)==-1);shown=1;
title_visible=0;assert(title_touch_hit(110,605,1)==-1);
/* Same music icon elsewhere must retain its native appearance. */
memcpy(foreign,icons[0],84);assert(!title_draw_eye(0,foreign));
tap(1);assert(title_draw_eye(0,icons[1]));
''')

    def test_coalesced_refresh_and_failed_adapter(self):
        self.case(r'''
tap(0);tap(1);title_refresh_pending();assert(refreshes==4);
title_refresh_pending();assert(refreshes==4);
title_abi_supported=0;assert(!title_draw_eye(0,icons[0]));
assert(!title_text_hidden(texts[0]));assert(title_touch_hit(110,605,1)==-1);
''')

    def test_module_is_explicitly_opt_in_and_restores_service_on_stop(self):
        self.run_units(r'''
#include "core/services/rx3_titles.h"
static char *setting;
static char *setting_get(const char *key){assert(!strcmp(key,"RX3_ASSHOLE_MODE"));return setting;}
#define getenv setting_get
#include "asshole-mode/rx3_asshole_module.c"
#undef getenv
int main(void) {
 assert(!configured());setting="0";assert(!configured());
 setting="10";assert(!configured());setting="1";assert(configured());
 struct rx3_services absent={0};assert(!start(&absent));stop();
 struct rx3_services services={.titles=&rx3_titles,.images=&rx3_images};
 assert(start(&services));assert(rx3_titles_enabled());
 assert(rx3_titles_touch(0,1,1));assert(rx3_titles_touch(0,0,0));
 assert(rx3_title_hidden(0));stop();assert(!rx3_title_hidden(0));
 assert(start(&services));assert(!rx3_title_hidden(0));stop();
 return 0;
}
''', ['core/services/rx3_titles.c','core/services/rx3_images.c'])

    def test_object_ids_match_native_property_table_when_firmware_is_available(self):
        import re
        import struct
        firmware = test_framework.ROOT / 'local/firmware/rx3/extracted/119/pdj/pdj/rbp'
        if not firmware.is_file():
            self.skipTest('local firmware 1.19 required for independent ABI verification')
        binary = firmware.read_bytes()
        table = struct.unpack_from('<87I', binary, 0x52b0e8 - 0x10000)
        header = (test_framework.MODULES / 'core/ui/rx3_title_visibility.h').read_text()
        for name, address in [('GROUP', 0x538f4c), ('TEXT', 0x538f00), ('ICON', 0x538ee8)]:
            actual = int(re.search(r'#define TITLE_' + name + r'_ID (\d+)u', header).group(1))
            self.assertEqual(actual, table.index(address), name)

    def test_native_touch_route_remains_live_without_another_tab_draw(self):
        from tests.test_runtime_transitions import function
        core = test_framework.MODULES / 'core/rx3_core_hook.c'
        self.run_units(HARNESS + r'''
#define RX3_DIAGNOSTIC_ONLY 0
#define RX3_PAD_TOUCH_TOP 500
#define RX3_PAD_TOUCH_BOTTOM 580
#define RX3_PAD_DECK_STRIDE 640
static unsigned touch_calls,captured_touch,captured_touch_deck,overlay_panel,native_calls;
static unsigned view[3]={0,1,0};static void *view_object=view;
static void *const *performance_view_pointer=&view_object;
static void original_solve_touch(void *handler,const void *status,const void *mode) {
 (void)mode;native_calls++;memcpy((uint8_t *)handler+4,status,12);
}
static int rx3_browse_touch(int x,int y,int p){(void)x;(void)y;(void)p;return 0;}
static void *row_for_id(unsigned id){(void)id;return 0;}
static int pad_row_touch(void *r,unsigned d,int x,unsigned p){(void)r;(void)d;(void)x;(void)p;return 0;}
static int performance_tab_touch(int x,int y){(void)x;(void)y;return 0;}
''' + function(core,'performance_overlay_is_visible') + function(core,'hooked_solve_touch') + r'''
int main(void) {
 setup();assert(title_draw_eye(0,icons[0]));
 unsigned handler[16]={0},event[3]={1,110,605};
 hooked_solve_touch(handler,event,0);assert(handler[1]==1 && !native_calls);
 event[0]=0;event[1]=event[2]=0;hooked_solve_touch(handler,event,0);
 assert(rx3_title_hidden(0) && !native_calls);
 view[1]=3;event[0]=1;event[1]=110;event[2]=605;
 hooked_solve_touch(handler,event,0);event[0]=0;hooked_solve_touch(handler,event,0);
 assert(native_calls==2 && rx3_title_hidden(0));
 view[1]=2;event[0]=1;hooked_solve_touch(handler,event,0);
 event[0]=0;hooked_solve_touch(handler,event,0);assert(!rx3_title_hidden(0));
 event[0]=1;event[1]=110;event[2]=780;hooked_solve_touch(handler,event,0);
 assert(handler[3]==780 && handler[2]==110); /* Pixel coordinates stay intact. */
 return 0;
}
''', [], flags=('-Wno-unused-function',))

    def test_eye_bitmap_has_smooth_edges_and_native_record_ownership(self):
        self.case(r'''
unsigned open=title_image(0,0);title_activate(0);unsigned closed=title_image(0,0);title_activate(0);
assert(open && closed && open!=closed);
unsigned n=rx3_image_count();assert(title_image(0,0)==open && rx3_image_count()==n);
struct variant *v=&variants[open-IMAGE_FIRST];
unsigned edge=0,ink=0,clear=0;
for(unsigned i=0;i<26*24;i++) {
 if(v->pixels[i]==0xf81f)clear++;
 else if(v->pixels[i]==0xe71c)ink++;
 else edge++;
}
assert(edge && ink && clear);
assert(memcmp(v->pixels,variants[closed-IMAGE_FIRST].pixels,26*24*2));
uint16_t caller[4]={1,2,3,4};
unsigned id=rx3_image_register_bitmap(&client,0xbf3,caller,2,2);
caller[0]=99;assert(variants[id-IMAGE_FIRST].pixels[0]==1);
assert(!rx3_image_register_bitmap(&client,0xbf3,caller,1025,1));
assert(!rx3_image_register_bitmap(&client,0xbf3,caller,2,0));
''')

    def test_bitmap_resolves_native_dimensions_pointer_and_palette(self):
        self.run_units(r'''
#include "core/services/rx3_images.c"
static struct { uint8_t record[44];uint16_t pixels[600]; } source;
static void *lookup(unsigned id){assert(id==0xbf3);return source.record;}
int main(void){
 uint16_t w=24,h=25;uint32_t offset=44,palette=1234;
 memcpy(source.record+4,&w,2);memcpy(source.record+6,&h,2);
 memcpy(source.record+32,&offset,4);memcpy(source.record+36,&palette,4);source.record[24]=2;
 uint16_t pixels[624];for(unsigned i=0;i<624;i++)pixels[i]=(uint16_t)i;
 static char owner;unsigned id=rx3_image_register_bitmap(&owner,0xbf3,pixels,26,24);
 uint8_t *record=rx3_image_resolve(id,lookup,&source);assert(record);
 memcpy(&w,record+4,2);memcpy(&h,record+6,2);assert(w==26 && h==24);
 memcpy(&palette,record+36,4);assert(!palette && record[24]==2);
 memcpy(&offset,record+12,4);assert(offset==(uint32_t)(unsigned long)variants[id-IMAGE_FIRST].pixels);
 assert(!memcmp(variants[id-IMAGE_FIRST].pixels,pixels,sizeof(pixels)));
 assert(source.record[4]==24); /* Source descriptor is unchanged. */
 rx3_images.unregister_owner(&owner);assert(!rx3_image_resolve(id,lookup,&source));
 return 0;
}
''', [], flags=('-Wno-unused-function',))
