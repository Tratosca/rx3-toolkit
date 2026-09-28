/* SPDX-License-Identifier: MPL-2.0 */
#include "rx3_mix_state.h"
static rx3_mix_reader provider;
int rx3_mix_claim(rx3_mix_reader reader)
{
    if (!reader) return 0;
    rx3_mix_reader expected = 0;
    return __atomic_compare_exchange_n(&provider, &expected, reader, 0,
                                       __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}
void rx3_mix_release(rx3_mix_reader reader)
{
    (void)__atomic_compare_exchange_n(&provider, &reader, 0, 0,
                                      __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}
struct rx3_mix_state rx3_mix_read(unsigned int deck)
{
    struct rx3_mix_state empty = {0, 0, 0};
    if (deck >= 2u) return empty;
    rx3_mix_reader reader = __atomic_load_n(&provider, __ATOMIC_SEQ_CST);
    return reader ? reader(deck) : empty;
}

static rx3_wave_reader wave_provider;
int rx3_wave_claim(rx3_wave_reader reader)
{
    rx3_wave_reader expected=0;
    return reader && __atomic_compare_exchange_n(&wave_provider,&expected,reader,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
}
void rx3_wave_release(rx3_wave_reader reader)
{
    (void)__atomic_compare_exchange_n(&wave_provider,&reader,0,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
}
unsigned int rx3_wave_read(unsigned int deck, unsigned int mask, unsigned int format, unsigned char *out, unsigned int count)
{
    rx3_wave_reader reader=__atomic_load_n(&wave_provider,__ATOMIC_SEQ_CST);
    return deck<2u && format<4u && out && reader ? reader(deck,mask,format,out,count) : 0;
}
