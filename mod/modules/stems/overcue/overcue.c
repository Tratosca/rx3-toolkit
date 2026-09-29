/* SPDX-License-Identifier: MPL-2.0 */
/* Opt-in prototype: original OVPGZ001 files, bounded 44.1 kHz cache. */
#ifdef RX3_OVERCUE_HOST
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <math.h>
#include <zlib.h>
#include <time.h>
#else
#include "../../core/api/rx3_platform.h"
extern unsigned int strlen(const char *);
extern int strcmp(const char *,const char *);
extern int snprintf(char *,size_t,const char *,...);
extern int openat(int,const char *,int,...);
extern double sin(double);
extern double cos(double);
struct timespec {long tv_sec,tv_nsec;};
extern int clock_gettime(int,struct timespec *);
#define CLOCK_MONOTONIC 1
#define CLOCK_THREAD_CPUTIME_ID 3
/* ARM Linux uses different bits from x86/asm-generic for these two flags. */
#define O_NOFOLLOW 0100000
#define O_DIRECTORY 040000
typedef struct {
    uint8_t *next_in;unsigned int avail_in;unsigned long total_in;
    uint8_t *next_out;unsigned int avail_out;unsigned long total_out;
    char *msg;void *state;void *(*zalloc)(void *,unsigned int,unsigned int);
    void (*zfree)(void *,void *);void *opaque;int data_type;unsigned long adler,reserved;
} z_stream;
extern const char *zlibVersion(void);
extern int inflateInit_(z_stream *,const char *,int);
extern int inflate(z_stream *,int);
extern int inflateEnd(z_stream *);
#endif
#if defined(__ARM_NEON) && !defined(RX3_OVERCUE_SCALAR)
#include <arm_neon.h>
#define OC_NEON 1
#endif
#include "overcue.h"
#include "sha256.h"
#include "json.h"

