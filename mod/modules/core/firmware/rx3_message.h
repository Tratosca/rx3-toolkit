/* SPDX-License-Identifier: MPL-2.0
 * Renderer-owned notices. Producers post bounded UTF-16 to rx3_notice;
 * the render task paints a temporary message in the native header.
 */

#ifndef RX3_MESSAGE_H
#define RX3_MESSAGE_H

/* The RX3 legacy renderer does not initialize uif::MsgManager. The similarly
 * named ui::Caution::set throws if it is called there and ignores custom text.
 * Notices are bounded renderer-owned text, painted in the native header. */
static uint16_t message_display_text[96];
static unsigned message_display_active,message_display_dirty;

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


#include "../services/rx3_notice.h"

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

static int rx3_message_call_site_ready(void)
{
    return text_template_ready != 0;
}
/* Called only by the render task. The producer's text never escapes a pump. */
static void rx3_message_render(unsigned int deck, const uint16_t *text, int show)
{
    (void)deck;
    unsigned n=0;
    if(show && text)while(n<95 && text[n]){message_display_text[n]=text[n];n++;}
    if(n && message_display_text[n-1]>=0xd800 && message_display_text[n-1]<=0xdbff)n--;
    message_display_text[n]=0;
    message_display_active=show && n;
    message_display_dirty=1;
    if(show)log_line("messages: native header notice ready");
}
static enum rx3_notice_result rx3_message_show(
    unsigned int deck, const struct rx3_message *message)
{
    struct rx3_notice request = {
        message, 0u, deck, RX3_NOTICE_WARNING, RX3_MESSAGE_HOLD_US / 1000u,
        rx3_message_text(message)
    };
    return rx3_notices.post(&request);
}
static void rx3_message_run_pending(void)
{
    int enabled = __atomic_load_n(&messages_enabled, __ATOMIC_SEQ_CST) &&
        rx3_message_call_site_ready();
    rx3_notice_pump(monotonic_enough_us() / 1000u, enabled, rx3_message_render);
}

/* The prose lives next door, so a translation can be corrected without reading
   a byte guard or a thread rule. */
#include "../ui/rx3_messages.h"

#endif /* RX3_MESSAGE_H */
