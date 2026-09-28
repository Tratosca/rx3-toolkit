/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_PANEL_API_H
#define RX3_PANEL_API_H
#include "rx3_platform.h"
/* What a control does when a finger arrives.
 *
 * A stepper is one widget with three touchable parts rather than three
 * controls that happen to sit together, because that is what it is: the ends
 * move a value the middle shows, and the row should not have to be told twice
 * that they belong to each other.
 */
#define RX3_PAD_OUTLINE_BUTTON 6u /* neutral face, semantic outline, fires on release */
#define RX3_PAD_STATUS  5u   /* informational; consumes touch without firing */
#define RX3_PAD_BUTTON  0u   /* fires on release */
#define RX3_PAD_TOGGLE  1u   /* fires on release; is_on lights it */
#define RX3_PAD_STEPPER 2u   /* one widget, three parts: [-] [value] [+] */
#define RX3_PAD_TOGGLE_SLIDER 4u /* tap toggles; hold 350 ms then drag adjusts */
#define RX3_PAD_SLIDER  3u   /* drag, and tap anywhere in the track */

/* A row is laid out inside one deck's half, or once across the screen and
   clipped into each half as it is drawn. */
#define RX3_PAD_SCOPE_DECK   0u
#define RX3_PAD_SCOPE_SCREEN 1u

struct rx3_pad_widget {
    unsigned char kind;
    unsigned char weight;   /* shares of the free width; 0 reads as 1 */
};

/* One row of controls, declared rather than drawn.
 *
 * Nothing a feature supplies here is a coordinate. The core solves the row,
 * paints it and hit-tests it from the one set of rectangles, which is the
 * point: every panel used to lay its controls out in its draw and then work
 * out what had been touched by repeating the same arithmetic somewhere else,
 * with nothing keeping the two in step.
 */
struct rx3_pad_row {
    unsigned int panel_id;
    unsigned int tab_image;
    unsigned char scope;
    unsigned char count;                    /* declared widgets */
    const struct rx3_pad_widget *widgets;

    /* How many of them this deck shows now. Null means always `count`. A
       stems row is one to four wide by what actually loaded. */
    unsigned int (*live_count)(unsigned int deck);

    /* `part` is 0 for a plain widget, and 0, 1 or 2 for a stepper's
       decrement, value and increment. */
    const uint16_t *(*caption)(unsigned int deck, unsigned int widget,
                               unsigned int part);
    int (*is_on)(unsigned int deck, unsigned int widget, unsigned int part);
    void (*fire)(unsigned int deck, unsigned int widget, unsigned int part);

    /* Sliders, in the feature's own units, so the core owns the only division
       on the path and a feature never converts a coordinate. `committed` is
       set on the release that ends a drag and clear while it is moving. */
    unsigned int (*slider_max)(unsigned int deck, unsigned int widget);
    unsigned int (*slider_get)(unsigned int deck, unsigned int widget);
    void (*slider_set)(unsigned int deck, unsigned int widget,
                       unsigned int value, unsigned int committed);

    int (*needs_refresh)(void);
    /* Optional per-deck presentation; state and actions stay with the client. */
    unsigned int (*kind)(unsigned int deck, unsigned int widget);
    /* Optional RGB565 accent; the renderer converts to native RGB888. */
    uint16_t (*colour)(unsigned int deck, unsigned int widget);
    /* Hybrid controls show a track during a drag and while this returns true. */
    int (*slider_visible)(unsigned int deck, unsigned int widget);
    /* Optional per-part semantic RGB565 accent, independent of selection.
       Zero means no semantic colour (unknown value or unavailable choice). */
    uint16_t (*part_colour)(unsigned int deck, unsigned int widget, unsigned int part);
};


/* Descriptors and callbacks have process lifetime. Register at start and
 * unregister at stop. The renderer owns geometry, colours and touch capture.
 * open() queues a request; the render thread applies it.
 */
struct rx3_panel_service {
    int (*register_row)(const struct rx3_pad_row *);
    void (*unregister_row)(const struct rx3_pad_row *);
    int (*open)(unsigned int panel_id);
};
extern const struct rx3_panel_service rx3_panels;
#endif
