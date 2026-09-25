/* SPDX-License-Identifier: MPL-2.0
 * Key Shift implementation of the core runtime-feature lifecycle.
 */

#ifndef RX3_KEYSHIFT_FEATURE_H
#define RX3_KEYSHIFT_FEATURE_H

static int keyshift_feature_configured(void)
{
    return keyshift_enabled;
}

static int keyshift_feature_install(void)
{
    original_audio_start = (audio_start_fn)install_hook(
        &audio_start_hook, AUDIO_START, audio_start_guard,
        (void *)hooked_audio_start);
    if (!original_audio_start)
        return 0;
    rx3_keyshift_install();
    return rx3_keyshift_ready();
}

static void keyshift_feature_remove(void)
{
    rx3_keyshift_remove();
    uninstall_hook(&audio_start_hook);
    original_audio_start = 0;
}

static void keyshift_feature_track_did_load(unsigned int deck, void *reader,
                                            const void *track_info)
{
    (void)reader;
    (void)track_info;
    rx3_keyshift_reload(deck);
}

#endif /* RX3_KEYSHIFT_FEATURE_H */
