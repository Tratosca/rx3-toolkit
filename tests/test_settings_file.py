# SPDX-License-Identifier: MPL-2.0
"""The app's writer for RX3_RUNTIME/settings.cfg against the deck's reader."""
import pathlib
import shlex
import tempfile
import unittest

from app.localization import LocalizedError
from app.services import settings
from tests.test_module_api import run_shell


def deck_reads(drive, key, fallback="none"):
    result = run_shell(f"USB={shlex.quote(str(drive))}\n"
                       f"module_setting {shlex.quote(key)} {shlex.quote(fallback)}\n")
    return result.stdout


class SettingsFileTests(unittest.TestCase):
    def test_new_file_is_read_back_by_the_deck(self):
        with tempfile.TemporaryDirectory() as drive:
            settings.update(pathlib.Path(drive), {"key-sync.range": "3", "key-sync.mode": "identical"})
            self.assertEqual(deck_reads(drive, "key-sync.range"), "3")
            self.assertEqual(deck_reads(drive, "key-sync.mode"), "identical")

    def test_other_lines_survive_and_duplicates_collapse_in_place(self):
        with tempfile.TemporaryDirectory() as drive:
            path = pathlib.Path(drive) / "RX3_RUNTIME" / "settings.cfg"
            path.parent.mkdir()
            path.write_text("# mine\r\nversion = 1\r\ntheme-white.mode = dark\r\n"
                            "key-sync.range = 2\r\nguard.stems = off\r\nkey-sync.range = 5\r\n")
            settings.update(pathlib.Path(drive), {"key-sync.range": "7"})
            self.assertEqual(path.read_text(), "# mine\nversion = 1\ntheme-white.mode = dark\n"
                                               "key-sync.range = 7\nguard.stems = off\n")
            self.assertEqual(deck_reads(drive, "key-sync.range"), "7")
            self.assertEqual(deck_reads(drive, "theme-white.mode"), "dark")

    def test_a_file_the_deck_would_ignore_is_left_untouched(self):
        for content in (b"key-sync.range = 2\n", b"version = 2\n", b"version = 1\n" + b"#" * 65536,
                        b"version = 1\n\xff\n"):
            with tempfile.TemporaryDirectory() as drive:
                path = pathlib.Path(drive) / "RX3_RUNTIME" / "settings.cfg"
                path.parent.mkdir()
                path.write_bytes(content)
                with self.assertRaises(LocalizedError):
                    settings.update(pathlib.Path(drive), {"key-sync.range": "3"})
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["settings.cfg"])


if __name__ == "__main__":
    unittest.main()
