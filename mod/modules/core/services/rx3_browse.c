/* SPDX-License-Identifier: MPL-2.0 */
#include "rx3_browse.h"
#include "rx3_hooks.h"
#include "../api/rx3_harmony.h"
#define ROW_HOOK 0x001c8048u
#define SEP 0xfdd0u
#define END 0xfdd1u
#define MAX_MESSAGE 8192u
/* Lib_Obj_CTRL_LIST_BROWSE property index 55, not the generated name suffix 220. */
#define COLUMN_HEADING_ID 55
/* UI-independent counters: the watcher logs snapshots, never the DB worker. */
static struct rx3_browse_metrics metrics;
#define METRIC_ADD(field,n) __atomic_fetch_add(&metrics.field,(unsigned)(n),__ATOMIC_RELAXED)
void rx3_browse_get_metrics(struct rx3_browse_metrics *out)
{
    if(!out)return;
#define METRIC_COPY(field) out->field=__atomic_load_n(&metrics.field,__ATOMIC_RELAXED)
    METRIC_COPY(pages);METRIC_COPY(native_ms);METRIC_COPY(added_ms);
    METRIC_COPY(hits);METRIC_COPY(misses);METRIC_COPY(expiries);METRIC_COPY(scopes);
    METRIC_COPY(key_queries);METRIC_COPY(field_queries);METRIC_COPY(local_hits);METRIC_COPY(local_ms);METRIC_COPY(local_records);
#undef METRIC_COPY
}
static const void *column_owner,*marker_owner;
static const struct rx3_browse_column *column;
static const struct rx3_browse_marker *marker;
static struct installed_hook row_hook,load_hooks[2],sort_hooks[4];
static int (*native_sort_request)(void *,unsigned,unsigned)=(void *)0x110c50u;
static int (*original_sort_validate)(void *,void *);
static int (*original_sort_select)(void *,void *,void *);
static unsigned task_sort[49];
static unsigned (*native_task)(void)=(void *)0x18a904u;
static int (*original_sort_dispatch)(void *,void *);
static void (*original_sort_keys)(unsigned,unsigned,int);
static int (*set_sort_type)(void *,unsigned,unsigned,unsigned,unsigned)=(void *)0x17bd28u;
static unsigned sort_pending,sort_observed,sort_capture,sort_cancelled;
static unsigned primary_field,secondary_field,preserve_field;
static unsigned preserve_db,preserve_depth,secondary_db,secondary_depth;
static int native_browse_visible(void);
static int native_track_layout(void);
static int (*track_layout)(void)=native_track_layout;
static int (*browse_visible)(void)=native_browse_visible;
static int (*menu_visible)(void)=(void *)0x112e10u;
static int enqueue_sort(void);
static int (*post_sort)(void)=enqueue_sort;
static int (*get_message)(unsigned,void **,unsigned)=(void *)0x186fc4u;
static int (*free_message)(unsigned,void *)=(void *)0x187068u;
static int (*send_message)(unsigned,void *)=(void *)0x186e18u;
static unsigned (*native_time)(void)=(void *)0x187290u;
static unsigned (*active_deck)(void)=(void *)0x1341d8u;
static int (*send_sorted)(void *,void *,void *,int,const uint16_t *)=(void *)0x256030u;
static void (*rectangle)(void *,void *)=(void *)0x1d2decu;
static int (*original_load[2])(unsigned);
static int (*original_rows)(void *,void *,void *);
static unsigned int callbacks,busy,track_list,caption_ready;
static uint32_t caption_model[21];
static void *caption_object;
static const uint8_t *list_context;
static const void *root_pointer=(void *)0x02684700u;
static void *(*object_by_id)(void *,int)=(void *)0x0018dae8u;
static void (*refresh_object)(void *,int)=(void *)0x0018e1a0u;
static uint8_t rebuilt[MAX_MESSAGE];
static unsigned int (*track_key)(void *,unsigned int)=(void *)0x00265f48u;
static int (*metadata)(void *,unsigned int,unsigned int)=(void *)0x002637f4u;
static int (*records)(void *,unsigned int,unsigned int *,unsigned int,unsigned int,unsigned int,unsigned int)=(void *)0x00262884u;
static int (*next_record)(void *,uint32_t *,int,void *)=(void *)0x00262a28u;
static void (*skip)(void *)=(void *)0x00262da0u;
static uint16_t *(*format)(uint32_t,uint32_t,unsigned int,unsigned int)=(void *)0x0026a480u;
static void (*free_item)(void *)=(void *)0x001f648cu;
static void (*free_text)(void *)=(void *)0x00175038u;
static unsigned word(const void *p){unsigned v;memcpy(&v,p,4);return v;}
/* BrowseUiIf::GetDisplayState uses primary 3 for the browser. The similarly
 * named CmnInfo BrowseWindow flag is zero in the full-screen USB browser. */
static int native_browse_visible(void)
{
    void *view=(void *)(unsigned long)word((void *)0x0114c2d0u);
    return view && word((uint8_t *)view+4)==3;
}
/* One atomic word couples the native key set, source key and local MASTER.
 * The music ID's device byte identifies storage, never the playing deck. */
static unsigned harmonic_snapshot,deck_keys[2];
/* Only the database worker owns cache entries. Other callbacks invalidate by
 * generation, never by clearing storage underneath an in-flight row stream. */
