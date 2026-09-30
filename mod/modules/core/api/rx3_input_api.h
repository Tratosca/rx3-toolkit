/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_INPUT_API_H
#define RX3_INPUT_API_H
#include "rx3_platform.h"
/* The core owns every native input hook: pad presses, SEND_KEY, the pad LED
 * refreshes and the physical pad-mode dispatcher. Modules register handlers;
 * they never install, remove or chain those hooks themselves.
 *
 * Handlers run on the player's input thread. They must return promptly and
 * must not allocate, perform I/O or wait. unregister_owner() closes admission
 * and drains in-flight handlers before it returns, so it must not be called
 * from a handler. A shared native hook is removed with its last client.
 */
#define RX3_NO_DECK 0xffffffffu

/* One native pad event. `operation` is the low nibble of the native operation
 * byte (0 press, 2 or 3 release). `channel` is the native channel byte
 * unchanged. `deck` is resolved from the channel, else from the player that
 * dispatched it, else RX3_NO_DECK. `pad_mode` is the player's pad mode
 * (2 is SLIP LOOP). */
struct rx3_pad_event {
    unsigned int code, operation, channel, deck, pad_mode;
};

/* Return nonzero to consume the event. Lower priority values run first;
 * the original player handler runs exactly once when nobody consumes. */
typedef int (*rx3_pad_handler)(const struct rx3_pad_event *);

/* SEND_KEY: key code, native operation (0 press, 2 or 3 release) and the
 * reporting channel. SHIFT state is updated before handlers run. Return
 * nonzero to consume the key: the player never sees it. */
struct rx3_key_event { unsigned int key, operation, channel; };
typedef int (*rx3_key_handler)(const struct rx3_key_event *);
#define RX3_KEY_SHIFT 0x4103u

/* Pad lights, declared rather than driven. When the player refreshes its pad
 * lights, the core asks the owner of that refresh what each control should
 * show and writes the native LEDs itself; modules never see an LED ID.
 * Controls are the eight performance pads, 0 (pad 1) to 7, and SHIFT.
 * Answering RX3_LIGHT_NATIVE leaves the player's own light. Callbacks run on
 * the input thread: no allocation, I/O or waiting. */
#define RX3_LIGHT_NATIVE 0u
#define RX3_LIGHT_ON     1u  /* the colour at full brightness */
#define RX3_LIGHT_DIM    2u  /* the colour at its idle brightness */
#define RX3_LIGHT_BLINK  3u  /* the colour, on the shared blink clock */
#define RX3_LIGHT_SHIFT  8u
struct rx3_light { unsigned int state; uint32_t rgb; /* 0xRRGGBB */ };
typedef void (*rx3_light_fn)(unsigned int deck, unsigned int control, struct rx3_light *);
/* The two native refreshes a module can own, one owner each. SLIP LOOP is
 * refreshed per deck while that pad mode is shown; the unit-wide refresh
 * covers every pad mode and SHIFT, with deck RX3_NO_DECK when the player
 * does not name one. */
#define RX3_LIGHTS_SLIP_LOOP 0u
#define RX3_LIGHTS_PADS      1u

struct rx3_input_service {
    int (*register_pad)(const void *owner, unsigned int priority, rx3_pad_handler);
    int (*register_key)(const void *owner, unsigned int priority, rx3_key_handler);
    /* One owner per refresh; a second registration fails without replacing it. */
    int (*register_lights)(const void *owner, unsigned int refresh, rx3_light_fn);
    /* Ask the core to close its custom panels when a physical pad-mode key
       is pressed on the firmware path that inlines SLIP LOOP. */
    int (*claim_mode_keys)(const void *owner);
    void (*unregister_owner)(const void *owner);
    /* SHIFT as last reported on a channel; RX3_NO_DECK means any channel. */
    int (*shift_held)(unsigned int channel);
    /* The shared blink clock: nonzero in its on half. Any caller starts it
       at the on phase; blink_restart() makes the next start fresh. The pad
       lights and on-screen controls share it, so they cannot drift apart. */
    int (*blink_on)(void);
    void (*blink_restart)(void);
};
extern const struct rx3_input_service rx3_input;
#endif
