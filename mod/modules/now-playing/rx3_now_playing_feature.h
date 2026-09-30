/* SPDX-License-Identifier: MPL-2.0
 * Now playing implementation of the core runtime-feature lifecycle.
 *
 * The hooks run on the player's own threads, so they do the least they can: a
 * load copies the title and track id into a per-deck record, and every event
 * sets a bit and wakes the worker. The worker owns everything else: the
 * player's accessors, the text of the datagram and the socket. A slow or absent
 * computer therefore never holds up the player.
 */

#ifndef RX3_NOW_PLAYING_FEATURE_H
#define RX3_NOW_PLAYING_FEATURE_H

struct now_playing_deck {
    volatile unsigned int revision;  /* odd while a load is writing */
    uint8_t  loaded;
    uint32_t track_id;
    uint16_t title[NOW_PLAYING_TITLE_UNITS];
};

static struct installed_hook now_playing_status_hook;
static struct installed_hook now_playing_load_hook;
static struct installed_hook now_playing_unload_hook;
static struct installed_hook now_playing_mixer_hook;
static now_playing_status_fn original_now_playing_status;
static now_playing_load_fn   original_now_playing_load;
static now_playing_unload_fn original_now_playing_unload;
static now_playing_mixer_fn  original_now_playing_mixer;

static struct now_playing_deck now_playing_decks[2];
static volatile unsigned int now_playing_pending;
static unsigned int now_playing_callbacks;
static volatile int now_playing_running;
static int now_playing_wake[2] = {-1, -1};
static int now_playing_socket = -1;
static unsigned int now_playing_sequence;
static pthread_t now_playing_thread;
static int now_playing_thread_started;
static const uint16_t now_playing_no_title[1] = {0};

/* Events --------------------------------------------------------------------- */

static void now_playing_signal(unsigned int decks)
{
    if (!decks)
        return;
    unsigned int before = __sync_fetch_and_or(&now_playing_pending, decks);
    if (!before && now_playing_wake[0] >= 0) {
        uint8_t wake = 1u;
        (void)send(now_playing_wake[0], &wake, sizeof(wake), NOW_PLAYING_DONTWAIT);
    }
}

static int now_playing_index(void *player)
{
    unsigned int channel = *((const uint8_t *)player + NOW_PLAYING_PLAYER_CHANNEL);
    return channel >= 1u && channel <= 2u ? (int)channel - 1 : -1;
}

static unsigned int now_playing_mask(void *player)
{
    int index = now_playing_index(player);
    return index >= 0 ? 1u << (unsigned int)index : 3u;
}

static void hooked_now_playing_status(void *player, int force)
{
    __atomic_add_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
    original_now_playing_status(player, force);
    now_playing_signal(now_playing_mask(player));
    __atomic_sub_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
}

static int hooked_now_playing_load(void *player, const void *music)
{
    __atomic_add_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
    int result = original_now_playing_load(player, music);
    int index = now_playing_index(player);
    if (!result || index < 0 || !music)
        goto done;
    struct now_playing_deck *deck = &now_playing_decks[index];
    (void)__sync_add_and_fetch(&deck->revision, 1u);
    memcpy(&deck->track_id, (const uint8_t *)music + NOW_PLAYING_MUSIC_ID,
           sizeof(deck->track_id));
    deck->loaded = deck->track_id != 0u;
    if (deck->loaded)
        memcpy(deck->title, (const uint8_t *)music + NOW_PLAYING_MUSIC_TITLE,
               sizeof(deck->title));
    else
        memset(deck->title, 0, sizeof(deck->title));
    deck->title[NOW_PLAYING_TITLE_UNITS - 1u] = 0;
    __sync_synchronize();
    (void)__sync_add_and_fetch(&deck->revision, 1u);
    now_playing_signal(1u << (unsigned int)index);
done:
    __atomic_sub_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
    return result;
}

/* An unload reports its result before the player lets go of the track, so the
   deck counts as empty only once the player's own reference has cleared. */
static void hooked_now_playing_unload(void *player, int result, unsigned int device,
                                      unsigned int number)
{
    __atomic_add_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
    original_now_playing_unload(player, result, device, number);
    int index = now_playing_index(player);
    if (index < 0 ||
        ((now_playing_current_track_fn)NOW_PLAYING_CURRENT_TRACK)(player, 0))
        goto done;
    struct now_playing_deck *deck = &now_playing_decks[index];
    int changed = deck->loaded || deck->track_id || deck->title[0];
    (void)__sync_add_and_fetch(&deck->revision, 1u);
    deck->loaded = 0u;
    deck->track_id = 0u;
    memset(deck->title, 0, sizeof(deck->title));
    __sync_synchronize();
    (void)__sync_add_and_fetch(&deck->revision, 1u);
    if (changed)
        now_playing_signal(1u << (unsigned int)index);
done:
    __atomic_sub_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
}

