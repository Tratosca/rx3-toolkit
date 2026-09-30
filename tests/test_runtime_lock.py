# SPDX-License-Identifier: MPL-2.0
"""Concurrent USB insertions must not share the guarded-word workspace."""

import subprocess
import tempfile
import unittest
from pathlib import Path


AUTOEXEC = Path(__file__).resolve().parents[1] / "mod/autoexec.sh"


class RuntimeLockTests(unittest.TestCase):
    def test_second_insertion_does_not_take_or_release_the_first_lock(self):
        source = AUTOEXEC.read_text()
        block = source.split("# The guarded-word workspace", 1)[1].split(
            "# End exclusive workspace entry.", 1
        )[0]
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "runtime.lock"
            setup = f'LOCK="{lock}"\nsay() {{ :; }}\n# The guarded-word workspace{block}'
            first = subprocess.Popen(
                ["sh", "-c", setup + 'echo acquired\nsleep 1\n'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                self.assertEqual(first.stdout.readline().strip(), "acquired")
                second = subprocess.run(
                    ["sh", "-c", setup + 'echo unexpected\n'],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(second.returncode, 1)
                self.assertNotIn("unexpected", second.stdout)
                self.assertTrue(lock.is_dir())
                first.communicate(timeout=5)
                self.assertEqual(first.returncode, 0)
                self.assertFalse(lock.exists())
                third = subprocess.run(
                    ["sh", "-c", setup + 'echo acquired\n'],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(third.returncode, 0)
                self.assertEqual(third.stdout.strip(), "acquired")
            finally:
                if first.poll() is None:
                    first.kill()
                    first.wait()
