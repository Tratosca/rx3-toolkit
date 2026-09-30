/* SPDX-License-Identifier: MPL-2.0
 * Accent folding implementation of the core runtime-feature lifecycle.
 */

#ifndef RX3_SEARCH_FEATURE_H
#define RX3_SEARCH_FEATURE_H

static int search_latin_enabled;
static unsigned int search_callbacks;

/* Fold the query the player is about to search with.
 *
 * The original runs first and does whatever shaping the firmware wanted; this
 * only rewrites what it produced. Working on the buffer in place is what keeps
 * the change invisible to everything downstream: no length changes, so no
 * caller has to know this ran.
 *
 * Which is also the limit. A fold that needed more room than it started with,
 * a ligature into its pair, cannot be done here and is left alone rather than
 * truncated. The sharp s folds to a single S for that reason.
 */
static void hooked_search_shape(uint16_t *text, void *context, int length)
{
    __atomic_add_fetch(&search_callbacks, 1u, __ATOMIC_SEQ_CST);
    original_search_shape(text, context, length);
    if (!text || length <= 0)
        goto done;
    for (int index = 0; index < length; index++) {
        uint16_t glyph = text[index];
        if (!glyph)
            break;
        if (glyph >= SEARCH_FOLD_FIRST && glyph <= SEARCH_FOLD_LAST)
            text[index] = search_fold_table[glyph - SEARCH_FOLD_FIRST];
        else if (glyph == SEARCH_FOLD_Y_DIAERESIS)
            text[index] = SEARCH_FOLD_Y;
    }
done:
    __atomic_sub_fetch(&search_callbacks, 1u, __ATOMIC_SEQ_CST);
}

static int search_latin_feature_configured(void)
{
    /* Only the setting. configure_features() calls this to decide whether
       install() runs at all, so asking here whether the hook is installed
       would answer no for ever. */
    const char *setting = getenv("RX3_SEARCH_LATIN");
    search_latin_enabled = setting && setting[0] == '1';
    return search_latin_enabled;
}

static int search_latin_feature_install(void)
{
    if (!search_latin_enabled)
        return 0;
    original_search_shape = (search_shape_fn)framework->install_hook(
        &search_shape_hook, SEARCH_SHAPE, search_shape_guard, hooked_search_shape);
    if (!original_search_shape)
        return 0;
    framework->log_line("browse search: accents no longer hide a track");
    return 1;
}

static void search_latin_feature_remove(void)
{
    if (!framework->detach_hook(&search_shape_hook)) return;
    while (__atomic_load_n(&search_callbacks, __ATOMIC_SEQ_CST)) usleep(1000u);
    if (framework->release_hook(&search_shape_hook))
        original_search_shape = 0;
}

#endif /* RX3_SEARCH_FEATURE_H */
