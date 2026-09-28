/* SPDX-License-Identifier: MPL-2.0 */
#include "rx3_notice.h"
struct notice_slot {
    const void *owner;
    unsigned int id, deck, priority, duration_ms;
    uint16_t text[RX3_NOTICE_TEXT_UNITS];
    uint64_t order, revision, deadline;
};
static struct notice_slot slots[RX3_NOTICE_CAPACITY];
static unsigned int gate, available;
static uint64_t serial;
/* Only the render thread owns display. Producers never touch its buffer. */
static struct notice_slot display;
static int pumping;
static int acquire(void) { return !__atomic_exchange_n(&gate, 1u, __ATOMIC_ACQUIRE); }
static void release(void) { __atomic_store_n(&gate, 0u, __ATOMIC_RELEASE); }
static enum rx3_notice_result post(const struct rx3_notice *request)
{
    if (!request || !request->owner || !request->text || request->deck > 1u ||
        request->priority > RX3_NOTICE_ERROR || !request->duration_ms ||
        request->duration_ms > 60000u) return RX3_NOTICE_INVALID;
    unsigned int length = 0;
    while (length < RX3_NOTICE_TEXT_UNITS && request->text[length]) length++;
    if (!length || length == RX3_NOTICE_TEXT_UNITS) return RX3_NOTICE_INVALID;
    if (!acquire()) return RX3_NOTICE_BUSY;
    struct notice_slot *target = 0, *empty = 0;
    for (unsigned int i = 0; i < RX3_NOTICE_CAPACITY; i++) {
        if (!slots[i].owner && !empty) empty = &slots[i];
        if (slots[i].owner == request->owner && slots[i].id == request->id) target = &slots[i];
    }
    if (!target) target = empty;
    if (!target) { release(); return RX3_NOTICE_FULL; }
    uint64_t order = target->owner ? target->order : ++serial;
    target->owner = request->owner;
    target->id = request->id;
    target->deck = request->deck;
    target->priority = request->priority;
    target->duration_ms = request->duration_ms;
    target->order = order;
    target->revision = ++serial;
    target->deadline = 0;
    memcpy(target->text, request->text, (length + 1u) * sizeof(uint16_t));
    release();
    return RX3_NOTICE_OK;
}
static enum rx3_notice_result cancel(const void *owner, unsigned int id)
{
    if (!owner) return RX3_NOTICE_INVALID;
    if (!acquire()) return RX3_NOTICE_BUSY;
    for (unsigned int i = 0; i < RX3_NOTICE_CAPACITY; i++)
        if (slots[i].owner == owner && slots[i].id == id) slots[i].owner = 0;
    release();
    return RX3_NOTICE_OK;
}
static int is_available(void) { return __atomic_load_n(&available, __ATOMIC_ACQUIRE); }
const struct rx3_notice_service rx3_notices = {post, cancel, is_available};
void rx3_notice_pump(uint64_t now_ms, int enabled, rx3_notice_renderer render)
{
    if (pumping) return;
    pumping = 1;
    __atomic_store_n(&available, enabled && render, __ATOMIC_RELEASE);
    if (!acquire()) { pumping = 0; return; }
    struct notice_slot *chosen = 0;
    for (unsigned int i = 0; i < RX3_NOTICE_CAPACITY; i++) {
        struct notice_slot *slot = &slots[i];
        if (!enabled || (slot->deadline && now_ms >= slot->deadline)) slot->owner = 0;
        if (!slot->owner) continue;
        if (!chosen || slot->priority > chosen->priority ||
            (slot->priority == chosen->priority && slot->order < chosen->order)) chosen = slot;
    }
    struct notice_slot next = {0};
    if (chosen && render) {
        if (!chosen->deadline) chosen->deadline = now_ms + chosen->duration_ms;
        next = *chosen;
    }
    release();
    if (display.owner && (!next.owner || display.revision != next.revision)) {
        if (render) render(display.deck, 0, 0);
        display.owner = 0;
    }
    if (next.owner && !display.owner) {
        display = next;
        render(display.deck, display.text, 1);
    }
    pumping = 0;
}
