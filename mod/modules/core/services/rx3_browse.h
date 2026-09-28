/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_BROWSE_H
#define RX3_BROWSE_H
#include "../api/rx3_browse_api.h"
unsigned int rx3_browse_count(void);
int rx3_browse_touch(int x,int y,int pressed);
int rx3_browse_hide_image(void *model);
int rx3_browse_draw(void *render,void *model,void (*text)(void *,void *),void (*image)(void *,void *));
void rx3_browse_caption(void *render,void *model,void (*text)(void *,void *));
#endif