static unsigned metadata_epoch;
static void invalidate_metadata(void)
{
    __atomic_add_fetch(&metadata_epoch,1u,__ATOMIC_SEQ_CST);
}
#if defined(__arm__)
static unsigned (*master_on)(unsigned)=(void *)0x18579cu;
#else
static unsigned no_master(unsigned deck){(void)deck;return 0;}
static unsigned (*master_on)(unsigned)=no_master;
#endif
static int master_deck(void)
{
#if defined(__arm__)
    static const uint8_t guard[8]={0x64,0x35,0x03,0xe3,0x25,0x33,0x40,0xe3};
    if(memcmp((const void *)master_on,guard,8))return -1;
#endif
    unsigned left=master_on(0)!=0,right=master_on(1)!=0;
    return left==right?-1:left?0:1;
}
static void observe_harmony(const uint8_t *context)
{
    int deck=master_deck();
    unsigned key=word(context+0x10b08),mask=0;
    if(deck<0 || key<1 || key>24) {
        __atomic_store_n(&harmonic_snapshot,0u,__ATOMIC_SEQ_CST);return;
    }
    for(unsigned i=0;i<4;i++) {
        unsigned compatible=word(context+0x10b08+i*4);
        if(compatible>=1 && compatible<=24)mask|=1u<<(compatible-1);
    }
    unsigned packed=mask|(key<<24)|((unsigned)(deck+1)<<29);
    __atomic_store_n(&harmonic_snapshot,packed,__ATOMIC_SEQ_CST);
}
static void publish_key(unsigned deck,int key,int shift)
{
    if(deck>1)return;
    unsigned value=key>=0 && key<24 && shift>=-12 && shift<=12?
        (unsigned)(key+1)|((unsigned)(shift+12)<<5):0;
    unsigned previous=__atomic_exchange_n(&deck_keys[deck],value,__ATOMIC_SEQ_CST);
    if((previous&31u)!=(value&31u))invalidate_metadata();
    if(!value) {
        unsigned snapshot=__atomic_load_n(&harmonic_snapshot,__ATOMIC_SEQ_CST);
        if((snapshot>>29)==deck+1)__atomic_compare_exchange_n(&harmonic_snapshot,&snapshot,0u,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
    }
}
static struct rx3_harmonic_reference harmonic_reference(void)
{
    struct rx3_harmonic_reference result={-1,-1,0};
    int deck=master_deck();if(deck<0)return result;
    unsigned packed=__atomic_load_n(&harmonic_snapshot,__ATOMIC_SEQ_CST);
    unsigned published=__atomic_load_n(&deck_keys[deck],__ATOMIC_SEQ_CST);
    int source=(int)((packed>>24)&31u)-1;
    unsigned mask=packed&0xffffffu;
    if((packed>>29)!=(unsigned)deck+1 || source<0 || source>=24 ||
       (published && (int)(published&31u)-1!=source)) {
        /* Loading or switching MASTER need not wait for another Browse page.
         * Use the published deck key and classic Camelot neighbours until
         * the native browser publishes its exact set for that same source. */
        if(!published)return result;
        source=(int)(published&31u)-1;mask=0;
        for(int key=0;key<24;key++)if(rx3_camelot_compatible(source,key))mask|=1u<<key;
    }
    int shift=published?(int)(published>>5)-12:0;
    result.deck=deck;result.key=rx3_harmonic_shifted(source,shift);
    for(int key=0;key<24;key++)if(mask&(1u<<key))
        result.native_keys|=1u<<(unsigned)rx3_harmonic_shifted(key,shift);
    return result;
}
static unsigned half(const void *p){uint16_t v;memcpy(&v,p,2);return v;}
static void put_half(void *p,unsigned v){uint16_t h=(uint16_t)v;memcpy(p,&h,2);}
static int track(unsigned k)
{
    switch(k&255u) {
    case 4:case 0x5a:case 0x5d:case 0x5b:case 0x5c:case 0xc:case 0x2f:
    case 0x60:case 0x31:case 0x61:case 0x65:case 0x66:case 0x68:case 0x69:
    case 0x6b:case 0x6c:case 0x6e:case 0x6f:case 0x47:case 0x48:case 0x49:
    case 0x74:case 0x76:return 1;
    default:return 0;
    }
}
/* Category navigation does not always resend the right-column stream.
 * Recheck the live native left-list cache rather than a stale row-hook flag. */
static int native_track_layout(void)
{
    const uint8_t *context=__atomic_load_n(&list_context,__ATOMIC_SEQ_CST);
    if(!context)return 0;
    unsigned index=word(context+4);if(index>4)return 0;
    unsigned offset=0x17eacu+index*0x1d1cu,count=word(context+offset-4);
    return count && count<=14 && track(half(context+offset+4));
}
static unsigned copy_text(uint16_t *out,const uint16_t *in,unsigned max)
{
    unsigned n=0;if(in)while(n<max && in[n]){out[n]=in[n];n++;}
    if(n && out[n-1]>=0xd800 && out[n-1]<=0xdbff)n--;
    out[n]=0;return n;
}
static void key_text(unsigned key,uint16_t *out)
{
    unsigned n=0;if(key>=1 && key<=24) {
        unsigned number=(key+1)/2;
        if(number>=10)out[n++]='1';
        out[n++]=(uint16_t)('0'+number%10);out[n++]=(key&1)?'A':'B';
    }
    out[n]=0;
}
/* Runs on the native database task after its existing row stream is consumed.
 * The renderer never performs I/O. Stream records and strings retain native
 * allocator ownership; only bounded UTF-16 copies cross into the UI message. */
static int values_for(void *db,unsigned id,unsigned key,unsigned field,uint16_t out[128],
                       unsigned second,uint16_t other[128])
{
    out[0]=other[0]=0;
    if(field==15)key_text(key,out);
    if(second==15)key_text(key,other);
    if((!field || field==15) && (!second || second==15))return 1;
    METRIC_ADD(field_queries,1);
    unsigned total=(unsigned)metadata(db,2,id),first=0;
    if(!total || total>64)return 0;
    uint8_t *connection=(void *)(unsigned long)word(db);
    unsigned traffic=connection?word(connection+0xb94u):0;
    unsigned consumed=0,formatted=1;
    if(records(db,2,&first,total,0,total,0)) {
        for(unsigned i=0;i<total;i++) {
            uint32_t r[10]={0};
            if(!next_record(db,r,0,0))break;
            consumed++;
            unsigned kind=r[2]&255u;
            if(kind!=15 && ((field && kind==field) || (second && kind==second))) {
                uint16_t *text=format(r[0],r[1],kind,0xffffu);
                if(!text)formatted=0;
                if(kind==field)copy_text(out,text,127);
                if(kind==second)copy_text(other,text,127);
                if(text)free_text(text);
            }
            if(r[7])free_item((void *)(unsigned long)r[7]);
        }
        skip(db);
    }
    if(connection)memcpy(connection+0xb94u,&traffic,4);
    for(unsigned i=0;i<2;i++) {
        if((i?second:field)!=13)continue;
        uint16_t *value=i?other:out;
        unsigned n=0;while(n<127 && value[n])n++;
        if(n>=4 && value[n-4]==' ' && value[n-3]=='b' && value[n-2]=='p' && value[n-1]=='m')value[n-4]=0;
    }
    return consumed==total && formatted;
}
/* Capture local USB metadata on the native database SERVER task while it is
 * preparing visible records. Never issue EDB calls on the client or renderer.
 * The client consumes bounded copies, so it adds no per-track mailbox trips.
 * Each server page replaces this snapshot, including across USB remounts. */
struct local_metadata {
    unsigned id,drive,key,bpm,length,valid,generation,has_artist,has_key;
    uint16_t artist[128];
};
static struct local_metadata local_page[32];
static unsigned local_gate,local_next,local_generation;
static unsigned metadata_clock(void);
static struct installed_hook local_page_hook,local_record_hook;
static int (*original_local_page)(void *,void *);
static void *(*original_local_record)(void *,const uint32_t *,unsigned,unsigned,unsigned,unsigned);
static void *(*edb_select)(int *,const char *,const char *,unsigned,unsigned,unsigned,
                           const char *,unsigned,const unsigned **)=(void *)0x3dd464u;
static void *(*edb_next)(void *,int *)=(void *)0x3ddd78u;
static void *(*edb_column)(void *,unsigned)=(void *)0x3dde5cu;
static int (*edb_close)(void *)=(void *)0x3ddb24u;
static unsigned (*local_key)(unsigned,unsigned)=(void *)0x16095cu;
static int (*table_string)(unsigned,unsigned,unsigned,uint16_t **,unsigned,unsigned)=(void *)0x19e360u;
static void (*edb_free)(void *)=(void *)0x175038u;
static int local_lock(void){return !__atomic_exchange_n(&local_gate,1u,__ATOMIC_ACQUIRE);}
static void local_unlock(void){__atomic_store_n(&local_gate,0u,__ATOMIC_RELEASE);}
static int local_page_rows(void *context,void *request)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    __atomic_add_fetch(&local_generation,1u,__ATOMIC_SEQ_CST);
    if(local_lock()){memset(local_page,0,sizeof(local_page));local_next=0;local_unlock();}
    int result=original_local_page(context,request);
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return result;
}
static void *local_record(void *context,const uint32_t *record,unsigned drive,
                          unsigned kind,unsigned mode,unsigned category)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    void *result=original_local_record(context,record,drive,kind,mode,category);
    if(result && kind==1 && drive>1 && drive<4 && (mode==1 || mode==2) &&
       (track(record[4]&255u)) && (column || marker)) {
        unsigned started=metadata_clock();
        /* Each lookup is a DeviceSQL read on the stick being browsed. Fetch only
         * what a visible field or the key marker can ask for; the client falls
         * back to its own path for anything this snapshot did not capture. */
        unsigned wanted=column?column->field:0,kept=__atomic_load_n(&preserve_field,__ATOMIC_SEQ_CST);
        int want_artist=wanted==7 || kept==7,want_key=marker || wanted==15 || kept==15;
        struct local_metadata item;memset(&item,0,sizeof(item));
        item.generation=__atomic_load_n(&local_generation,__ATOMIC_SEQ_CST);
        item.id=record[0];item.drive=drive;
        const unsigned *id=&item.id;int error=0;
        void *set=edb_select(&error,"djdbContent","idxContent",0,0,0,"=",1,&id);
        if(set && !error) {
            void *row=edb_next(set,&error);
            if(row && !error) {
                const void *bpm=edb_column(row,8),*length=edb_column(row,9),*artist=edb_column(row,5);
                if(bpm && length && artist) {
                    item.bpm=word(bpm);item.length=half(length);item.valid=1;
                    if(want_artist) {
                        uint16_t *name=0;
                        if(table_string(7,word(artist),item.id,&name,1,drive)>=0) {
                            copy_text(item.artist,name,127);item.has_artist=1;
                        } else item.valid=0;
                        if(name)edb_free(name);
                    }
                }
            }
        }
        if(set)edb_close(set);
        METRIC_ADD(local_records,1);
        if(item.valid) {
            if(want_key){item.key=local_key(item.id,drive);item.has_key=1;}
            if(local_lock()) {
                local_page[local_next]=item;local_next=(local_next+1u)%32u;
                local_unlock();
            }
        }
        METRIC_ADD(local_ms,metadata_clock()-started);
    }
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return result;
}
static int local_field(unsigned field){return !field || field==7 || field==11 || field==13 || field==15;}
static unsigned decimal_text(uint16_t *out,unsigned value)
{
    uint16_t reverse[10];unsigned n=0;
    do{reverse[n++]=(uint16_t)('0'+value%10u);value/=10u;}while(value && n<10);
    for(unsigned i=0;i<n;i++)out[i]=reverse[n-i-1];
    return n;
}
static int local_value(const struct local_metadata *item,unsigned field,uint16_t out[128])
{
    out[0]=0;if(!field)return 1;
    if(field==7){if(!item->has_artist)return 0;copy_text(out,item->artist,127);return 1;}
    if(field==15){if(!item->has_key)return 0;key_text(item->key,out);return 1;}
    /* ConvertRKey2RStr consumes a DBCCmd-owned input string, including for
     * numbers. These snapshots own no such string: format the bounded number. */
    unsigned n=0;
    if(field==13 && item->bpm && item->bpm!=0x7fffffffu) {
        unsigned tenths=(item->bpm+5u)/10u;
        n=decimal_text(out,tenths/10u);out[n++]='.';out[n++]=(uint16_t)('0'+tenths%10u);
    } else if(field==11 && item->length) {
        n=decimal_text(out,item->length/60u);out[n++]=':';
        out[n++]=(uint16_t)('0'+item->length%60u/10u);out[n++]=(uint16_t)('0'+item->length%10u);
    }
    out[n]=0;return 1;
}
static int local_cached_values(unsigned drive,unsigned id,unsigned field,uint16_t value[128],
                                unsigned second,uint16_t other[128],unsigned *key)
{
    struct local_metadata item;int found=0;
    if(!local_lock())return 0;
    unsigned generation=__atomic_load_n(&local_generation,__ATOMIC_SEQ_CST);
    for(unsigned i=0;i<32;i++)if(local_page[i].valid && local_page[i].generation==generation && local_page[i].id==id && local_page[i].drive==drive) {
        item=local_page[i];found=1;break;
    }
    local_unlock();
    if(!found)return 0;
    /* A snapshot taken before the key marker registered carries no key. */
    if(marker && !item.has_key)return 0;
    *key=item.key;
    return local_value(&item,field,value) && local_value(&item,second,other);
}
static int local_values(void *db,unsigned id,unsigned field,uint16_t value[128],
                         unsigned second,uint16_t other[128],unsigned *key)
{
    if(!original_local_page || !original_local_record || !local_field(field) || !local_field(second))return 0;
    const uint8_t *connection=(void *)(unsigned long)word(db);
    /* SetHeader: db[1] is the drive byte, db[2] the database kind.
     * Remote players have connection[1]!=0 and cannot use our local snapshot. */
    if(!connection || word(connection+4) || word((uint8_t *)db+8)!=1)return 0;
    return local_cached_values(word((uint8_t *)db+4),id,field,value,second,other,key);
}
/* Two viewports, bounded to ~34 KiB. Cache raw metadata, never classifications:
 * MASTER, native green and selected rules are evaluated on every message.
 * Native source, row and settings changes invalidate entries; time alone does not.
 * A failed lookup is retried; an empty but complete field stream is cacheable. */
