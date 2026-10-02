/* SPDX-License-Identifier: MPL-2.0 */
/* Native input broker. One owner for each shared input hook; features only
 * register handlers. Registration happens on the serial startup thread; the
 * dispatch paths read a fixed table and never allocate, log or wait. */
#include "../api/rx3_input_api.h"
#include "rx3_input.h"
#include "rx3_hooks.h"
#include "rx3_log.h"

#define ON_KEY_PAD     ((unsigned long)0x003060e8)
#define SEND_KEY       ((unsigned long)0x0037ad64)
#define CHECK_SLIP_LED ((unsigned long)0x002fcc04)
#define CHECK_LED_STAT ((unsigned long)0x002f6318)
#define PHYSICAL_KEY   ((unsigned long)0x00306b78)
#define SET_LED_COLOR  ((unsigned long)0x0033e4f8)
#define SET_LED_STATE  ((unsigned long)0x0033e3f4)

static const uint8_t pad_guard[8] = {0xb8,0x30,0xd1,0xe1,0xf0,0x4f,0x2d,0xe9};
static const uint8_t send_key_guard[8] = {0xf0,0x4f,0x2d,0xe9,0x0c,0xd0,0x4d,0xe2};
/* This prologue contains a PC-relative ldr and requires literal relocation. */
static const uint8_t slip_led_guard[8] = {0xb4,0x3d,0x9f,0xe5,0xf0,0x4f,0x2d,0xe9};
static const uint8_t led_stat_guard[8] = {0xf0,0x4f,0x2d,0xe9,0x00,0x40,0xa0,0xe1};
static const uint8_t physical_guard[8] = {0xb8,0x30,0xd1,0xe1,0x00,0xc0,0xa0,0xe3};

typedef int (*on_key_pad_fn)(void *, const void *);
typedef int (*send_key_fn)(void *, unsigned int, unsigned int, unsigned int,
                           unsigned int, unsigned int, unsigned int);
typedef void (*led_refresh_fn)(void *, void *);
/* uif::Led::setState(State, period_ms, started_at_ms, long, BrightnessState).
   With State 2 the panel runs the blink itself. */
typedef void (*set_led_state_fn)(void *, int, unsigned int, unsigned int, long, int);
typedef void (*set_led_color_fn)(void *, int, int, const void *);

#define CLIENT_LIMIT 4u
#define KEY_CHANNELS 4u

struct pad_client { const void *owner; unsigned int priority; rx3_pad_handler handler; };
struct key_client { const void *owner; unsigned int priority; rx3_key_handler handler; };
struct shared_hook {
    struct installed_hook hook;
    void *original;
    unsigned int active;
};
/* The native LED list a refresh hands over: a count at +4 and 44-byte
   entries at +8, each with its LED ID and channel. */
#define LED_STRIDE 44u
#define LED_LIMIT 256u
/* uif::Led::State. With BLINK the panel runs the blink itself from a
   half-period and an origin in juce::Time::currentTimeMillis. */
#define LED_ON 1
#define LED_BLINK 2
#define BLINK_PERIOD_MS 500u

static struct pad_client pad_clients[CLIENT_LIMIT];
static struct key_client key_clients[CLIENT_LIMIT];
static unsigned int pad_client_count, key_client_count;
static const void *slip_led_owner, *pad_led_owner, *mode_key_owners[CLIENT_LIMIT];
static rx3_light_fn slip_light, pad_light;
static volatile unsigned int blink_origin, blink_valid;
static struct shared_hook pad_hook, key_hook, slip_led_hook, pad_led_hook, mode_key_hook;
static void (*mode_key_action)(void);
static uint8_t shift_held[KEY_CHANNELS];
static unsigned int key_trace_limit, key_traced;
/* The firmware's LED writers. */
static set_led_state_fn led_state_writer = (set_led_state_fn)SET_LED_STATE;
static set_led_color_fn led_colour_writer = (set_led_color_fn)SET_LED_COLOR;

