/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_THEME_CONVERSION_H
#define RX3_THEME_CONVERSION_H
/* One render-owned job. Both classification and conversion spend this budget;
   records never point into a partially filled allocation. */
#define THEME_PIXEL_BUDGET 8192u
#define THEME_JOB_BUDGET 4u
static uint8_t theme_requested[(STOCK_IMAGE_COUNT + 7u) / 8u];
static unsigned int theme_request_cursor;
static unsigned long theme_memory_kb;
static uint64_t theme_memory_next_us;
static struct {
    const uint16_t *source;
    unsigned int image, count, cursor, opaque, vivid, classifying;
    int light, artwork;
} theme_job;

/* Watcher only: no renderer opens /proc or allocates the image arena. The
   allocation remains resident, including during theme changes and shutdown. */
static void theme_prepare_conversion(void)
{
    if (!theme_enabled || !framework->images->variants_ready()) return;
    uint64_t now = monotonic_enough_us();
    if (now < theme_memory_next_us) return;
    theme_memory_next_us = now + 250000u;
    const struct rx3_memory_service *memory = framework->memory;
    unsigned long available = memory->available_kb();
    __atomic_store_n(&theme_memory_kb, available, __ATOMIC_SEQ_CST);
    if (__atomic_load_n(&theme_arena, __ATOMIC_SEQ_CST) || available < THEME_ARENA_FLOOR_KB) return;
    /* The same floor through the shared ledger: the arena itself is inside
       it, and allocations other modules have in flight are counted. */
    if (!memory->reserve(&theme_enabled, THEME_ARENA_BYTES,
                         THEME_ARENA_FLOOR_KB - THEME_ARENA_BYTES / 1024u)) return;
    void *arena = mmap(0, THEME_ARENA_BYTES, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (arena == MAP_FAILED) {
        memory->abandon(&theme_enabled, THEME_ARENA_BYTES);
        return;
    }
    memory->settle(&theme_enabled, THEME_ARENA_BYTES);
    __atomic_store_n(&theme_arena, arena, __ATOMIC_SEQ_CST);
}

/* Render thread, from the core just before a stock image is drawn. Images the
   core has replaced never reach the conversion: native_image() refuses them. */
static void theme_remap_image(unsigned int image)
{
    if ((!theme_light_active() && !theme_global_dark) ||
        !framework->images->variants_ready() || image >= STOCK_IMAGE_COUNT) return;
    unsigned int bit = 1u << (image & 7u);
    if (!(theme_id_done[image >> 3u] & bit)) theme_requested[image >> 3u] |= bit;
}

static void theme_publish_conversion(unsigned int image, const uint16_t *pixels)
{
    (void)framework->images->publish_variant(image, pixels);
    unsigned int bit = 1u << (image & 7u);
    theme_id_done[image >> 3u] |= bit;
    theme_requested[image >> 3u] &= ~bit;
}

/* At most one full scan per admission; the number of admissions is bounded. */
static int theme_next_request(void)
{
    for (unsigned int n = 0; n < STOCK_IMAGE_COUNT; n++) {
        unsigned int image = theme_request_cursor++;
        if (theme_request_cursor == STOCK_IMAGE_COUNT) theme_request_cursor = 0;
        if (theme_requested[image >> 3u] & (1u << (image & 7u))) return (int)image;
    }
    return -1;
}

static int theme_begin_conversion(unsigned int image)
{
    struct rx3_native_image native;
    int known = framework->images->native_image(image, &native);
    uint64_t bytes = known ? (uint64_t)native.width * native.height * 2u : 0u;
    const uint16_t *source = known ? native.pixels : 0;
    if (!known || (native.format != THEME_FORMAT_RGB565 &&
                   native.format != THEME_FORMAT_RGB565_KEYED) || native.paletted ||
        !native.width || !native.height || bytes > THEME_IMAGE_MAX_BYTES) {
        theme_id_done[image >> 3u] |= 1u << (image & 7u);
        theme_requested[image >> 3u] &= ~(1u << (image & 7u));
        return 0;
    }
    for (unsigned int i = 0; i < theme_seen_count; i++) {
        if (theme_seen_source[i] == source) {
            theme_publish_conversion(image, theme_seen_pixels[i]);
            return 1;
        }
    }
    if (bytes > THEME_ARENA_BYTES - theme_arena_used) {
        theme_id_done[image >> 3u] |= 1u << (image & 7u);
        theme_requested[image >> 3u] &= ~(1u << (image & 7u));
        return 0;
    }
    memset(&theme_job, 0, sizeof(theme_job));
    theme_job.source = source;theme_job.image = image;
    theme_job.count = native.width * native.height;
    theme_job.light = theme_light_active() != 0;
    theme_job.classifying = theme_job.light;
    return 0;
}

static int theme_run_conversions(void)
{
    uint8_t *arena = __atomic_load_n(&theme_arena, __ATOMIC_SEQ_CST);
    if ((!theme_light_active() && !theme_global_dark) ||
        !arena || !framework->images->variants_ready() ||
        __atomic_load_n(&theme_memory_kb, __ATOMIC_SEQ_CST) < THEME_CONVERT_RESERVE_KB) return 0;
    /* A partial result belongs to the mode it was started in. Its source stays
       queued, and its uncommitted arena space can be reused on a mode change. */
    if (theme_job.source) {
        struct rx3_native_image native;
        if (theme_job.light != (theme_light_active() != 0) ||
            !framework->images->native_image(theme_job.image, &native) ||
            theme_job.source != native.pixels ||
            theme_job.count != native.width * native.height)
            memset(&theme_job, 0, sizeof(theme_job));
    }
    unsigned int remaining = THEME_PIXEL_BUDGET;
    int changed = 0;
    for (unsigned int jobs = 0; jobs < THEME_JOB_BUDGET && remaining; jobs++) {
        if (!theme_job.source) {
            int image = theme_next_request();
            if (image < 0) break;
            changed |= theme_begin_conversion((unsigned int)image);
            if (!theme_job.source) continue;
        }
        if (theme_job.classifying) {
            while (remaining && theme_job.cursor < theme_job.count) {
                uint16_t pixel = theme_job.source[theme_job.cursor++];remaining--;
                if (pixel == COLOUR_KEY) continue;
                unsigned int red, green, blue;
                theme_unpack(pixel, &red, &green, &blue);
                theme_job.opaque++;
                if (theme_spread(red, green, blue) > THEME_VIVID_SPREAD) theme_job.vivid++;
            }
            if (theme_job.cursor != theme_job.count) break;
            theme_job.artwork = theme_job.opaque &&
                theme_job.opaque * THEME_ARTWORK_PERCENT <= theme_job.vivid * 100u;
            theme_job.classifying = 0;theme_job.cursor = 0;
        }
        uint16_t *converted = (void *)(arena + theme_arena_used);
        while (remaining && theme_job.cursor < theme_job.count) {
            unsigned int i = theme_job.cursor++;remaining--;
            converted[i] = theme_job.light ?
                theme_pixel_light_for_image(theme_job.image, theme_job.source[i], theme_job.artwork) :
                theme_pixel_dark(theme_job.source[i]);
        }
        if (theme_job.cursor != theme_job.count) break;
        theme_arena_used += theme_job.count * 2u;
        if (theme_seen_count < 4096u) {
            theme_seen_source[theme_seen_count] = theme_job.source;
            theme_seen_pixels[theme_seen_count++] = converted;
        }
        theme_publish_conversion(theme_job.image, converted);
        theme_job.source = 0;changed = 1;
    }
    return changed;
}
#endif
