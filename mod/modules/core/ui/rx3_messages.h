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
 * On length: the player's own notices in this position run to about twenty-two
 * characters -- "HOT CUE - NOW LOADING..." is one of them -- so these are
 * written to that. What the player does with a longer one has not been tried.
 *
 * On the translations: English and French are the author's. The rest are
 * written with care and none has been read by a native speaker of that
 * language, nor seen on a deck set to it. A correction is a one line change
 * and is welcome; that is much of why they are in a file of their own.
 */

#ifndef RX3_MESSAGES_H
#define RX3_MESSAGES_H

#define RX3_TEXT(s) ((const uint16_t *)u##s)

/* Shown only after the native core starts drawing on the normal load path.
   The notice identifies the mod while keeping the USB warning. Its absence
   alone cannot prove safe mode: rendering or notice delivery may fail. */
static const uint16_t *const message_loading_table[RX3_LANGUAGE_COUNT] = {
    /*  1 ENGLISH             */ RX3_TEXT("MODS LOADING - KEEP USB"),
    /*  2 FRANCAIS            */ RX3_TEXT("MODS EN COURS - USB EN PLACE"),
    /*  3 DEUTSCH             */ RX3_TEXT("MODS LADEN - USB BELASSEN"),
    /*  4 ITALIANO            */ RX3_TEXT("CARICO MOD - TENERE USB"),
    /*  5 NEDERLANDS          */ RX3_TEXT("MODS LADEN - USB LATEN"),
    /*  6 ESPANOL             */ RX3_TEXT("CARGANDO MODS - DEJAR USB"),
    /*  7 Russian             */ RX3_TEXT("ЗАГРУЗКА МОДОВ - НЕ ТРОГАТЬ USB"),
    /*  8 Korean              */ RX3_TEXT("모드 로딩 중 - USB 유지"),
    /*  9 Chinese simplified  */ RX3_TEXT("正在加载模组 - 请勿拔出USB"),
    /* 10 Chinese traditional */ RX3_TEXT("正在載入模組 - 請勿拔出USB"),
    /* 11 Japanese            */ RX3_TEXT("MOD読込中 - USBを抜かない"),
    /* 12 PORTUGUES           */ RX3_TEXT("A CARREGAR MODS - MANTER USB"),
    /* 13 SVENSKA             */ RX3_TEXT("MODDAR LADDAS - BEHÅLL USB"),
    /* 14 CESTINA             */ RX3_TEXT("NAČÍTÁNÍ MODŮ - NECHAT USB"),
    /* 15 MAGYAR              */ RX3_TEXT("MODOK TÖLTÉSE - USB MARAD"),
    /* 16 DANSK               */ RX3_TEXT("MODS INDLÆSES - BEHOLD USB"),
    /* 17 Greek               */ RX3_TEXT("ΦΟΡΤΩΣΗ MOD - ΚΡΑΤΗΣΤΕ USB"),
    /* 18 TURKCE              */ RX3_TEXT("MODLAR YÜKLENİYOR - USB KALSIN")
};

static const struct rx3_message message_drive_loading = {
    message_loading_table, RX3_LANGUAGE_COUNT
};

#endif /* RX3_MESSAGES_H */