static void enter(struct shared_hook *hook) { __atomic_add_fetch(&hook->active, 1u, __ATOMIC_SEQ_CST); }
static void leave(struct shared_hook *hook) { __atomic_sub_fetch(&hook->active, 1u, __ATOMIC_SEQ_CST); }

/* A handler cleared before this returns can no longer be entered: every path
   that reaches it increments the counter first. */
static void drain(struct shared_hook *hook)
{
    for (;;) {
        while (__atomic_load_n(&hook->active, __ATOMIC_SEQ_CST)) usleep(1000u);
        usleep(10000u);
        if (!__atomic_load_n(&hook->active, __ATOMIC_SEQ_CST)) return;
    }
}

static int acquire(struct shared_hook *hook, unsigned long address, const uint8_t guard[8],
                   void *replacement, int literal)
{
    if (hook->original) return 1;
    return RX3_INSTALL_HOOK(literal ? install_pc_ldr_hook : install_hook,
                            hook->original, &hook->hook, address, guard, replacement);
}

/* Detach, drain, then release the trampoline. A failed detach retains the
   trampoline and the original entry: the replacement stays reachable and
   passes every event through while nobody is registered. */
static void relinquish(struct shared_hook *hook)
{
    if (!hook->original) return;
    int detached = detach_hook(&hook->hook);
    drain(hook);
    if (!detached) {
        log_line("input: native hook retained after restore failure");
        return;
    }
    (void)release_hook(&hook->hook);
    hook->original = 0;
}

static int pad_hooked(void *player, const void *input)
{
    enter(&pad_hook);
    const uint8_t *event = input;
    const uint8_t *innards = player;
    struct rx3_pad_event e;
    e.code = event[8] | ((unsigned int)event[9] << 8u);
    e.operation = event[11] & 15u;
    e.channel = event[10];
    unsigned int number = e.channel >= 1u && e.channel <= 2u ? e.channel : innards[0x26u];
    e.deck = number >= 1u && number <= 2u ? number - 1u : RX3_NO_DECK;
    e.pad_mode = *(const uint32_t *)(innards + 0x74u);
    int result = 0;
    for (unsigned int i = 0; i < pad_client_count && !result; i++) {
        rx3_pad_handler handler = __atomic_load_n(&pad_clients[i].handler, __ATOMIC_SEQ_CST);
        if (handler) result = handler(&e);
    }
    if (!result) result = ((on_key_pad_fn)pad_hook.original)(player, input);
    leave(&pad_hook);
    return result;
}

static void trace_key(unsigned int key, unsigned int operation, unsigned int channel)
{
    if (key_traced >= key_trace_limit) return;
    key_traced++;
    rx3_log_number("key kkkkooocc =", (key & 0xffffu) * 100000u +
               (operation & 0xffu) * 100u + (channel & 0xffu));
}

static int key_hooked(void *target, unsigned int key, unsigned int operation,
                      unsigned int channel, unsigned int a, unsigned int b, unsigned int c)
{
    enter(&key_hook);
    trace_key(key, operation, channel);
    unsigned int slot = channel < KEY_CHANNELS ? channel : 0u;
    if (key == RX3_KEY_SHIFT) {
        if (operation == 0u) shift_held[slot] = 1u;
        else if ((operation & ~1u) == 2u) shift_held[slot] = 0u;
    }
    struct rx3_key_event e = {key, operation, channel};
    int consumed = 0;
    for (unsigned int i = 0; i < key_client_count && !consumed; i++) {
        rx3_key_handler handler = __atomic_load_n(&key_clients[i].handler, __ATOMIC_SEQ_CST);
        if (handler) consumed = handler(&e);
    }
    int result = consumed ? 0 : ((send_key_fn)key_hook.original)(target, key, operation,
                                                                 channel, a, b, c);
    leave(&key_hook);
    return result;
}

