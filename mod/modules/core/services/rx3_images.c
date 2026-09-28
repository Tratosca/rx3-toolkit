/* SPDX-License-Identifier: MPL-2.0 */
#include "rx3_images.h"
/* Three suggestion colours need five native states and one badge each. */
#define IMAGE_LIMIT 24u
#define IMAGE_FIRST 0x1700u
#define IMAGE_PIXELS 1024u
struct variant {
    const void *owner;
    unsigned int source, ready;
    uint16_t from, to, pixels[IMAGE_PIXELS];
    uint32_t record[11];
};
static struct variant variants[IMAGE_LIMIT];
/* Preserve antialiasing shades along the source colour's RGB565 ray. */
static uint16_t recolour(uint16_t pixel,uint16_t from,uint16_t to)
{
    unsigned r=pixel>>11,g=(pixel>>5)&63,b=pixel&31;
    unsigned fr=from>>11,fg=(from>>5)&63,fb=from&31;
    if(r*fg!=g*fr || r*fb!=b*fr || g*fb!=b*fg)return pixel;
    unsigned scale=fr?fr:(fg?fg:fb),amount=fr?r:(fg?g:b);
    if(!scale || amount>scale)return pixel==from?to:pixel;
    return (uint16_t)((((to>>11)*amount+scale/2)/scale)<<11 |
        (((((to>>5)&63)*amount+scale/2)/scale)<<5) |
        (((to&31)*amount+scale/2)/scale));
}
static unsigned int register_recolour(const void *owner,unsigned int source,uint16_t from,uint16_t to)
{
    if (!owner || source>=IMAGE_FIRST || from==to) return 0;
    for(unsigned int i=0;i<IMAGE_LIMIT;i++) {
        struct variant *v=&variants[i];
        if(v->owner) continue;
        v->source=source;v->from=from;v->to=to;v->ready=0;
        __atomic_store_n(&v->owner,owner,__ATOMIC_SEQ_CST);
        return IMAGE_FIRST+i;
    }
    return 0;
}
static void unregister_owner(const void *owner)
{
    for(unsigned int i=0;i<IMAGE_LIMIT;i++)
        if(variants[i].owner==owner) __atomic_store_n(&variants[i].owner,0,__ATOMIC_SEQ_CST);
}
unsigned int rx3_image_count(void)
{
    unsigned int n=0;
    for(unsigned int i=0;i<IMAGE_LIMIT;i++) n+=variants[i].owner!=0;
    return n;
}
/* Firmware adapter calls on the serialized native rendering thread. Offsets
   always use the current image-table base, including after a theme change. */
void *rx3_image_resolve(unsigned int id,void *(*lookup)(unsigned int),const void *base)
{
    if(id<IMAGE_FIRST || id>=IMAGE_FIRST+IMAGE_LIMIT || !lookup || !base) return 0;
    struct variant *v=&variants[id-IMAGE_FIRST];
    if(!__atomic_load_n(&v->owner,__ATOMIC_SEQ_CST)) return 0;
    const uint8_t *source=lookup(v->source);
    if(!source) return 0;
    uint16_t width,height;
    uint32_t offset;
    memcpy(&width,source+4,2);memcpy(&height,source+6,2);
    unsigned int count=(unsigned int)width*height;
    if(!width || !height || count>IMAGE_PIXELS || source[0x19] ||
       (source[0x18]!=1 && source[0x18]!=2)) return 0;
    memcpy(v->record,source,44);
    if(!v->ready) {
        memcpy(&offset,source+0x20,4);
        const uint16_t *pixels=(const void *)((unsigned long)base+offset);
        /* Offsets wrap at 32 bits on ARM; native tests use a nearby fixture. */
        for(unsigned int i=0;i<count;i++) v->pixels[i]=recolour(pixels[i],v->from,v->to);
        v->ready=1;
    }
    offset=(uint32_t)((unsigned long)v->pixels-(unsigned long)base);
    memcpy((uint8_t *)v->record+0x20,&offset,4);
    /* lookup() already resolved the native record's absolute pixel pointer.
       Returning our record bypasses that native fixup, so resolve ours too. */
    uint32_t pixels=(uint32_t)(unsigned long)v->pixels;
    memcpy((uint8_t *)v->record+0x0c,&pixels,4);
    return v->record;
}
const struct rx3_image_service rx3_images={register_recolour,unregister_owner};
