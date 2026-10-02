/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_TEXT_H
#define RX3_TEXT_H
#include "../api/rx3_text_api.h"
void rx3_text_draw_native(void *render, void *glyph,
                          void (*native_draw)(void *, void *));
#endif
