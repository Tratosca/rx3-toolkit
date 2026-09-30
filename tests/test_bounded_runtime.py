# SPDX-License-Identifier: MPL-2.0
"""Bounded background work and render-thread publication, without firmware calls."""
from pathlib import Path
import unittest
from tests import test_framework as harness
from tests.test_runtime_transitions import function

MODULES = Path(__file__).resolve().parents[1] / 'mod/modules'

THEME = r'''
#include "core/api/rx3_module_api.h"
#include "theme-white/rx3_theme_decl.h"
#include "theme-white/rx3_theme_pixels.h"
#undef STOCK_IMAGE_COUNT
#define STOCK_IMAGE_COUNT 3u
static int theme_enabled=1,light_selected;
static struct {uint8_t records[132];uint16_t pixels[32768];} fixture;
static uint8_t light[132],storage[THEME_ARENA_BYTES];
static uint8_t *theme_arena;
static uint8_t theme_id_done[1];
static size_t theme_arena_used;
static const uint16_t *theme_seen_source[4096];
static const uint16_t *theme_seen_pixels[4096];
static unsigned theme_seen_count,allocations,observations,work,allocation_failure;
static unsigned long available;
static uint64_t clock_us;
static uint64_t monotonic_enough_us(void){return clock_us;}
static unsigned long memory_available_kb(void){observations++;return available;}
/* The image service as the module sees it: stock records in the fixture,
   publication into the light records. */
static int light_active(void){return light_selected;}
static int variants_ready(void){return 1;}
static int native_image(unsigned id,struct rx3_native_image *out){
 if(id>=STOCK_IMAGE_COUNT)return 0;
 const uint8_t *r=fixture.records+id*44;uint16_t w,h;uint32_t off;
 memcpy(&w,r+4,2);memcpy(&h,r+6,2);memcpy(&off,r+32,4);
 out->width=w;out->height=h;out->format=r[24];out->paletted=r[25];
 out->pixels=(const void *)((const uint8_t *)&fixture+off);return 1;
}
static int publish_variant(unsigned id,const uint16_t *pixels){
 uint32_t off=(uint32_t)(uintptr_t)pixels-(uint32_t)(uintptr_t)light;
 memcpy(light+id*44+32,&off,4);return 1;
}
static const struct rx3_image_service images={.light_active=light_active,
 .variants_ready=variants_ready,.native_image=native_image,.publish_variant=publish_variant};
static int mock_reserve(const void *o, unsigned long bytes, unsigned long floor_kb) {
    (void)o; unsigned long kb = bytes / 1024u + (bytes % 1024u != 0u), have = available;
    return !floor_kb || (have > floor_kb && have - floor_kb >= kb);
}
static void mock_move(const void *o, unsigned long b) { (void)o; (void)b; }
static unsigned long mock_held(void) { return 0; }
static const struct rx3_memory_service memory_mock={mock_reserve,mock_move,mock_move,mock_move,memory_available_kb,mock_held};
static const struct rx3_services services={.images=&images,.memory=&memory_mock};
static const struct rx3_services *framework=&services;
static int theme_light_active(void){return framework->images->light_active();}
static void *test_map(void *a,size_t n,int p,int f,int d,off_t o){
 (void)a;(void)p;(void)f;(void)d;(void)o;assert(n==sizeof(storage));allocations++;return allocation_failure?MAP_FAILED:storage;
}
static void counted_unpack(uint16_t p,unsigned *r,unsigned *g,unsigned *b){work++;theme_unpack(p,r,g,b);}
static uint16_t counted_light(unsigned id,uint16_t p,int artwork){work++;return theme_pixel_light_for_image(id,p,artwork);}
static uint16_t counted_dark(uint16_t p){work++;return theme_pixel_dark(p);}
#define mmap test_map
#define theme_unpack counted_unpack
#define theme_pixel_light_for_image counted_light
#define theme_pixel_dark counted_dark
#include "theme-white/rx3_theme_conversion.h"
#undef theme_unpack
#undef theme_pixel_light_for_image
#undef theme_pixel_dark
static void record(unsigned id,unsigned start,unsigned count){
 uint8_t *r=fixture.records+id*44;uint16_t w=count,h=1;uint32_t off=132+start*2;
 memcpy(r+4,&w,2);memcpy(r+6,&h,2);memcpy(r+32,&off,4);r[24]=1;
 memcpy(light+id*44,r,44);
}
static uint32_t image_offset(unsigned id){uint32_t v;memcpy(&v,light+id*44+32,4);return v;}
'''


