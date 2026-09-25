# SPDX-License-Identifier: MPL-2.0
import pathlib
import shutil
import subprocess
import unittest


class SamplePreviewTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node runs the UI event tests')
    def test_pad_playback_events(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/sample_preview.cjs'], cwd=root,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
