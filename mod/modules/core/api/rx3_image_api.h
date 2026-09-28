/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_IMAGE_API_H
#define RX3_IMAGE_API_H
#include "rx3_platform.h"
/* Immutable small RGB565 variants; owner and registration have process lifetime.
   Zero is failure. Unregister only after the module's callers have drained. */
struct rx3_image_service {
    unsigned int (*register_recolour)(const void *owner, unsigned int source,
                                      uint16_t from, uint16_t to);
    void (*unregister_owner)(const void *owner);
};
extern const struct rx3_image_service rx3_images;
#endif
