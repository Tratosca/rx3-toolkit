# SPDX-License-Identifier: MPL-2.0
"""The RX3 TOOLKIT rows in Utility: parsed safely and drawn by label."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class UtilityRowsTests(unittest.TestCase):
    def test_rows_are_parsed_bounded_and_found_by_label(self):
        compiler = shutil.which("clang") or shutil.which("cc")
        if not compiler:
            self.skipTest("C compiler required")
        source = r'''
#define _DEFAULT_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
static void log_line(const char *line) { (void)line; }
static int rx3_write_guarded(unsigned long a, const void *e, const void *w, size_t n)
{ (void)a; (void)e; (void)w; (void)n; return 0; }
#include "rx3_utility.h"

static int same(const uint16_t *wide, const char *text)
{
    while (*text) if (*wide++ != (uint8_t)*text++) return 0;
    return *wide == 0;
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
    assert(same(rx3_utility_rows[0].label, "  VERSION"));
    assert(same(rx3_utility_rows[0].value, "0.5.2-117-g8351ffc-dirty"));
    assert(same(rx3_utility_rows[1].label, "  KEY SHIFT"));
    assert(same(rx3_utility_rows[2].value, "OFF 8351ffc+"));

    /* The player hands back the label pointer of a row, wherever the row sits. */
    assert(rx3_utility_value((uint32_t)(unsigned long)rx3_utility_rows[2].label) ==
           rx3_utility_rows[2].value);
    assert(!rx3_utility_value((uint32_t)(unsigned long)child));

    /* Overlong text is cut, control characters dropped, the count capped. */
    char many[4096] = "";
    for (int i = 0; i < 40; i++)
        strcat(many, "A\tVERY LONG MODULE NAME THAT KEEPS GOING AND GOING|ON 0123456789abcdef;");
    setenv("RX3_UTILITY_ROWS", many, 1);
    unsetenv("RX3_TOOLKIT_VERSION");
    rx3_utility_collect(child);
    assert(rx3_utility_row_count == RX3_UTILITY_MAX_ROWS);
    assert(same(rx3_utility_rows[0].value, "UNKNOWN"));
    assert(rx3_utility_rows[1].label[RX3_UTILITY_LABEL - 1] == 0);
    assert(rx3_utility_rows[1].label[3] == 'V');
    assert(rx3_utility_rows[1].value[RX3_UTILITY_VALUE - 1] == 0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path / "test.c").write_text(source)
            binary = path / "test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-function",
                            "-I", str(ROOT / "mod/modules/core/firmware"),
                            str(path / "test.c"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