enum { METADATA_SLOTS=32 };
static struct {
    const void *context,*db;
    unsigned connection,index,depth,sort,field,second,epoch;
} metadata_scope;
static struct {
    unsigned used,id,key,key_valid,values_valid,key_time,value_time;
    uint8_t identity[532];
    uint16_t value[128],other[128];
} metadata_cache[METADATA_SLOTS];
static unsigned metadata_next;
static unsigned metadata_clock(void)
{
    struct {long seconds,micros;} now;
    if(gettimeofday(&now,0))return 0;
    return (unsigned)((uint64_t)now.seconds*1000u+(unsigned long)now.micros/1000u);
}
static unsigned (*metadata_now)(void)=metadata_clock;
static void metadata_bind(const void *context,void *db,unsigned index,unsigned depth,
                          unsigned sort,unsigned field,unsigned second)
{
    unsigned epoch=__atomic_load_n(&metadata_epoch,__ATOMIC_SEQ_CST),connection=word(db);
    if(metadata_scope.context!=context || metadata_scope.db!=db ||
       metadata_scope.connection!=connection || metadata_scope.index!=index ||
       metadata_scope.depth!=depth || metadata_scope.sort!=sort ||
       metadata_scope.field!=field || metadata_scope.second!=second || metadata_scope.epoch!=epoch) {
        METRIC_ADD(scopes,1);
        memset(metadata_cache,0,sizeof(metadata_cache));metadata_next=0;
        metadata_scope.context=context;metadata_scope.db=db;metadata_scope.connection=connection;
        metadata_scope.index=index;metadata_scope.depth=depth;metadata_scope.sort=sort;
        metadata_scope.field=field;metadata_scope.second=second;metadata_scope.epoch=epoch;
    }
}
static unsigned metadata_values(void *db,unsigned id,const uint8_t identity[532],int need_key,
                                unsigned field,uint16_t value[128],unsigned second,uint16_t other[128])
{
    value[0]=other[0]=0;
    if(!need_key && !field && !second)return 0;
    unsigned slot=METADATA_SLOTS;
    for(unsigned i=0;i<METADATA_SLOTS;i++)if(metadata_cache[i].used && metadata_cache[i].id==id &&
        !memcmp(metadata_cache[i].identity,identity,532)) {slot=i;break;}
    if(slot==METADATA_SLOTS) {
        METRIC_ADD(misses,1);
        slot=metadata_next;metadata_next=(metadata_next+1u)%METADATA_SLOTS;
        memset(&metadata_cache[slot],0,sizeof(metadata_cache[slot]));
        metadata_cache[slot].used=1;metadata_cache[slot].id=id;
        memcpy(metadata_cache[slot].identity,identity,532);
    } else METRIC_ADD(hits,1);
    /* Exported USB metadata follows the native list/source lifetime. A wall
     * clock timeout forced an entire visible page through synchronous I/O. */
    {
        unsigned key=0;
        if(local_values(db,id,field,metadata_cache[slot].value,second,metadata_cache[slot].other,&key)) {
            metadata_cache[slot].values_valid=1;metadata_cache[slot].key=key;
            metadata_cache[slot].key_valid=key<=24;
            METRIC_ADD(local_hits,1);
        }
    }
    unsigned key=0;
    if(need_key) {
        if(!metadata_cache[slot].key_valid) {
            METRIC_ADD(key_queries,1);
            metadata_cache[slot].key=track_key(db,id);
            metadata_cache[slot].key_valid=metadata_cache[slot].key>=1 && metadata_cache[slot].key<=24;
            metadata_cache[slot].key_time=metadata_now();

        }
        key=metadata_cache[slot].key;
    }
    if(field || second) {
        if(!metadata_cache[slot].values_valid) {
            metadata_cache[slot].values_valid=values_for(db,id,key,field,metadata_cache[slot].value,
                                                       second,metadata_cache[slot].other);
            metadata_cache[slot].value_time=metadata_now();

        }
        memcpy(value,metadata_cache[slot].value,256);memcpy(other,metadata_cache[slot].other,256);
        /* Key text follows the current key lookup, including failed lookups. */
        if(field==15)key_text(key,value);
        if(second==15)key_text(key,other);
    }
    return key;
}
/* Extension travels inside each native row, so queued updates, scrolling and
 * duplicate artist names cannot associate a value with the wrong track.
 * Only this renderer interprets the noncharacter-delimited suffix. */
