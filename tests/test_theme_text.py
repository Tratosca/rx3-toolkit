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
    for (unsigned view = 0; view <= 12; ++view) {
        for (unsigned light = 0; light < 2; ++light) {
            unsigned expected = light && (view == 3 || view == 7 || view == 12)
                ? THEME_TEXT_DARK : 0u;
            assert(theme_text_colour(light, view, 0u, 15u, 700u, 0u, 0u) == expected);
            if (view == 3 || view == 7) {
                unsigned first = view == 3 ? 60u : 11u;
                unsigned step = view == 3 ? 50u : 52u;
                for (unsigned row = 0; row < 12; ++row) {
                    unsigned y = first + row * step;
                    unsigned fill = view == 3 ? 1u : 0u;
                    assert(theme_text_colour(light, view, 0u, 15u, y, row,
                        fill) == 0u);
                    assert(theme_text_colour(light, view, 0u, 15u, y,
                        (row + 1u) % 12u, 0u) == expected);
                    if (view == 3)
                        assert(theme_text_colour(light, view, 0u, 15u, y,
                            row, 0u) == expected);
                    if (view == 7)
                        assert(theme_text_colour(light, view, 0u, 750u, y,
                            row, 0u) == expected);
                }
            }
            for (unsigned i = 0; i < sizeof(semantic)/sizeof(semantic[0]); ++i)
                assert(theme_text_colour(light, view, semantic[i], 15u, 700u,
                    0u, 0u)
                       == semantic[i]);
            unsigned source_ink = 0xffe0e0e0u;
            assert(theme_text_colour(light, view, source_ink, 780u, 110u,
                0u, 0u) == (light && (view == 3u || view == 7u || view == 12u)
                    ? THEME_TEXT_DARK : source_ink));
            assert(theme_text_colour(light, view, source_ink, 780u, 110u,
                0u, 1u) == source_ink);
        }
    }
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