struct rx3_timeval { long seconds, microseconds; };
/* juce::Time::currentTimeMillis is gettimeofday reduced to milliseconds, so
   the panel's LED blink and the on-screen controls share one time domain. */
static unsigned int now_ms(void)
{
    struct rx3_timeval value;
    if (gettimeofday(&value, 0)) return 0;
    return (unsigned int)(((uint64_t)(unsigned long)value.seconds * 1000000u +
                           (uint64_t)(unsigned long)value.microseconds) / 1000u);
}

static unsigned int blink_origin_ms(void)
{
    if (!__atomic_load_n(&blink_valid, __ATOMIC_SEQ_CST)) {
        __atomic_store_n(&blink_origin, now_ms(), __ATOMIC_SEQ_CST);
        __atomic_store_n(&blink_valid, 1u, __ATOMIC_SEQ_CST);
    }
    return __atomic_load_n(&blink_origin, __ATOMIC_SEQ_CST);
}

static int blink_on(void)
{
    return (((now_ms() - blink_origin_ms()) / BLINK_PERIOD_MS) & 1u) == 0u;
}

static void blink_restart(void) { __atomic_store_n(&blink_valid, 0u, __ATOMIC_SEQ_CST); }

/* One declared light onto one native LED. The SLIP LOOP refresh sets its own
   states, so a steady light there changes only the colour; the unit-wide
   refresh leaves states to whoever colours the pad. */
static void apply_light(uint8_t *led, const struct rx3_light *light, int set_state)
{
    const uint8_t colour[3] = {(uint8_t)(light->rgb >> 16u), (uint8_t)(light->rgb >> 8u),
                               (uint8_t)light->rgb};
    if (light->state == RX3_LIGHT_BLINK) {
        led_state_writer(led, LED_BLINK, BLINK_PERIOD_MS, blink_origin_ms(), 0, 0);
        led_colour_writer(led, LED_BLINK, 0, colour);
        return;
    }
    if (set_state) led_state_writer(led, LED_ON, 0u, 0u, 0, 0);
    led_colour_writer(led, LED_ON, light->state == RX3_LIGHT_DIM, colour);
}

static int led_list(void *list, uint8_t **entries, unsigned int *count)
{
    if (!list) return 0;
    *entries = *(uint8_t **)((uint8_t *)list + 8u);
    *count = *(const uint16_t *)((const uint8_t *)list + 4u);
    return *entries && *count <= LED_LIMIT;
}

/* SLIP LOOP, one deck: that deck's pads carry IDs 18 to 25. */
static void slip_led_hooked(void *player, void *led_stat)
{
    enter(&slip_led_hook);
    ((led_refresh_fn)slip_led_hook.original)(player, led_stat);
    rx3_light_fn light_of = __atomic_load_n(&slip_light, __ATOMIC_SEQ_CST);
    unsigned int number = *(const uint8_t *)((const uint8_t *)player + 0x26u);
    uint8_t *entries;
    unsigned int count;
    if (light_of && number >= 1u && number <= 2u && led_list(led_stat, &entries, &count)) {
        for (unsigned int i = 0; i < count; i++) {
            uint8_t *led = entries + i * LED_STRIDE;
            unsigned int id = *(const uint32_t *)led;
            if (*(const uint32_t *)(led + 4u) != number || id < 18u || id > 25u) continue;
            struct rx3_light light = {RX3_LIGHT_NATIVE, 0u};
            light_of(number - 1u, id - 18u, &light);
            if (light.state != RX3_LIGHT_NATIVE) apply_light(led, &light, 0);
        }
    }
    leave(&slip_led_hook);
}

/* Every pad mode: the pads are IDs 18 to 25 when the list carries them there,
   else 1 to 8; SHIFT is ID 14. */
