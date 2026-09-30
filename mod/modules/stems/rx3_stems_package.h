/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_PACKAGE_H
#define RX3_STEMS_PACKAGE_H
#include "rx3_stems_io.h"
struct __attribute__((packed)) rx3_package_header {
    char magic[8];
    uint32_t version, header_size, count, entry_size;
    uint64_t size, frames;
    uint8_t reserved[24];
};
struct __attribute__((packed)) rx3_package_entry {
    uint32_t kind, role;
    uint64_t offset, size;
    uint32_t crc, reserved;
    char name[32];
};
struct __attribute__((packed)) rx3_wave_header {
    char magic[8];
    uint32_t version, size, rate, cadence, count, stride, roles, entry_size;
    uint8_t source_hash[32], analysis_hash[32];
    uint64_t frames;
    uint8_t reserved[16];
};
struct __attribute__((packed)) rx3_wave_entry {
    uint32_t role, stride;
    uint64_t offset, size;
    uint8_t hash[32], reserved[8];
};
static int package_zero(const uint8_t *p, unsigned int n)
{
    for (unsigned int i=0;i<n;i++) if(p[i]) return 0;
    return 1;
}
static int package_crc(const uint8_t *p, unsigned int n, const struct stems_io *io, uint32_t *out)
{
    uint32_t table[256];
    for(unsigned int i=0;i<256;i++) {
        uint32_t v=i;
        for(unsigned int j=0;j<8;j++) v=(v>>1)^((v&1)?0xedb88320u:0u);
        table[i]=v;
    }
    uint32_t crc=~0u;
    for(unsigned int start=0;start<n;) {
        if (stems_io_cancelled(io)) return 0;
        unsigned int end=n-start>STEMS_IO_CHUNK?start+STEMS_IO_CHUNK:n;
        for(unsigned int i=start;i<end;i++) crc=table[(crc^p[i])&255u]^(crc>>8);
        start=end;
    }
    if (stems_io_cancelled(io)) return 0;
    *out=~crc;
    return 1;
}
/* All pointers below refer to a single resident, read-only allocation, owned
   exclusively by payload[0]. Other payloads borrow it until readers drain. */
