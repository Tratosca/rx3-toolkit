/* SPDX-License-Identifier: MPL-2.0
 * The toolkit identity is a read-only native Utility item, after VERSION No.
 * Firmware 1.19 only. The table and all seven literal references are guarded.
 */
#ifndef RX3_UTILITY_H
#define RX3_UTILITY_H

#define RX3_UTILITY_STOCK_TABLE 0x005140b8u
#define RX3_UTILITY_STOCK_COUNT 33u
#define RX3_UTILITY_ROW_BYTES 56u
#define RX3_UTILITY_TABLE_BYTES (4u + (RX3_UTILITY_STOCK_COUNT + 1u) * RX3_UTILITY_ROW_BYTES)
static const unsigned long rx3_utility_count_literals[6] = {
    0x0013c9a8u, 0x0013cbccu, 0x0013cd1cu,
    0x0013cf30u, 0x0013cfc4u, 0x0013d9ecu
};
static uint8_t *rx3_utility_table;
static uint16_t rx3_utility_version[48];
static const uint16_t rx3_utility_title[] = {
    ' ', ' ', ' ', ' ', ' ', ' ', 'R', 'X', '3', ' ', 'T', 'O', 'O',
    'L', 'K', 'I', 'T', 0
};

static void rx3_utility_copy_line(uint8_t *line, const uint16_t *text)
{
    unsigned length = 0;
    while (length < 255u && text[length]) length++;
    memset(line + 0x22u, 0, 512u);
    *(uint16_t *)(line + 0x20u) = (uint16_t)length;
    memcpy(line + 0x22u, text, length * 2u);
}

/* Same two line buffers as Util_SetLine_VersionNo at 0x0013abd0. */
static int rx3_utility_set_line(uint32_t *row, uint8_t **lines)
{
    if (!row || !lines || !lines[0] || !lines[1]) return 0;
    rx3_utility_copy_line(lines[0], (const uint16_t *)(unsigned long)row[0]);
    rx3_utility_copy_line(lines[1], rx3_utility_version);
    lines[0][3] |= 0x20u;
    return 0;
}

static int rx3_utility_write_literal(unsigned long address, uint32_t expected,
                                     uint32_t wanted)
{
    if (*(const uint32_t *)address == wanted) return 1;
    return rx3_write_guarded(address, &expected, &wanted, sizeof(wanted));
}

static void rx3_utility_remove(void)
{
    if (!rx3_utility_table) return;
    uint32_t count = (uint32_t)(unsigned long)rx3_utility_table;
    uint32_t rows = count + 4u;
    int failed = !rx3_utility_write_literal(0x0013d9e4u, rows,
                                             RX3_UTILITY_STOCK_TABLE + 4u);
    for (unsigned i = 0; i < 6u; i++)
        failed |= !rx3_utility_write_literal(rx3_utility_count_literals[i], count,
                                              RX3_UTILITY_STOCK_TABLE);
    if (failed) {
        log_line("toolkit: Utility table retained after restore failure");
        return;
    }
    munmap(rx3_utility_table, RX3_UTILITY_TABLE_BYTES);
    rx3_utility_table = 0;
}

static void rx3_utility_install(void)
{
    if (rx3_utility_table) return;
    const char *version = getenv("RX3_TOOLKIT_VERSION");
    unsigned length = 0;
    if (version) {
        while (length + 1u < sizeof(rx3_utility_version) /
                              sizeof(rx3_utility_version[0]) &&
               version[length] >= 0x20 && version[length] <= 0x7e) {
            rx3_utility_version[length] = (uint8_t)version[length];
            length++;
        }
    }
    if (!length) {
        static const uint16_t unknown[] = {'U','N','K','N','O','W','N',0};
        memcpy(rx3_utility_version, unknown, sizeof(unknown));
    } else rx3_utility_version[length] = 0;

    if (*(const uint32_t *)RX3_UTILITY_STOCK_TABLE != RX3_UTILITY_STOCK_COUNT ||
        *(const uint32_t *)0x0013d9e4u != RX3_UTILITY_STOCK_TABLE + 4u ||
        *(const uint32_t *)0x005147d8u != 0x0013abd0u ||
        *(const uint32_t *)0x005147bcu != 0x0043cc08u) {
        log_line("toolkit: Utility table guard rejected");
        return;
    }
    for (unsigned i = 0; i < 6u; i++)
        if (*(const uint32_t *)rx3_utility_count_literals[i] != RX3_UTILITY_STOCK_TABLE)
            return;

    uint8_t *table = mmap(0, RX3_UTILITY_TABLE_BYTES, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (table == MAP_FAILED) return;
    memcpy(table + 4u, (const void *)(RX3_UTILITY_STOCK_TABLE + 4u),
           RX3_UTILITY_STOCK_COUNT * RX3_UTILITY_ROW_BYTES);
    *(uint32_t *)table = RX3_UTILITY_STOCK_COUNT + 1u;
    uint32_t *row = (uint32_t *)(table + 4u + RX3_UTILITY_STOCK_COUNT *
                                RX3_UTILITY_ROW_BYTES);
    memcpy(row, (const void *)0x005147bcu, RX3_UTILITY_ROW_BYTES);
    row[0] = (uint32_t)(unsigned long)rx3_utility_title;
    row[7] = (uint32_t)(unsigned long)rx3_utility_set_line;
    rx3_utility_table = table;
    uint32_t rows = (uint32_t)(unsigned long)(table + 4u);
    uint32_t count = (uint32_t)(unsigned long)table;
    int failed = !rx3_utility_write_literal(0x0013d9e4u,
                                             RX3_UTILITY_STOCK_TABLE + 4u, rows);
    for (unsigned i = 0; !failed && i < 6u; i++)
        failed = !rx3_utility_write_literal(rx3_utility_count_literals[i],
                                             RX3_UTILITY_STOCK_TABLE, count);
    if (failed) rx3_utility_remove();
    else log_line("toolkit: version row installed in Utility");
}

#endif /* RX3_UTILITY_H */
