/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_IMAGES_H
#define RX3_IMAGES_H
#include "../api/rx3_image_api.h"
unsigned int rx3_image_count(void);
void *rx3_image_resolve(unsigned int id, void *(*lookup)(unsigned int), const void *base);
#endif