#define OC_PAGE 131072u
#define OC_TABLE (24u+4096u*48u)
#define OC_BLOCK 4096u
#define OC_SLOTS 8u
#define OC_TAPS 192u
#define OC_INPUT 9216u
#define OC_PI 3.14159265358979323846
typedef struct {float l,r;} oc_pair;
struct oc_role {int fd;unsigned int count,bytes,cached;uint8_t hash[32],table[OC_TABLE],page[OC_PAGE];};
struct oc_bank {unsigned int frames;struct oc_role roles[7];uint8_t compressed[OC_PAGE*2];float input[OC_INPUT*2];};
struct oc_slot {unsigned int block,valid;oc_pair samples[OC_BLOCK];};
struct oc_deck {
    volatile unsigned int gate,generation,status,wanted,mask;
    char path[1024];
    struct oc_bank bank;
    struct oc_slot slots[7][OC_SLOTS];
    oc_pair staging[OC_BLOCK];
    unsigned int output_generation,last_mask,fade;
    oc_pair last;
    volatile unsigned int hits,misses,blocks;
    struct rx3_overcue_stats metrics;
};
static struct oc_deck oc_decks[2];
static float oc_filter[147][OC_TAPS];
static pthread_t oc_thread;
static volatile unsigned int oc_running;
static int oc_started;
static const char *oc_root;
static const char *oc_names[7]={"vocal","instrumental","drums","harmonics","vocals-drums","vocals-harmonics","full-mix"};
static const unsigned int oc_role_for_mask[8]={0,3,0,5,2,1,4,6};
#define OC_LOAD(x) __atomic_load_n(&(x),__ATOMIC_SEQ_CST)
#define OC_STORE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_SEQ_CST)
static int oc_try(struct oc_deck *d) {return !__atomic_exchange_n(&d->gate,1u,__ATOMIC_SEQ_CST);}
static void oc_lock(struct oc_deck *d) {while(!oc_try(d))usleep(1000);}
static void oc_unlock(struct oc_deck *d) {OC_STORE(d->gate,0);}
static void oc_log(unsigned int deck,const char *event,unsigned int a,unsigned int b)
{
    char line[256];int n=snprintf(line,sizeof(line),"overcue deck=%u %s a=%u b=%u\n",deck+1,event,a,b);
    int fd=open("/tmp/rx3-stems.log",O_WRONLY|O_CREAT|O_APPEND,0600);
    if(fd>=0){
        if(n>0&&(unsigned int)n<sizeof(line)) {
            ssize_t written=write(fd,line,(unsigned int)n);
            (void)written;
        }
        close(fd);
    }
}
static uint64_t oc_time_us(int clock)
{
    struct timespec t;
    if(clock_gettime(clock,&t))return 0;
    return (uint64_t)t.tv_sec*1000000u+(unsigned int)t.tv_nsec/1000u;
}
int rx3_overcue_stats(unsigned int deck,struct rx3_overcue_stats *out)
{
    if(deck>=2||!out)return 0;
    struct oc_deck *d=&oc_decks[deck];if(!oc_try(d))return 0;
    *out=d->metrics;out->hits=OC_LOAD(d->hits);out->misses=OC_LOAD(d->misses);
    out->blocks=OC_LOAD(d->blocks);oc_unlock(d);return 1;
}
static int oc_read(int fd,void *p,unsigned int n)
{
    uint8_t *s=p;while(n){ssize_t got=read(fd,s,n);if(got<=0)return 0;s+=got;n-=(unsigned int)got;}return 1;
}
static void oc_bank_close(struct oc_bank *b)
{for(unsigned int r=0;r<7;r++){if(b->roles[r].fd>=0)close(b->roles[r].fd);b->roles[r].fd=-1;b->roles[r].cached=~0u;}b->frames=0;}
static int oc_child(int fd,const char *name,int directory)
{return openat(fd,name,O_RDONLY|O_NOFOLLOW|(directory?O_DIRECTORY:0));}
static int oc_source(int root,const char *path)
{
    if(path[0]!='/')return -1;
    int fd=oc_child(root,".",1);const char *p=path+1;
    while(fd>=0&&*p) {
        char component[512];unsigned int n=0;
        while(*p&&*p!='/'){if(n+1>=sizeof(component)){close(fd);return -1;}component[n++]=*p++;}
        component[n]=0;
        if(!n||!strcmp(component,".")||!strcmp(component,"..")){close(fd);return -1;}
        int next=oc_child(fd,component,*p=='/');close(fd);fd=next;if(*p=='/')p++;
    }
    return fd;
}
static int oc_role_open(struct oc_bank *b,unsigned int r,int directory,const uint8_t table_hash[32])
{
    struct oc_role *role=&b->roles[r];char name[96];
    snprintf(name,sizeof(name),"stems-sidecar-%s.s16le.pgz",oc_names[r]);
    role->fd=oc_child(directory,name,0);if(role->fd<0)return 0;
    off_t bytes=lseek(role->fd,0,SEEK_END);
    if(bytes<24||lseek(role->fd,0,SEEK_SET)!=0||!oc_read(role->fd,role->table,24))return 0;
    uint8_t *h=role->table;unsigned int count=oc_be32(h+12);
    if(memcmp(h,"OVPGZ001",8)||oc_be32(h+8)!=OC_PAGE||!count||count>4096||
       oc_be64(h+16)!=(uint64_t)b->frames*4||count!=((uint64_t)b->frames*4+OC_PAGE-1)/OC_PAGE)return 0;
    unsigned int end=24+48*count;
    if(!oc_read(role->fd,h+24,48*count)||!oc_hash_equal(h,end,table_hash))return 0;
    uint64_t offset=end;
    for(unsigned int i=0;i<count;i++) {
        uint8_t *p=h+24+48*i;unsigned int compressed=oc_be32(p+8),expanded=oc_be32(p+12);
        unsigned int expected=i+1<count?OC_PAGE:b->frames*4-i*OC_PAGE;
        if(oc_be64(p)!=offset||!compressed||compressed>OC_PAGE*2||expanded!=expected||offset+compressed>(uint64_t)bytes)return 0;
        offset+=compressed;
    }
    if(offset!=(uint64_t)bytes)return 0;
    role->count=count;role->bytes=(unsigned int)bytes;role->cached=~0u;return 1;
}
/* Return 0 for absent track, -1 for malformed data, 1 for a verified directory.
 * No basename or cross-library numeric ID matching is permitted. */
