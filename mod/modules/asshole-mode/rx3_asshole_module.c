/* SPDX-License-Identifier: MPL-2.0 */
#include "../core/api/rx3_module_api.h"
static const struct rx3_title_service *titles;
static const char owner[]="asshole-mode";
#include "rx3_asshole_artwork.h"
static const struct rx3_image_service *images;
static unsigned int hidden, eye_images[4];
static int title_hidden(unsigned int deck)
{
    return deck<2u && (__atomic_load_n(&hidden,__ATOMIC_SEQ_CST)&(1u<<deck));
}
static void title_activate(unsigned int deck)
{
    if(deck<2u) __atomic_fetch_xor(&hidden,1u<<deck,__ATOMIC_SEQ_CST);
}
static unsigned int title_image(unsigned int deck,int light)
{
    return eye_images[(light?2u:0u)+(title_hidden(deck)!=0)];
}
static const struct rx3_title_provider provider={title_hidden,title_activate,title_image};
static int register_artwork(void)
{
    for(unsigned int variant=0;variant<4u;variant++) {
        uint16_t pixels[26*24];
        unsigned int background=variant>=2u?208u:32u;
        unsigned int foreground=variant>=2u?32u:224u;
        for(unsigned int y=0;y<24;y++) for(unsigned int x=0;x<26;x++) {
            unsigned int coverage=title_eye_coverage[variant&1u][y][x];
            unsigned int c=(foreground*coverage+background*(16u-coverage)+8u)/16u;
            pixels[y*26+x]=coverage?(uint16_t)(((c>>3)<<11)|((c>>2)<<5)|(c>>3)):0xf81fu;
        }
        eye_images[variant]=images->register_bitmap(owner,0xbf3u,pixels,26u,24u);
        if(!eye_images[variant]) return 0;
    }
    return 1;
}
static int configured(void)
{
    const char *value=getenv("RX3_ASSHOLE_MODE");
    return value && value[0]=='1' && !value[1];
}
static int start(const struct rx3_services *services)
{
    titles=services->titles;images=services->images;
    if(!titles || !images || !images->register_bitmap || !images->unregister_owner) return 0;
    __atomic_store_n(&hidden,0u,__ATOMIC_SEQ_CST);
    return register_artwork() && titles->acquire(owner,&provider);
}
static void stop(void)
{
    if(titles) titles->release(owner);
    if(images && images->unregister_owner) images->unregister_owner(owner);
    memset(eye_images,0,sizeof(eye_images));
    titles=0;images=0;
}
const struct rx3_module rx3_asshole_module={
    RX3_MODULE_API_VERSION,sizeof(struct rx3_module),owner,configured,start,stop,
    0,0,0,0,0
};
