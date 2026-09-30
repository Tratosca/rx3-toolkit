# SPDX-License-Identifier: MPL-2.0
"""The shared input, audio and image services, against fake native hooks."""
import unittest

from tests import test_framework

# A hook table standing in for the firmware: installing records the
# replacement and hands back an "original" the test can observe.
HOOKS = r'''
struct installed_hook;
static void *replacement[8];
static unsigned long address_of[8];
static unsigned installed, detached, released, refuse_address, refuse_detach;
static void *original_for(unsigned long address);
static void *fake_install(struct installed_hook *h, unsigned long a, const uint8_t g[8], void *r) {
    (void)h; assert(g);
    if (a == refuse_address) return 0;
    replacement[installed] = r; address_of[installed++] = a; return original_for(a);
}
void *install_hook(struct installed_hook *h, unsigned long a, const uint8_t g[8], void *r) { return fake_install(h, a, g, r); }
void *install_pc_ldr_hook(struct installed_hook *h, unsigned long a, const uint8_t g[8], void *r) { return fake_install(h, a, g, r); }
int detach_hook(struct installed_hook *h) { (void)h; detached++; return !refuse_detach; }
int release_hook(struct installed_hook *h) { (void)h; released++; return 1; }
int uninstall_hook(struct installed_hook *h) { (void)h; return 1; }
static void *hooked(unsigned long address) {
    for (unsigned i = installed; i > 0; i--) if (address_of[i - 1] == address) return replacement[i - 1];
    return 0;
}
'''


