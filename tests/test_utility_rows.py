# SPDX-License-Identifier: MPL-2.0
"""The RX3 TOOLKIT rows in Utility: parsed safely, drawn by label, and the
DJ's choices served live and left in RAM for the drive."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

SOURCE = r'''
#define _DEFAULT_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
static void log_line(const char *line) { (void)line; }
static int rx3_write_guarded(unsigned long a, const void *e, const void *w, size_t n)
{ (void)a; (void)e; (void)w; (void)n; return 0; }
static int rx3_rename(const char *from, const char *to) { return rename(from, to); }
#include "rx3_utility.h"

static int same(const uint16_t *wide, const char *text)
{
    while (*text) if (*wide++ != (uint8_t)*text++) return 0;
    return *wide == 0;
}

static struct rx3_utility_row *row_at(unsigned i) { return &rx3_utility_rows[i]; }

static const uint16_t *drawn(unsigned i, uint32_t pending)
{
    uint32_t words[14] = {0};
    words[3] = RX3_UTILITY_NONE;
    words[4] = pending;
    const uint16_t *text = rx3_utility_shown(row_at(i), words);
    if (pending == RX3_UTILITY_NONE)
        assert(words[3] == row_at(i)->chosen); /* the picker opens on the current choice */
    return text;
}

static char saved[512];
static const char *pending_file(void)
{
    FILE *file = fopen(RX3_SETTINGS_PENDING, "r");
    if (!file) return 0;
    size_t n = fread(saved, 1, sizeof(saved) - 1, file);
    saved[n] = 0;
    fclose(file);
    return saved;
}

int main(void)
{
    static const uint16_t child[] = {' ', ' ', 'V', 0};
    setenv("RX3_TOOLKIT_VERSION", "0.5.2-117-g8351ffc-dirty", 1);
    setenv("RX3_UTILITY_ROWS",
           "KEY SHIFT|ON 3f2a9c1;STEMS|OFF 8351ffc+;BROKEN ROW;LATER|ON 1", 1);
    rx3_utility_collect(child);
    /* A row without its value ends the list: nothing after it is trusted. */
    assert(rx3_utility_row_count == 3);
    assert(same(row_at(0)->label, "  VERSION"));
    assert(same(row_at(0)->value, "0.5.2-117-g8351ffc-dirty"));
    assert(same(row_at(1)->label, "  KEY SHIFT"));
    assert(same(row_at(2)->value, "OFF 8351ffc+"));
    assert(!row_at(1)->key[0] && !row_at(2)->key[0]);

    /* The player hands back the label pointer of a row, wherever the row sits. */
    assert(rx3_utility_find((uint32_t)(unsigned long)row_at(2)->label) == row_at(2));
    assert(!rx3_utility_find((uint32_t)(unsigned long)child));

    /* Overlong text is cut, control characters dropped, the count capped. */
    char many[4096] = "";
    for (int i = 0; i < 40; i++)
        strcat(many, "A\tVERY LONG MODULE NAME THAT KEEPS GOING AND GOING|ON 0123456789abcdef;");
    setenv("RX3_UTILITY_ROWS", many, 1);
    unsetenv("RX3_TOOLKIT_VERSION");
    rx3_utility_collect(child);
    assert(rx3_utility_row_count == RX3_UTILITY_MAX_ROWS);
    assert(same(row_at(0)->value, "UNKNOWN"));
    assert(row_at(1)->label[RX3_UTILITY_LABEL - 1] == 0);
    assert(row_at(1)->label[3] == 'V');
    assert(row_at(1)->value[RX3_UTILITY_VALUE - 1] == 0);

    /* Rows the DJ can change: a module switch, two live options, and rows
       that do not parse, which stay read-only and show their note. */
    setenv("RX3_UTILITY_ROWS",
           "KEY SYNC|abc1234|key-sync.enabled|0|on|on=ON,off=OFF;"
           "  SYNC RANGE||key-sync.range|1|2|1=1 SEMITONE,2=2 SEMITONES,3=3 SEMITONES;"
           "  THIRD COLUMN||browse-columns.column|0|13|13=BPM,7=ARTIST;"
           "BAD LIVE|n1|bad.live|2|on|on=ON,off=OFF;"
           "UNKNOWN VALUE|n2|bad.value|1|maybe|on=ON,off=OFF;"
           "ONE CHOICE|n3|bad.one|1|on|on=ON;"
           "UPPER KEY|n4|Bad.key|1|on|on=ON,off=OFF;"
           "LOGO|ON 0123456", 1);
    rx3_utility_collect(child);
    assert(rx3_utility_row_count == 9);
    assert(!strcmp(row_at(1)->key, "key-sync.enabled") && !row_at(1)->live);
    assert(row_at(1)->count == 2 && row_at(1)->chosen == 0);
    assert(same(row_at(2)->label, "    SYNC RANGE"));
    assert(row_at(2)->live && row_at(2)->count == 3 && row_at(2)->chosen == 1);
    for (unsigned i = 4; i <= 7; i++) {
        assert(!row_at(i)->key[0]);
        assert(row_at(i)->value[0] == 'n');
    }
    assert(same(row_at(8)->value, "ON 0123456"));
    assert(row_at(2)->choice_list[2] == (uint32_t)(unsigned long)row_at(2)->choices[2]);

    /* Only live options are served; the others wait for the next insertion. */
    assert(!strcmp(rx3_utility_setting("key-sync.range"), "2"));
    assert(!rx3_utility_setting("key-sync.enabled"));
    assert(!rx3_utility_setting("browse-columns.column"));
    assert(!rx3_utility_setting("key-sync"));
    assert(!rx3_utility_setting(0));

    assert(same(drawn(1, RX3_UTILITY_NONE), "ON abc1234"));
    assert(same(drawn(1, 1), "OFF AFTER REPLUG")); /* committed, not yet picked up */
    assert(same(drawn(2, RX3_UTILITY_NONE), "2 SEMITONES"));
    assert(same(drawn(3, RX3_UTILITY_NONE), "BPM"));

    /* Choices apply at once and reach RAM only once the DJ stops. */
    unlink(RX3_SETTINGS_PENDING);
    rx3_utility_choose(row_at(2), 0, 10000000u);
    assert(!strcmp(rx3_utility_setting("key-sync.range"), "1"));
    rx3_utility_choose(row_at(1), 1, 10500000u);
    rx3_utility_choose(row_at(3), 1, 11000000u);
    rx3_utility_choose(row_at(3), 9, 11100000u);  /* out of range: ignored */
    rx3_utility_choose(row_at(4), 1, 11200000u);  /* read-only: ignored */
    assert(same(drawn(1, RX3_UTILITY_NONE), "OFF AFTER REPLUG"));
    assert(same(drawn(3, RX3_UTILITY_NONE), "ARTIST AFTER REPLUG"));
    rx3_utility_flush(12000000u);
    assert(!pending_file());
    rx3_utility_flush(13000000u);
    assert(!strcmp(pending_file(),
                   "key-sync.enabled = off\nkey-sync.range = 1\nbrowse-columns.column = 7\n"));

    /* Turning one back keeps its line: the drive may already hold the old one. */
    unlink(RX3_SETTINGS_PENDING);
    rx3_utility_choose(row_at(1), 0, 20000000u);
    assert(same(drawn(1, RX3_UTILITY_NONE), "ON abc1234"));
    rx3_utility_flush(23000000u);
    assert(!strcmp(pending_file(),
                   "key-sync.enabled = on\nkey-sync.range = 1\nbrowse-columns.column = 7\n"));
    unlink(RX3_SETTINGS_PENDING);
    rx3_utility_flush(30000000u);
    assert(!pending_file()); /* nothing new: nothing written */
    return 0;
}
'''


class UtilityRowsTests(unittest.TestCase):
    def test_rows_choices_live_values_and_pending_file(self):
        compiler = shutil.which("clang") or shutil.which("cc")
        if not compiler:
            self.skipTest("C compiler required")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path / "test.c").write_text(SOURCE)
            binary = path / "test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-function",
                            f"-DRX3_SETTINGS_PENDING=\"{path / 'pending'}\"",
                            "-I", str(ROOT / "mod/modules/core/firmware"),
                            str(path / "test.c"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
