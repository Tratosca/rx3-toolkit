/* SPDX-License-Identifier: MPL-2.0
 * An RX3 TOOLKIT section at the end of Utility: VERSION, then one row per
 * module of the build (ON/OFF and its revision), each followed by the options
 * its manifest declares. Layout after Evan Purkhiser's PR #48: a copy of the
 * stock spacer and GENERAL heading, then rows shaped like VERSION No., or like
 * the stock choice rows DISPLAY MODE already uses when the DJ can change one.
 * Firmware 1.19 table; the table and all seven literal references are guarded.
 *
 * A choice committed in Utility is picked up by the core's watcher thread.
 * A live option is served at once to its module through value(); every change
 * is left in RAM (RX3_SETTINGS_PENDING) two seconds after the last one, for
 * the shell to merge into RX3_RUNTIME/settings.cfg on the drive.
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
#define RX3_UTILITY_CHOICES 12u
#define RX3_UTILITY_WORD 16u
#define RX3_UTILITY_CHOICE 24u
#define RX3_UTILITY_KEY 48u
#define RX3_UTILITY_NONE 0xffffffffu
#define RX3_UTILITY_QUIET_US 2000000u
#ifndef RX3_SETTINGS_PENDING
#define RX3_SETTINGS_PENDING "/tmp/rx3-settings.pending"
#endif

static const unsigned long rx3_utility_count_literals[6] = {
    0x0013c9a8u, 0x0013cbccu, 0x0013cd1cu,
    0x0013cf30u, 0x0013cfc4u, 0x0013d9ecu
};
struct rx3_utility_row {
    uint16_t label[RX3_UTILITY_LABEL];
    uint16_t value[RX3_UTILITY_VALUE]; /* read-only text, or the note shown after a choice */
    char key[RX3_UTILITY_KEY];         /* empty for a read-only row */
    unsigned int live, count, running, touched;
    unsigned int chosen;               /* atomic: written by the watcher */
    char words[RX3_UTILITY_CHOICES][RX3_UTILITY_WORD];
    uint16_t choices[RX3_UTILITY_CHOICES][RX3_UTILITY_CHOICE];
    uint32_t choice_list[RX3_UTILITY_CHOICES]; /* what the firmware reads */
    uint16_t shown[RX3_UTILITY_VALUE];         /* drawn by the Utility thread only */
};
static uint8_t *rx3_utility_table;
static uint32_t rx3_utility_bytes;
static struct rx3_utility_row rx3_utility_rows[RX3_UTILITY_MAX_ROWS];
static unsigned rx3_utility_row_count;
static uint16_t rx3_utility_heading[RX3_UTILITY_LABEL];
static unsigned rx3_utility_dirty;
static uint64_t rx3_utility_changed_at;

static void rx3_utility_copy_line(uint8_t *line, const uint16_t *text)
{
    unsigned length = 0;
    while (length < 255u && text[length]) length++;
    memset(line + 0x22u, 0, 512u);
    *(uint16_t *)(line + 0x20u) = (uint16_t)length;
    memcpy(line + 0x22u, text, length * 2u);
}

/* Rows are found by label pointer, so a table copied by another module (the
   DISPLAY MODE row of theme-white) still works. */
static struct rx3_utility_row *rx3_utility_find(uint32_t label)
{
    for (unsigned i = 0; i < rx3_utility_row_count; i++)
        if (label == (uint32_t)(unsigned long)rx3_utility_rows[i].label)
            return &rx3_utility_rows[i];
    return 0;
}

static void rx3_utility_append(uint16_t *out, unsigned *length, const uint16_t *wide,
                               const char *text)
{
    while (wide && *wide && *length + 1u < RX3_UTILITY_VALUE) out[(*length)++] = *wide++;
    while (text && *text && *length + 1u < RX3_UTILITY_VALUE) out[(*length)++] = (uint8_t)*text++;
    out[*length] = 0;
}

/* The choice on screen, then the module's revision, or what a DJ needs to
   know about an option that only applies once the drive goes in again. */
