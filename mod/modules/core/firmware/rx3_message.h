/* SPDX-License-Identifier: MPL-2.0
 *
 * Telling the operator something, in the player's own words.
 *
 * The player already has this. EMERGENCY LOOP is one entry in a table of
 * on-screen notices -- PC FULL, OVERCURRENT, DATABASE UNFOUND and dozens more
 * -- and each is a `ui::Caution` object constructed once at start-up and shown
 * through a method that takes the text as a UTF-16 pointer:
 *
 *     ui::Caution::set(bool show, Channel deck, unsigned short const *text)
 *
 * So a message goes on screen the way the player's own do: its placement, its
 * timer, its priority. Nothing here paints a rectangle over the top.
 *
 * The object is borrowed rather than built. The player constructs 72 of them in
 * one static initialiser and 20 are never referenced anywhere else in the
 * binary, so it never raises them itself. B051 is one of those: an info-bar
 * notice with a three second life, which is the shape of what we have to say.
 * Building one instead would mean modelling a C++ object with bitfields and
 * multiple inheritance, and a wrong field is a frozen player mid-set.
 *
 * That risk is not hypothetical. A build predating this repository had its own
 * caution workers, and `tools/rx3_runtime/patch_r38_ui.py` in the tag
 * `snapshot/before-cleanup` records how that ended: "Native caution workers
 * are disabled; invoking that path froze rbp." The cause was never written
 * down. Everything below that looks like caution rather than ceremony is
 * there for that sentence.
 */

#ifndef RX3_MESSAGE_H
#define RX3_MESSAGE_H

/* ui::Caution::set(bool, uif::UiObject::Channel, unsigned short const *) const.
   Identical in firmware 1.19 and 1.20, prologue and all. */
#define CAUTION_SET ((unsigned long)0x0032b374)
static const uint8_t caution_set_guard[8] = {
    0xf8, 0x45, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};

/* ui::CautionObj::B051 -- a pointer to the object, not the object. An info-bar
   notice the player constructs and then never raises. */
#define CAUTION_B051 ((unsigned long)0x004cbaec)

/* gUtilityLanguageNo: one byte, and it counts from one. The Utility row reads
   it and subtracts one before indexing, which is the off-by-one that would
   otherwise pick the language next to the operator's. */
#define UTILITY_LANGUAGE_NO ((unsigned long)0x00521310)
#define RX3_LANGUAGE_COUNT 18u

/* The order the player lists them in, so a table below can be read against it:
   1 ENGLISH, 2 FRANCAIS, 3 DEUTSCH, 4 ITALIANO, 5 NEDERLANDS, 6 ESPANOL,
   7 RUSSIAN, 8 KOREAN, 9 CHINESE SIMPLIFIED, 10 CHINESE TRADITIONAL,
   11 JAPANESE, 12 PORTUGUES, 13 SVENSKA, 14 CESTINA, 15 MAGYAR, 16 DANSK,
   17 GREEK, 18 TURKCE. */

#define RX3_MESSAGE_OFF_SENTINEL "/tmp/rx3-messages.off"
#define RX3_MESSAGE_HOLD_US 4000000u

/* A message is one string per language, English first. A table shorter than the
   language it is asked for falls back to English, which is what the player does
   with a string set that does not cover a language either. */
struct rx3_message {
    const uint16_t *const *by_language;
    unsigned char count;
};

static int messages_enabled = 1;
static unsigned int message_guard_checked;
static unsigned int message_guard_passed;
#include "../services/rx3_notice.h"

typedef void (*caution_set_fn)(const void *caution, int show,
                               unsigned int channel, const uint16_t *text);

/* RX3 MESSAGE SELECT BEGIN */
/* The player's language number, as a table index.
 *
 * It counts from one and the tables count from zero, which the Utility row
 * itself shows: it reads the number and subtracts one before indexing. Getting
 * that wrong shows an operator the language listed next to theirs, and says
 * nothing about it. Anything outside the range the player knows falls back to
 * English rather than indexing on a byte we do not understand.
 */
static unsigned int rx3_message_language_from(unsigned int number)
{
    if (number < 1u || number > RX3_LANGUAGE_COUNT)
        return 0u;
    return number - 1u;
}

/* Which string a message shows in a given language.
 *
 * Separated from the byte that says which language because this is the half
 * that can be wrong in silence: an index past the end of a table reads whatever
 * follows it and hands the player a pointer to nothing. The test compiles this
 * block on the computer and walks every index against every table length.
 */
static const uint16_t *rx3_message_text_for(const struct rx3_message *message,
                                            unsigned int language)
{
    if (!message || !message->by_language || !message->count)
        return 0;
    if (language >= message->count || !message->by_language[language])
        language = 0u;
    return message->by_language[language];
}
/* RX3 MESSAGE SELECT END */

/* The operator's language, zero based, or 0 when the byte says something this
   core does not recognise. Reading it is a byte load: no call, no vtable, and
   nothing that cares which thread asks. */
static unsigned int rx3_message_language(void)
{
    return rx3_message_language_from(
        *(const volatile uint8_t *)UTILITY_LANGUAGE_NO);
}

static const uint16_t *rx3_message_text(const struct rx3_message *message)
{
    return rx3_message_text_for(message, rx3_message_language());
}

/* The switch an operator can reach without building another drive. A frozen
   player is the failure this path has already produced once, and the symptom
   would arrive in the middle of a set. */
static int rx3_message_allowed(void)
{
    int sentinel;
    if (!__atomic_load_n(&messages_enabled, __ATOMIC_SEQ_CST))
        return 0;
    sentinel = open(RX3_MESSAGE_OFF_SENTINEL, O_RDONLY);
    if (sentinel >= 0) {
        close(sentinel);
        __atomic_store_n(&messages_enabled, 0, __ATOMIC_SEQ_CST);
        log_line("messages: rx3-messages.off seen, no further notices");
        return 0;
    }
    return 1;
}

/* Guarded the way a hook site is: the prologue is compared before anything
   jumps there. An unrecognised player gets no message rather than a call into
   the middle of something else. */
static int rx3_message_call_site_ready(void)
{
    if (!message_guard_checked) {
        message_guard_checked = 1u;
        message_guard_passed =
            memcmp((const void *)CAUTION_SET, caution_set_guard, 8) ? 0u : 1u;
        if (!message_guard_passed)
            log_line("messages: the caution entry point is not the one expected");
    }
    return (int)message_guard_passed;
}

/* Native calls stay on the renderer. The framework owns text lifetimes. */
static void rx3_message_render(unsigned int deck, const uint16_t *text, int show)
{
    const void *caution = *(const void *const *)CAUTION_B051;
    if (caution && rx3_message_call_site_ready())
        ((caution_set_fn)CAUTION_SET)(caution, show, deck, text);
}
static void rx3_message_show(unsigned int deck, const struct rx3_message *message)
{
    struct rx3_notice request = {
        message, 0u, deck, RX3_NOTICE_WARNING, RX3_MESSAGE_HOLD_US / 1000u,
        rx3_message_text(message)
    };
    (void)rx3_notices.post(&request);
}
static void rx3_message_run_pending(void)
{
    int enabled = __atomic_load_n(&messages_enabled, __ATOMIC_SEQ_CST) &&
        rx3_message_call_site_ready() &&
        *(const void *const *)CAUTION_B051;
    rx3_notice_pump(monotonic_enough_us() / 1000u, enabled, rx3_message_render);
}

/* The prose lives next door, so a translation can be corrected without reading
   a byte guard or a thread rule. */
#include "../ui/rx3_messages.h"

#endif /* RX3_MESSAGE_H */
