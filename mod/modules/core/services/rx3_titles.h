/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_TITLES_H
#define RX3_TITLES_H
#include "../api/rx3_platform.h"
#include "../api/rx3_title_api.h"
int rx3_titles_enabled(void);
int rx3_title_hidden(unsigned int deck);
unsigned int rx3_title_image(unsigned int deck,int light);
unsigned int rx3_titles_take_refresh(void);
/* hit=-1 outside a currently visible eye; begin=first native press only.
   Once captured, consume through release, even after cancellation. */
int rx3_titles_touch(int hit, int pressed, int begin);
#endif
