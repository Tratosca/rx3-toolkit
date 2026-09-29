/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_HOOKS_H
#define RX3_HOOKS_H
#include "../api/rx3_platform.h"
/* Zero initialize. The framework owns the record and trampoline.
 * Installation/removal is serialized by the startup/shutdown thread.
 * No hot unload: callers must quiesce replacement callbacks before release.
 */
#include "../api/rx3_hook_types.h"
int hook_is_installed(const struct installed_hook *);
int detach_hook(struct installed_hook *);
int release_hook(struct installed_hook *);
/* original_slot points to pointer-sized caller storage. The trampoline is
 * published there before target code changes and cleared on release. */
int install_hook(struct installed_hook *, unsigned long, const uint8_t[8],
                 void *, void *);
int install_pc_ldr_hook(struct installed_hook *, unsigned long,
                        const uint8_t[8], void *, void *);
int uninstall_hook(struct installed_hook *);
#endif
