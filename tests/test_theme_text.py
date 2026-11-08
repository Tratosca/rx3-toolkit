# SPDX-License-Identifier: MPL-2.0
"""Check neutral list ink without depending on the player renderer."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ThemeTextTests(unittest.TestCase):
    def test_native_styles_and_views(self):
        compiler = shutil.which("clang") or shutil.which("cc")
        if not compiler:
            self.skipTest("C compiler required")
        source = r'''
#include <assert.h>
#include "rx3_theme_text.h"
int main(void) {
    const unsigned semantic[] = {0x100u, 0x200u, 0x1c00u,
                                  0xffe02020u, 0xff00aa00u};
    const unsigned neutral[] = {0u, 0xffe0e0e0u, 0xffffffffu};
    for (unsigned view = 0; view <= 12; ++view) {
        /* Lists of BROWSE, UTILITY and SOURCE; no other view outside HOME. */
        assert(theme_text_light_surface(view, 0x801u, 60u) ==
               (view == 3 || view == 7 || view == 12));
        for (unsigned light = 0; light < 2; ++light) {
            for (unsigned i = 0; i < sizeof(neutral)/sizeof(neutral[0]); ++i) {
                /* Light surface: dark ink. Selection fill: native ink. */
                assert(theme_text_colour(light, 1u, neutral[i], 0u) ==
                       (light ? THEME_TEXT_DARK : neutral[i]));
                assert(theme_text_colour(light, 0u, neutral[i], 0u) == neutral[i]);
                assert(theme_text_colour(light, 1u, neutral[i], 1u) == neutral[i]);
            }
            for (unsigned i = 0; i < sizeof(semantic)/sizeof(semantic[0]); ++i)
                for (unsigned fill = 0; fill < 2; ++fill)
                    assert(theme_text_colour(light, 1u, semantic[i], fill) == semantic[i]);
        }
    }
    /* HOME: deck strip title rows and the left column only. */
    assert(theme_text_light_surface(1u, 0x201u, 15u));
    assert(theme_text_light_surface(1u, 0x301u, 15u));
    assert(!theme_text_light_surface(1u, 0x201u, 65u));
    assert(theme_text_light_surface(1u, 0x1101u, 98u));
    assert(!theme_text_light_surface(1u, 0x1701u, 23u));
    /* UTILITY redraws only the name newly uncovered by the blue edit cell. */
    for (unsigned row = 0; row < 12u; row++) {
        unsigned name = (row << 2) | 1u;
        unsigned value = (row << 2) | 2u;
        assert(theme_utility_name_row(name, value) == row + 1u);
        assert(theme_utility_name_row(value, value) == 0u);
        assert(theme_utility_name_row(value, name) == 0u);
    }
    assert(theme_utility_name_row(1u, (12u << 2) | 2u) == 0u);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path / "test.c").write_text(source)
            binary = path / "test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "mod/modules/theme-white"),
                            str(path / "test.c"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
