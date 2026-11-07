/* SPDX-License-Identifier: MPL-2.0
 * An RX3 TOOLKIT section at the end of Utility: VERSION, then one read-only
 * row per module of the build (ON/OFF and its revision). Layout after Evan
 * Purkhiser's PR #48: a copy of the stock spacer and GENERAL heading, then rows
 * shaped like VERSION No. Firmware 1.19 table; the table and all seven literal
 * references are guarded.
 */
#ifndef RX3_UTILITY_H
#define RX3_UTILITY_H

#define RX3_UTILITY_STOCK_TABLE 0x005140b8u
#define RX3_UTILITY_STOCK_COUNT 33u
#define RX3_UTILITY_ROW_BYTES 56u
#define RX3_UTILITY_SPACER 24u
#define RX3_UTILITY_HEADING 25u
#define RX3_UTILITY_VERSION_NO 32u
/* VERSION plus module rows; theme-white adds one more, the total stays < 64. */
#define RX3_UTILITY_MAX_ROWS 25u
#define RX3_UTILITY_LABEL 56u
#define RX3_UTILITY_VALUE 52u /* a toolkit version is up to 48 characters */

static const unsigned long rx3_utility_count_literals[6] = {
    0x0013c9a8u, 0x0013cbccu, 0x0013cd1cu,
    0x0013cf30u, 0x0013cfc4u, 0x0013d9ecu
};
struct rx3_utility_row {
    uint16_t label[RX3_UTILITY_LABEL];
    uint16_t value[RX3_UTILITY_VALUE];
};
static uint8_t *rx3_utility_table;
static uint32_t rx3_utility_bytes;
static struct rx3_utility_row rx3_utility_rows[RX3_UTILITY_MAX_ROWS];
static unsigned rx3_utility_row_count;
static uint16_t rx3_utility_heading[RX3_UTILITY_LABEL];

static void rx3_utility_copy_line(uint8_t *line, const uint16_t *text)
{
    unsigned length = 0;
    while (length < 255u && text[length]) length++;
    memset(line + 0x22u, 0, 512u);
    *(uint16_t *)(line + 0x20u) = (uint16_t)length;
    memcpy(line + 0x22u, text, length * 2u);
}

/* Same two line buffers as Util_SetLine_VersionNo at 0x0013abd0. Rows are
   found by label pointer, so a table copied by another module still works. */
static const uint16_t *rx3_utility_value(uint32_t label)
{
    for (unsigned i = 0; i < rx3_utility_row_count; i++)
        if (label == (uint32_t)(unsigned long)rx3_utility_rows[i].label)
            return rx3_utility_rows[i].value;
    return 0;
}

static int rx3_utility_set_line(uint32_t *row, uint8_t **lines)
{
    if (!row || !lines || !lines[0] || !lines[1]) return 0;
    static const uint16_t empty[] = {0};
    const uint16_t *value = rx3_utility_value(row[0]);
    rx3_utility_copy_line(lines[0], (const uint16_t *)(unsigned long)row[0]);
    rx3_utility_copy_line(lines[1], value ? value : empty);
    if (value) lines[0][3] |= 0x20u;
    return 0;
}

/* Copy printable ASCII after the indentation of a stock label, up to `stop` or
   the row separator; returns the number of source characters read. */
static unsigned rx3_utility_text(uint16_t *out, unsigned capacity,
                                 const uint16_t *indent_from, const char *text,
                                 char stop)
{
    unsigned length = 0, read = 0;
    while (indent_from && indent_from[length] == ' ' && length + 1u < capacity)
        out[length] = ' ', length++;
    while (text[read] && text[read] != stop && text[read] != ';') {
        if (text[read] >= 0x20 && text[read] <= 0x7e && length + 1u < capacity)
            out[length++] = (uint8_t)text[read];
        read++;
    }
    out[length] = 0;
    return read;
}

/* RX3_UTILITY_ROWS is "LABEL|VALUE;LABEL|VALUE", written by module-api.sh
   from the build's modules/utility file. */