static const uint16_t *rx3_utility_shown(struct rx3_utility_row *own, uint32_t *row)
{
    unsigned int choice = __atomic_load_n(&row[4], __ATOMIC_SEQ_CST);
    if (choice >= own->count) {
        choice = __atomic_load_n(&own->chosen, __ATOMIC_SEQ_CST);
        row[3] = choice;
    }
    unsigned length = 0;
    rx3_utility_append(own->shown, &length, own->choices[choice], 0);
    if (!own->live && choice != own->running)
        rx3_utility_append(own->shown, &length, 0, " AFTER REPLUG");
    else if (own->value[0]) {
        rx3_utility_append(own->shown, &length, 0, " ");
        rx3_utility_append(own->shown, &length, own->value, 0);
    }
    return own->shown;
}

/* Same two line buffers as Util_SetLine_VersionNo at 0x0013abd0. */
static int rx3_utility_set_line(uint32_t *row, uint8_t **lines)
{
    if (!row || !lines || !lines[0] || !lines[1]) return 0;
    static const uint16_t empty[] = {0};
    struct rx3_utility_row *own = rx3_utility_find(row[0]);
    rx3_utility_copy_line(lines[0], (const uint16_t *)(unsigned long)row[0]);
    if (own && own->key[0]) {
        rx3_utility_copy_line(lines[1], rx3_utility_shown(own, row));
        return 0;
    }
    rx3_utility_copy_line(lines[1], own ? own->value : empty);
    if (own) lines[0][3] |= 0x20u;
    return 0;
}

/* Copy printable ASCII after the indentation of a stock label, up to `stop`,
   the field separator or the row separator; returns the characters read. */
static unsigned rx3_utility_text(uint16_t *out, unsigned capacity,
                                 const uint16_t *indent_from, const char *text,
                                 char stop)
{
    unsigned length = 0, read = 0;
    while (indent_from && indent_from[length] == ' ' && length + 1u < capacity)
        out[length] = ' ', length++;
    while (text[read] && text[read] != stop && text[read] != ';' && text[read] != '|') {
        if (text[read] >= 0x20 && text[read] <= 0x7e && length + 1u < capacity)
            out[length++] = (uint8_t)text[read];
        read++;
    }
    out[length] = 0;
    return read;
}

/* A setting key or value: what the shell may write into settings.cfg. An
   overlong or unexpected word leaves `out` empty. */
