/* SPDX-License-Identifier: MPL-2.0
 *
 * Contract between the firmware-specific performance core and an on-screen
 * feature. The broker owns native rendering and touch objects. A feature owns
 * its labels, state and actions and never calls another feature.
 */

#ifndef RX3_FEATURE_API_H
#define RX3_FEATURE_API_H

/* What a control does when a finger arrives.
 *
 * A stepper is one widget with three touchable parts rather than three
 * controls that happen to sit together, because that is what it is: the ends
 * move a value the middle shows, and the row should not have to be told twice
 * that they belong to each other.
 */
#define RX3_PAD_BUTTON  0u   /* fires on release */
#define RX3_PAD_TOGGLE  1u   /* fires on release; is_on lights it */
#define RX3_PAD_STEPPER 2u   /* one widget, three parts: [-] [value] [+] */
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
};

struct rx3_runtime_feature {
    const char *name;
    int active;
    const struct rx3_pad_row *row;
    int (*configured)(void);
    int (*install)(void);
    void (*remove)(void);
    void (*track_will_load)(unsigned int deck, void *reader,
                            const void *track_info);
    void (*track_did_load)(unsigned int deck, void *reader,
                           const void *track_info);
    void (*audio_started)(unsigned int sample_rate);
    void (*report)(void);
    void (*destroy_deck)(unsigned int deck);
};

#endif /* RX3_FEATURE_API_H */
