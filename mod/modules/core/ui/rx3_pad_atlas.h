/* SPDX-License-Identifier: MPL-2.0
 *
 * The pad row's typeface, as artwork.
 *
 * The row used to letter its controls by cloning one of the player's own text
 * objects and rewriting the string, on the assumption that the clone carried
 * the face. It does not, and it cannot: the pad subtree issues no text draw at
 * all, because Pioneer's own pad labels are images, so there is never a label
 * there to clone and the controls fall back to the header glyph at twice the
 * size they want.
 *
 * So a label is artwork here too, one image per character, composed at draw
 * time. One image per whole caption was tried first and cannot work: the KEY
 * centre shows a key and a move, `3A (+1)`, which is twenty-four keys times
 * twenty-five shifts, and the sample row shows a volume.
 *
 * The cells are keyed rather than opaque, and the file says which. Ink
 * overflows its advance on A, W, V, X, Y and the solidus, so opaque cells laid
 * end to end would have each one erase the last column of the letter before it.
 * Only pixels the ink never touched carry the key; an anti-aliased edge is a
 * blend of ink and the ground it was drawn on, and it is kept, because it is
 * already right. That is why there is a set of glyphs per ground.
 *
 * The grounds travel in the file with the glyphs. Nothing here writes down a
 * pad colour: the artwork was drawn on a ground, and whatever paints underneath
 * it reads that same ground back out of the file, so the two cannot drift.
 */

#ifndef RX3_PAD_ATLAS_H
#define RX3_PAD_ATLAS_H

#define RX3_PAD_ATLAS_PATH       "/root/pdj/rx3-glyph-atlas-dark.rgb565"
#define RX3_PAD_ATLAS_LIGHT_PATH "/root/pdj/rx3-glyph-atlas-light.rgb565"

/* Private image ids for the glyphs, past the tab strip's four. The reserve is
   larger than the repertoire so a character added to the artwork does not move
   the lookup bound, which is a guarded byte patch on the player and the one
   number here that is expensive to change. */
#define RX3_PAD_GLYPH_IMAGE_BASE 0x1610u
#define RX3_PAD_GLYPH_IMAGE_MAX  150u

/* Grounds, in the order the artwork stores them. These name a ground, not a
   widget state: the atlas never learns what a button is. */
#define RX3_PAD_INK_INACTIVE 0u
#define RX3_PAD_INK_PRESSED  1u
#define RX3_PAD_INK_SELECTED 2u

#define RX3_PAD_ATLAS_MAX_BYTES (512u * 1024u)

struct __attribute__((packed)) rx3_pad_atlas_header {
    char magic[8];
    uint16_t cell_height;
    uint16_t glyph_count;
    uint16_t state_count;
    uint16_t colour_key;
    uint16_t space_advance;
    uint16_t ink_left;
};

struct __attribute__((packed)) rx3_pad_glyph {
    uint16_t codepoint;
    uint16_t width;
    uint16_t advance;
    uint16_t reserved;
    uint32_t offset;
};

static uint8_t *pad_atlas_blob;
static uint8_t *pad_atlas_light_blob;
static struct rx3_pad_atlas_header pad_atlas;
static const struct rx3_pad_glyph *pad_atlas_glyphs;
static unsigned int pad_atlas_ready;
/* Codepoint to glyph index, built once, so nothing searches on the draw path. */
static signed char pad_atlas_index[128];
static uint32_t pad_atlas_ground[4];

static unsigned int pad_atlas_image_count(void)
{
    return (unsigned int)pad_atlas.glyph_count * pad_atlas.state_count;
}