static unsigned append(uint8_t *dest,const uint8_t *entry,const uint16_t *value,unsigned image)
{
    unsigned len=half(entry+20),extra=0;
    while(extra<127 && value[extra])extra++;
    unsigned prefix=len,room=255u-extra-4u;
    if(prefix>room)prefix=room;
    const uint16_t *text=(const void *)(entry+22);
    if(prefix && text[prefix-1]>=0xd800 && text[prefix-1]<=0xdbff)prefix--;
    memcpy(dest,entry,22+prefix*2);
    if(prefix<len && prefix)put_half(dest+22+(prefix-1)*2,0x2026);
    unsigned n=prefix;
    put_half(dest+22+n++*2,SEP);put_half(dest+22+n++*2,image+1u);
    memcpy(dest+22+n*2,value,extra*2);n+=extra;
    put_half(dest+22+n++*2,END);put_half(dest+22+n++*2,SEP);
    put_half(dest+20,n);return 22+n*2;
}
static uint8_t *replace_row_field(uint8_t *entry,uint8_t replacement[532],
                                 const uint16_t *value,unsigned field,unsigned row,
                                 unsigned *category)
{
    /* Header kind 98 is also the native filter-applied state. */
    if(!row)return entry;
    unsigned length=0;while(length<127 && value[length])length++;
    memcpy(replacement,entry,22);put_half(replacement+20,length);
    memcpy(replacement+22,value,length*2);
    if(*category!=52)*category=field;
    return replacement;
}
static unsigned observed_sort(unsigned code)
{
    unsigned base=code&127u;
    int down=(code&0x4000u)?(code&0x8000u)!=0:
        base==5 || base==8 || base==13 || base==16 || base==17;
    return base|(down?128u:0u);
}
static unsigned semantic_field(unsigned category,unsigned previous)
{
    /* Compatibility badges are row presentation, never metadata categories. */
    if(category==51 || category==52 || (category>=120 && category<=122))
        return previous?previous:15;
    return category;
}
static void process(uint8_t *context,uint8_t *message,
                    const struct rx3_browse_column *column,
                    const struct rx3_browse_marker *marker)
{
    observe_harmony(context);
    __atomic_store_n(&list_context,context,__ATOMIC_SEQ_CST);
    __atomic_store_n(&track_list,0u,__ATOMIC_SEQ_CST);
    unsigned index=word(context+4),bytes=word(message+0x1c),count=half(message+0x80);
    if(index>4 || bytes<20 || bytes>MAX_MESSAGE-0x70 || count<2 || count>15){invalidate_metadata();return;}
    unsigned rows=0x17eacu+index*0x1d1cu,available=word(context+rows-4);
    if(available>14 || count>available+1){invalidate_metadata();return;}
    void *db=(void *)(unsigned long)word(context+(index+0x1bceu)*4u+4u);
    if(!db || !word(db)){invalidate_metadata();return;}
    unsigned native_sort=word((uint8_t *)db+16);
    __atomic_store_n(&sort_observed,observed_sort(native_sort),__ATOMIC_SEQ_CST);
    if(preserve_field && (preserve_db!=(unsigned)(unsigned long)db || preserve_depth!=word((uint8_t *)db+4)))preserve_field=0;
    /* A folder/category list remains the native two-pane navigator. */
    for(unsigned i=0;i<count-1;i++)if(!track(half(context+rows+i*532+4))){invalidate_metadata();return;}
    __atomic_store_n(&track_list,1u,__ATOMIC_SEQ_CST);
    __atomic_store_n(&primary_field,half(context+rows+4),__ATOMIC_SEQ_CST);
    unsigned source=20;
    for(unsigned i=0;i<count;i++) {
        if(source+22>bytes){invalidate_metadata();return;}
        unsigned len=half(message+0x70+source+20);
        if(len>255 || source+22+len*2>bytes){invalidate_metadata();return;}
        source+=22+len*2;
    }
    unsigned first_row=0x84u+22u+half(message+0x98u)*2u;
    unsigned depth=word((uint8_t *)db+4);
    if(secondary_db!=(unsigned)(unsigned long)db || secondary_depth!=depth)secondary_field=0;
    secondary_db=(unsigned)(unsigned long)db;secondary_depth=depth;
    unsigned second=preserve_field?preserve_field:semantic_field(half(message+first_row),secondary_field);
    __atomic_store_n(&secondary_field,second,__ATOMIC_SEQ_CST);
    unsigned expected=0;
    if(!__atomic_compare_exchange_n(&busy,&expected,1u,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)){invalidate_metadata();return;}
    memcpy(rebuilt,message,0x84);source=20;unsigned dest=20;
    metadata_bind(context,db,index,depth,native_sort,column?column->field:0,preserve_field);
    struct rx3_harmonic_reference harmony=harmonic_reference();
    unsigned ref=word(context+0x10af8) && harmony.key>=0?(unsigned)harmony.key+1:0;
    for(unsigned i=0;i<count;i++) {
        uint8_t *entry=message+0x70+source;
        unsigned old_size=22+half(entry+20)*2,category=half(entry),key=0;
        uint16_t value[128]={0},native_value[128]={0};unsigned badge=0;
        if(i) {
            unsigned id=word(context+rows+(i-1)*532);
            int need_key=(marker && ref) || (column && (column->field==15 || preserve_field==15));
            key=metadata_values(db,id,context+rows+(i-1)*532,need_key,
                                column?column->field:0,value,preserve_field,native_value);
            if(marker && ref && key>=1 && key<=24) {
                if(harmony.native_keys&(1u<<(key-1)))category=52;
            }
            if(marker)category=marker->category(ref,key,category);
            if(column) {
                if(!value[0]){value[0]=0x2014;value[1]=0;}
                if(column->field==15 && marker)badge=marker->image(category);
            }
        } else if(column)copy_text(value,column->caption,127);
        uint8_t replacement[532];
        if(column && preserve_field) {
            entry=replace_row_field(entry,replacement,native_value,preserve_field,i,&category);
            if(i && marker)category=marker->category(ref,key,category);
        }
        unsigned size=column?append(rebuilt+0x70+dest,entry,value,badge):old_size;
        if(!column)memcpy(rebuilt+0x70+dest,entry,size);
        put_half(rebuilt+0x70+dest,category);dest+=size;source+=old_size;
    }
    /* 15 native maximum-length strings fit the original 8 KiB message. */
    memcpy(rebuilt+0x1c,&dest,4);memcpy(message,rebuilt,0x70+dest);
    __atomic_store_n(&busy,0u,__ATOMIC_SEQ_CST);
}
static int rows(void *context,void *message,void *request)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    unsigned started=metadata_now();
    int result=original_rows(context,message,request);
    unsigned native_done=metadata_now();
    const struct rx3_browse_column *c=__atomic_load_n(&column,__ATOMIC_SEQ_CST);
    const struct rx3_browse_marker *m=__atomic_load_n(&marker,__ATOMIC_SEQ_CST);
    if(c || m) {
        process(context,message,c,m);
        unsigned done=metadata_now();
        METRIC_ADD(pages,1);
        if(started && native_done)METRIC_ADD(native_ms,native_done-started);
        if(native_done && done)METRIC_ADD(added_ms,done-native_done);
    }
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return result;
}
static int ensure(void)
{
    if(original_rows)return 1;
    static const struct {unsigned address,a,b;} guards[]={
        {0x3dd464,0xe92d4ff0,0xe24dd04c},
        {0x3ddd78,0xe92d41f0,0xe24dd020},
        {0x3dde5c,0xeaffe2fa,0xe92d4038},
        {0x3ddb24,0xe92d40f0,0xe24dd01c},
        {0x16095c,0xe92d41f0,0xe24dd028},
        {0x19e360,0xe92d41f0,0xe24dd0c8},
        {0x265f48,0xe92d40f0,0xe2507000},{0x2637f4,0xe1a0c001,0xe1a03002},
        {0x262884,0xe92d4ff0,0xe24dd00c},{0x262a28,0xe92d4ff0,0xe24dd014},
        {0x262da0,0xe92d4ff0,0xe24dd00c},{0x26a480,0xe352000d,0x13520011},
        {0x1f648c,0xe3500000,0x012fff1e},{0x175038,0xe92d4070,0xe2504000},
        {0x18dae8,0xe2503000,0xe92d4010},{0x18e1a0,0xe92d4070,0xe1a04000}};
    for(unsigned i=0;i<sizeof(guards)/sizeof(*guards);i++)
        if(memcmp((const void *)(unsigned long)guards[i].address,&guards[i].a,8))return 0;
    static const uint8_t guard[8]={0xf0,0x4f,0x2d,0xe9,0x2c,0xd0,0x4d,0xe2};
    original_rows=(void *)install_hook(&row_hook,ROW_HOOK,guard,(void *)rows);
    if(!original_rows)return 0;
    static const uint32_t page_guard[2]={0xe92d4ff0u,0xe24dd064u};
    static const uint32_t record_guard[2]={0xe92d4ff0u,0xe24dd014u};
    original_local_page=(void *)install_hook(&local_page_hook,0x20805cu,(const uint8_t *)page_guard,(void *)local_page_rows);
    if(original_local_page)original_local_record=(void *)install_hook(&local_record_hook,0x207dd0u,(const uint8_t *)record_guard,(void *)local_record);
    /* A failed optional optimization keeps the existing metadata path. */
    return 1;
}
/* Only the on-screen list actions are intercepted; physical LOAD keys call
 * UiKey_Load1/2 directly. Never leave an invisible load action under metadata. */
