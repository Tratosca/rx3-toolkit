# SPDX-License-Identifier: MPL-2.0
"""Exercise real metadata reuse with fake firmware I/O, never fixed host mappings."""
import unittest
from tests import test_framework

HARNESS = r'''
#include "core/services/rx3_browse.c"
void *install_hook(struct installed_hook *h,unsigned long a,const uint8_t g[8],void *r){(void)h;(void)a;(void)g;(void)r;return 0;}
int hook_is_installed(const struct installed_hook *h){return h->record!=0;}
int detach_hook(struct installed_hook *h){(void)h;return 1;}
int release_hook(struct installed_hook *h){(void)h;return 1;}
static unsigned stamp=10,requests,key_requests,streams,frees,drains,position,requested;
static unsigned fail_meta,fail_stream,fail_record,fail_format,fail_key,variant;
static unsigned now(void){return stamp;}
static unsigned get_key(void *db,unsigned id){assert(db);key_requests++;return fail_key?0:1+(id+variant)%24;}
static int meta(void *db,unsigned kind,unsigned id){assert(db && kind==2);requests++;requested=id;return fail_meta?0:2;}
static int rec(void *db,unsigned k,unsigned *f,unsigned n,unsigned a,unsigned b,unsigned c) {
 assert(db && k==2 && !*f && n==2 && !a && b==2 && !c);streams++;position=0;return !fail_stream;
}
static int next(void *db,uint32_t *r,int a,void *b) {
 assert(db && !a && !b);if(fail_record && position==1)return 0;
 r[0]=requested+variant;r[2]=position++?7:13;return 1;
}
static uint16_t *fmt(uint32_t a,uint32_t b,unsigned kind,unsigned flags) {
 (void)b;assert(flags==65535);static uint16_t value[32];
 if(fail_format)return 0;
 value[0]=(uint16_t)(kind==13?'0'+a%10:'A'+a%26);value[1]=0;return value;
}
static void drain(void *db){assert(db);drains++;}
static void drop(void *p){assert(p);frees++;}
static uint32_t database[8];
static unsigned context;
static uint16_t value[128],other[128];
static void bind(void){metadata_bind(&context,database,1,2,4,13,7);}
static unsigned fetch(unsigned id,unsigned changed) {
 uint8_t row[532]={0};memcpy(row,&id,4);memcpy(row+20,&changed,4);
 return metadata_values(database,id,row,1,13,value,7,other);
}
static void setup(void) {
 metadata=meta;records=rec;next_record=next;format=fmt;skip=drain;free_text=drop;
 track_key=get_key;metadata_now=now;bind();
}
'''

class BrowsePerformanceTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def run_case(self, body):
        self.run_units(HARNESS + '\nint main(void){setup();\n' + body + '\nreturn 0;}\n',
                       [], flags=('-Wno-unused-function',))

    def test_overlapping_viewports_query_only_entering_tracks(self):
        self.run_case(r'''
/* Baseline: the previous row loop rereads all fourteen tracks each time. */
for(unsigned page=0;page<100;page++)for(unsigned row=0;row<14;row++) {
 unsigned id=1+page+row,key=track_key(database,id);
 assert(values_for(database,id,key,13,value,7,other));
}
assert(requests==1400 && key_requests==1400);
requests=key_requests=streams=frees=drains=0;
for(unsigned page=0;page<100;page++) {
 stamp=10+page*8;bind();
 for(unsigned row=0;row<14;row++) {
  unsigned id=1+page+row;assert(fetch(id,0)==1+id%24);
  assert(value[0]=='0'+id%10 && other[0]=='A'+id%26);
 }
 if(page==0)assert(requests==14 && key_requests==14);
 if(page==1)assert(requests==15 && key_requests==15);
}
assert(requests==113 && key_requests==113 && streams==113);
assert(frees==226 && drains==113);
assert(sizeof(metadata_cache)<36*1024);
/* Revisited records keep their ID association, independent of row index. */
unsigned before=requests;fetch(110,0);fetch(100,0);fetch(110,0);assert(requests==before);
fetch(1,0);assert(requests==before+1); /* Bounded eviction, not an unbounded library cache. */
''')

    def test_realistic_scroll_does_not_expire_visible_rows_each_second(self):
        self.run_case(r'''
/* 21 ms per uncached track and 1.2 seconds between encoder events. */
for(unsigned page=0;page<6;page++) {
 stamp=10+page*1200;bind();
 for(unsigned row=0;row<14;row++) {
  unsigned before=requests;fetch(page+row+1,0);
  stamp+=(requests-before)*21;
 }
}
assert(requests==19 && key_requests==19);
''')

    def test_source_navigation_and_settings_invalidate_reused_ids(self):
        self.run_case(r'''
uint32_t other_database[8]={0};
fetch(42,0);fetch(42,0);assert(requests==1);
variant=1;fetch(42,1);assert(requests==2 && value[0]=='3'); /* Native row changed. */
metadata_bind(&context,other_database,1,2,4,13,7);fetch(42,1);assert(requests==3);
bind();fetch(42,1);assert(requests==4);
metadata_bind(&context,database,2,2,4,13,7);fetch(42,1);assert(requests==5);
metadata_bind(&context,database,2,3,4,13,7);fetch(42,1);assert(requests==6);
metadata_bind(&context,database,2,3,132,13,7);fetch(42,1);assert(requests==7);
metadata_bind(&context,database,2,3,132,11,7);fetch(42,1);assert(requests==8);
metadata_bind(&context,database,2,3,132,11,15);fetch(42,1);assert(requests==9);
unsigned second_context=0;metadata_bind(&second_context,database,2,3,132,11,15);
fetch(42,1);assert(requests==10);
/* Connection identity changes invalidate without touching the pointed-to memory. */
database[0]=123;metadata_bind(&context,database,1,2,4,13,7);
for(unsigned i=0;i<METADATA_SLOTS;i++)assert(!metadata_cache[i].used);
database[0]=0;bind();fetch(42,1);assert(requests==11);
invalidate_metadata();bind();fetch(42,1);assert(requests==12);
/* A new track/key invalidates atomically; shift-only updates do not cache colours. */
publish_key(0,1,0);bind();fetch(42,1);assert(requests==13);
publish_key(0,1,2);bind();fetch(42,1);assert(requests==13);
publish_key(0,-1,0);bind();fetch(42,1);assert(requests==14);
publish_key(0,-1,0);bind();fetch(42,1);assert(requests==14); /* Repeated empty deck metadata is not a new generation. */
''')

    def test_idle_and_clock_changes_do_not_reread_unchanged_export(self):
        self.run_case(r'''
fetch(5,0);assert(value[0]=='5');variant=1;
stamp=30010;fetch(5,0);assert(requests==1 && value[0]=='5');
stamp=0;fetch(5,0);stamp=0xffffffff;fetch(5,0);assert(requests==1);
/* A changed row or source, rather than time, refreshes exported metadata. */
fetch(5,1);assert(requests==2 && value[0]=='6');
invalidate_metadata();bind();fetch(5,1);assert(requests==3);
''')

    def test_failed_metadata_and_keys_are_retried_without_losing_ownership(self):
        self.run_case(r'''
fail_meta=1;fetch(1,0);fetch(1,0);assert(requests==2 && !streams && !value[0]);
fail_meta=0;fail_stream=1;fetch(1,0);fetch(1,0);assert(requests==4 && streams==2 && !drains);
fail_stream=0;fail_record=1;fetch(1,0);fetch(1,0);assert(requests==6 && drains==2 && frees==2);
fail_record=0;fail_format=1;fetch(1,0);fetch(1,0);assert(requests==8 && drains==4 && frees==2);
fail_format=0;fetch(1,0);fetch(1,0);assert(requests==9 && drains==5 && frees==4);
fail_key=1;assert(fetch(2,0)==0);unsigned before=key_requests;
assert(fetch(2,0)==0 && key_requests==before+1);
fail_key=0;assert(fetch(2,0)==3 && key_requests==before+2);
''')

    def test_key_only_and_empty_fields_do_not_request_full_metadata(self):
        self.run_case(r'''
uint8_t row[532]={0};metadata_bind(&context,database,1,2,4,15,0);
unsigned key=metadata_values(database,42,row,1,15,value,0,other);
assert(key==19 && value[0]=='1' && value[1]=='0' && value[2]=='A');
assert(!requests && key_requests==1);
metadata_values(database,42,row,1,15,value,0,other);assert(!requests && key_requests==1);
metadata_bind(&context,database,1,2,4,0,0);
metadata_values(database,42,row,0,0,value,0,other);assert(!requests && key_requests==1);
''')

    def test_metrics_distinguish_reuse_expiry_and_scope_invalidation(self):
        self.run_case(r'''
fetch(7,0);fetch(7,0);
struct rx3_browse_metrics m;rx3_browse_get_metrics(&m);
assert(m.hits==1 && m.misses==1 && m.scopes==1);
assert(m.key_queries==1 && m.field_queries==1 && !m.expiries);
stamp+=30001;fetch(7,0);rx3_browse_get_metrics(&m);
assert(m.hits==2 && !m.expiries && m.field_queries==1);
invalidate_metadata();bind();fetch(7,0);rx3_browse_get_metrics(&m);
assert(m.scopes==2 && m.misses==2 && m.field_queries==2);
''')

    def test_local_page_copies_metadata_and_never_frees_static_numeric_input(self):
        code = HARNESS + r'''
static unsigned selection,closed,names_freed,local_requests;
static uint32_t bpm=12856,length=247,artist=42;
static uint16_t artist_name[]={'D','J',0};
static void *server_original(void *c,const uint32_t *r,unsigned d,unsigned k,unsigned m,unsigned cat) {
 (void)c;(void)r;(void)d;(void)k;(void)m;(void)cat;return &context;
}
static int server_page(void *c,void *r){(void)c;(void)r;return 7;}
static void *select_row(int *e,const char *t,const char *idx,unsigned a,unsigned b,unsigned c,const char *op,unsigned n,const unsigned **id) {
 assert(!strcmp(t,"djdbContent") && !strcmp(idx,"idxContent") && !strcmp(op,"="));
 assert(!a && !b && !c && n==1 && **id==42);*e=0;selection++;return &context;
}
static void *next_row(void *s,int *e){assert(s==&context);*e=0;return &context;}
static void *column_value(void *r,unsigned n){assert(r==&context);return n==8?&bpm:n==9?&length:&artist;}
static int close_row(void *s){assert(s==&context);closed++;return 0;}
static unsigned key_local(unsigned id,unsigned drive){assert(id==42 && (drive==2 || drive==3));local_requests++;return drive==2?9:0;}
static int artist_text(unsigned t,unsigned aid,unsigned id,uint16_t **name,unsigned kind,unsigned drive) {
 assert(t==7 && aid==42 && id==42 && kind==1 && (drive==2 || drive==3));*name=artist_name;return 0;
}
static void free_artist(void *p){assert(p==artist_name);names_freed++;}
int main(void) {
 setup();original_local_page=server_page;original_local_record=server_original;
 edb_select=select_row;edb_next=next_row;edb_column=column_value;edb_close=close_row;
 table_string=artist_text;edb_free=free_artist;local_key=key_local;
 uint32_t record[9]={42,0,0,0,4};unsigned key=99;
 /* A BPM column reads the content row only: no artist string, no key lookup. */
 struct rx3_browse_column col={0};col.field=13;column=&col;
 assert(local_page_rows(&context,0)==7);
 local_record(&context,record,2,1,1,0);
 assert(selection==1 && closed==1 && names_freed==0 && local_requests==0 && !callbacks);
 assert(local_cached_values(2,42,13,value,11,other,&key));
 const uint16_t expected_bpm[]={'1','2','8','.','6',0},expected_time[]={'4',':','0','7',0};
 assert(!memcmp(value,expected_bpm,sizeof(expected_bpm)) && !memcmp(other,expected_time,sizeof(expected_time)));
 /* Fields the snapshot did not capture send the client to its own path. */
 assert(!local_cached_values(2,42,7,value,0,other,&key));
 assert(!local_cached_values(2,42,15,value,0,other,&key));
 /* An artist column fetches the name. */
 col.field=7;local_page_rows(&context,0);local_record(&context,record,2,1,1,0);
 assert(names_freed==1 && local_requests==0);
 assert(local_cached_values(2,42,7,value,13,other,&key) && value[0]=='D' && value[1]=='J' && other[0]=='1');
 /* A key column fetches the key, including a track without one. */
 col.field=15;local_page_rows(&context,0);local_record(&context,record,2,1,1,0);
 assert(local_requests==1 && local_cached_values(2,42,15,value,0,other,&key) && key==9);
 assert(value[0]=='5' && value[1]=='A');
 assert(!requests && !key_requests && !frees); /* No DBCCmd format/free or mailbox queries. */
 assert(!local_cached_values(3,42,13,value,0,other,&key));
 local_record(&context,record,3,1,1,0);
 assert(local_cached_values(3,42,15,value,0,other,&key) && !key && !value[0]);
 unsigned saved=selection;local_record(&context,record,2,2,1,0);assert(selection==saved);
 local_page_rows(&context,0);assert(!local_cached_values(2,42,13,value,0,other,&key));
 return 0;
}
'''
        self.run_units(code, [], flags=('-Wno-unused-function',))

if __name__ == '__main__':
    unittest.main()