static void pad_led_hooked(void *self, void *state)
{
    enter(&pad_led_hook);
    ((led_refresh_fn)pad_led_hook.original)(self, state);
    rx3_light_fn light_of = __atomic_load_n(&pad_light, __ATOMIC_SEQ_CST);
    uint8_t *entries;
    unsigned int count;
    if (light_of && led_list(state, &entries, &count) && count) {
        unsigned int base = 1u;
        for (unsigned int i = 0; i < count; i++) {
            unsigned int id = *(const uint32_t *)(entries + i * LED_STRIDE);
            if (id >= 18u && id <= 25u) base = 18u;
        }
        for (unsigned int i = 0; i < count; i++) {
            uint8_t *led = entries + i * LED_STRIDE;
            unsigned int id = *(const uint32_t *)led;
            unsigned int control = id == 14u ? RX3_LIGHT_SHIFT :
                                   id >= base && id < base + 8u ? id - base : RX3_NO_DECK;
            if (control == RX3_NO_DECK) continue;
            unsigned int channel = *(const uint32_t *)(led + 4u);
            struct rx3_light light = {RX3_LIGHT_NATIVE, 0u};
            light_of(channel >= 1u && channel <= 2u ? channel - 1u : RX3_NO_DECK, control, &light);
            if (light.state != RX3_LIGHT_NATIVE) apply_light(led, &light, 1);
        }
    }
    leave(&pad_led_hook);
}

/* 1.19 inlines SLIP LOOP in onPhysicalKey. Never consume a native mode event
   or add a page to its cycle: the core only closes its own panels. */
static int mode_key_hooked(void *player, const void *input)
{
    enter(&mode_key_hook);
    const uint8_t *event = input;
    unsigned int code = event[8] | ((unsigned int)event[9] << 8u);
    void (*action)(void) = __atomic_load_n(&mode_key_action, __ATOMIC_SEQ_CST);
    if (action && code >= 0x4113u && code <= 0x4116u && !(event[11] & 0x0fu)) action();
    int result = ((on_key_pad_fn)mode_key_hook.original)(player, input);
    leave(&mode_key_hook);
    return result;
}

static int register_pad(const void *owner, unsigned int priority, rx3_pad_handler handler)
{
    if (!owner || !handler || pad_client_count >= CLIENT_LIMIT) return 0;
    for (unsigned int i = 0; i < pad_client_count; i++)
        if (pad_clients[i].owner == owner && pad_clients[i].handler) return 0;
    if (!acquire(&pad_hook, ON_KEY_PAD, pad_guard, (void *)pad_hooked, 0)) return 0;
    unsigned int at = pad_client_count;
    while (at && pad_clients[at - 1u].priority > priority) {
        pad_clients[at] = pad_clients[at - 1u];
        at--;
    }
    pad_clients[at].owner = owner;
    pad_clients[at].priority = priority;
    pad_clients[at].handler = handler;
    __atomic_store_n(&pad_client_count, pad_client_count + 1u, __ATOMIC_SEQ_CST);
    return 1;
}

static int register_key(const void *owner, unsigned int priority, rx3_key_handler handler)
{
    if (!owner || !handler || key_client_count >= CLIENT_LIMIT) return 0;
    for (unsigned int i = 0; i < key_client_count; i++)
        if (key_clients[i].owner == owner && key_clients[i].handler) return 0;
    if (!acquire(&key_hook, SEND_KEY, send_key_guard, (void *)key_hooked, 0)) return 0;
    unsigned int at = key_client_count;
    while (at && key_clients[at - 1u].priority > priority) {
        key_clients[at] = key_clients[at - 1u];
        at--;
    }
    key_clients[at].owner = owner;
    key_clients[at].priority = priority;
    key_clients[at].handler = handler;
    __atomic_store_n(&key_client_count, key_client_count + 1u, __ATOMIC_SEQ_CST);
    return 1;
}

