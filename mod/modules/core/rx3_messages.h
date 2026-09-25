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

/* The drive is in, the player has come back, and the loaders are still working.
   The operator sees the wait whatever we do; what they cannot see is that this
   is the window in which pulling the drive costs them a folder on a FAT stick.
   So the notice spends its one line on the warning rather than on narrating the
   wait. It does not promise that removal becomes safe when it clears: the
   player keeps its output file open for as long as it plays whenever logging is
   on, which is why the README says eject and never pull. */
static const uint16_t *const message_loading_table[RX3_LANGUAGE_COUNT] = {
    /*  1 ENGLISH             */ RX3_TEXT("DO NOT REMOVE THE USB KEY"),
    /*  2 FRANCAIS            */ RX3_TEXT("NE PAS RETIRER LA CLÉ USB"),
    /*  3 DEUTSCH             */ RX3_TEXT("USB-STICK NICHT ENTFERNEN"),
    /*  4 ITALIANO            */ RX3_TEXT("NON RIMUOVERE LA CHIAVE USB"),
    /*  5 NEDERLANDS          */ RX3_TEXT("USB-STICK NIET VERWIJDEREN"),
    /*  6 ESPANOL             */ RX3_TEXT("NO RETIRAR LA MEMORIA USB"),
    /*  7 Russian             */ RX3_TEXT("НЕ ИЗВЛЕКАЙТЕ USB-НАКОПИТЕЛЬ"),
    /*  8 Korean              */ RX3_TEXT("USB를 분리하지 마십시오"),
    /*  9 Chinese simplified  */ RX3_TEXT("请勿拔出 USB 存储器"),
    /* 10 Chinese traditional */ RX3_TEXT("請勿拔出 USB 隨身碟"),
    /* 11 Japanese            */ RX3_TEXT("USB を抜かないでください"),
    /* 12 PORTUGUES           */ RX3_TEXT("NÃO REMOVER A PEN USB"),
    /* 13 SVENSKA             */ RX3_TEXT("TA INTE BORT USB-MINNET"),
    /* 14 CESTINA             */ RX3_TEXT("NEVYJÍMEJTE USB DISK"),
    /* 15 MAGYAR              */ RX3_TEXT("NE TÁVOLÍTSA EL AZ USB-T"),
    /* 16 DANSK               */ RX3_TEXT("FJERN IKKE USB-NØGLEN"),
    /* 17 Greek               */ RX3_TEXT("ΜΗΝ ΑΦΑΙΡΕΙΤΕ ΤΟ USB"),
    /* 18 TURKCE              */ RX3_TEXT("USB BELLEĞİ ÇIKARMAYIN")
};

static const struct rx3_message message_drive_loading = {
    message_loading_table, RX3_LANGUAGE_COUNT
};

#endif /* RX3_MESSAGES_H */
