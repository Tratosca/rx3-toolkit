/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_PANELS_H
#define RX3_PANELS_H
#include "../api/rx3_panel_api.h"
const struct rx3_pad_row *rx3_panel_find(unsigned int);
unsigned int rx3_panel_count(void);
unsigned int rx3_panel_take_open(void);
void rx3_panel_activate(unsigned int id);
void rx3_panels_bind_refresh(void (*)(void));
#endif