class BoundedRuntimeTests(unittest.TestCase):
    run_units = harness.FrameworkTests.run_units

    def test_theme_budget_retry_publication_and_pixel_equivalence(self):
        self.run_units(THEME + r'''
int main(void){
 light_selected=1;record(0,0,16384);record(1,0,16384);record(2,16384,1);
 for(unsigned i=0;i<32768;i++)fixture.pixels[i]=(uint16_t)(i*79u);
 uint32_t original=image_offset(0);
 theme_remap_image(0);theme_remap_image(1);theme_remap_image(2);
 assert(!observations && !allocations);assert(!theme_run_conversions());
 theme_prepare_conversion();assert(observations==1 && !allocations);
 available=THEME_ARENA_FLOOR_KB+1024;clock_us=249999;theme_prepare_conversion();assert(!allocations);
 clock_us=250000;theme_prepare_conversion();assert(allocations==1);
 work=0;assert(!theme_run_conversions());assert(work<=THEME_PIXEL_BUDGET);
 assert(image_offset(0)==original && !theme_arena_used && !theme_id_done[0]);
 /* Memory pressure pauses the private job without publishing partial pixels. */
 clock_us=500000;available=0;theme_prepare_conversion();work=0;
 assert(!theme_run_conversions() && !work && image_offset(0)==original);
 clock_us=750000;available=THEME_ARENA_FLOOR_KB+1024;theme_prepare_conversion();
 unsigned reads=observations;
 for(unsigned pass=0;pass<16 && theme_id_done[0]!=7;pass++){
  work=0;theme_run_conversions();assert(work<=THEME_PIXEL_BUDGET);
 }
 assert(theme_id_done[0]==7 && observations==reads && allocations==1);
 assert(theme_arena_used==16384u*2u+2u && image_offset(0)==image_offset(1));
 int artwork=theme_is_artwork(fixture.pixels,16384);
 const uint16_t *result=(const void *)storage;
 for(unsigned i=0;i<16384;i++)assert(result[i]==theme_pixel_light_for_image(0,fixture.pixels[i],artwork));
 return 0;
}
''', [], ['-Wno-unused-function', '-Wno-unused-variable'])

    def test_theme_discards_partial_conversion_on_mode_change(self):
        self.run_units(THEME + r'''
int main(void){
 record(0,0,16384);for(unsigned i=0;i<16384;i++)fixture.pixels[i]=(uint16_t)(i*41u);
 light_selected=1;available=THEME_ARENA_FLOOR_KB+1024;theme_prepare_conversion();
 theme_remap_image(0);theme_run_conversions();assert(theme_job.source && !theme_arena_used);
 light_selected=0;theme_global_dark=1;
 for(unsigned pass=0;pass<8 && !(theme_id_done[0]&1);pass++){
  work=0;theme_run_conversions();assert(work<=THEME_PIXEL_BUDGET);
 }
 assert(theme_id_done[0]&1);assert(theme_arena_used==32768);
 const uint16_t *result=(const void *)storage;
 for(unsigned i=0;i<16384;i++)assert(result[i]==theme_pixel_dark(fixture.pixels[i]));
 return 0;
}
''', [], ['-Wno-unused-function', '-Wno-unused-variable'])

    def test_stems_read_and_crc_stop_between_chunks(self):
        self.run_units(r'''
static unsigned reads,cancel_after,checks,cancel_now;
static ssize_t source_read(int fd,void *p,size_t n){
 (void)fd;assert(n<=65536u);reads++;memset(p,0,n);if(reads==cancel_after)cancel_now=1;return n;
}
#define read source_read
#include "stems/rx3_stems_io.h"
static int cancelled(const void *context){(void)context;checks++;return cancel_now;}
''' + function(MODULES/'stems/rx3_stems_package.h','package_crc') + r'''
static unsigned crc_checks;
static int crc_cancelled(const void *context){(void)context;return ++crc_checks==3;}
int main(void){
 uint8_t data[STEMS_IO_CHUNK*3]={0};const struct stems_io io={cancelled,0};
 cancel_now=1;assert(stems_read(1,data,sizeof(data),&io) && !reads);
 cancel_now=0;cancel_after=1;assert(stems_read(1,data,sizeof(data),&io) && reads==1);
 cancel_now=0;cancel_after=0;reads=0;assert(!stems_read(1,data,sizeof(data),&io) && reads==3);
 uint32_t crc=123;assert(package_crc((const uint8_t *)"123456789",9,0,&crc) && crc==0xcbf43926u);
 const struct stems_io crc_io={crc_cancelled,0};crc=123;
 assert(!package_crc(data,sizeof(data),&crc_io,&crc) && crc_checks==3 && crc==123);
 return 0;
}
''', [])

    def test_request_generation_cancels_even_when_reader_is_reused(self):
        self.run_units(r'''
#include "stems/rx3_stems_decl.h"
/* The shared loader answers whether this module's release has begun. */
static unsigned loader_stopping;
static int stems_loader_stopping(void){return loader_stopping;}
''' + function(MODULES/'stems/rx3_stems_loader.h','stems_request_cancelled') + r'''
int main(void){
 struct stems_deck_context context={0};context.generation=7;context.reader=&context;
 struct stems_load_request request={.context=&context,.reader=&context,.generation=7};
 assert(!stems_request_cancelled(&request));
 __atomic_add_fetch(&context.generation,1u,__ATOMIC_SEQ_CST);
 assert(stems_request_cancelled(&request));
 request.generation=8;assert(!stems_request_cancelled(&request));
 loader_stopping=1;assert(stems_request_cancelled(&request));return 0;
}
''', [], ['-Wno-unused-function', '-Wno-unused-variable'])

    def test_theme_retries_allocation_and_restarts_if_native_source_changes(self):
        self.run_units(THEME + r'''
int main(void){
 record(0,0,16384);light_selected=1;theme_remap_image(0);
 for(unsigned i=0;i<32768;i++)fixture.pixels[i]=(uint16_t)(i*31u);
 available=THEME_ARENA_FLOOR_KB+1024;allocation_failure=1;theme_prepare_conversion();
 assert(allocations==1 && !theme_arena && !theme_run_conversions());
 allocation_failure=0;clock_us=250000;theme_prepare_conversion();assert(allocations==2 && theme_arena);
 theme_run_conversions();assert(theme_job.source==(const void *)fixture.pixels);
 record(0,16384,16384);uint32_t stock=image_offset(0);
 theme_run_conversions();assert(image_offset(0)==stock && !theme_arena_used);
 assert(theme_job.source==(const void *)(fixture.pixels+16384));
 for(unsigned pass=0;pass<8 && !theme_id_done[0];pass++)theme_run_conversions();
 assert(theme_id_done[0] && theme_arena_used==32768);
 int artwork=theme_is_artwork(fixture.pixels+16384,16384);
 const uint16_t *result=(const void *)storage;
 for(unsigned i=0;i<16384;i++)assert(result[i]==theme_pixel_light_for_image(0,fixture.pixels[16384+i],artwork));
 return 0;
}
''', [], ['-Wno-unused-function', '-Wno-unused-variable'])