static int list_load(unsigned deck,unsigned event)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    int result=__atomic_load_n(&column,__ATOMIC_SEQ_CST)?0:original_load[deck](event);
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    return result;
}
static int list_load1(unsigned event){return list_load(0,event);}
static int list_load2(unsigned event){return list_load(1,event);}
static void remove_load_hooks(void)
{
    for(unsigned i=0;i<2;i++)if(original_load[i] && detach_hook(&load_hooks[i])) {
        while(__atomic_load_n(&callbacks,__ATOMIC_SEQ_CST))usleep(1000);
        release_hook(&load_hooks[i]);original_load[i]=0;
    }
}
static int install_load_hooks(void)
{
    static const uint8_t guard[8]={0x10,0x40,0x2d,0xe9,0x00,0x40,0xa0,0xe1};
    original_load[0]=(void *)install_hook(&load_hooks[0],0x11d9b0u,guard,(void *)list_load1);
    if(original_load[0])original_load[1]=(void *)install_hook(&load_hooks[1],0x11d83cu,guard,(void *)list_load2);
    if(original_load[0] && original_load[1])return 1;
    remove_load_hooks();return 0;
}
/* Native sort IDs differ from metadata categories. Default/title sorts use
 * 1, artist 2, BPM 4, duration 8 and key 12. Direction is supplied separately to the native comparator. */
static unsigned sort_for_field(unsigned field)
{
    if(track(field))return 1;
    switch(field&255u) {
    case 7:return 2;case 2:return 3;case 13:return 4;case 10:return 5;
    case 6:return 6;case 35:return 7;case 11:return 8;case 41:return 9;
    case 14:return 10;case 40:return 11;case 15:return 12;case 16:return 13;
    default:return 0;
    }
}
/* Touch posts a private command; the native worker owns sequence numbers and
 * wait state. Only our pending request gets a reserved selector. Database work
 * stays on the database task, through its normal request/response transport. */
/* Native Ui_Event -> BrowseComm envelope. The renderer's touch callback is
 * not BrowseKeyProcessing: MenuEnter() only stages a command for that caller.
 * Allocate from the native pool and transfer ownership to the native mailbox,
 * identifying this input as a UI event just like SendMessage_ToBrowseComm. */
static int enqueue_sort(void)
{
    unsigned pool=word((void *)0x03268be0u);uint32_t *msg=0;
    if(get_message(pool,(void **)&msg,0x1808u) || !msg)return 0;
    memset(msg,0,0x70);
    msg[1]=word((void *)0x0042dcb8u);msg[2]=0x32c9;
    msg[4]=word((void *)0x03268b20u);msg[6]=pool;msg[8]=0x70;
    msg[9]=0x10fe;msg[10]=0x52583353u;
    msg[0x1a]=active_deck()==2;msg[0x1b]=native_time();
    if(send_message(word((void *)0x03267230u),msg)) {free_message(pool,msg);return 0;}
    return 1;
}
static int sort_validate(void *context,void *message)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    unsigned pending=__atomic_load_n(&sort_pending,__ATOMIC_SEQ_CST);
    int result=original_sort_validate(context,message);
    if(pending && word((uint8_t *)message+0x24)==0x10feu &&
       word((uint8_t *)message+0x28)==0x52583353u) {
        if(!result || !column || !track_list || !track_layout() || !browse_visible() || menu_visible() ||
           native_sort_request(context,0x7e00u|pending,word((uint8_t *)message+0x68)))
            __atomic_store_n(&sort_pending,0u,__ATOMIC_SEQ_CST);
        /* Consume this command before native MENU_ENTER checks its menu-only
         * cursor. Its normal DB response will update the browser. */
        result=0;
    }
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return result;
}
static int sort_select(void *context,void *response,void *request)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    unsigned item=half((uint8_t *)request+0x78);int result;
    if((item&0xff00u)!=0x7e00u){preserve_field=0;secondary_field=0;result=original_sort_select(context,response,request);}
    else {
        unsigned code=item&255u;
        uint8_t *ctx=context;unsigned index=word(ctx+4);
        if(column && track_list && index<=4 && code==sort_pending) {
            static const uint16_t empty[]={0};
            preserve_field=__atomic_load_n(&secondary_field,__ATOMIC_SEQ_CST);
            preserve_db=word(ctx+(index+0x1bceu)*4u+4u);
            preserve_depth=preserve_db?word((uint8_t *)(unsigned long)preserve_db+4):0;
            ctx[0x15]=1;
            unsigned native_code=0x4000u|(code&127u)|((code&128u)?0x8000u:0u);
            result=send_sorted(context,response,request,(int)native_code,empty);
        } else result=0;
        __atomic_store_n(&sort_pending,0u,__ATOMIC_SEQ_CST);
    }
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return result;
}
/* The native dispatcher narrows the sort to a signed byte. Retain our full
 * request only for the synchronous call on its native task (IDs 1..48). The
 * native cache still compares the complete request, including direction. */
