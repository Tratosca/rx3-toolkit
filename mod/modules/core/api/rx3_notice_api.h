/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_NOTICE_API_H
#define RX3_NOTICE_API_H
#include "rx3_platform.h"
#define RX3_NOTICE_CAPACITY 8u
#define RX3_NOTICE_TEXT_UNITS 96u
#define RX3_NOTICE_GLOBAL 2u
#define RX3_NOTICE_INFO 0u
#define RX3_NOTICE_WARNING 1u
#define RX3_NOTICE_ERROR 2u
enum rx3_notice_result { RX3_NOTICE_OK, RX3_NOTICE_BUSY, RX3_NOTICE_FULL, RX3_NOTICE_INVALID };
/* owner is an identity token with process lifetime, never dereferenced.
 * Text is copied; at most 95 UTF-16 units plus terminator. Overlong strings
 * are rejected. deck is 0/1; GLOBAL is reserved and returns INVALID until
 * global routing is verified on firmware.
 * Same owner/id replaces a notice. duration_ms is 1..60000 from display.
 * A higher priority preempts, equal priority is FIFO. Preemption does not
 * restart a notice's lifetime. No allocation, I/O, spinning or native UI call.
 */
struct rx3_notice {
    const void *owner;
    unsigned int id, deck, priority, duration_ms;
    const uint16_t *text;
};
struct rx3_notice_service {
    enum rx3_notice_result (*post)(const struct rx3_notice *);
    enum rx3_notice_result (*cancel)(const void *owner, unsigned int id);
    int (*available)(void);
};
#endif
