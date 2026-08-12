# SPDX-License-Identifier: MPL-2.0
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "runtime/modules/buffer/decoder-sleep/1.19/apply.sh"


class DecoderSleepPatchTests(unittest.TestCase):
    def test_rejects_non_numeric_interval_before_runtime_access(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "decoder-sleep.log"
            result = subprocess.run(
                ["/bin/sh", str(SCRIPT), "invalid", str(log)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("positive integer", log.read_text())


if __name__ == "__main__":
    unittest.main()