static int sort_dispatch(void *context,void *message)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    unsigned task=native_task(),saved=0;
    if(task && task<49) {
        void *request=(void *)(unsigned long)word((uint8_t *)message+0x1c);
        saved=task_sort[task];task_sort[task]=request?word((uint8_t *)request+0x18):0;
    }
    int result=original_sort_dispatch(context,message);
    if(task && task<49)task_sort[task]=saved;
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return result;
}
/* Reserved bits belong only to requests from this service. Native record
 * extraction masks them; the comparator explicitly receives direction bit 7. */
static void sort_keys(unsigned node,unsigned code,int grouped)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    unsigned task=native_task();
    if(task && task<49 && (task_sort[task]&0x4000u) && (task_sort[task]&127u)==code)code=task_sort[task];
    if(!(code&0x4000u))original_sort_keys(node,code,grouped);
    else {
        unsigned base=code&127u,kind;
        switch(base) {
        case 2:case 3:case 6:case 7:case 9:case 10:case 11:case 12:kind=2;break;
        case 4:case 5:case 8:case 13:case 15:case 16:case 17:kind=4;break;
        default:kind=1;break;
        }
        unsigned flags=kind|((code&0x8000u)?0x80u:0u)|(grouped==1?0x40u:0u);
        set_sort_type((void *)0x032c682cu,node,flags,kind==1?3u:1u,kind==1?0u:3u);
    }
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
}
static void remove_sort_hooks(void)
{
    for(unsigned i=0;i<4;i++)if(hook_is_installed(&sort_hooks[i]) && detach_hook(&sort_hooks[i])) {
        while(__atomic_load_n(&callbacks,__ATOMIC_SEQ_CST))usleep(1000);
        release_hook(&sort_hooks[i]);
    }
    original_sort_validate=0;original_sort_select=0;original_sort_keys=0;original_sort_dispatch=0;sort_pending=0;sort_capture=0;preserve_field=0;
}
static int install_sort_hooks(void)
{
    static const struct {unsigned address,a,b;} guards[]={
        {0x18a904,0xe92d4008,0xebfa1021},{0x17bd28,0xe92d41f0,0xe302596c},{0x186fc4,0xe92d40f0,0xe24dd00c},
        {0x187068,0xe3500000,0x012fff1e},{0x186e18,0xeaffde69,0xeaffded6},
        {0x187290,0xe52de004,0xe24dd00c},{0x1341d8,0xe30c3a08,0xe3403114},{0xd07d8,0xe2800004,0xe12fff1e},
        {0x112e10,0xe30f38b8,0xe3403326},{0x256030,0xe92d4ff0,0xe1a09002},
        {0x1d2dec,0xe1d131b0,0xe92d4ff0},{0x110c50,0xe92d4070,0xe24dd010}};
    for(unsigned i=0;i<sizeof(guards)/sizeof(*guards);i++)
        if(memcmp((void *)(unsigned long)guards[i].address,&guards[i].a,8))return 0;
    static const uint8_t req_guard[]={0x38,0x40,0x2d,0xe9,0x01,0x50,0xa0,0xe1};
    static const uint8_t sel_guard[]={0xf0,0x4f,0x2d,0xe9,0xc8,0x8f,0x06,0xe3};
    original_sort_select=(void *)install_hook(&sort_hooks[1],0x2596ccu,sel_guard,(void *)sort_select);
    if(original_sort_select)original_sort_validate=(void *)install_hook(&sort_hooks[0],0x104edcu,req_guard,(void *)sort_validate);
    static const uint8_t key_guard[]={0x01,0x10,0x41,0xe2,0x30,0x40,0x2d,0xe9};
    if(original_sort_validate)original_sort_keys=(void *)install_hook(&sort_hooks[2],0x171780u,key_guard,(void *)sort_keys);
    static const uint8_t dispatch_guard[]={0xf0,0x40,0x2d,0xe9,0x01,0x50,0xa0,0xe1};
    if(original_sort_keys)original_sort_dispatch=(void *)install_hook(&sort_hooks[3],0x153530u,dispatch_guard,(void *)sort_dispatch);
    if(original_sort_validate && original_sort_select && original_sort_keys && original_sort_dispatch)return 1;
    remove_sort_hooks();return 0;
}
static unsigned header_at(int x,int y)
{
    if(y<50 || y>=100 || x<434 || x>=1280)return 0;
    return x<855?1u:x<1118?2u:3u;
}
int rx3_browse_touch(int x,int y,int pressed)
{
    unsigned cell=header_at(x,y);
    static int down;
    int began=pressed && !down;down=pressed;
    int active=column && track_list && track_layout() && browse_visible() && !menu_visible();
    if(sort_capture) {
        if(!active || cell!=sort_capture)sort_cancelled=1;
        if(!pressed) {
            unsigned target=sort_capture;sort_capture=0;
            if(!sort_cancelled && !sort_pending) {
                unsigned field=target==3?column->field:target==1?primary_field:secondary_field;
                unsigned code=sort_for_field(field);
                if(code) {
                    if((sort_observed&127u)==code)code=sort_observed^128u;
                    __atomic_store_n(&sort_pending,code,__ATOMIC_SEQ_CST);if(!post_sort())sort_pending=0;
                }
            }
        }
        return 1;
    }
    if(active && cell && began) {sort_capture=cell;sort_cancelled=0;return 1;}
    return 0;
}
/* Use the two native Browse scrolling surfaces and their UI timers. No
 * animation thread, font renderer or separate scrolling engine is introduced. */
static struct installed_hook scroll_hooks[3];
static void (*original_scroll_prepare)(unsigned,unsigned);
static void (*original_scroll_start)(const uint16_t *,void *,unsigned);
static void (*original_scroll_run)(unsigned);
static void (*scroll_timer)(unsigned,unsigned,unsigned)=(void *)0x18e260u;
static void (*scroll_kill)(unsigned,unsigned)=(void *)0x18e2a0u;
static int (*scroll_destroy)(void *)=(void *)0x18e730u;
static void (*scroll_show)(void *,unsigned)=(void *)0x1cec2cu;
static uint8_t *scroll_state=(void *)0x02684610u;
static uint8_t *scroll_strings=(void *)0x0551abcau;
static const uint8_t *scroll_ids=(void *)0x004c97b8u;
static uint16_t scroll_text[2][256];
static unsigned scroll_owned[2],scroll_phase[2],scroll_seen[2],scroll_row[2];
enum { SCROLL_STEP_MS=60, SCROLL_TAIL_PX=24 };
static const void *scroll_selection=(void *)0x05b528ecu;
static void put_word(void *p,unsigned value){memcpy(p,&value,4);}
static void scroll_prepare(unsigned lane,unsigned row)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    if(lane>1 || row>11 || !column || !track_layout()) {
        if(lane<2){scroll_owned[lane]=0;scroll_phase[lane]=0;}
        original_scroll_prepare(lane,row);
    } else {
        uint8_t *state=scroll_state+lane*0x74;
        uint16_t *source=(void *)(scroll_strings+lane*0x1ce4+(row+1)*0x238);
        uint16_t saved[256];memcpy(saved,source,sizeof(saved));
        unsigned n=0;while(n<255 && saved[n] && saved[n]!=SEP)n++;
        memcpy(scroll_text[lane],saved,n*2);scroll_text[lane][n]=0;
        void *root=(void *)(unsigned long)word(root_pointer);
        void *glyph=root?object_by_id(root,(int)(int16_t)half(scroll_ids+0x100+(row+lane*12)*2)):0;
        unsigned right=glyph?half((uint8_t *)glyph+0x1c):0;
        /* The native right lane sees only its own text and actual width;
         * our in-row metadata transport never reaches the scroll surface. */
        if(lane==1 && glyph)put_half((uint8_t *)glyph+0x1c,1110);
        memcpy(source,scroll_text[lane],(n+1)*2);
        original_scroll_prepare(lane,row);
        memcpy(source,saved,sizeof(saved));
        if(lane==1 && glyph)put_half((uint8_t *)glyph+0x1c,right);
        put_word(state+0x20,(unsigned)(unsigned long)scroll_text[lane]);
        scroll_owned[lane]=1;scroll_phase[lane]=0;
        unsigned timer=word(state+0x38);
        if(timer){scroll_kill(0x82a,timer);scroll_timer(0x82a,timer,2000);}
    }
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
}
static void scroll_start(const uint16_t *text,void *glyph,unsigned lane)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    original_scroll_start(text,glyph,lane);
    if(lane<2 && column && scroll_owned[lane]) {
        unsigned timer=word(scroll_state+lane*0x74+0x10);
        scroll_kill(0x82a,timer);scroll_timer(0x82a,timer,SCROLL_STEP_MS);
    }
    if(lane==1 && column && scroll_owned[1]) {
        /* Keep the added field visible. The ordinary renderer omits only the
         * prefix while the native surface paints that part of the row. */
        scroll_show(glyph,1);
    }
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
}
/* Move the native repeated copy outside the viewport while it paints.
 * Keep its real measured width intact between calls. */
