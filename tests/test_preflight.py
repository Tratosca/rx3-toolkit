# SPDX-License-Identifier: MPL-2.0
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).parents[1]


class PreflightTests(unittest.TestCase):
    def test_rejects_extensionless_elf_by_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(REPOSITORY / "scripts/preflight.sh", scripts)
            (root / "innocent-name").write_bytes(b"\x7fELFgenerated")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)

            result = subprocess.run(
                ["./scripts/preflight.sh"],
                cwd=root,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "REJECTED compiled ELF artifact: innocent-name", result.stderr
            )


if __name__ == "__main__":
    unittest.main()
