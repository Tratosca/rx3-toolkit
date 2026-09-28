/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_LOGO_GEOMETRY_H
#define RX3_LOGO_GEOMETRY_H
#define LOGO_PLACEMENT ((unsigned long)0x005318a4)
static uint32_t logo_saved_position, logo_written_position;
static int logo_position_owned;
static uint32_t logo_center_position(uint32_t width, uint32_t height)
{
    uint32_t x = width < 1272u ? 636u - width / 2u : 0u;
    uint32_t y = height < 320u ? 160u - height / 2u : 0u;
    return x | (y << 16u);
}
static int logo_place(uint32_t *record, uint32_t width, uint32_t height)
{
    /* The RW player record contains position followed by image ID. */
    static const uint8_t logo_placement_guard[8] = {
        0x8b, 0x01, 0xb2, 0x00, 0x3f, 0x06, 0x00, 0x00
    };
    if (memcmp(record, logo_placement_guard, sizeof(logo_placement_guard)))
        return 0;
    logo_saved_position = record[0];
    logo_written_position = logo_center_position(width, height);
    __atomic_store_n(record, logo_written_position, __ATOMIC_SEQ_CST);
    logo_position_owned = 1;
    return 1;
}
static void logo_restore_position(uint32_t *record)
{
    if (logo_position_owned && record[1] == LOGO_IMAGE_INDEX) {
        uint32_t expected = logo_written_position;
        (void)__atomic_compare_exchange_n(record, &expected, logo_saved_position,
                                          0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
    }
    logo_position_owned = 0;
}
#endif
