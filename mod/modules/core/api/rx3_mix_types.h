/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_MIX_TYPES_H
#define RX3_MIX_TYPES_H
/* A copied observation. Role bits match the stem container's public roles.
 * ready=0 means the audible stream is stock: render all available roles.
 * Never retain a pointer into a provider. No allocation or waits in read().
 */
struct rx3_mix_state { unsigned int selected, available, ready; };
#endif
