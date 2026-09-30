/* SPDX-License-Identifier: MPL-2.0 */
#include "rx3_titles.h"
static const void *owner;
static unsigned int refresh, generation;
static unsigned int captured_generation;
static const struct rx3_title_provider *provider;
/* Gesture state belongs exclusively to the native UI thread. */
static int captured=-1, cancelled;
int rx3_titles_enabled(void) { return __atomic_load_n(&owner,__ATOMIC_SEQ_CST)!=0; }
int rx3_title_hidden(unsigned int deck)
{
    const struct rx3_title_provider *p=__atomic_load_n(&provider,__ATOMIC_SEQ_CST);
    return deck<2u && rx3_titles_enabled() && p && p->hidden(deck);
}
unsigned int rx3_title_image(unsigned int deck,int light)
{
    const struct rx3_title_provider *p=__atomic_load_n(&provider,__ATOMIC_SEQ_CST);
    return deck<2u && rx3_titles_enabled() && p ? p->image(deck,light) : 0u;
}
static int acquire(const void *candidate,const struct rx3_title_provider *p)
{
    if (!candidate || !p || !p->hidden || !p->activate || !p->image || rx3_titles_enabled()) return 0;
    __atomic_add_fetch(&generation,1u,__ATOMIC_SEQ_CST);
    __atomic_store_n(&provider,p,__ATOMIC_SEQ_CST);
    __atomic_store_n(&owner,candidate,__ATOMIC_SEQ_CST);
    __atomic_store_n(&refresh,3u,__ATOMIC_SEQ_CST);
    return 1;
}
static void release(const void *candidate)
{
    if (!candidate) return;
    const void *expected=candidate;
    if (__atomic_compare_exchange_n(&owner,&expected,0,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST))
        __atomic_store_n(&refresh,3u,__ATOMIC_SEQ_CST);
}
unsigned int rx3_titles_take_refresh(void)
{
    /* Most native glyph draws have no title work. Avoid a read/modify/write
       barrier on that hot path, especially while BROWSE is scrolling. */
    if (!__atomic_load_n(&refresh,__ATOMIC_RELAXED)) return 0u;
    return __atomic_exchange_n(&refresh,0u,__ATOMIC_SEQ_CST);
}
int rx3_titles_touch(int hit,int pressed,int begin)
{
    if (!rx3_titles_enabled()) hit=-1;
    if (captured<0) {
        if (!pressed || !begin || hit<0 || hit>1) return 0;
        captured=hit;cancelled=0;
        captured_generation=__atomic_load_n(&generation,__ATOMIC_SEQ_CST);
        return 1;
    }
    if (hit!=captured || captured_generation!=__atomic_load_n(&generation,__ATOMIC_SEQ_CST)) cancelled=1;
    if (!pressed) {
        if (!cancelled) {
            unsigned int bit=1u<<(unsigned int)captured;
            const struct rx3_title_provider *p=__atomic_load_n(&provider,__ATOMIC_SEQ_CST);
            if (rx3_titles_enabled() && p) p->activate((unsigned int)captured);
            __atomic_fetch_or(&refresh,bit,__ATOMIC_SEQ_CST);
        }
        captured=-1;
    }
    return 1;
}
const struct rx3_title_service rx3_titles={acquire,release};
