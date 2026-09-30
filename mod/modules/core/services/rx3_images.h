/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_IMAGES_H
#define RX3_IMAGES_H
#include "../api/rx3_image_api.h"
/* The player's image-table pointer and its stock size. The private extended
   table adds the tab strip and the glyph atlas reserve after the stock
   records; module.sh patches the player's own bound to match. */
#define RX3_IMAGE_TABLE_POINTER ((unsigned long)0x05a14f60)
#define RX3_STOCK_IMAGE_COUNT RX3_NATIVE_IMAGE_COUNT
unsigned int rx3_image_count(void);
/* Recolours, bitmaps, replacements and a variant policy together. */
unsigned int rx3_image_contributions(void);
/* Internal immutable bitmap variant; pixels are copied, native format and
   colour-key semantics come from the source image. */
unsigned int rx3_image_register_bitmap(const void *owner,unsigned int source,
    const uint16_t *pixels,unsigned int width,unsigned int height);
void *rx3_image_resolve(unsigned int id, void *(*lookup)(unsigned int), const void *base);
/* The table builder's side of the service, on the rendering thread. */
void rx3_image_install_replacements(uint8_t *table, int light);
int rx3_image_variants_wanted(void);
void rx3_image_publish_tables(uint8_t *dark, uint8_t *light, const uint8_t *stock);
void rx3_image_suspend_fill(int suspended);
int rx3_image_is_light(void);
void rx3_image_drawn(unsigned int image);
#endif
