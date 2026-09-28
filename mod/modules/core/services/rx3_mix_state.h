/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_MIX_STATE_H
#define RX3_MIX_STATE_H
#include "../api/rx3_mix_types.h"
typedef struct rx3_mix_state (*rx3_mix_reader)(unsigned int deck);
/* One provider, registered at startup. Code stays resident until exit. */
int rx3_mix_claim(rx3_mix_reader);
void rx3_mix_release(rx3_mix_reader);
struct rx3_mix_state rx3_mix_read(unsigned int deck);
typedef unsigned int (*rx3_wave_reader)(unsigned int, unsigned int, unsigned int, unsigned char *, unsigned int);
int rx3_wave_claim(rx3_wave_reader);
void rx3_wave_release(rx3_wave_reader);
unsigned int rx3_wave_read(unsigned int deck, unsigned int mask, unsigned int format, unsigned char *out, unsigned int count);
#endif
