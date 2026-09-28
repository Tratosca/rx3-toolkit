/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_HOOK_TYPES_H
#define RX3_HOOK_TYPES_H
struct hook_record;
struct installed_hook { struct hook_record *record; };
/* Handle identity is its address: do not copy or move a live handle. */
#endif