/* Read one atlas file whole. Returns the mapping, or zero. */
static uint8_t *pad_atlas_read(const char *path, unsigned int *length)
{
    int fd = open(path, O_RDONLY);
    long size;
    uint8_t *buffer;

    if (fd < 0)
        return 0;
    size = lseek(fd, 0, SEEK_END);
    if (size <= (long)sizeof(struct rx3_pad_atlas_header) ||
        size > (long)RX3_PAD_ATLAS_MAX_BYTES ||
        lseek(fd, 0, SEEK_SET) != 0) {
        close(fd);
        return 0;
    }
    buffer = mmap(0, (size_t)size, PROT_READ | PROT_WRITE,
                  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (buffer == MAP_FAILED) {
        close(fd);
        return 0;
    }
    if (read_exactly(fd, buffer, (size_t)size)) {
        close(fd);
        munmap(buffer, (size_t)size);
        return 0;
    }
    close(fd);
    *length = (unsigned int)size;
    return buffer;
}

/* Does the file describe itself consistently? A short or lying atlas would
   otherwise point image records at addresses past the end of the mapping. */
static int pad_atlas_is_sound(const uint8_t *blob, unsigned int length)
{
    const struct rx3_pad_atlas_header *head = (const void *)blob;
    static const char magic[8] = {'R','X','3','G','L','Y','F','1'};
    const struct rx3_pad_glyph *glyphs;
    unsigned int i, directory, states;

    if (length < sizeof(*head) || memcmp(head->magic, magic, 8))
        return 0;
    states = head->state_count;
    if (!head->cell_height || !head->glyph_count || !states || states > 4u)
        return 0;
    if ((unsigned int)head->glyph_count * states > RX3_PAD_GLYPH_IMAGE_MAX)
        return 0;
    directory = (unsigned int)sizeof(*head) + states * 4u;
    if (length < directory +
        (unsigned int)head->glyph_count * sizeof(struct rx3_pad_glyph))
        return 0;
    glyphs = (const void *)(blob + directory);
    for (i = 0; i < head->glyph_count; i++) {
        unsigned int cell = (unsigned int)glyphs[i].width * head->cell_height * 2u;
        if (!glyphs[i].width || glyphs[i].codepoint >= 128u)
            return 0;
        if (glyphs[i].offset > length || cell * states > length - glyphs[i].offset)
            return 0;
    }
    return 1;
}

static void pad_atlas_load(void)
{
    unsigned int length = 0, i;

    if (pad_atlas_ready)
        return;
    pad_atlas_blob = pad_atlas_read(RX3_PAD_ATLAS_PATH, &length);
    if (!pad_atlas_blob) {
        log_line("warning: pad glyph atlas missing; the row keeps stock text");
        return;
    }
    if (!pad_atlas_is_sound(pad_atlas_blob, length)) {
        log_line("warning: pad glyph atlas is not one this core can read");
        munmap(pad_atlas_blob, length);
        pad_atlas_blob = 0;
        return;
    }
    memcpy(&pad_atlas, pad_atlas_blob, sizeof(pad_atlas));
    for (i = 0; i < pad_atlas.state_count && i < 4u; i++)
        memcpy(&pad_atlas_ground[i],
               pad_atlas_blob + sizeof(pad_atlas) + i * 4u, 4u);
    pad_atlas_glyphs = (const void *)(pad_atlas_blob + sizeof(pad_atlas) +
                                      pad_atlas.state_count * 4u);
    for (i = 0; i < 128u; i++)
        pad_atlas_index[i] = -1;
    for (i = 0; i < pad_atlas.glyph_count; i++)
        pad_atlas_index[pad_atlas_glyphs[i].codepoint] = (signed char)i;

    /* The light set is optional and shares the dark set's image ids: the theme
       swaps the whole table, so a record is repointed rather than added. */
    length = 0;
    pad_atlas_light_blob = pad_atlas_read(RX3_PAD_ATLAS_LIGHT_PATH, &length);
    if (pad_atlas_light_blob && !pad_atlas_is_sound(pad_atlas_light_blob, length)) {
        munmap(pad_atlas_light_blob, length);
        pad_atlas_light_blob = 0;
    }
    pad_atlas_ready = 1u;
    log_number("pad glyph atlas loaded, glyphs = ", pad_atlas.glyph_count);
    log_number("  grounds per glyph = ", pad_atlas.state_count);
    log_number("  light set present = ", pad_atlas_light_blob ? 1u : 0u);
    /* The ids the artwork will occupy. A row that comes up blank on a deck is
       otherwise silent, and this line is what says whether the artwork asked
       for more ids than the launch patch admits. */
    log_number("  private image ids = ", pad_atlas_image_count());
    log_number("  last id = ",
               RX3_PAD_GLYPH_IMAGE_BASE + pad_atlas_image_count() - 1u);
}

/* The row is upper case; fold what a panel hands over rather than shipping a
   second set of glyphs for letters no control uses. */
static int pad_atlas_slot(unsigned int codepoint)
{
    if (codepoint >= 'a' && codepoint <= 'z')
        codepoint -= 32u;
    if (codepoint >= 128u)
        return -1;
    return pad_atlas_index[codepoint];
}

/* The cell a character is drawn from. The painter wants this and the advance
   and nothing else, so the directory stays private to this file. */
static unsigned int pad_atlas_cell_width(unsigned int codepoint)
{
    int slot = pad_atlas_slot(codepoint);
    return slot < 0 ? 0u : pad_atlas_glyphs[slot].width;
}

static unsigned int pad_atlas_advance(unsigned int codepoint)
{
    int slot;
    if (codepoint == ' ')
        return pad_atlas.space_advance;
    slot = pad_atlas_slot(codepoint);
    return slot < 0 ? 0u : pad_atlas_glyphs[slot].advance;
}

static unsigned int pad_atlas_text_width(const uint16_t *text)
{
    unsigned int width = 0;
    if (!text)
        return 0;
    while (*text)
        width += pad_atlas_advance(*text++);
    return width;
}

static uint32_t pad_atlas_ground_colour(unsigned int ink)
{
    if (ink >= pad_atlas.state_count) ink=RX3_PAD_INK_INACTIVE;
    if (theme_light_active && pad_atlas_light_blob) {
        uint32_t colour;
        memcpy(&colour,pad_atlas_light_blob+sizeof(struct rx3_pad_atlas_header)+ink*4u,4u);
        return colour;
    }
    return pad_atlas_ground[ink];
}

/* One record per glyph per ground, cloned from the same donor the tab strip
   uses so every field this does not write is one the renderer already accepts.
   `pixels` selects which artwork the records point at, which is how the light
   table carries the same ids with a different face. */
static void pad_atlas_install_records(uint8_t *table, const uint8_t *blob)
{
    const struct rx3_pad_atlas_header *head = (const void *)blob;
    const struct rx3_pad_glyph *glyphs =
        (const void *)(blob + sizeof(*head) + head->state_count * 4u);
    unsigned int i, state;

    for (i = 0; i < head->glyph_count; i++) {
        unsigned int cell = (unsigned int)glyphs[i].width * head->cell_height * 2u;
        for (state = 0; state < head->state_count; state++) {
            unsigned int id = RX3_PAD_GLYPH_IMAGE_BASE +
                              i * head->state_count + state;
            uint8_t *record = table + id * 44u;
            uint16_t width = glyphs[i].width, height = head->cell_height;
            uint32_t at = (uint32_t)(unsigned long)
                              (blob + glyphs[i].offset + state * cell) -
                          (uint32_t)(unsigned long)table;
            /* Reserve the selected slot for contrasting text: use the other
               theme's keyed pressed glyph, retaining the same image IDs. */
            const uint8_t *opposite = blob == pad_atlas_blob ? pad_atlas_light_blob : pad_atlas_blob;
            if (state == RX3_PAD_INK_SELECTED && opposite) {
                const struct rx3_pad_atlas_header *other=(const void *)opposite;
                const struct rx3_pad_glyph *entries=(const void *)(opposite+sizeof(*other)+other->state_count*4u);
                if (i < other->glyph_count && other->cell_height == height &&
                    other->state_count > RX3_PAD_INK_PRESSED &&
                    entries[i].codepoint == glyphs[i].codepoint && entries[i].width == width)
                    at=(uint32_t)(unsigned long)(opposite+entries[i].offset+cell*RX3_PAD_INK_PRESSED)
                        -(uint32_t)(unsigned long)table;
            }
            uint32_t no_palette = 0u;
            memcpy(record, table + 0x1598u * 44u, 44u);
            memcpy(record + 4u, &width, sizeof(width));
            memcpy(record + 6u, &height, sizeof(height));
            /* 2 is the variant that honours the colour key, as the logo uses;
               an atlas built with --opaque says so and takes 1. */
            record[0x18u] = head->colour_key ? 2u : 1u;
            record[0x19u] = 0u;
            memcpy(record + 0x20u, &at, sizeof(at));
            memcpy(record + 0x24u, &no_palette, sizeof(no_palette));
        }
    }
}

static unsigned int pad_atlas_image_id(unsigned int codepoint, unsigned int ink)
{
    int slot = pad_atlas_slot(codepoint);
    if (slot < 0)
        return 0u;
    if (ink >= pad_atlas.state_count)
        ink = RX3_PAD_INK_INACTIVE;
    return RX3_PAD_GLYPH_IMAGE_BASE +
           (unsigned int)slot * pad_atlas.state_count + ink;
}

#endif /* RX3_PAD_ATLAS_H */