static int register_lights(const void *owner, unsigned int refresh, rx3_light_fn light)
{
    if (!owner || !light || refresh > RX3_LIGHTS_PADS) return 0;
    if (refresh == RX3_LIGHTS_SLIP_LOOP) {
        if (slip_led_owner ||
            !acquire(&slip_led_hook, CHECK_SLIP_LED, slip_led_guard, (void *)slip_led_hooked, 1))
            return 0;
        slip_led_owner = owner;
        __atomic_store_n(&slip_light, light, __ATOMIC_SEQ_CST);
        return 1;
    }
    if (pad_led_owner ||
        !acquire(&pad_led_hook, CHECK_LED_STAT, led_stat_guard, (void *)pad_led_hooked, 0))
        return 0;
    pad_led_owner = owner;
    __atomic_store_n(&pad_light, light, __ATOMIC_SEQ_CST);
    return 1;
}

static int claim_mode_keys(const void *owner)
{
    if (!owner) return 0;
    unsigned int free_slot = CLIENT_LIMIT;
    for (unsigned int i = 0; i < CLIENT_LIMIT; i++) {
        if (mode_key_owners[i] == owner) return 0;
        if (!mode_key_owners[i] && free_slot == CLIENT_LIMIT) free_slot = i;
    }
    if (free_slot == CLIENT_LIMIT ||
        !acquire(&mode_key_hook, PHYSICAL_KEY, physical_guard, (void *)mode_key_hooked, 0))
        return 0;
    mode_key_owners[free_slot] = owner;
    return 1;
}

static void unregister_owner(const void *owner)
{
    if (!owner) return;
    unsigned int pads = 0, keys = 0, modes = 0;
    for (unsigned int i = 0; i < pad_client_count; i++) {
        if (pad_clients[i].owner == owner) __atomic_store_n(&pad_clients[i].handler, 0, __ATOMIC_SEQ_CST);
        if (pad_clients[i].handler) pads++;
    }
    for (unsigned int i = 0; i < key_client_count; i++) {
        if (key_clients[i].owner == owner) __atomic_store_n(&key_clients[i].handler, 0, __ATOMIC_SEQ_CST);
        if (key_clients[i].handler) keys++;
    }
    if (slip_led_owner == owner) {
        __atomic_store_n(&slip_light, 0, __ATOMIC_SEQ_CST);
        slip_led_owner = 0;
    }
    if (pad_led_owner == owner) {
        __atomic_store_n(&pad_light, 0, __ATOMIC_SEQ_CST);
        pad_led_owner = 0;
    }
    for (unsigned int i = 0; i < CLIENT_LIMIT; i++) {
        if (mode_key_owners[i] == owner) mode_key_owners[i] = 0;
        if (mode_key_owners[i]) modes++;
    }
    /* Handlers the owner left behind can still be running; wait them out
       before its code or state may be released. */
    drain(&pad_hook); drain(&key_hook); drain(&slip_led_hook);
    drain(&pad_led_hook); drain(&mode_key_hook);
    if (!pads) { relinquish(&pad_hook); if (!pad_hook.original) pad_client_count = 0; }
    if (!keys) { relinquish(&key_hook); if (!key_hook.original) key_client_count = 0; }
    if (!slip_led_owner) relinquish(&slip_led_hook);
    if (!pad_led_owner) relinquish(&pad_led_hook);
    if (!modes) relinquish(&mode_key_hook);
}

static int shift_is_held(unsigned int channel)
{
    if (channel != RX3_NO_DECK) return channel < KEY_CHANNELS && shift_held[channel];
    for (unsigned int i = 0; i < KEY_CHANNELS; i++) if (shift_held[i]) return 1;
    return 0;
}

void rx3_input_bind_mode_keys(void (*action)(void))
{
    __atomic_store_n(&mode_key_action, action, __ATOMIC_SEQ_CST);
}

void rx3_input_trace_keys(unsigned int limit)
{
    key_trace_limit = limit;
}

unsigned int rx3_input_count(void)
{
    return pad_client_count + key_client_count + (slip_led_owner != 0) + (pad_led_owner != 0);
}

const struct rx3_input_service rx3_input = {
    register_pad, register_key, register_lights, claim_mode_keys,
    unregister_owner, shift_is_held, blink_on, blink_restart
};
