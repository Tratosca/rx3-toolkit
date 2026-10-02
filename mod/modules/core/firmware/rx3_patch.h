/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_PATCH_H
#define RX3_PATCH_H
#include "../api/rx3_platform.h"
/* Four/eight-byte firmware writes. Failure preserves the previous bytes.
 * If RX restoration fails twice, the restored page remains RWX. Callers must
 * still serialize patching and ensure native instruction quiescence.
 * Feature modules use the hook service or the guarded write service. */
int write_code(unsigned long, const void *, size_t);
enum rx3_replace_result {
    RX3_REPLACE_APPLIED,
    RX3_REPLACE_UNCHANGED,
    RX3_REPLACE_ROLLED_BACK,
    RX3_REPLACE_RECOVERY_PENDING,
};
enum rx3_replace_result replace_code(unsigned long, const void *,
                                     const void *, size_t);
void clear_instruction_cache(unsigned long, unsigned long);
/* Compare, then write through write_code. Returns 1 on success. */
int rx3_write_guarded(unsigned long, const void *, const void *, unsigned int);
#endif