static int oc_bank_open(struct oc_bank *b,const char *root,const char *loaded)
{
    oc_bank_close(b);
    int rootfd=-1,mods=-1,index=-1,stems=-1,directory=-1,result=-1;
    char *json=MAP_FAILED;struct oc_token *tokens=MAP_FAILED;
    rootfd=open(root,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(rootfd<0)goto done;
    mods=oc_child(rootfd,"CDJMODS",1);if(mods<0){result=0;goto done;}
    index=oc_child(mods,"index.json",0);if(index<0)goto done;
    off_t size=lseek(index,0,SEEK_END);if(size<=0||size>4*1024*1024||lseek(index,0,SEEK_SET)!=0)goto done;
    json=mmap(0,(size_t)size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    tokens=mmap(0,OC_TOKENS*sizeof(*tokens),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(json==MAP_FAILED||tokens==MAP_FAILED||!oc_read(index,json,(unsigned int)size))goto done;
    struct oc_json j={json,(unsigned int)size,0,0,tokens};
    if(oc_value(&j,0)!=0)goto done;
    oc_space(&j);if(j.pos!=j.size)goto done;
    char text[1024];if(!oc_string(&j,oc_key(&j,0,"schema"),text,sizeof(text))||strcmp(text,"overcue-index/1"))goto done;
    const char *wanted=loaded;unsigned int rootlen=(unsigned int)strlen(root);
    if(strlen(loaded)>rootlen&&!memcmp(loaded,root,rootlen)&&loaded[rootlen]=='/')wanted=loaded+rootlen;
    if(wanted[0]!='/')goto done;
    int chosen=-1;const char *maps[2]={"tracks","tracks_onelibrary"};
    for(unsigned int m=0;m<2;m++) {
        int map=oc_key(&j,0,maps[m]);if(map<0)continue;if(j.s[j.t[map].start]!='{')goto done;
        for(unsigned int k=(unsigned int)map+1;k<j.t[map].next;) {
            unsigned int entry=k+1;if(entry>=j.count)goto done;
            if(oc_string(&j,oc_key(&j,(int)entry,"file_path"),text,sizeof(text))&&!strcmp(text,wanted)) {
                if(chosen>=0) {
                    /* Duplicate library maps may differ in incidental metadata.
                     * Every field that controls audio must agree. */
                    const char *fields[]={"bundle","frames","three_part","page_bytes","source_sha256"};
                    for(unsigned int q=0;q<5;q++) {
                        int x=oc_key(&j,chosen,fields[q]),y=oc_key(&j,(int)entry,fields[q]);
                        if(x<0||y<0){if(x!=y)goto done;continue;}
                        unsigned int n=j.t[x].end-j.t[x].start;
                        if(n!=j.t[y].end-j.t[y].start||memcmp(j.s+j.t[x].start,j.s+j.t[y].start,n))goto done;
                    }
                    for(unsigned int r=0;r<7;r++)for(unsigned int q=0;q<2;q++) {
                        char key[96];snprintf(key,sizeof(key),"%s%s",oc_names[r],q?"_page_table_sha256":"_sha256");
                        for(char *p=key;*p;p++)if(*p=='-')*p='_';
                        uint8_t x[32],y[32];if(!oc_digest(&j,chosen,key,x)||!oc_digest(&j,(int)entry,key,y)||memcmp(x,y,32))goto done;
                    }
                } else chosen=(int)entry;
            }
            k=j.t[entry].next;
        }
    }
    if(chosen<0){result=0;goto done;}
    unsigned int n;
    if(!oc_number(&j,oc_key(&j,chosen,"frames"),&b->frames)||!b->frames||b->frames>4096u*OC_PAGE/4||
       !oc_number(&j,oc_key(&j,chosen,"three_part"),&n)||n!=1||
       !oc_number(&j,oc_key(&j,chosen,"page_bytes"),&n)||n!=OC_PAGE)goto done;
    if(!oc_string(&j,oc_key(&j,chosen,"bundle"),text,sizeof(text))||strlen(text)!=16)goto done;
    for(unsigned int i=0;i<16;i++)if(!((text[i]>='0'&&text[i]<='9')||(text[i]>='a'&&text[i]<='f')))goto done;
    stems=oc_child(mods,"stems",1);if(stems<0)goto done;directory=oc_child(stems,text,1);if(directory<0)goto done;
    for(unsigned int r=0;r<7;r++) {
        char key[96];uint8_t hash[32];
        snprintf(key,sizeof(key),"%s_sha256",oc_names[r]);for(char *p=key;*p;p++)if(*p=='-')*p='_';
        if(!oc_digest(&j,chosen,key,b->roles[r].hash))goto done;
        snprintf(key,sizeof(key),"%s_page_table_sha256",oc_names[r]);for(char *p=key;*p;p++)if(*p=='-')*p='_';
        if(!oc_digest(&j,chosen,key,hash)||!oc_role_open(b,r,directory,hash))goto done;
    }
    {
        static const char hex[]="0123456789abcdef";
        struct oc_sha identity;uint8_t digest[32];char encoded[64];
        oc_sha_init(&identity);oc_sha_add(&identity,"three-part/1:",13);
        for(unsigned int r=0;r<7;r++) {
            if(r)oc_sha_add(&identity,":",1);
            for(unsigned int i=0;i<32;i++){encoded[i*2]=hex[b->roles[r].hash[i]>>4];encoded[i*2+1]=hex[b->roles[r].hash[i]&15];}
            oc_sha_add(&identity,encoded,64);
        }
        oc_sha_end(&identity,digest);
        for(unsigned int i=0;i<8;i++)if(text[i*2]!=hex[digest[i]>>4]||text[i*2+1]!=hex[digest[i]&15])goto done;
    }
    if(oc_key(&j,chosen,"source_sha256")>=0) {
        uint8_t expected[32],hash[32];struct oc_sha sha;
        if(!oc_digest(&j,chosen,"source_sha256",expected))goto done;
        int fd=oc_source(rootfd,wanted);if(fd<0)goto done;oc_sha_init(&sha);ssize_t got;
        while((got=read(fd,b->compressed,sizeof(b->compressed)))>0)oc_sha_add(&sha,b->compressed,(unsigned int)got);
        close(fd);oc_sha_end(&sha,hash);if(got<0||memcmp(expected,hash,32))goto done;
    }
    result=1;
done:
    if(json!=MAP_FAILED)munmap(json,(size_t)size);
    if(tokens!=MAP_FAILED)munmap(tokens,OC_TOKENS*sizeof(*tokens));
    if(index>=0)close(index);
    if(directory>=0)close(directory);
    if(stems>=0)close(stems);
    if(mods>=0)close(mods);
    if(rootfd>=0)close(rootfd);
    if(result!=1)oc_bank_close(b);
    return result;
}
static int oc_page(struct oc_bank *b,unsigned int r,unsigned int number)
{
    struct oc_role *role=&b->roles[r];if(number==role->cached)return 1;if(number>=role->count)return 0;
    const uint8_t *p=role->table+24+number*48;
    unsigned int bytes=oc_be32(p+8),expanded=oc_be32(p+12);
    if(lseek(role->fd,(off_t)oc_be64(p),SEEK_SET)!=(off_t)oc_be64(p)||!oc_read(role->fd,b->compressed,bytes))return 0;
    z_stream z;memset(&z,0,sizeof(z));z.next_in=b->compressed;z.avail_in=bytes;z.next_out=role->page;z.avail_out=expanded;
    if(inflateInit_(&z,zlibVersion(),sizeof(z)))return 0;
    int rc=inflate(&z,4);int valid=rc==1&&z.total_in==bytes&&z.total_out==expanded;inflateEnd(&z);
    if(!valid||!oc_hash_equal(role->page,expanded,p+16))return 0;
    role->cached=number;return 1;
}
static void oc_filter_init(void)
{
    const double cutoff=20500.0/96000.0;
    for(unsigned int phase=0;phase<147;phase++) {
        double total=0;
        for(unsigned int t=0;t<OC_TAPS;t++) {
            double x=(double)((int)t-(int)OC_TAPS/2+1)-(double)phase/147;
            double window=.42-.5*cos(2*OC_PI*t/(OC_TAPS-1))+.08*cos(4*OC_PI*t/(OC_TAPS-1));
            double value=(x==0?2*cutoff:sin(2*OC_PI*cutoff*x)/(OC_PI*x))*window;
            oc_filter[phase][t]=(float)value;total+=value;
        }
        for(unsigned int t=0;t<OC_TAPS;t++)oc_filter[phase][t]/=(float)total;
    }
}
static int oc_convert(struct oc_bank *b,unsigned int r,unsigned int position,unsigned int frames,oc_pair *out)
{
    if(!frames||frames>OC_BLOCK)return 0;
    uint64_t origin=(uint64_t)position*320;int first=(int)(origin/147)-(int)OC_TAPS/2+1;
    int last=(int)(((uint64_t)(position+frames-1)*320)/147)+(int)OC_TAPS/2;
    if(last-first+1>(int)OC_INPUT)return 0;
    for(int i=first;i<=last;) {
        float *dest=b->input+(i-first)*2;
        if(i<0||(unsigned int)i>=b->frames){dest[0]=dest[1]=0;i++;continue;}
        unsigned int page=(unsigned int)i/(OC_PAGE/4),offset=(unsigned int)i%(OC_PAGE/4),take=OC_PAGE/4-offset;
        if(take>(unsigned int)(last-i+1))take=(unsigned int)(last-i+1);
        if(take>b->frames-(unsigned int)i)take=b->frames-(unsigned int)i;
        if(!oc_page(b,r,page))return 0;
        const int16_t *source=(const int16_t *)(b->roles[r].page+offset*4);
        /* Convert once per input block, not once per tap and output frame. */
        for(unsigned int j=0;j<take*2;j++)dest[j]=(float)source[j];
        i+=(int)take;
    }
    for(unsigned int i=0;i<frames;i++) {
        uint64_t p=origin+(uint64_t)i*320;unsigned int phase=(unsigned int)(p%147);
        int offset=(int)(p/147)-(int)OC_TAPS/2+1-first;const float *s=b->input+offset*2;
        const float *coeff=oc_filter[phase];float l=0,rgt=0;
        #ifdef OC_NEON
        float32x4_t left=vdupq_n_f32(0),right=vdupq_n_f32(0);
        for(unsigned int t=0;t<OC_TAPS;t+=4) {
            float32x4x2_t samples=vld2q_f32(s+t*2);
            float32x4_t c=vld1q_f32(coeff+t);
            left=vmlaq_f32(left,samples.val[0],c);
            right=vmlaq_f32(right,samples.val[1],c);
        }
        float32x2_t ls=vadd_f32(vget_low_f32(left),vget_high_f32(left));
        float32x2_t rs=vadd_f32(vget_low_f32(right),vget_high_f32(right));
        l=vget_lane_f32(vpadd_f32(ls,ls),0);
        rgt=vget_lane_f32(vpadd_f32(rs,rs),0);
#else
        for(unsigned int t=0;t<OC_TAPS;t++){l+=s[t*2]*coeff[t];rgt+=s[t*2+1]*coeff[t];}
#endif
        out[i].l=l*(1.0f/32768);out[i].r=rgt*(1.0f/32768);
    }
    return 1;
}
static void *oc_worker(void *unused)
{
    (void)unused;unsigned int seen[2]={0,0},logged[2]={0,0};oc_filter_init();
    while(OC_LOAD(oc_running)) {
        int worked=0;
        for(unsigned int deck=0;deck<2;deck++) {
            struct oc_deck *d=&oc_decks[deck];unsigned int gen=OC_LOAD(d->generation);
            if(gen!=seen[deck]) {
                char path[1024];oc_lock(d);memcpy(path,d->path,sizeof(path));gen=d->generation;
                memset(d->slots,0,sizeof(d->slots));oc_unlock(d);
                int found=path[0]?oc_bank_open(&d->bank,oc_root,path):0;
                if(!path[0])oc_bank_close(&d->bank);
                seen[deck]=gen;
                oc_lock(d);
                if(gen==OC_LOAD(d->generation))OC_STORE(d->status,found==1?2:found<0?3:0);
                oc_unlock(d);
                oc_log(deck,found==1?"tables-verified-96k":found<0?"rejected":"no-match",d->bank.frames,gen);
            }
            if(OC_LOAD(d->status)!=2||seen[deck]!=OC_LOAD(d->generation))continue;
            unsigned int mask=OC_LOAD(d->mask)&7,block=OC_LOAD(d->wanted)/OC_BLOCK;
            if(!mask)continue;
            unsigned int role=oc_role_for_mask[mask];
            for(unsigned int ahead=0;ahead<4;ahead++) {
                unsigned int target=block+ahead;struct oc_slot *slot=&d->slots[role][target%OC_SLOTS];
                if((uint64_t)target*OC_BLOCK*320/147>=d->bank.frames)break;
                oc_lock(d);int present=slot->valid&&slot->block==target;oc_unlock(d);if(present)continue;
                uint64_t wall=oc_time_us(CLOCK_MONOTONIC),cpu=oc_time_us(CLOCK_THREAD_CPUTIME_ID);
                int converted=oc_convert(&d->bank,role,target*OC_BLOCK,OC_BLOCK,d->staging);
                uint64_t end_cpu=oc_time_us(CLOCK_THREAD_CPUTIME_ID),end_wall=oc_time_us(CLOCK_MONOTONIC);
                oc_lock(d);
                if(cpu&&wall&&end_cpu>=cpu&&end_wall>=wall) {
                    unsigned int cu=(unsigned int)(end_cpu-cpu),wu=(unsigned int)(end_wall-wall);
                    d->metrics.cpu_us+=cu;d->metrics.wall_us+=wu;d->metrics.timed_blocks++;
                    if(cu>d->metrics.max_cpu_us)d->metrics.max_cpu_us=cu;
                    if(wu>d->metrics.max_wall_us)d->metrics.max_wall_us=wu;
                } else d->metrics.clock_errors++;
                oc_unlock(d);
                if(!converted) {
                    oc_lock(d);
                    if(gen==OC_LOAD(d->generation))OC_STORE(d->status,3);
                    oc_unlock(d);
                    oc_log(deck,"page-rejected",role,target);break;
                }
                oc_lock(d);
                if(gen==OC_LOAD(d->generation)){memcpy(slot->samples,d->staging,sizeof(d->staging));slot->block=target;slot->valid=1;__atomic_add_fetch(&d->blocks,1u,__ATOMIC_SEQ_CST);}
                oc_unlock(d);worked=1;
                if((OC_LOAD(d->blocks)&255u)==0) {
                    oc_log(deck,"block-us-max-cpu-wall",d->metrics.max_cpu_us,d->metrics.max_wall_us);
                    oc_log(deck,"cache-hit-miss",OC_LOAD(d->hits),OC_LOAD(d->misses));
                }
                /* Fairness: another deck and a seek can preempt each block. */
                break;
            }
            unsigned int hits=OC_LOAD(d->hits);
            if(hits/65536!=logged[deck]) {logged[deck]=hits/65536;oc_log(deck,"rendered-44k1",hits,OC_LOAD(d->misses));}
        }
        if(!worked)usleep(2000);
    }
    for(unsigned int d=0;d<2;d++)oc_bank_close(&oc_decks[d].bank);
    return 0;
}
int rx3_overcue_start(void)
{
    if(oc_started)return 1;
    oc_root=getenv("RX3_OVERCUE_ROOT");if(!oc_root||!*oc_root)return 0;
    memset(oc_decks,0,sizeof(oc_decks));
    for(unsigned int d=0;d<2;d++){oc_decks[d].mask=7;for(unsigned int r=0;r<7;r++)oc_decks[d].bank.roles[r].fd=-1;}
    OC_STORE(oc_running,1);
    if(pthread_create(&oc_thread,0,oc_worker,0)){OC_STORE(oc_running,0);return 0;}
    oc_started=1;return 1;
}
void rx3_overcue_stop(void)
{if(oc_started){OC_STORE(oc_running,0);pthread_join(oc_thread,0);oc_started=0;}}
void rx3_overcue_track(unsigned int deck,const char *path)
{
    if(deck>=2||!oc_started)return;
    struct oc_deck *d=&oc_decks[deck];
    oc_lock(d);unsigned int n=path?(unsigned int)strlen(path):0;
    if(n>=sizeof(d->path))n=0;
    if(n)memcpy(d->path,path,n);
    d->path[n]=0;
    __atomic_add_fetch(&d->generation,1u,__ATOMIC_SEQ_CST);
    OC_STORE(d->status,n?1:0);OC_STORE(d->wanted,0);OC_STORE(d->mask,7);oc_unlock(d);
}
unsigned int rx3_overcue_status(unsigned int deck) {return deck<2?OC_LOAD(oc_decks[deck].status):0;}
int rx3_overcue_render(unsigned int deck,unsigned int position,void *buffer,unsigned int frames,unsigned int mask)
{
    if(deck>=2||!buffer||!frames||frames>OC_BLOCK*4||mask>7||!oc_started)return 0;
    struct oc_deck *d=&oc_decks[deck];OC_STORE(d->wanted,position);OC_STORE(d->mask,mask);
    if(!oc_try(d))return 0;
    oc_pair *out=buffer;unsigned int first=position/OC_BLOCK,last=(position+frames-1)/OC_BLOCK;
    int ready=OC_LOAD(d->status)==2;unsigned int role=oc_role_for_mask[mask];
    if(mask)for(unsigned int block=first;ready&&block<=last;block++) {
        struct oc_slot *s=&d->slots[role][block%OC_SLOTS];if(!s->valid||s->block!=block)ready=0;
    }
    if(!ready){__atomic_add_fetch(&d->misses,1u,__ATOMIC_SEQ_CST);d->fade=0;d->last=out[frames-1];oc_unlock(d);return 0;}
    if(d->output_generation!=OC_LOAD(d->generation)){d->output_generation=OC_LOAD(d->generation);d->last=out[0];d->fade=0;}
    if(d->last_mask!=mask){d->last_mask=mask;d->fade=0;}
    oc_pair start=d->last;
    for(unsigned int i=0;i<frames;i++) {
        unsigned int at=position+i;oc_pair target={0,0};
        if(mask)target=d->slots[role][at/OC_BLOCK%OC_SLOTS].samples[at%OC_BLOCK];
        if(d->fade<256){float alpha=(float)++d->fade/256;target.l=start.l+(target.l-start.l)*alpha;target.r=start.r+(target.r-start.r)*alpha;}
        out[i]=target;
    }
    d->last=out[frames-1];__atomic_add_fetch(&d->hits,1u,__ATOMIC_SEQ_CST);oc_unlock(d);return 1;
}

#ifdef RX3_OVERCUE_HOST
/* Synchronous entry for parser, corruption and spectral regression tests. */
int oc_test_read(const char *root,const char *path,unsigned int mask,unsigned int pos,unsigned int n,void *out)
{
    if(mask<1||mask>7)return 0;
    struct oc_bank *b=calloc(1,sizeof(*b));if(!b)return 0;for(unsigned int r=0;r<7;r++)b->roles[r].fd=-1;
    oc_filter_init();int ok=oc_bank_open(b,root,path)==1;
    for(unsigned int done=0;ok&&done<n;) {unsigned int take=n-done;if(take>OC_BLOCK)take=OC_BLOCK;ok=oc_convert(b,oc_role_for_mask[mask],pos+done,take,(oc_pair *)out+done);done+=take;}
    oc_bank_close(b);free(b);return ok;
}
#endif
