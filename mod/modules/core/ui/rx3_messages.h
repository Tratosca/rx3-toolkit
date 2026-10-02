/* SPDX-License-Identifier: MPL-2.0
 *
 * What the mod says on screen, in every language the player offers.
 *
 * Kept apart from the mechanism in rx3_message.h on purpose: this file is
 * prose, and someone correcting a translation should not have to read a byte
 * guard or a thread rule to do it. Nothing here calls anything.
 *
 * The order is the player's own, from the LANGUAGE row in Utility, and it is
 * the order rx3_message_language_from() indexes. Adding a language means adding
 * a line in the right place, not renumbering anything. Leaving an entry as 0 is
 * allowed and means "fall back to English", which is what the selection does
 * with a short table anyway.
 *
 * The strings are UTF-16 because that is what the player's notice method takes.
 * The u"" literals compile to exactly that, so the text stays readable here
 * rather than becoming a wall of code points.
 *
 * The active flag and module noun stay short; the supplied version and count
 * are bounded by the notice queue before they reach the native text renderer.
 *
 * On the translations: English and French are the author's. The rest are
 * written with care and none has been read by a native speaker of that
 * language, nor seen on a deck set to it. A correction is a one line change
 * and is welcome; that is much of why they are in a file of their own.
 */

#ifndef RX3_MESSAGES_H
#define RX3_MESSAGES_H

#define RX3_TEXT(s) ((const uint16_t *)u##s)

/* The version and count are supplied by the image. The core only formats this
   generic summary; the labels follow the player's language order above. */
static const uint16_t *const message_mod_count_table[RX3_LANGUAGE_COUNT] = {
    RX3_TEXT("MODS"), RX3_TEXT("MODS"), RX3_TEXT("MODS"),
    RX3_TEXT("MOD"), RX3_TEXT("MODS"), RX3_TEXT("MODS"),
    RX3_TEXT("МОДОВ"), RX3_TEXT("모드"), RX3_TEXT("模组"),
    RX3_TEXT("模組"), RX3_TEXT("MOD"), RX3_TEXT("MODS"),
    RX3_TEXT("MODDAR"), RX3_TEXT("MODŮ"), RX3_TEXT("MOD"),
    RX3_TEXT("MODS"), RX3_TEXT("MOD"), RX3_TEXT("MOD")
};
static const struct rx3_message message_mod_count = {
    message_mod_count_table, RX3_LANGUAGE_COUNT
};
static const uint16_t *const message_active_table[RX3_LANGUAGE_COUNT] = {
    RX3_TEXT("ON"), RX3_TEXT("ACTIF"), RX3_TEXT("AKTIV"),
    RX3_TEXT("ATTIVO"), RX3_TEXT("ACTIEF"), RX3_TEXT("ACTIVO"),
    RX3_TEXT("АКТИВЕН"), RX3_TEXT("활성"), RX3_TEXT("已启用"),
    RX3_TEXT("已啟用"), RX3_TEXT("有効"), RX3_TEXT("ATIVO"),
    RX3_TEXT("AKTIV"), RX3_TEXT("AKTIVNÍ"), RX3_TEXT("AKTÍV"),
    RX3_TEXT("AKTIV"), RX3_TEXT("ΕΝΕΡΓΟ"), RX3_TEXT("AKTİF")
};
static const struct rx3_message message_active = {
    message_active_table, RX3_LANGUAGE_COUNT
};

#endif /* RX3_MESSAGES_H */
