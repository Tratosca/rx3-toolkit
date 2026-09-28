/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_NOTICE_H
#define RX3_NOTICE_H
#include "../api/rx3_notice_api.h"
extern const struct rx3_notice_service rx3_notices;
/* Render thread only. The renderer must hide before accepting new text.
 * It can retain the supplied text until the next hide call. enabled=0 clears
 * the queue and current display. Availability is published by this adapter.
 */
typedef void (*rx3_notice_renderer)(unsigned int deck, const uint16_t *text, int show);
void rx3_notice_pump(uint64_t now_ms, int enabled, rx3_notice_renderer);
#endif