static unsigned rx3_utility_word(char *out, unsigned capacity, const char *text,
                                 char stop, int key)
{
    unsigned read = 0, valid = 1;
    while (text[read] && text[read] != stop && text[read] != ';' && text[read] != '|') {
        char c = text[read];
        valid &= (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' ||
                 (key ? c == '.' : (c >= 'A' && c <= 'Z') || c == '.' || c == '+');
        if (read + 1u < capacity) out[read] = c;
        read++;
    }
    if (!valid || !read || read + 1u > capacity) out[0] = 0;
    else out[read] = 0;
    return read;
}

static int rx3_utility_same(const char *a, const char *b)
{
    while (*a && *a == *b) a++, b++;
    return *a == *b;
}

/* After LABEL|NOTE: |KEY|LIVE|VALUE|WORD=TEXT,WORD=TEXT. Anything that does not
   parse leaves the row read-only, showing its note. */
static const char *rx3_utility_choice_fields(struct rx3_utility_row *row, const char *text)
{
    char current[RX3_UTILITY_WORD];
    row->key[0] = 0;
    row->count = 0;
    if (*text != '|') return text;
    text++;
    text += rx3_utility_word(row->key, RX3_UTILITY_KEY, text, '|', 1);
    if (*text++ != '|' || (*text != '0' && *text != '1') || text[1] != '|') goto refuse;
    row->live = *text == '1';
    text += 2;
    text += rx3_utility_word(current, sizeof(current), text, '|', 0);
    if (*text++ != '|') goto refuse;
    while (row->count < RX3_UTILITY_CHOICES && *text && *text != ';') {
        unsigned n = row->count;
        text += rx3_utility_word(row->words[n], RX3_UTILITY_WORD, text, '=', 0);
        if (*text++ != '=') goto refuse;
        text += rx3_utility_text(row->choices[n], RX3_UTILITY_CHOICE, 0, text, ',');
        if (!row->words[n][0] || !row->choices[n][0]) goto refuse;
        row->choice_list[n] = (uint32_t)(unsigned long)row->choices[n];
        row->count++;
        if (*text == ',') text++;
    }
    row->running = RX3_UTILITY_NONE;
    for (unsigned i = 0; i < row->count; i++)
        if (rx3_utility_same(row->words[i], current)) row->running = i;
    if (!row->key[0] || !current[0] || row->count < 2u || row->running == RX3_UTILITY_NONE)
        goto refuse;
    row->chosen = row->running;
    return text;
refuse:
    row->key[0] = 0;
    row->count = 0;
    return text;
}

/* RX3_UTILITY_ROWS is "LABEL|VALUE;LABEL|NOTE|KEY|LIVE|VALUE|CHOICES", written
   by module-api.sh from the build's modules/utility and modules/settings. */
static void rx3_utility_collect(const uint16_t *child_label)
{
    const char *version = getenv("RX3_TOOLKIT_VERSION");
    struct rx3_utility_row *row = &rx3_utility_rows[0];
    rx3_utility_text(row->label, RX3_UTILITY_LABEL, child_label, "VERSION", 0);
    rx3_utility_text(row->value, RX3_UTILITY_VALUE, 0,
                     version && version[0] ? version : "UNKNOWN", 0);
    row->key[0] = 0;
    rx3_utility_row_count = 1;
    const char *rows = getenv("RX3_UTILITY_ROWS");
    while (rows && *rows && rx3_utility_row_count < RX3_UTILITY_MAX_ROWS) {
        row = &rx3_utility_rows[rx3_utility_row_count];
        rows += rx3_utility_text(row->label, RX3_UTILITY_LABEL, child_label,
                                 rows, '|');
        if (*rows != '|') break;
        rows++;
        rows += rx3_utility_text(row->value, RX3_UTILITY_VALUE, 0, rows, '|');
        rows = rx3_utility_choice_fields(row, rows);
        rx3_utility_row_count++;
        while (*rows && *rows != ';') rows++;
        if (*rows == ';') rows++;
    }
}

/* The value the DJ chose for a live option, for its module; null when the
   key has no live row, and the module's environment then holds its value.
   Any thread: the string never changes, only which one is current. */
static const char *rx3_utility_setting(const char *key)
{
    if (!key) return 0;
    for (unsigned i = 0; i < rx3_utility_row_count; i++) {
        struct rx3_utility_row *row = &rx3_utility_rows[i];
        if (row->key[0] && row->live && rx3_utility_same(row->key, key))
            return row->words[__atomic_load_n(&row->chosen, __ATOMIC_SEQ_CST)];
    }
    return 0;
}

static void rx3_utility_choose(struct rx3_utility_row *row, unsigned int choice,
                               uint64_t now_us)
{
    if (!row->key[0] || choice >= row->count ||
        choice == __atomic_load_n(&row->chosen, __ATOMIC_SEQ_CST)) return;
    __atomic_store_n(&row->chosen, choice, __ATOMIC_SEQ_CST);
    row->touched = 1u;
    rx3_utility_dirty = 1u;
    rx3_utility_changed_at = now_us;
}

static unsigned rx3_utility_put(char *out, unsigned at, unsigned capacity, const char *text)
{
    while (*text && at < capacity) out[at++] = *text++;
    return at;
}

/* Every key the DJ touched, current value, replaced as one file: the shell
   takes the file by renaming it, never while it is half written. */
static int rx3_utility_save(void)
{
    char text[RX3_UTILITY_MAX_ROWS * (RX3_UTILITY_KEY + RX3_UTILITY_WORD + 4u)];
    unsigned length = 0;
    for (unsigned i = 0; i < rx3_utility_row_count; i++) {
        struct rx3_utility_row *row = &rx3_utility_rows[i];
        if (!row->key[0] || !row->touched) continue;
        length = rx3_utility_put(text, length, sizeof(text), row->key);
        length = rx3_utility_put(text, length, sizeof(text), " = ");
        length = rx3_utility_put(text, length, sizeof(text),
                                 row->words[__atomic_load_n(&row->chosen, __ATOMIC_SEQ_CST)]);
        length = rx3_utility_put(text, length, sizeof(text), "\n");
    }
    int fd = open(RX3_SETTINGS_PENDING ".new", O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return 0;
    int written = (int)write(fd, text, length) == (int)length;
    written &= close(fd) == 0;
    return written && rx3_rename(RX3_SETTINGS_PENDING ".new", RX3_SETTINGS_PENDING) == 0;
}

/* Watcher thread. Changes are saved once the DJ has left them alone for a
   moment, so scrolling through a list writes the drive once. */
static void rx3_utility_flush(uint64_t now_us)
{
    if (rx3_utility_dirty && now_us - rx3_utility_changed_at >= RX3_UTILITY_QUIET_US &&
        rx3_utility_save())
        rx3_utility_dirty = 0;
}

/* Utility commits a choice into word 4 of the row it shows, which may sit in
   a copy of our table; consume it like utility_poll_theme_row does. */
static void rx3_utility_poll(uint64_t now_us)
{
    if (!rx3_utility_table) return;
    uint32_t table = *(const uint32_t *)rx3_utility_count_literals[0];
    if (!table) return;
    uint32_t count = *(const uint32_t *)(unsigned long)table;
    for (uint32_t i = RX3_UTILITY_STOCK_COUNT; i < count && i < 64u; i++) {
        uint32_t *row = (uint32_t *)(unsigned long)(table + 4u + i * RX3_UTILITY_ROW_BYTES);
        struct rx3_utility_row *own = rx3_utility_find(row[0]);
        if (!own || !own->key[0]) continue;
        unsigned int choice = __atomic_load_n(&row[4], __ATOMIC_SEQ_CST);
        if (choice >= own->count) continue;
        __atomic_store_n(&row[4], RX3_UTILITY_NONE, __ATOMIC_SEQ_CST);
        row[3] = choice;
        rx3_utility_choose(own, choice, now_us);
    }
    rx3_utility_flush(now_us);
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

/* The stock choice row DISPLAY MODE is built from (theme-white), checked the
   same way; without it every toolkit row stays read-only. */
static int rx3_utility_choice_rows_known(void)
{
    return *(const uint32_t *)0x0051410cu == 0x0013a924u &&
           *(const uint32_t *)0x00514118u == 0x0013c360u &&
           *(const uint32_t *)0x00514128u == 0x0013a99cu;
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
    int choices = rx3_utility_choice_rows_known();
    if (!choices) log_line("toolkit: Utility choice rows unknown, toolkit rows read-only");

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
        struct rx3_utility_row *own = &rx3_utility_rows[i];
        row += RX3_UTILITY_ROW_BYTES;
        if (!choices) own->key[0] = 0;
        if (own->key[0]) {
            const uint32_t choice_row[14] = {
                (uint32_t)(unsigned long)own->label,
                (uint32_t)(unsigned long)own->choice_list,
                own->count, RX3_UTILITY_NONE, RX3_UTILITY_NONE, 1u, 0x0013a924u,
                (uint32_t)(unsigned long)rx3_utility_set_line,
                0x0013a928u, 0x0013c360u, 0x0013a958u, 0x0013a984u,
                0x0013a98cu, 0x0013a99cu
            };
            memcpy(row, choice_row, sizeof(choice_row));
            continue;
        }
        memcpy(row, stock + RX3_UTILITY_VERSION_NO * words, RX3_UTILITY_ROW_BYTES);
        ((uint32_t *)row)[0] = (uint32_t)(unsigned long)own->label;
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
