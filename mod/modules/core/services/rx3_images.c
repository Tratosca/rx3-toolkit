/* SPDX-License-Identifier: MPL-2.0 */
#include "rx3_images.h"
#include "rx3_hooks.h"
#include "rx3_log.h"
/* Three suggestion colours need five native states and one badge each. */
#define IMAGE_LIMIT 24u
#define IMAGE_FIRST 0x1700u
#define IMAGE_PIXELS 1024u
struct variant {
    const void *owner;
    unsigned int source, ready, bitmap_width, bitmap_height;
    const void *source_base;
    uint32_t source_offset;
    uint16_t source_width, source_height;
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
        v->bitmap_width=v->bitmap_height=0;
        __atomic_store_n(&v->owner,owner,__ATOMIC_SEQ_CST);
        return IMAGE_FIRST+i;
    }
    return 0;
}
unsigned int rx3_image_register_bitmap(const void *owner,unsigned int source,
    const uint16_t *pixels,unsigned int width,unsigned int height)
{
    if(!owner || !pixels || source>=IMAGE_FIRST || !width || !height ||
       width>IMAGE_PIXELS || height>IMAGE_PIXELS/width) return 0;
    for(unsigned int i=0;i<IMAGE_LIMIT;i++) {
        struct variant *v=&variants[i];
        if(v->owner) continue;
        v->source=source;v->bitmap_width=width;v->bitmap_height=height;
        v->ready=0;memcpy(v->pixels,pixels,width*height*2u);
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
    memcpy(&offset,source+0x20,4);
    if(v->bitmap_width) {
        width=(uint16_t)v->bitmap_width;height=(uint16_t)v->bitmap_height;
        memcpy((uint8_t *)v->record+4,&width,2);
        memcpy((uint8_t *)v->record+6,&height,2);
        /* The replacement is raw RGB565, with no source palette. */
        memset((uint8_t *)v->record+0x24,0,4);
    } else if(!v->ready || v->source_base!=base || v->source_offset!=offset ||
       v->source_width!=width || v->source_height!=height) {
        const uint16_t *pixels=(const void *)((unsigned long)base+offset);
        /* Offsets wrap at 32 bits on ARM; native tests use a nearby fixture. */
        for(unsigned int i=0;i<count;i++) v->pixels[i]=recolour(pixels[i],v->from,v->to);
        v->source_base=base;v->source_offset=offset;
        v->source_width=width;v->source_height=height;v->ready=1;
    }
    offset=(uint32_t)((unsigned long)v->pixels-(unsigned long)base);
    memcpy((uint8_t *)v->record+0x20,&offset,4);
    /* lookup() already resolved the native record's absolute pixel pointer.
       Returning our record bypasses that native fixup, so resolve ours too. */
    uint32_t pixels=(uint32_t)(unsigned long)v->pixels;
    memcpy((uint8_t *)v->record+0x0c,&pixels,4);
    return v->record;
}

/* Native record replacements. The pixels belong to the contributor and stay
   referenced by every table built after registration. */
#define REPLACEMENT_LIMIT 4u
struct replacement {
    const void *owner;
    unsigned int image, width, height;
    const uint16_t *dark, *light;
};
static struct replacement replacements[REPLACEMENT_LIMIT];
static uint8_t *dark_table, *light_table;
static const uint8_t *stock_table;
static volatile int tables_published, light_selected, fill_suspended;
static const void *policy_owner;
static const struct rx3_image_policy *policy;

/* The display-mode fill adapter. The player keeps the colour of its next
   solid fill in one word: blue at bits 0..4, green at 8..13, red at 16..20.
   A rectangle carries its width and height at offsets 8 and 10. */
#define HW_FILL_RECT ((unsigned long)0x001a46dc)
#define FILL_REGISTER ((unsigned long)0x02459748)
static const uint8_t hw_fill_rect_guard[8] = {0xf0,0x41,0x2d,0xe9,0x08,0xd0,0x4d,0xe2};
typedef void (*hw_fill_rect_fn)(void *, const uint8_t *);
static struct installed_hook fill_hook;
static hw_fill_rect_fn original_fill;
static unsigned int fill_active;

static int replaced(unsigned int image)
{
    for (unsigned int i = 0; i < REPLACEMENT_LIMIT; i++)
        if (replacements[i].owner && replacements[i].image == image) return 1;
    return 0;
}

static int replace_native(const void *owner, unsigned int image, const uint16_t *dark,
                          const uint16_t *light, unsigned int width, unsigned int height)
{
    if (!owner || !dark || !width || !height || width > 0xffffu || height > 0xffffu ||
        image >= RX3_STOCK_IMAGE_COUNT || replaced(image) ||
        __atomic_load_n(&tables_published, __ATOMIC_SEQ_CST)) return 0;
    for (unsigned int i = 0; i < REPLACEMENT_LIMIT; i++) {
        struct replacement *r = &replacements[i];
        if (r->owner) continue;
        r->image = image; r->width = width; r->height = height;
        r->dark = dark; r->light = light; r->owner = owner;
        return 1;
    }
    return 0;
}

static int release_native(const void *owner)
{
    if (__atomic_load_n(&tables_published, __ATOMIC_SEQ_CST)) return 0;
    for (unsigned int i = 0; i < REPLACEMENT_LIMIT; i++)
        if (replacements[i].owner == owner) memset(&replacements[i], 0, sizeof(replacements[i]));
    return 1;
}

/* Called by the table builder. The format byte is 2, the variant that
   honours the colour key: replacements may leave parts of themselves
   unpainted. That is a reading of one released build, not a measurement. */
void rx3_image_install_replacements(uint8_t *table, int light)
{
    for (unsigned int i = 0; i < REPLACEMENT_LIMIT; i++) {
        const struct replacement *r = &replacements[i];
        if (!r->owner) continue;
        uint8_t *record = table + r->image * 44u;
        if (light) {
            if (!r->light) continue;
            uint32_t offset = (uint32_t)(unsigned long)r->light - (uint32_t)(unsigned long)table;
            memcpy(record + 0x20u, &offset, 4u);
            continue;
        }
        uint16_t width = (uint16_t)r->width, height = (uint16_t)r->height;
        uint32_t pixels = (uint32_t)(unsigned long)r->dark - (uint32_t)(unsigned long)table;
        uint32_t no_palette = 0u;
        memcpy(record + 4u, &width, 2u);
        memcpy(record + 6u, &height, 2u);
        record[0x18u] = 2u;
        record[0x19u] = 0u;
        memcpy(record + 0x20u, &pixels, 4u);
        memcpy(record + 0x24u, &no_palette, 4u);
        rx3_log_number("native image replaced = ", r->image);
    }
}

int rx3_image_variants_wanted(void) { return policy != 0; }

void rx3_image_publish_tables(uint8_t *dark, uint8_t *light, const uint8_t *stock)
{
    dark_table = dark;
    light_table = light;
    stock_table = stock;
    __atomic_store_n(&tables_published, 1, __ATOMIC_SEQ_CST);
}

void rx3_image_suspend_fill(int suspended) { fill_suspended = suspended; }
int rx3_image_is_light(void) { return light_selected; }

void rx3_image_drawn(unsigned int image)
{
    const struct rx3_image_policy *current = __atomic_load_n(&policy, __ATOMIC_SEQ_CST);
    if (current && current->drawn && image < RX3_STOCK_IMAGE_COUNT) current->drawn(image);
}

static void fill_hooked(void *target, const uint8_t *rect)
{
    __atomic_add_fetch(&fill_active, 1u, __ATOMIC_SEQ_CST);
    const struct rx3_image_policy *current = __atomic_load_n(&policy, __ATOMIC_SEQ_CST);
    if (current && current->fill && light_selected && rect && !fill_suspended) {
        volatile unsigned int *fill = (volatile unsigned int *)FILL_REGISTER;
        uint16_t width, height;
        memcpy(&width, rect + 8u, 2u);
        memcpy(&height, rect + 10u, 2u);
        unsigned int colour = *fill, wanted = current->fill(colour, width, height);
        if (wanted != colour) *fill = wanted;
    }
    original_fill(target, rect);
    __atomic_sub_fetch(&fill_active, 1u, __ATOMIC_SEQ_CST);
}

static int claim_variants(const void *owner, const struct rx3_image_policy *wanted)
{
    if (!owner || !wanted || policy_owner) return 0;
    if (!original_fill) {
        original_fill = (hw_fill_rect_fn)install_hook(&fill_hook, HW_FILL_RECT,
                                                      hw_fill_rect_guard, (void *)fill_hooked);
        if (!original_fill) return 0;
    }
    policy_owner = owner;
    __atomic_store_n(&policy, wanted, __ATOMIC_SEQ_CST);
    return 1;
}

static void select_variant(int light)
{
    light_selected = light != 0;
    uint8_t *table = light_selected && light_table ? light_table : dark_table;
    if (table) {
        __sync_synchronize();
        *(uint8_t **)RX3_IMAGE_TABLE_POINTER = table;
    }
}

static void release_variants(const void *owner)
{
    if (!owner || owner != policy_owner) return;
    __atomic_store_n(&policy, 0, __ATOMIC_SEQ_CST);
    select_variant(0);
    int detached = original_fill && detach_hook(&fill_hook);
    for (;;) {
        while (__atomic_load_n(&fill_active, __ATOMIC_SEQ_CST)) usleep(1000u);
        usleep(10000u);
        if (!__atomic_load_n(&fill_active, __ATOMIC_SEQ_CST)) break;
    }
    policy_owner = 0;
    if (!original_fill) return;
    if (!detached) {
        log_line("images: fill adapter retained after restore failure");
        return;
    }
    (void)release_hook(&fill_hook);
    original_fill = 0;
}

static int variants_ready(void) { return dark_table && light_table; }

static int native_image(unsigned int image, struct rx3_native_image *out)
{
    if (!out || !dark_table || image >= RX3_STOCK_IMAGE_COUNT || replaced(image)) return 0;
    const uint8_t *record = dark_table + image * 44u;
    uint16_t width, height;
    uint32_t offset;
    memcpy(&width, record + 4u, 2u);
    memcpy(&height, record + 6u, 2u);
    memcpy(&offset, record + 0x20u, 4u);
    const uint16_t *pixels = (const void *)(dark_table + offset);
    /* Records whose pixels sit inside the stock record array carry no bitmap
       of their own. */
    uint32_t from_stock = (uint32_t)(unsigned long)pixels - (uint32_t)(unsigned long)stock_table;
    if (stock_table && from_stock <= RX3_STOCK_IMAGE_COUNT * 44u + 43u) return 0;
    out->width = width;
    out->height = height;
    out->format = record[0x18u];
    out->paletted = record[0x19u];
    out->pixels = pixels;
    return 1;
}

static int publish_variant(unsigned int image, const uint16_t *pixels)
{
    if (!light_table || !pixels || image >= RX3_STOCK_IMAGE_COUNT || replaced(image)) return 0;
    uint32_t offset = (uint32_t)(unsigned long)pixels - (uint32_t)(unsigned long)light_table;
    memcpy(light_table + image * 44u + 0x20u, &offset, 4u);
    return 1;
}

static int light_active(void) { return light_selected; }

unsigned int rx3_image_contributions(void)
{
    unsigned int n = policy != 0;
    for (unsigned int i = 0; i < REPLACEMENT_LIMIT; i++) n += replacements[i].owner != 0;
    return n + rx3_image_count();
}

const struct rx3_image_service rx3_images={
    register_recolour, unregister_owner, rx3_image_register_bitmap,
    replace_native, release_native, claim_variants, release_variants,
    variants_ready, native_image, publish_variant, select_variant, light_active
};