static unsigned int stems_package_load(int fd, struct stem_payload next[3],
                                       unsigned int other_bytes, const struct stems_io *io)
{
    struct rx3_package_header h;
    off_t size=lseek(fd,0,SEEK_END);
    if(size<64 || lseek(fd,0,SEEK_SET)!=0 || stems_read(fd,&h,64,io)) return 0;
    if(memcmp(h.magic,"RX3PKG2\0",8) || (h.version!=2 && h.version!=3) || h.header_size!=64 ||
       h.entry_size!=64 || h.count<3 || h.count>5 || h.size!=(uint64_t)size ||
       h.frames<RX3_STEMS_MIN_FRAMES || h.frames>RX3_STEMS_MAX_FRAMES ||
       !package_zero(h.reserved,24)) return 0;
    /* Checked before narrowing, so an oversized file cannot wrap around. */
    if((uint64_t)size>RX3_STEMS_RESIDENT_BYTES) return 0;
    unsigned int bytes=(unsigned int)size;
    if(other_bytes>=RX3_STEMS_RESIDENT_BYTES || bytes>RX3_STEMS_RESIDENT_BYTES-other_bytes) return 0;
    const struct rx3_memory_service *memory=framework->memory;
    if(!memory->reserve(&stems_decks,bytes,RX3_STEMS_PLAYER_RESERVE_KIB)) return 0;
    uint8_t *block=mmap(0,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(block==MAP_FAILED) { memory->abandon(&stems_decks,bytes); return 0; }
    if(lseek(fd,0,SEEK_SET)!=0 || stems_read(fd,block,bytes,io)) goto bad;
    /* Header may not change between sizing and copying. */
    if(memcmp(block,&h,64)) goto bad;
    unsigned int roles=h.count-2u, offset=64u+h.count*64u;
    if(offset>bytes) goto bad;
    const struct rx3_package_entry *entries=(const void *)(block+64u);
    static const char *names[5]={"vocals","drums","bass","waveform","manifest"};
    for(unsigned int i=0;i<h.count;i++) {
        const struct rx3_package_entry *e=&entries[i];
        uint32_t crc;
        unsigned int kind=i<roles?1u:i==roles?2u:3u;
        unsigned int role=i<roles?2u<<i:0u;
        const char *name=i<roles?names[i]:names[3u+i-roles];
        unsigned int len=0; while(name[len]) len++;
        if(e->kind!=kind || e->role!=role || e->offset!=offset || e->reserved ||
           (!e->size && !(h.version==3 && kind==2u)) || e->size>bytes-offset || memcmp(e->name,name,len) ||
           !package_zero((const uint8_t *)e->name+len,32u-len) ||
           (kind==3u && e->size>RX3_STEMS_MANIFEST_BYTES) ||
           !package_crc(block+offset,(unsigned int)e->size,io,&crc) || crc!=e->crc) goto bad;
        if(kind==1u) {
            if(e->size!=64u+h.frames*4u) goto bad;
            const struct stem_header *pcm=(const void *)(block+offset);
            if(memcmp(pcm->magic,"RX3STM1\0",8) || pcm->sample_rate!=44100 ||
               pcm->channels!=2 || !stems_pcm_gain(pcm) || pcm->header_size!=64 ||
               pcm->frames!=h.frames) goto bad;
        }
        offset+=(unsigned int)e->size;
    }
    if(offset!=bytes) goto bad;
    const struct rx3_package_entry *we=&entries[roles];
    const uint8_t *wave=0;
    if(we->size) {
    if(we->size<sizeof(struct rx3_wave_header)) goto bad;
    wave=block+(unsigned int)we->offset;
    const struct rx3_wave_header *w=(const void *)wave;
    int multi=(w->version==2u && !memcmp(w->magic,"RX3WAV2\0",8)) ||
        (w->version==3u && !memcmp(w->magic,"RX3WAV3\0",8)) ||
        (w->version==4u && !memcmp(w->magic,"RX3WAV4\0",8));
    unsigned int wave_roles=multi?(roles==1u?3u:7u):roles+1u;
    if((!multi && (memcmp(w->magic,"RX3WAV1\0",8) || w->version!=1)) || w->size!=128 ||
       w->rate!=44100 || w->cadence!=150 || w->entry_size!=64 ||
       w->roles!=wave_roles || !w->count || w->count>RX3_STEMS_MAX_COLUMNS ||
       w->frames!=h.frames || w->count!=(h.frames+293u)/294u ||
       (w->version==4u ? (w->stride<1u || w->stride>3u) : multi?w->stride!=6u:(w->stride!=1 && w->stride!=2)) || !package_zero(w->reserved,16)) goto bad;
    unsigned int wave_offset=128u+w->roles*64u;
    if(wave_offset>we->size) goto bad;
    const struct rx3_wave_entry *wr=(const void *)(wave+128u);
    for(unsigned int i=0;i<w->roles;i++) {
        if(wr[i].role!=i+1u || wr[i].stride!=w->stride || wr[i].offset!=wave_offset ||
           wr[i].size!=(uint64_t)w->count*w->stride ||
           wr[i].size>we->size-wave_offset || !package_zero(wr[i].reserved,8)) goto bad;
        if(w->version==2u) {
            const uint8_t *data=wave+wave_offset;
            for(unsigned int c=0;c<w->count;c++) {
                if (!(c & 4095u) && stems_io_cancelled(io)) goto bad;
                if((unsigned int)data[c*6u+3u]+data[c*6u+4u]+data[c*6u+5u]>31u) goto bad;
            }
        }
        wave_offset+=(unsigned int)wr[i].size;
    }
    if(wave_offset!=we->size) goto bad;
    }
    if(stems_io_cancelled(io) || mprotect(block,bytes,PROT_READ)) goto bad;
    for(unsigned int i=0;i<roles;i++) {
        next[i].data=block+(unsigned int)entries[i].offset+64u;
        const struct stem_header *pcm=(const void *)(block+(unsigned int)entries[i].offset);
        next[i].format=pcm->format; next[i].pcm_gain=stems_pcm_gain(pcm); next[i].frames=h.frames;
    }
    next[0].block=block; next[0].block_size=bytes;
    next[0].wave=wave; next[0].wave_size=(unsigned int)we->size;
    memory->settle(&stems_decks,bytes);
    return roles;
bad:
    munmap(block,bytes);
    memory->abandon(&stems_decks,bytes);
    return 0;
}
#endif
