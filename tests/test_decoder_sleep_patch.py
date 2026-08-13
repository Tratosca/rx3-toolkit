# SPDX-License-Identifier: MPL-2.0
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).parents[1]
sys.path.insert(0, str(REPOSITORY / "tools"))

from rx3_runtime.build import discover_patches  # noqa: E402

MODULE = next(
    patch.directory for patch in discover_patches() if patch.patch_id == "decoder-sleep"
)
SCRIPT = MODULE / "apply.sh"


class DecoderSleepPatchTests(unittest.TestCase):
    def test_registers_its_post_launch_hook(self):
        # The setting is volatile and applied after rbp starts, so the adapter
        # is useless unless it is registered on that lifecycle point.
        module = (MODULE / "module.sh").read_text(encoding="utf-8")
        self.assertIn("register_post_launch_hook decoder_sleep_apply", module)

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