class ServiceTests(unittest.TestCase):
    run_units = test_framework.FrameworkTests.run_units

    def test_pad_chain_priority_consumption_and_last_client_removal(self):
        self.run_units(HOOKS + r'''
#include "core/api/rx3_input_api.h"
#include "core/services/rx3_input.h"
static unsigned player_calls, first_calls, second_calls, first_takes, keys_seen;
static int player_pad(void *p, const void *e) { (void)p; (void)e; player_calls++; return 7; }
static int player_key(void *t, unsigned k, unsigned o, unsigned c, unsigned a, unsigned b, unsigned d) {
    (void)t; (void)k; (void)o; (void)c; (void)a; (void)b; (void)d; return 9;
}
static void *original_for(unsigned long a) {
    return a == 0x003060e8u ? (void *)player_pad : (void *)player_key;
}
static struct rx3_pad_event last;
static int first(const struct rx3_pad_event *e) { first_calls++; last = *e; return first_takes; }
static int second(const struct rx3_pad_event *e) { (void)e; second_calls++; return 0; }
static int watch(const struct rx3_key_event *e) { keys_seen += e->key == RX3_KEY_SHIFT; return e->key == 0x0210u; }
static const char a = 0, b = 0;
int main(void) {
    /* Registration order does not decide dispatch order; priority does. */
    assert(rx3_input.register_pad(&b, 20, second));
    assert(rx3_input.register_pad(&a, 10, first));
    assert(!rx3_input.register_pad(&a, 10, first));
    assert(installed == 1);
    int (*pad)(void *, const void *) = hooked(0x003060e8u);
    uint8_t player[0x80] = {0}; player[0x26] = 2; player[0x74] = 2;
    uint8_t event[12] = {0}; event[8] = 0x1b; event[9] = 0x41; event[10] = 0; event[11] = 3;
    assert(pad(player, event) == 7 && first_calls == 1 && second_calls == 1 && player_calls == 1);
    /* The channel names the deck; without one the dispatching player does. */
    assert(last.code == 0x411b && last.operation == 3 && last.deck == 1 && last.pad_mode == 2);
    event[10] = 1; pad(player, event); assert(last.deck == 0 && last.channel == 1);
    /* A consumed event goes no further, and the player never sees it. */
    first_takes = 1; player_calls = 0;
    assert(pad(player, event) == 1 && second_calls == 2 && !player_calls);
    /* Removing one client keeps the shared hook for the other. */
    rx3_input.unregister_owner(&a);
    assert(!detached); pad(player, event); assert(second_calls == 3 && player_calls == 1);
    rx3_input.unregister_owner(&b);
    assert(detached == 1 && released == 1);
    /* SHIFT is tracked before handlers run; a consumed key returns 0. */
    assert(rx3_input.register_key(&a, 10, watch));
    int (*key)(void *, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned) = hooked(0x0037ad64u);
    assert(key(0, RX3_KEY_SHIFT, 0, 2, 0, 0, 0) == 9 && keys_seen == 1);
    assert(rx3_input.shift_held(2) && rx3_input.shift_held(RX3_NO_DECK) && !rx3_input.shift_held(1));
    assert(key(0, 0x0210u, 0, 0, 0, 0, 0) == 0);
    assert(key(0, RX3_KEY_SHIFT, 3, 2, 0, 0, 0) == 9 && !rx3_input.shift_held(RX3_NO_DECK));
    /* A refused restore keeps the trampoline and passes everything through. */
    refuse_detach = 1; rx3_input.unregister_owner(&a);
    assert(key(0, 0x0210u, 0, 0, 0, 0, 0) == 9);
    return 0;
}
''', ['core/services/rx3_input.c'], ['-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE'])

    def test_declared_lights_reach_only_the_leds_they_name(self):
        self.run_units(HOOKS + r"""
#include "core/services/rx3_input.c"
static void native_refresh(void *a, void *b) { (void)a; (void)b; }
static void *original_for(unsigned long a) { (void)a; return (void *)native_refresh; }
struct write { uint8_t *led; int state, flag; unsigned period, origin; uint32_t rgb; };
static struct write writes[64];
static unsigned count;
static void fake_state(void *led, int state, unsigned period, unsigned origin, long x, int y) {
    (void)x; (void)y; writes[count++] = (struct write){led, state, -1, period, origin, 0};
}
static void fake_colour(void *led, int state, int dim, const void *rgb) {
    const uint8_t *c = rgb;
    writes[count++] = (struct write){led, state, dim, 0, 0, (uint32_t)c[0] << 16 | c[1] << 8 | c[2]};
}
static unsigned asked;
static void slip(unsigned deck, unsigned control, struct rx3_light *light) {
    asked++; assert(deck == 1);
    if (control == 5) { light->state = RX3_LIGHT_BLINK; light->rgb = 0x00ff00; }
    if (control == 6) { light->state = RX3_LIGHT_DIM; light->rgb = 0x0000ff; }
}
static void pads(unsigned deck, unsigned control, struct rx3_light *light) {
    (void)deck;
    if (control == RX3_LIGHT_SHIFT) { light->state = RX3_LIGHT_ON; light->rgb = 0xff0000; }
    if (control == 0) { light->state = RX3_LIGHT_DIM; light->rgb = 0x123456; }
}
static uint8_t entries[6][44];
static void set_led(unsigned i, unsigned id, unsigned channel) {
    memcpy(entries[i], &id, 4); memcpy(entries[i] + 4, &channel, 4);
}
static const char owner = 0;
int main(void) {
    led_state_writer = fake_state; led_colour_writer = fake_colour;
    assert(rx3_input.register_lights(&owner, RX3_LIGHTS_SLIP_LOOP, slip));
    assert(!rx3_input.register_lights(&owner, RX3_LIGHTS_SLIP_LOOP, slip));
    assert(rx3_input.register_lights(&owner, RX3_LIGHTS_PADS, pads));
    uint8_t list[16] = {0}; uint8_t *base = &entries[0][0]; uint16_t n = 6;
    memcpy(list + 4, &n, 2); memcpy(list + 8, &base, sizeof(base));
    /* SLIP LOOP, deck 2: only its own pads 1 to 8 (IDs 18 to 25) are asked. */
    set_led(0, 23, 2); set_led(1, 24, 2); set_led(2, 23, 1); set_led(3, 14, 2);
    set_led(4, 17, 2); set_led(5, 25, 2);
    uint8_t player[0x40] = {0}; player[0x26] = 2;
    void (*slip_refresh)(void *, void *) = hooked(0x002fcc04u);
    slip_refresh(player, list);
    assert(asked == 3);
    /* Blink carries the half-period and the shared origin; a steady light in
       this refresh changes only the colour. */
    assert(count == 3);
    assert(writes[0].led == entries[0] && writes[0].state == 2 && writes[0].period == 500);
    assert(writes[1].led == entries[0] && writes[1].rgb == 0x00ff00);
    assert(writes[2].led == entries[1] && writes[2].state == 1 && writes[2].flag == 1 && writes[2].rgb == 0x0000ff);
    unsigned origin = writes[0].origin;
    assert(rx3_input.blink_on());
    slip_refresh(player, list); assert(writes[3].origin == origin);
    rx3_input.blink_restart(); (void)rx3_input.blink_on();
    /* The unit-wide refresh: pads at 1 to 8 here, SHIFT at 14, states set. */
    count = 0; set_led(0, 1, 1); set_led(1, 2, 1); set_led(2, 14, 0);
    set_led(3, 30, 1); set_led(4, 9, 1); set_led(5, 0, 1);
    void (*pad_refresh)(void *, void *) = hooked(0x002f6318u);
    pad_refresh(0, list);
    assert(count == 4);
    assert(writes[0].led == entries[0] && writes[0].state == 1 && writes[1].flag == 1 && writes[1].rgb == 0x123456);
    assert(writes[2].led == entries[2] && writes[3].flag == 0 && writes[3].rgb == 0xff0000);
    /* The last owner gone, both native refreshes are handed back. */
    rx3_input.unregister_owner(&owner);
    assert(detached == 2 && released == 2);
    return 0;
}
""", [], ['-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE'])

    def test_memory_ledger_counts_what_others_have_in_flight(self):
        self.run_units(r"""
static const char *meminfo = "MemTotal: 1000000 kB\nMemAvailable:     10000 kB\n";
static int fake_open(const char *path, int flags, ...) { (void)flags; assert(!strcmp(path, "/proc/meminfo")); return 5; }
static ssize_t fake_read(int fd, void *out, size_t n) { assert(fd == 5); size_t l = strlen(meminfo); if (l > n) l = n; memcpy(out, meminfo, l); return (ssize_t)l; }
static int fake_close(int fd) { assert(fd == 5); return 0; }
#define open fake_open
#define read fake_read
#define close fake_close
#include "core/services/rx3_memory.c"
static const char stems = 0, samples = 0, theme = 0;
int main(void) {
    const struct rx3_memory_service *m = &rx3_memory;
    assert(m->available_kb() == 10000);
    /* The floor is the caller's: 6000 KiB reserved, 4000 KiB to give. */
    assert(!m->reserve(&stems, 4001u * 1024u, 6000));
    assert(m->reserve(&stems, 4000u * 1024u, 6000));
    /* Until it is resident, what one owner reserved is not there for another. */
    assert(!m->reserve(&theme, 1024u, 6000));
    m->settle(&stems, 4000u * 1024u);
    assert(m->held() == 4000u * 1024u);
    /* Settled pages are in the kernel's own figure now; /proc answers. */
    assert(m->reserve(&theme, 1024u, 6000));
    m->abandon(&theme, 1024u);
    assert(m->reserve(&theme, 4000u * 1024u, 6000));
    m->abandon(&theme, 4000u * 1024u);
    /* A zero floor records and never refuses. */
    assert(m->reserve(&samples, 1u << 30, 0));
    m->settle(&samples, 1u << 30);
    m->release(&samples, 1u << 30);
    m->release(&stems, 4000u * 1024u);
    assert(m->held() == 0);
    /* Unreadable memory refuses anything with a floor. */
    meminfo = "";
    assert(!m->reserve(&stems, 1024u, 1) && m->reserve(&stems, 1024u, 0));
    return 0;
}
""", [], ['-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE', '-Wno-unused-function'])

    def test_loader_runs_in_order_and_release_waits_for_the_running_job(self):
        self.run_units(r"""
#include "core/services/rx3_loader.h"
static const char stems = 0, samples = 0;
static volatile int order[8], ran, discarded, gate, saw_stopping;
static void record(void *c) { order[ran++] = (int)(intptr_t)c; }
static void blocking(void *c) {
    (void)c; order[ran++] = 99;
    while (!__atomic_load_n(&gate, __ATOMIC_SEQ_CST)) {
        if (rx3_loader.stopping(&stems)) { saw_stopping = 1; return; }
        usleep(1000);
    }
}
static void drop(void *c) { (void)c; discarded++; }
static void *release_stems(void *u) { (void)u; rx3_loader.release(&stems); return 0; }
int main(void) {
    assert(rx3_loader.claim(&stems) && !rx3_loader.claim(&stems));
    assert(rx3_loader.claim(&samples));
    struct rx3_load_job one = {record, drop, (void *)1}, two = {record, drop, (void *)2};
    struct rx3_load_job hold = {blocking, drop, 0};
    assert(!rx3_loader.submit(&stems, &(struct rx3_load_job){0, 0, 0}));
    /* One at a time, in submission order, whoever submitted. */
    assert(rx3_loader.submit(&stems, &one) && rx3_loader.submit(&samples, &two));
    while (ran < 2) usleep(1000);
    assert(order[0] == 1 && order[1] == 2);
    /* A running job keeps release waiting until it sees stopping and returns;
       the owner's queued job is dropped, the other owner's still runs. */
    assert(rx3_loader.submit(&stems, &hold));
    while (ran < 3) usleep(1000);
    assert(rx3_loader.submit(&stems, &one) && rx3_loader.submit(&samples, &two));
    pthread_t releaser; assert(!pthread_create(&releaser, 0, release_stems, 0));
    pthread_join(releaser, 0);
    assert(saw_stopping && discarded == 1);
    assert(!rx3_loader.submit(&stems, &one));
    while (ran < 4) usleep(1000);
    assert(order[3] == 2 && !rx3_loader_pending());
    rx3_loader.release(&samples);
    /* Nobody left: a new owner starts a fresh worker. */
    assert(rx3_loader.claim(&stems) && rx3_loader.submit(&stems, &one));
    while (ran < 5) usleep(1000);
    rx3_loader.release(&stems);
    return 0;
}
""", ['core/services/rx3_loader.c'], ['-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE', '-pthread'])

    def test_audio_stages_order_ownership_and_deck_identity(self):
        self.run_units(HOOKS + r'''
#include "core/services/rx3_audio.h"
static unsigned stream_calls, talkover_calls;
static float seen_by_talkover;
static unsigned long native_stream(void *s, unsigned long p, struct rx3_stereo *o, unsigned long n) {
    (void)s; (void)p; stream_calls++; for (unsigned long i = 0; i < n; i++) o[i].left = 1; return n;
}
static void native_talkover(void *s, void *t, struct rx3_stereo *o, int n) {
    (void)s; (void)t; (void)n; talkover_calls++; seen_by_talkover = o[0].left;
}
static void *original_for(unsigned long a) {
    return a == 0x000c292cu ? (void *)native_stream : (void *)native_talkover;
}
static unsigned deck_seen = 9; static int position_seen;
static void deck_client(unsigned d, const void *r, int p, struct rx3_stereo *o, unsigned n) {
    (void)r; (void)n; deck_seen = d; position_seen = p; assert(o[0].left == 1); /* after the stream */
    o[0].left = 2;
}
static void master_client(struct rx3_stereo *o, unsigned n) { (void)n; o[0].left += 0.5f; }
static const char owner = 0, other = 0;
int main(void) {
    assert(rx3_audio.claim_deck_stream(&owner, deck_client));
    assert(!rx3_audio.claim_deck_stream(&other, deck_client));
    unsigned long (*stream)(void *, unsigned long, struct rx3_stereo *, unsigned long) = hooked(0x000c292cu);
    /* ARM32 layout: the reader pointer sits at byte 4 of TimeStretch. */
    int reader = 0; uint8_t stretch[16] = {0}; void *pointer = &reader; memcpy(stretch + 4, &pointer, sizeof(pointer));
    struct rx3_stereo out[1] = {{0, 0}};
    /* A reader that names no deck is played but never processed. */
    stream(stretch, 44, out, 1); assert(deck_seen == 9 && out[0].left == 1);
    rx3_audio_track_loading(1); rx3_audio_track_loaded(1, &reader);
    stream(stretch, 44, out, 1); assert(deck_seen == 1 && position_seen == 44 && out[0].left == 2);
    rx3_audio_track_loading(1); deck_seen = 9;
    stream(stretch, 44, out, 1); assert(deck_seen == 9);
    /* The master client runs before the talkover attenuator. */
    assert(rx3_audio.claim_master(&owner, master_client));
    void (*talkover)(void *, void *, struct rx3_stereo *, int) = hooked(0x0009c750u);
    out[0].left = 0; talkover(0, 0, out, 1); assert(seen_by_talkover == 0.5f);
    /* Only the owner releases; release detaches, drains and frees. */
    rx3_audio.release_master(&other); assert(!detached);
    rx3_audio.release_master(&owner); assert(detached == 1 && released == 1);
    rx3_audio.release_deck_stream(&owner); assert(detached == 2 && released == 2);
    assert(rx3_audio.claim_deck_stream(&other, deck_client) && installed == 3);
    return 0;
}
''', ['core/services/rx3_audio.c'], ['-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE'])

    def test_native_replacements_are_retained_once_published(self):
        self.run_units(HOOKS + r'''
#include "core/services/rx3_images.h"
static void *original_for(unsigned long a) { (void)a; return (void *)1; }
static const char logo = 0, theme = 0;
static uint16_t dark[4], light[4];
static unsigned drawn;
static void on_drawn(unsigned id) { drawn = id; }
static unsigned fill(unsigned c, unsigned w, unsigned h) { (void)w; (void)h; return c; }
static const struct rx3_image_policy policy = {on_drawn, fill};
int main(void) {
    static uint8_t table[RX3_NATIVE_IMAGE_COUNT * 44u];
    /* One policy owner; drawing is reported to it, never for private IDs.
       Released before any table exists, so no firmware pointer is written. */
    assert(rx3_images.claim_variants(&theme, &policy) && !rx3_images.claim_variants(&logo, &policy));
    rx3_image_drawn(0x10); assert(drawn == 0x10);
    rx3_image_drawn(0x1700); assert(drawn == 0x10);
    assert(!rx3_images.variants_ready() && !rx3_images.light_active());
    rx3_images.release_variants(&theme); assert(released == 1);
    assert(rx3_images.replace_native(&logo, 0x63f, dark, light, 2, 2));
    assert(!rx3_images.replace_native(&theme, 0x63f, dark, 0, 2, 2));
    assert(!rx3_images.replace_native(&logo, RX3_NATIVE_IMAGE_COUNT, dark, 0, 2, 2));
    assert(rx3_image_contributions() == 1);
    /* Before publication the owner may take its pixels back. */
    assert(rx3_images.release_native(&logo) && !rx3_image_contributions());
    assert(rx3_images.replace_native(&logo, 0x63f, dark, light, 2, 2));
    rx3_image_install_replacements(table, 0);
    uint8_t *record = table + 0x63f * 44u; uint16_t w; memcpy(&w, record + 4, 2);
    assert(w == 2 && record[0x18] == 2);
    rx3_image_publish_tables(table, 0, 0);
    /* Once a published table points at them, they stay. */
    assert(!rx3_images.release_native(&logo));
    assert(!rx3_images.replace_native(&theme, 0x100, dark, 0, 2, 2));
    /* Replaced records never reach a conversion policy. */
    struct rx3_native_image native;
    assert(!rx3_images.native_image(0x63f, &native));
    return 0;
}
''', ['core/services/rx3_images.c'], ['-D_DEFAULT_SOURCE', '-D_DARWIN_C_SOURCE', '-Wno-unused-function'])


if __name__ == '__main__':
    unittest.main()