static void scroll_native_frame(unsigned lane,uint8_t *state,unsigned width,unsigned viewport)
{
    put_word(state+0x48,width+viewport+SCROLL_TAIL_PX);
    original_scroll_run(lane);
    put_word(state+0x48,width);
}
static void scroll_run(unsigned lane)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    if(lane<2 && column && scroll_owned[lane]) {
        uint8_t *state=scroll_state+lane*0x74;
        unsigned width=word(state+0x48),viewport=word(state+0x2c),timer=word(state+0x10);
        if(word(state+0x24) && width>viewport) {
            int offset=(int)word(state+0x58);unsigned end=width+SCROLL_TAIL_PX;
            if(scroll_phase[lane]==1) {
                /* Native run advances by three pixels. Draw the start again,
                 * then pause this same native timer for two seconds. */
                put_word(state+0x58,3);put_word(state+0x64,0);
                scroll_native_frame(lane,state,width,viewport);scroll_phase[lane]=2;
                scroll_kill(0x82a,timer);scroll_timer(0x82a,timer,2000);
                __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return;
            }
            if(scroll_phase[lane]==2) {
                scroll_phase[lane]=0;scroll_kill(0x82a,timer);scroll_timer(0x82a,timer,SCROLL_STEP_MS);
            }
            if(offset<=0 && (unsigned)(-offset)+3>=end) {
                put_word(state+0x58,(unsigned)(3-(int)end));scroll_phase[lane]=1;
            }
            scroll_native_frame(lane,state,width,viewport);
            __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);return;
        }
    }
    original_scroll_run(lane);
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
}
/* Stock scroll eligibility was computed before the added column narrowed the
 * text. Reuse its setup for the selected native glyph after layout is final. */
static void scroll_observe(void *model)
{
    if(!column || !track_layout() || !browse_visible() || menu_visible())return;
    unsigned row=word(scroll_selection);if(row>=12)return;
    void *root=(void *)(unsigned long)word(root_pointer);if(!root)return;
    const uint8_t *context=list_context;unsigned index=word(context+4);
    unsigned id=word(context+0x17eac+index*0x1d1c+row*532);
    for(unsigned lane=0;lane<2;lane++) {
        int glyph_id=(int)(int16_t)half(scroll_ids+0x100+(row+lane*12)*2);
        if(model!=object_by_id(root,glyph_id))continue;
        if(scroll_seen[lane]==id && scroll_row[lane]==row && scroll_owned[lane])return;
        uint8_t *state=scroll_state+lane*0x74;
        if(scroll_owned[lane]) {
            scroll_kill(0x82a,word(state+8));scroll_kill(0x82a,word(state+0x10));
            if(word(state+0x24))scroll_destroy(state+0x24);
            scroll_show((void *)(unsigned long)word(state+0x1c),1);
            int old_id=(int)(int16_t)half(scroll_ids+0x100+(scroll_row[lane]+lane*12)*2);
            refresh_object(root,old_id);
        }
        scroll_seen[lane]=id;scroll_row[lane]=row;scroll_prepare(lane,row);return;
    }
}
static void remove_scroll_hooks(void)
{
    for(unsigned i=0;i<3;i++)if(hook_is_installed(&scroll_hooks[i]) && detach_hook(&scroll_hooks[i])) {
        while(__atomic_load_n(&callbacks,__ATOMIC_SEQ_CST))usleep(1000);
        release_hook(&scroll_hooks[i]);
    }
    for(unsigned lane=0;lane<2;lane++)if(scroll_owned[lane]) {
        uint8_t *state=scroll_state+lane*0x74;
        scroll_kill(0x82a,word(state+8));scroll_kill(0x82a,word(state+0x10));
        scroll_destroy(state+0x24);
        scroll_show((void *)(unsigned long)word(state+0x1c),1);
        put_word(state+0x38,0);put_word(state+0x3c,0);
        scroll_owned[lane]=scroll_phase[lane]=0;
    }
    original_scroll_prepare=0;original_scroll_start=0;original_scroll_run=0;
}
static int install_scroll_hooks(void)
{
    static const struct {unsigned address,a,b;} guards[]={
        {0x18e260,0xe92d4070,0xe24dd008},{0x18e2a0,0xe92d4070,0xe1a04001},
        {0x18e730,0xe92d4010,0xe1a04000},{0x1cec2c,0xe3500000,0x0a00000a}};
    for(unsigned i=0;i<sizeof(guards)/sizeof(*guards);i++)
        if(memcmp((void *)(unsigned long)guards[i].address,&guards[i].a,8))return 0;
    static const uint8_t prep[]={0x80,0x30,0x80,0xe0,0xb0,0x22,0x9f,0xe5};
    static const uint8_t start[]={0xf0,0x4f,0x2d,0xe9,0x74,0xa0,0xa0,0xe3};
    static const uint8_t run[]={0xf0,0x4f,0x2d,0xe9,0x74,0x40,0xa0,0xe3};
    original_scroll_prepare=(void *)install_hook(&scroll_hooks[0],0x2995c8u,prep,(void *)scroll_prepare);
    if(original_scroll_prepare)original_scroll_start=(void *)install_hook(&scroll_hooks[1],0x2955d8u,start,(void *)scroll_start);
    if(original_scroll_start)original_scroll_run=(void *)install_hook(&scroll_hooks[2],0x29992cu,run,(void *)scroll_run);
    if(original_scroll_run)return 1;
    remove_scroll_hooks();return 0;
}
static int register_column(const void *owner,const struct rx3_browse_column *c)
{
    if(!owner || !c || !c->caption || column || !ensure() || !install_load_hooks())return 0;
    if(!install_sort_hooks()){remove_load_hooks();return 0;}
    if(!install_scroll_hooks()){remove_sort_hooks();remove_load_hooks();return 0;}
    column_owner=owner;__atomic_store_n(&column,c,__ATOMIC_SEQ_CST);return 1;
}
static int register_marker(const void *owner,const struct rx3_browse_marker *m)
{
    if(!owner || !m || !m->category || !m->image || marker || !ensure())return 0;
    marker_owner=owner;__atomic_store_n(&marker,m,__ATOMIC_SEQ_CST);return 1;
}
static void unregister_owner(const void *owner)
{
    invalidate_metadata();
    if(owner==column_owner){__atomic_store_n(&column,0,__ATOMIC_SEQ_CST);column_owner=0;remove_scroll_hooks();remove_load_hooks();remove_sort_hooks();}
    if(owner==marker_owner){__atomic_store_n(&marker,0,__ATOMIC_SEQ_CST);marker_owner=0;__atomic_store_n(&harmonic_snapshot,0u,__ATOMIC_SEQ_CST);}
    while(__atomic_load_n(&callbacks,__ATOMIC_SEQ_CST))usleep(1000);
    if(!column && !marker && original_rows) {
        if(original_local_record && !detach_hook(&local_record_hook))return;
        if(original_local_page && !detach_hook(&local_page_hook))return;
        if(!detach_hook(&row_hook))return;
        while(__atomic_load_n(&callbacks,__ATOMIC_SEQ_CST))usleep(1000);
        if(original_local_record){release_hook(&local_record_hook);original_local_record=0;}
        if(original_local_page){release_hook(&local_page_hook);original_local_page=0;}
        release_hook(&row_hook);original_rows=0;
    }
}
unsigned int rx3_browse_count(void){return column!=0 || marker!=0;}
const struct rx3_browse_service rx3_browse={register_column,register_marker,unregister_owner,harmonic_reference,publish_key};