static void hooked_now_playing_mixer(void *mixer)
{
    __atomic_add_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
    uint8_t a = *((const uint8_t *)mixer + NOW_PLAYING_MIXER_ON_AIR_A);
    uint8_t b = *((const uint8_t *)mixer + NOW_PLAYING_MIXER_ON_AIR_B);
    original_now_playing_mixer(mixer);
    if (a != *((const uint8_t *)mixer + NOW_PLAYING_MIXER_ON_AIR_A) ||
        b != *((const uint8_t *)mixer + NOW_PLAYING_MIXER_ON_AIR_B))
        now_playing_signal(3u);
    __atomic_sub_fetch(&now_playing_callbacks, 1u, __ATOMIC_SEQ_CST);
}

/* The datagram ----------------------------------------------------------------- */

struct now_playing_text {
    char         bytes[NOW_PLAYING_DATAGRAM_MAX];
    unsigned int length;
};

/* Everything is appended through here, so a title however long cuts the
   datagram short rather than writing past it. */
static void now_playing_put(struct now_playing_text *text, const char *value,
                            unsigned int count)
{
    if (text->length + count >= sizeof(text->bytes))
        count = sizeof(text->bytes) - 1u - text->length;
    memcpy(text->bytes + text->length, value, count);
    text->length += count;
}

static void now_playing_literal(struct now_playing_text *text, const char *value)
{
    now_playing_put(text, value, (unsigned int)strlen(value));
}

/* Unsigned and signed apart: long is 32 bits here, so a track id past 2^31
   cast to it would come out negative. */
