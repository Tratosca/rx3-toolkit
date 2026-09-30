/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_AUDIO_H
#define RX3_AUDIO_H
#include "../api/rx3_audio_api.h"
/* Deck identity, published by the core's PcmReader::load adapter. */
void rx3_audio_track_loading(unsigned int deck);
void rx3_audio_track_loaded(unsigned int deck, void *reader);
int rx3_audio_deck_for_reader(const void *reader);
unsigned int rx3_audio_count(void);
#endif