/* Native glyph ABI: rect at 0x18, UTF-16 at 0x34, length byte at 0x38.
 * Keep the native font, colour, alignment and window ancestry. */
int rx3_browse_draw(void *render,void *model,void (*text)(void *,void *),void (*image)(void *,void *))
{
    const struct rx3_browse_column *selected=__atomic_load_n(&column,__ATOMIC_SEQ_CST);
    if(selected)scroll_observe(model);
    uint8_t *m=model;
    unsigned left=half(m+0x18),right=half(m+0x1c);
    const uint16_t *s=(void *)(unsigned long)word(m+0x34);
    unsigned n=m[0x38],split=0;
    if(!s || !n)return 0;
    if(n==255){n=0;while(n<255 && s[n])n++;}
    if(n<4 || s[n-2]!=END || s[n-1]!=SEP)return 0;
    while(split<n-3 && s[split]!=SEP)split++;
    if(split>=n-3 || !s[split+1])return 0;
    unsigned badge=s[split+1]-1u,extra=n-split-4u;
    if(extra>127)return 0;
    uint32_t clone[21];memcpy(clone,model,sizeof(clone));
    uint8_t *c=(void *)clone;
    if(right<=left+24)return 0;
    /* The selected row normally ends at LOAD 1. Reclaim the same right edge
     * as unselected rows now that the touch actions are disabled. */
    if(selected && right==1020)right=1258;
    unsigned edge=right-140;
    uint16_t prefix[256]={0},value[128]={0};
    memcpy(prefix,s,split*2);memcpy(value,s+split+2,extra*2);
    uint32_t ptr=(uint32_t)(unsigned long)prefix;
    memcpy(c+0x34,&ptr,4);c[0x38]=(uint8_t)split;
    put_half(c+0x1c,edge-8);
    int native_prefix=selected && scroll_owned[1] && word(scroll_state+0x74+0x24) &&
        (void *)(unsigned long)word(scroll_state+0x74+0x1c)==model;
    if(!native_prefix)text(render,c);
    memcpy(clone,model,sizeof(clone));
    ptr=(uint32_t)(unsigned long)value;memcpy(c+0x34,&ptr,4);c[0x38]=(uint8_t)extra;
    put_half(c+0x18,edge+8);put_half(c+0x1c,right);c[0x3c]=(uint8_t)(c[0x3c]%3);
    if(badge && image && right>edge+80) {
        uint32_t icon[21];memcpy(icon,c,sizeof(icon));uint8_t *im=(void *)icon;
        unsigned top=half(c+0x1a),bottom=half(c+0x1e),y=top+(bottom-top>24?(bottom-top-24)/2:0);
        put_half(im+0x18,edge+8);put_half(im+0x1c,edge+32);
        put_half(im+0x1a,y);put_half(im+0x1e,y+24);memcpy(im+0x44,&badge,4);
        image(render,im);put_half(c+0x18,edge+38);
    }
    text(render,c);
    if(selected && !caption_ready) {
        void *root=(void *)(unsigned long)word(root_pointer);
        if(root) {
            caption_object=object_by_id(root,COLUMN_HEADING_ID);
            if(caption_object) {
                memcpy(caption_model,model,sizeof(caption_model));caption_ready=1;
                refresh_object(root,COLUMN_HEADING_ID);
            }
        }
    }
    return 1;
}

/* Headings are native images in a different render context from scrolling
 * rows. Draw after that image using its own window and rectangle, and a real
 * row font. The first row schedules this single refresh once its font exists. */
void rx3_browse_caption(void *render,void *model,void (*text)(void *,void *))
{
    const struct rx3_browse_column *c=__atomic_load_n(&column,__ATOMIC_SEQ_CST);
    if(!c || !caption_ready || !__atomic_load_n(&track_list,__ATOMIC_SEQ_CST) )return;
    void *root=(void *)(unsigned long)word(root_pointer);
    int primary=root && model==object_by_id(root,64);
    if(model!=caption_object && !primary)return;
    if(!track_layout())return;
    uint32_t clone[21];memcpy(clone,caption_model,sizeof(clone));
    uint8_t *m=(void *)clone,*source=model;
    memcpy(m+8,source+8,12);memcpy(m+0x18,source+0x18,8);
    uint16_t label[128]={0};unsigned n=copy_text(label,c->caption,127);
    uint32_t ptr=(uint32_t)(unsigned long)label,color=0,fill=0;
    memcpy(m+0x34,&ptr,4);m[0x38]=(uint8_t)n;m[0x3c]=1;
    put_half(m+0x18,1126);put_half(m+0x1c,1258);
    unsigned center=(half(source+0x1a)+half(source+0x1e))/2;
    put_half(m+0x1a,center>20?center-20:0);put_half(m+0x1e,center+20);
    /* Browse text uses the native neutral style ALL_COLOR_LIST_TEXT[0]. */
    memcpy(m+0x28,&color,4);memcpy(m+0x40,&fill,4);
    if(!primary)text(render,m);
    unsigned active=__atomic_load_n(&sort_observed,__ATOMIC_SEQ_CST)&127u;
    unsigned first=sort_for_field(primary_field),second=sort_for_field(secondary_field);
    unsigned x=0;
    if(primary && active==first)x=828;
    if(!primary && active==second)x=1092;
    if(!primary && active==sort_for_field(c->field))x=1244;
    if(x && active) {
        uint32_t shape[21];memcpy(shape,model,sizeof(shape));uint8_t *r=(void *)shape;
        unsigned white=0xffffffffu;memcpy(r+0x28,&white,4);r[0x31]=1;r[0x24]=1;
        for(unsigned line=0;line<6;line++) {
            unsigned y=center-3+((sort_observed&128u)?5-line:line);
            put_half(r+0x18,x+5-line);put_half(r+0x1c,x+6+line);
            put_half(r+0x1a,y);put_half(r+0x1e,y+1);rectangle(render,r);
        }
    }
}

/* Property IDs 8/9 belong to the two floating Browse LOAD images. Restrict by
 * object identity, not shared image IDs: track-info and other screens survive. */
int rx3_browse_hide_image(void *model)
{
    if(!__atomic_load_n(&column,__ATOMIC_SEQ_CST))return 0;
    void *root=(void *)(unsigned long)word(root_pointer);
    return root && (model==object_by_id(root,8) || model==object_by_id(root,9));
}