static void now_playing_unsigned(struct now_playing_text *text, unsigned int value,
                                 int negative)
{
    char digits[12];
    unsigned int count = 0;
    do {
        digits[sizeof(digits) - 1u - count++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value);
    if (negative)
        digits[sizeof(digits) - 1u - count++] = '-';
    now_playing_put(text, digits + sizeof(digits) - count, count);
}

static void now_playing_signed(struct now_playing_text *text, int value)
{
    now_playing_unsigned(text, value < 0 ? 0u - (unsigned int)value : (unsigned int)value,
                         value < 0);
}

/* The player keeps titles as UTF-16. JSON wants UTF-8 with quotes, backslashes
   and control characters escaped; an unpaired surrogate becomes U+FFFD. */
static void now_playing_title(struct now_playing_text *text, const uint16_t *title)
{
    now_playing_put(text, "\"", 1u);
    for (unsigned int i = 0; i < NOW_PLAYING_TITLE_UNITS && title[i]; i++) {
        uint32_t point = title[i];
        if (point >= 0xd800u && point <= 0xdbffu && i + 1u < NOW_PLAYING_TITLE_UNITS &&
            title[i + 1u] >= 0xdc00u && title[i + 1u] <= 0xdfffu)
            point = 0x10000u + ((point - 0xd800u) << 10u) + (title[++i] - 0xdc00u);
        else if (point >= 0xd800u && point <= 0xdfffu)
            point = 0xfffdu;

        char bytes[6];
        unsigned int count = 0;
        if (point == '"' || point == '\\') {
            bytes[count++] = '\\';
            bytes[count++] = (char)point;
        } else if (point < 0x20u) {
            static const char hex[] = "0123456789abcdef";
            now_playing_literal(text, "\\u00");
            bytes[count++] = hex[point >> 4u];
            bytes[count++] = hex[point & 0xfu];
        } else if (point < 0x80u) {
            bytes[count++] = (char)point;
        } else if (point < 0x800u) {
            bytes[count++] = (char)(0xc0u | (point >> 6u));
            bytes[count++] = (char)(0x80u | (point & 0x3fu));
        } else if (point < 0x10000u) {
            bytes[count++] = (char)(0xe0u | (point >> 12u));
            bytes[count++] = (char)(0x80u | ((point >> 6u) & 0x3fu));
            bytes[count++] = (char)(0x80u | (point & 0x3fu));
        } else {
            bytes[count++] = (char)(0xf0u | (point >> 18u));
            bytes[count++] = (char)(0x80u | ((point >> 12u) & 0x3fu));
            bytes[count++] = (char)(0x80u | ((point >> 6u) & 0x3fu));
            bytes[count++] = (char)(0x80u | (point & 0x3fu));
        }
        /* Never half a character: stop before one that does not fit, leaving
           room for the rest of the datagram's structure. */
        if (text->length + count + 64u >= sizeof(text->bytes))
            break;
        now_playing_put(text, bytes, count);
    }
    now_playing_put(text, "\"", 1u);
}

/* A consistent copy of one deck's record, retried while a load is writing. */
static void now_playing_read_deck(unsigned int index, struct now_playing_deck *copy)
{
    struct now_playing_deck *deck = &now_playing_decks[index];
    for (;;) {
        unsigned int before = deck->revision;
        if (before & 1u)
            continue;
        __sync_synchronize();
        copy->loaded = deck->loaded;
        copy->track_id = deck->track_id;
        memcpy(copy->title, deck->title, sizeof(copy->title));
        __sync_synchronize();
        if (deck->revision == before)
            return;
    }
}

/* Every datagram carries both decks whole, so a listener that missed one, or
   started late, is right again at the next. The units are the player's own:
   BPM in hundredths, tempo and play mode as read, until a capture on hardware
   says what their values mean. */
static void now_playing_send(const char *reason)
{
    struct now_playing_text text;
    text.length = 0;
    now_playing_literal(&text, "{\"type\":\"now-playing\",\"version\":1,\"sequence\":");
    now_playing_unsigned(&text, now_playing_sequence++, 0);
    now_playing_literal(&text, ",\"reason\":\"");
    now_playing_literal(&text, reason);
    now_playing_literal(&text, "\",\"decks\":[");
    for (unsigned int index = 0; index < 2u; index++) {
        struct now_playing_deck deck;
        now_playing_read_deck(index, &deck);
        int bpm = ((now_playing_deck_int_fn)NOW_PLAYING_PLAY_BPM)(index);
        if (!deck.loaded || bpm < 0 || bpm == 0xffff)
            bpm = 0;
        now_playing_literal(&text, index ? ",{\"deck\":" : "{\"deck\":");
        now_playing_unsigned(&text, index + 1u, 0);
        now_playing_literal(&text, deck.loaded ? ",\"loaded\":true" : ",\"loaded\":false");
        now_playing_literal(&text,
            ((now_playing_on_air_fn)NOW_PLAYING_ON_AIR)(index, 0)
                ? ",\"onAir\":true" : ",\"onAir\":false");
        now_playing_literal(&text, ",\"trackId\":");
        now_playing_unsigned(&text, deck.track_id, 0);
        now_playing_literal(&text, ",\"bpmX100\":");
        now_playing_signed(&text, bpm);
        now_playing_literal(&text, ",\"tempoRaw\":");
        now_playing_signed(&text, (int16_t)
            ((now_playing_deck_int_fn)NOW_PLAYING_PLAY_TEMPO)(index));
        now_playing_literal(&text, ",\"playModeRaw\":");
        now_playing_signed(&text,
            ((now_playing_deck_int_fn)NOW_PLAYING_PLAY_MODE)(index));
        now_playing_literal(&text, ",\"title\":");
        now_playing_title(&text, deck.loaded ? deck.title : now_playing_no_title);
        now_playing_literal(&text, "}");
    }
    now_playing_literal(&text, "]}\n");

    struct now_playing_address to;
    memset(&to, 0, sizeof(to));
    to.family = NOW_PLAYING_AF_INET;
    to.port = (uint16_t)((NOW_PLAYING_PORT >> 8u) | ((NOW_PLAYING_PORT & 0xffu) << 8u));
    to.address = NOW_PLAYING_BROADCAST;
    /* No computer on the link is the ordinary case, not an error. */
    (void)sendto(now_playing_socket, text.bytes, text.length, NOW_PLAYING_DONTWAIT,
                 &to, sizeof(to));
}

/* The worker -------------------------------------------------------------------- */

static void *now_playing_worker(void *unused)
{
    (void)unused;
    struct pollfd wake;
    wake.fd = now_playing_wake[1];
    wake.events = NOW_PLAYING_POLLIN;
    now_playing_send("start");
    while (__atomic_load_n(&now_playing_running, __ATOMIC_SEQ_CST)) {
        wake.revents = 0;
        int ready = poll(&wake, 1u, NOW_PLAYING_HEARTBEAT_MS);
        if (!__atomic_load_n(&now_playing_running, __ATOMIC_SEQ_CST))
            break;
        if (ready <= 0) {
            now_playing_send("heartbeat");
            continue;
        }
        uint8_t drained[32];
        while (recv(now_playing_wake[1], drained, sizeof(drained),
                    NOW_PLAYING_DONTWAIT) > 0)
            ;
        /* A load raises status, load and mixer events within a few
           milliseconds. One datagram for all of them. */
        usleep(10000u);
        if (__sync_lock_test_and_set(&now_playing_pending, 0u))
            now_playing_send("change");
    }
    return 0;
}

/* Lifecycle -------------------------------------------------------------------- */

static int now_playing_feature_configured(void)
{
    const char *setting = getenv("RX3_NOW_PLAYING");
    return setting && setting[0] == '1';
}

static void now_playing_feature_remove(void)
{
    __atomic_store_n(&now_playing_running, 0, __ATOMIC_SEQ_CST);
    if (now_playing_thread_started) {
        uint8_t wake = 1u;
        (void)send(now_playing_wake[0], &wake, sizeof(wake), NOW_PLAYING_DONTWAIT);
        pthread_join(now_playing_thread, 0);
        now_playing_thread_started = 0;
    }
    int detached = framework->detach_hook(&now_playing_mixer_hook);
    detached = framework->detach_hook(&now_playing_unload_hook) && detached;
    detached = framework->detach_hook(&now_playing_load_hook) && detached;
    detached = framework->detach_hook(&now_playing_status_hook) && detached;
    if (!detached) return; /* Live hooks still own their wake descriptors. */
    while (__atomic_load_n(&now_playing_callbacks, __ATOMIC_SEQ_CST)) usleep(1000u);
    if (framework->release_hook(&now_playing_mixer_hook))
        original_now_playing_mixer = 0;
    if (framework->release_hook(&now_playing_unload_hook))
        original_now_playing_unload = 0;
    if (framework->release_hook(&now_playing_load_hook))
        original_now_playing_load = 0;
    if (framework->release_hook(&now_playing_status_hook))
        original_now_playing_status = 0;
    for (unsigned int i = 0; i < 2u; i++) {
        if (now_playing_wake[i] >= 0)
            close(now_playing_wake[i]);
        now_playing_wake[i] = -1;
    }
    if (now_playing_socket >= 0)
        close(now_playing_socket);
    now_playing_socket = -1;
}

/* Returns 0 on any refusal. The core then calls remove(), which takes out
   whatever part of this had already been put in. */
static int now_playing_feature_install(void)
{
    if (memcmp((const void *)NOW_PLAYING_CURRENT_TRACK, now_playing_current_track_guard, 8) ||
        memcmp((const void *)NOW_PLAYING_PLAY_MODE, now_playing_play_mode_guard, 8) ||
        memcmp((const void *)NOW_PLAYING_PLAY_BPM, now_playing_play_bpm_guard, 8) ||
        memcmp((const void *)NOW_PLAYING_PLAY_TEMPO, now_playing_play_tempo_guard, 8) ||
        memcmp((const void *)NOW_PLAYING_ON_AIR, now_playing_on_air_guard, 8)) {
        framework->log_line("now playing refused: an accessor prologue differs");
        return 0;
    }
    if (socketpair(NOW_PLAYING_AF_UNIX, NOW_PLAYING_DGRAM | NOW_PLAYING_NONBLOCK, 0,
                   now_playing_wake)) {
        now_playing_wake[0] = now_playing_wake[1] = -1;
        framework->log_line("now playing refused: no wake-up socket");
        return 0;
    }
    now_playing_socket = socket(NOW_PLAYING_AF_INET, NOW_PLAYING_DGRAM, 0);
    int on = 1;
    if (now_playing_socket < 0 ||
        setsockopt(now_playing_socket, NOW_PLAYING_SOL_SOCKET, NOW_PLAYING_SO_BROADCAST,
                   &on, sizeof(on))) {
        framework->log_line("now playing refused: no broadcast socket");
        return 0;
    }

    original_now_playing_status = (now_playing_status_fn)framework->install_hook(
        &now_playing_status_hook, NOW_PLAYING_STATUS_UPDATED,
        now_playing_status_guard, (void *)hooked_now_playing_status);
    original_now_playing_load = (now_playing_load_fn)framework->install_hook(
        &now_playing_load_hook, NOW_PLAYING_LOAD_TRACK,
        now_playing_load_guard, (void *)hooked_now_playing_load);
    original_now_playing_unload = (now_playing_unload_fn)framework->install_hook(
        &now_playing_unload_hook, NOW_PLAYING_UNLOAD_RESULT,
        now_playing_unload_guard, (void *)hooked_now_playing_unload);
    original_now_playing_mixer = (now_playing_mixer_fn)framework->install_hook(
        &now_playing_mixer_hook, NOW_PLAYING_MIXER_ON_AIR_UPDATE,
        now_playing_mixer_guard, (void *)hooked_now_playing_mixer);
    if (!original_now_playing_status || !original_now_playing_load ||
        !original_now_playing_unload || !original_now_playing_mixer) {
        framework->log_line("now playing refused: a player event prologue differs");
        return 0;
    }

    __atomic_store_n(&now_playing_running, 1, __ATOMIC_SEQ_CST);
    if (pthread_create(&now_playing_thread, 0, now_playing_worker, 0)) {
        framework->log_line("now playing refused: the worker did not start");
        return 0;
    }
    now_playing_thread_started = 1;
    framework->log_line("now playing: deck state broadcast on UDP 50123 over the USB link");
    return 1;
}

#endif /* RX3_NOW_PLAYING_FEATURE_H */
