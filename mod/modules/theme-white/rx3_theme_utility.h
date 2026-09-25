/* SPDX-License-Identifier: MPL-2.0
 * Insert DISPLAY MODE into the guarded native Utility table.
 */
#ifndef RX3_THEME_UTILITY_H
#define RX3_THEME_UTILITY_H

static uint8_t *utility_theme_table;
static const unsigned long utility_count_literals[6] = {
    0x0013c9a8, 0x0013cbcc, 0x0013cd1c,
    0x0013cf30, 0x0013cfc4, 0x0013d9ec
};
static const uint16_t utility_theme_title[] = {
    ' ', ' ', ' ', ' ', ' ', ' ', 'D', 'I', 'S', 'P', 'L', 'A', 'Y',
    ' ', 'M', 'O', 'D', 'E', 0
};
static const uint16_t utility_dark[] = {'D', 'A', 'R', 'K', 0};
static const uint16_t utility_light[] = {'L', 'I', 'G', 'H', 'T', 0};
static const uint16_t *const utility_theme_choices[] = {utility_dark, utility_light};

static void utility_copy_line(uint8_t *line, const uint16_t *text)
{
    uint16_t length = 0;
    while (length < 255u && text[length]) length++;
    memset(line + 0x22u, 0, 512u);
    memcpy(line + 0x20u, &length, 2u);
    memcpy(line + 0x22u, text, length * 2u);
}

static int utility_theme_set_line(uint32_t *row, uint8_t **lines)
{
    if (!row || !lines || !lines[0] || !lines[1]) return 0;
    utility_copy_line(lines[0], (const uint16_t *)(unsigned long)row[0]);
    unsigned int choice = row[4];
    if (choice >= row[2]) {
        choice = theme_light_active != 0;
        row[3] = choice;
    } else if (choice != (unsigned int)theme_light_active) {
        __sync_bool_compare_and_swap(&theme_toggle_pending, 0, 2);
    }
    const uint16_t *const *choices = (const uint16_t *const *)(unsigned long)row[1];
    utility_copy_line(lines[1], choices[choice]);
    return 0;
}

/* Utility can commit a choice without redrawing its value line. Consume that
   field too, then leave the actual mode change to the UI draw callbacks. */
static void utility_poll_theme_row(void)
{
    if (!utility_theme_table) return;
    uint32_t *row = (uint32_t *)(utility_theme_table + 0x624u);
    unsigned int choice = __atomic_load_n(&row[4], __ATOMIC_SEQ_CST);
    if (choice >= row[2]) return;
    __atomic_store_n(&row[4], 0xffffffffu, __ATOMIC_SEQ_CST);
    row[3] = choice != 0u;
    if ((choice != 0u) != (theme_light_active != 0))
        __sync_bool_compare_and_swap(&theme_toggle_pending, 0, 2);
}

static void utility_remove_theme_row(void)
{
    if (!utility_theme_table) return;
    uint32_t rows = 0x005140bcu, count = 0x005140b8u;
    int failed = write_code(0x0013d9e4, &rows, 4u);
    for (unsigned int i = 0; i < 6u; i++)
        failed |= write_code(utility_count_literals[i], &count, 4u);
    /* A failed restoration can leave the firmware pointing at this allocation. */
    if (!failed) {
        munmap(utility_theme_table, 0x774u);
        utility_theme_table = 0;
    } else {
        log_line("light theme: Utility table retained after restore failure");
    }
}

static void utility_install_theme_row(void)
{
    if (utility_theme_table) return;
    if (*(const uint32_t *)0x005140b8 != 33u ||
        *(const uint32_t *)0x0013d9e4 != 0x005140bcu ||
        *(const uint32_t *)0x0051410c != 0x0013a924u ||
        *(const uint32_t *)0x00514118 != 0x0013c360u ||
        *(const uint32_t *)0x00514128 != 0x0013a99cu ||
        !*(const uint32_t *)0x005146a8 ||
        *(const uint32_t *)0x005146ac < 2u)
        return;
    for (unsigned int i = 0; i < 6u; i++)
        if (*(const uint32_t *)utility_count_literals[i] != 0x005140b8u)
            return;
    uint8_t *table = mmap(0, 0x774u, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (table == MAP_FAILED) return;
    memcpy(table + 4u, (const void *)0x005140bc, 0x620u);
    memcpy(table + 0x65cu, (const void *)0x005146dc, 0x118u);
    *(uint32_t *)table = 34u;
    uint32_t row[14] = {
        (uint32_t)(unsigned long)utility_theme_title,
        (uint32_t)(unsigned long)utility_theme_choices,
        2u, 0xffffffffu, 0xffffffffu, 1u, 0x0013a924u,
        (uint32_t)(unsigned long)utility_theme_set_line,
        0x0013a928u, 0x0013c360u, 0x0013a958u, 0x0013a984u,
        0x0013a98cu, 0x0013a99cu
    };
    memcpy(table + 0x624u, row, sizeof(row));
    uint32_t rows = (uint32_t)(unsigned long)(table + 4u);
    uint32_t count = (uint32_t)(unsigned long)table;
    utility_theme_table = table;
    int failed = write_code(0x0013d9e4, &rows, 4u);
    for (unsigned int i = 0; !failed && i < 6u; i++)
        failed = write_code(utility_count_literals[i], &count, 4u);
    if (failed) utility_remove_theme_row();
    else log_line("light theme: DISPLAY MODE installed in Utility");
}

#endif /* RX3_THEME_UTILITY_H */
