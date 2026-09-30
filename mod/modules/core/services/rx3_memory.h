/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_MEMORY_H
#define RX3_MEMORY_H
/* Reads /proc: never on audio, input or render threads. */
unsigned long rx3_memory_available_kb(void);
#endif
