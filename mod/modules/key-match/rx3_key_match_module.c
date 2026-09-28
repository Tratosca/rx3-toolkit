/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
#include "../core/api/rx3_harmony.h"
#define ICON_ID 0x00194578u
#define SET_ICON 0x00295904u
#define SHOW_ICON 0x00193c14u
#define KEY_GREEN 52u
#define KEY_YELLOW 120u
#define KEY_ORANGE 121u
#define KEY_RED 122u
#define COLOUR_COUNT 3u
static const struct rx3_services *framework;
static struct installed_hook icon_hook,set_hook,show_hook;
static unsigned int rules=0, coloured_images[COLOUR_COUNT][5], badges[4];
static const uint16_t colours[COLOUR_COUNT]={0xffe0u,0xfc00u,0xf800u};
/* Native Browse icon composition is serialized on the UI thread. */
static unsigned int composing,pending_colour;
static unsigned int callbacks,enabled;
static const unsigned char owner;
typedef int (*icon_fn)(unsigned int,int,int);
static icon_fn original_icon;
static void (*original_set)(unsigned int,unsigned int);
static int (*original_show)(void *,int,int);
static void set_icon(unsigned int side,unsigned int row)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    unsigned saved=composing,pending=pending_colour;composing=1;pending_colour=0;
    original_set(side,row);
    composing=saved;pending_colour=pending;
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
}
static int show_icon(void *window,int object,int image)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    if(composing && pending_colour && image>=0xa0f && image<=0xa13 &&
       __atomic_load_n(&enabled,__ATOMIC_SEQ_CST)) image=(int)coloured_images[pending_colour-1][image-0xa0f];
    int result=original_show(window,object,image);
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    return result;
}
static int icon(unsigned int category,int selected,int side)
{
    __atomic_add_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    int result;
    if(category>=KEY_YELLOW && category<=KEY_RED) {
        result=original_icon(KEY_GREEN,selected,side);
        if(composing && result==227)pending_colour=category-KEY_YELLOW+1;
    } else result=original_icon(category,selected,side);
    __atomic_sub_fetch(&callbacks,1u,__ATOMIC_SEQ_CST);
    return result;
}
static unsigned category(unsigned reference,unsigned key,unsigned native)
{
    if(native==KEY_GREEN || reference<1 || reference>24 || key<1 || key>24)return native;
    switch(rx3_camelot_extended(reference-1,key-1,rules)) {
    case RX3_MATCH_BOOST_TWO:return KEY_YELLOW;
    case RX3_MATCH_BOOST_SEVEN:return KEY_ORANGE;
    case RX3_MATCH_FOUR:return KEY_RED;
    default:return native;
    }
}
static unsigned badge(unsigned kind)
{
    return kind==KEY_GREEN?badges[0]:
        kind>=KEY_YELLOW && kind<=KEY_RED?badges[kind-KEY_YELLOW+1]:0;
}
static const struct rx3_browse_marker markers={category,badge};
static int configured(void)
{
    const char *value=getenv("RX3_KEY_MATCH");return value && value[0]=='1';
}
static int start(const struct rx3_services *services)
{
    framework=services;
    rules=rx3_match_rules(getenv("RX3_KEY_MATCH_RULES"));
    /* Guards generated from rbp SHA256 60bcbd88...f3b09 (1.19). */
    static const uint8_t icon_guard[8]={0x77,0x0,0x50,0xe3,0x4,0x40,0x2d,0xe5};
    badges[0]=framework->images->register_recolour(&owner,227,7755,0x07e0);
    if(!badges[0])return 0;
    for(unsigned colour=0;colour<COLOUR_COUNT;colour++) {
        for(unsigned i=0;i<5;i++) {
            coloured_images[colour][i]=framework->images->register_recolour(&owner,0xa0fu+i,0x07e0u,colours[colour]);
            if(!coloured_images[colour][i])return 0;
        }
        badges[colour+1]=framework->images->register_recolour(&owner,227,7755,colours[colour]);
        if(!badges[colour+1])return 0;
    }
    static const uint8_t set_guard[8]={0xf0,0x4f,0x2d,0xe9,0x01,0x50,0xa0,0xe1};
    static const uint8_t show_guard[8]={0x01,0x00,0x72,0xe3,0x70,0x40,0x2d,0xe9};
    original_set=(void *)framework->install_hook(&set_hook,SET_ICON,set_guard,(void *)set_icon);
    original_show=(void *)framework->install_hook(&show_hook,SHOW_ICON,show_guard,(void *)show_icon);
    original_icon=(icon_fn)framework->install_hook(&icon_hook,ICON_ID,icon_guard,(void *)icon);
    if(!original_icon || !original_set || !original_show || !framework->browse->marker(&owner,&markers))return 0;
    __atomic_store_n(&enabled,1u,__ATOMIC_SEQ_CST);
    return 1;
}
static void stop(void)
{
    __atomic_store_n(&enabled,0u,__ATOMIC_SEQ_CST);
    framework->browse->unregister_owner(&owner);
    int ok=framework->detach_hook(&icon_hook);
    ok=framework->detach_hook(&set_hook) && ok;
    ok=framework->detach_hook(&show_hook) && ok;
    if(!ok)return;
    while(__atomic_load_n(&callbacks,__ATOMIC_SEQ_CST))usleep(1000u);
    framework->release_hook(&icon_hook);
    framework->release_hook(&set_hook);framework->release_hook(&show_hook);
    framework->images->unregister_owner(&owner);
}
const struct rx3_module rx3_key_match_module={
    .version=RX3_MODULE_API_VERSION,.size=sizeof(struct rx3_module),.name="key-match",
    .configured=configured,.start=start,.stop=stop
};
