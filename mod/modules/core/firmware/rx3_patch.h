/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_PATCH_H
#define RX3_PATCH_H
#include "../api/rx3_platform.h"
/* Firmware adapter primitives. Feature modules use the hook service. */
int write_code(unsigned long, const void *, size_t);
void clear_instruction_cache(unsigned long, unsigned long);
#endif
