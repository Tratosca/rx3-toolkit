/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_TITLE_VISIBILITY_H
#define RX3_TITLE_VISIBILITY_H
#include "../services/rx3_titles.h"
#define TITLE_GROUP_ID 64u
#define TITLE_TEXT_ID 62u
#define TITLE_ICON_ID 61u
/* rbp 1.19: CounterInfoUpdate selects active-winscape instances 2480/2569.
   Their property-table indices are group 64, text 62, music icon 61.
   Symbol name suffixes (22/24/25) are NOT runtime object IDs. Match object identity, not
   the contents of a string or a shared icon ID (also used by BROWSE).
   See REFERENCES.md, Deck-title eye controls, for binary evidence and hardware test gates. */
static void *(*title_object)(void *,unsigned int)=(void *)0x0018dae8u;
static void (*title_refresh)(void *,unsigned int)=(void *)0x0018e1a0u;
static int (*title_shown)(void *)=(void *)0x001d1c6cu;
static void (*title_origin)(int *,int *)=(void *)0x001d46f0u;
static void *title_roots[2];
static int title_hits[2][4];
static unsigned int title_visible;
static int title_abi_checked,title_abi_supported;
static int title_adapter_supported(void)
{
    if (!title_abi_checked) {
        static const uint32_t object_guard[]={0xe2503000u,0xe92d4010u};
        static const uint32_t origin_guard[]={0xe30831d0u,0xe3403249u};
        static const uint32_t refresh_guard[]={0xe92d4070u,0xe1a04000u};
        static const uint32_t shown_guard[]={0xe590000cu,0xe12fff1eu};
        static const uint32_t fill_guard[]={0xe92d4030u,0xe24dd014u};
        static const uint32_t colour_guard[]={0xe59f3140u,0xe92d4030u};
        title_abi_supported=!memcmp((void *)0x001a245cu,fill_guard,8) &&
                  !memcmp((void *)0x001a0680u,colour_guard,8) &&
                  !memcmp((void *)title_object,object_guard,8) &&
                  !memcmp((void *)title_shown,shown_guard,8) &&
                  !memcmp((void *)title_origin,origin_guard,8) &&
                  !memcmp((void *)title_refresh,refresh_guard,8);
        title_abi_checked=1;
        if (!title_abi_supported) log_line("title visibility disabled: unexpected native UI ABI");
    }
    return title_abi_supported;
}
static unsigned int title_root_id(unsigned int deck) { return deck?2569u:2480u; }
static int title_deck(const void *glyph,unsigned int id)
{
    if (!rx3_titles_enabled() || !title_adapter_supported()) return -1;
    for(unsigned int deck=0;deck<2u;deck++) {
        void *root=title_object(0,title_root_id(deck));
        if(root && title_object(root,id)==glyph) return (int)deck;
    }
    return -1;
}
static int title_text_hidden(const void *glyph)
{
    /* Cheap property gate before any native tree traversal. These are local
       coordinates from Obj_CTRL_COUNTER_GRP_TITLE_TEXT_TITLE_24. */
    uint16_t box[4];memcpy(box,(const uint8_t *)glyph+0x18u,8);
    if(box[0]!=135u || box[1]!=15u || box[2]!=599u || box[3]!=48u) return 0;
    int deck=title_deck(glyph,TITLE_TEXT_ID);
    return deck>=0 && rx3_title_hidden((unsigned int)deck);
}
static int title_screen_origin(const void *glyph,int *x,int *y)
{
    title_origin(x,y);
    /* Render positions are window-local. InitialOffsetPos excludes Window
       (type 0x14), whereas InitialOffsetPosABS includes its signed position
       at +0x18. Add that missing translation for screen-space touch only. */
    const uint8_t *cursor=glyph;
    for(unsigned int depth=0;cursor && depth<32u;depth++) {
        if(cursor[4]==0x14u) {
            int16_t position[2];memcpy(position,cursor+0x18u,4);
            *x+=position[0];*y+=position[1];return 1;
        }
        const uint8_t *parent;memcpy(&parent,cursor+8u,sizeof(parent));
        if(parent==cursor)break;
        cursor=parent;
    }
    return 0;
}
static int title_draw_eye(void *render,const void *glyph)
{
    uint32_t id;memcpy(&id,(const uint8_t *)glyph+0x44u,4);
    if(id!=0xbf3u) return 0;
    int deck=title_deck(glyph,TITLE_ICON_ID);
    if(deck<0) return 0;
    int ox=0,oy=0;
    int positioned=title_screen_origin(glyph,&ox,&oy);
    title_roots[deck]=title_object(0,title_root_id((unsigned int)deck));
    /* A 38 x 50 touch target in the existing title background, before text.
       Render-context translation handles both deck instances. */
    title_hits[deck][0]=ox+96;title_hits[deck][1]=oy+4;
    title_hits[deck][2]=ox+133;title_hits[deck][3]=oy+53;
    if (positioned && !(title_visible&(1u<<(unsigned int)deck))) {
        log_line(deck?"title eye attached: deck 2":"title eye attached: deck 1");
        log_number("title eye touch left = ", (unsigned long)title_hits[deck][0]);
        log_number("title eye touch top = ", (unsigned long)title_hits[deck][1]);
    }
    if(positioned)title_visible|=1u<<(unsigned int)deck;
    else title_visible&=~(1u<<(unsigned int)deck);
    unsigned int artwork=rx3_title_image((unsigned int)deck,rx3_image_is_light());
    if(!artwork) return 0;
    uint16_t layer;memcpy(&layer,(const uint8_t *)glyph+0x10u,2);
    draw_native_image_local(render,glyph,(uint8_t)layer,104,15,129,38,artwork);
    return 1;
}
static void title_refresh_pending(void)
{
    unsigned int pending=rx3_titles_take_refresh();
    if(!pending || !title_adapter_supported()) return;
    for(unsigned int deck=0;deck<2u;deck++) if(pending&(1u<<deck)) {
        void *root=title_object(0,title_root_id(deck));
        /* Invalidate the background AND title/icon, never just overpaint text.
           Native metadata stays intact, including across a new track load. */
        if(root) title_refresh(root,TITLE_GROUP_ID);
    }
}
static int title_touch_hit(int x,int y,int performance_visible)
{
    if(!performance_visible || !rx3_titles_enabled() || !title_adapter_supported()) return -1;
    for(unsigned int deck=0;deck<2u;deck++) {
        const int *box=title_hits[deck];
        if((title_visible&(1u<<deck)) && x>=box[0] && x<=box[2] &&
           y>=box[1] && y<=box[3] && title_roots[deck] &&
           title_object(0,title_root_id(deck))==title_roots[deck]) {
            void *icon=title_object(title_roots[deck],TITLE_ICON_ID);
            void *group=title_object(title_roots[deck],TITLE_GROUP_ID);
            if(icon && group && title_shown(title_roots[deck]) &&
               title_shown(group) && title_shown(icon)) return (int)deck;
        }
    }
    return -1;
}
#endif
