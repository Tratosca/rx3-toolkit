# SPDX-License-Identifier: MPL-2.0
import shutil
import subprocess
import unittest


class StemsScreenTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node runs the UI event tests")
    def test_screen_initialization_and_mode_switching(self):
        result = subprocess.run(
            ["node", "tests/stems_screen.cjs"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