static void rx3_utility_collect(const uint16_t *child_label)
{
    const char *version = getenv("RX3_TOOLKIT_VERSION");
    struct rx3_utility_row *row = &rx3_utility_rows[0];
    rx3_utility_text(row->label, RX3_UTILITY_LABEL, child_label, "VERSION", 0);
    rx3_utility_text(row->value, RX3_UTILITY_VALUE, 0,
                     version && version[0] ? version : "UNKNOWN", 0);
    rx3_utility_row_count = 1;
    const char *rows = getenv("RX3_UTILITY_ROWS");
    while (rows && *rows && rx3_utility_row_count < RX3_UTILITY_MAX_ROWS) {
        row = &rx3_utility_rows[rx3_utility_row_count];
        rows += rx3_utility_text(row->label, RX3_UTILITY_LABEL, child_label,
                                 rows, '|');
        if (*rows != '|') break;
        rows++;
        rows += rx3_utility_text(row->value, RX3_UTILITY_VALUE, 0, rows, ';');
        rx3_utility_row_count++;
        if (*rows == ';') rows++;
    }
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
    munmap(rx3_utility_table, rx3_utility_bytes);
    rx3_utility_table = 0;
}

static void rx3_utility_install(void)
{
    if (rx3_utility_table) return;
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

    const uint32_t *stock = (const uint32_t *)(RX3_UTILITY_STOCK_TABLE + 4u);
    const unsigned words = RX3_UTILITY_ROW_BYTES / 4u;
    const uint16_t *child_label = (const uint16_t *)(unsigned long)
        stock[RX3_UTILITY_VERSION_NO * words];
    rx3_utility_collect(child_label);
    rx3_utility_text(rx3_utility_heading, RX3_UTILITY_LABEL,
                     (const uint16_t *)(unsigned long)stock[RX3_UTILITY_HEADING * words],
                     "RX3 TOOLKIT", 0);

    uint32_t count = RX3_UTILITY_STOCK_COUNT + 2u + rx3_utility_row_count;
    uint32_t bytes = 4u + count * RX3_UTILITY_ROW_BYTES;
    uint8_t *table = mmap(0, bytes, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (table == MAP_FAILED) return;
    *(uint32_t *)table = count;
    uint8_t *row = table + 4u;
    memcpy(row, stock, RX3_UTILITY_STOCK_COUNT * RX3_UTILITY_ROW_BYTES);
    row += RX3_UTILITY_STOCK_COUNT * RX3_UTILITY_ROW_BYTES;
    memcpy(row, stock + RX3_UTILITY_SPACER * words, RX3_UTILITY_ROW_BYTES);
    row += RX3_UTILITY_ROW_BYTES;
    memcpy(row, stock + RX3_UTILITY_HEADING * words, RX3_UTILITY_ROW_BYTES);
    ((uint32_t *)row)[0] = (uint32_t)(unsigned long)rx3_utility_heading;
    ((uint32_t *)row)[7] = (uint32_t)(unsigned long)rx3_utility_set_line;
    for (unsigned i = 0; i < rx3_utility_row_count; i++) {
        row += RX3_UTILITY_ROW_BYTES;
        memcpy(row, stock + RX3_UTILITY_VERSION_NO * words, RX3_UTILITY_ROW_BYTES);
        ((uint32_t *)row)[0] = (uint32_t)(unsigned long)rx3_utility_rows[i].label;
        ((uint32_t *)row)[7] = (uint32_t)(unsigned long)rx3_utility_set_line;
    }
    rx3_utility_table = table;
    rx3_utility_bytes = bytes;
    uint32_t rows = (uint32_t)(unsigned long)(table + 4u);
    uint32_t table_count = (uint32_t)(unsigned long)table;
    int failed = !rx3_utility_write_literal(0x0013d9e4u,
                                             RX3_UTILITY_STOCK_TABLE + 4u, rows);
    for (unsigned i = 0; !failed && i < 6u; i++)
        failed = !rx3_utility_write_literal(rx3_utility_count_literals[i],
                                             RX3_UTILITY_STOCK_TABLE, table_count);
    if (failed) rx3_utility_remove();
    else log_line("toolkit: RX3 TOOLKIT section installed in Utility");
}

#endif /* RX3_UTILITY_H */
