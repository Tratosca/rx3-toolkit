# SPDX-License-Identifier: MPL-2.0
import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "rx3_kernel" / "validate-symvers.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("validate_symvers", VALIDATOR)
VALIDATE_SYMVERS = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATE_SYMVERS)


class ProductionSymversTest(unittest.TestCase):
    def validate(self, contents, checksum_contents=None):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            profile = directory / "production.symvers"
            checksum = directory / "production.symvers.sha256"
            profile.write_text(contents)

            digest = hashlib.sha256(profile.read_bytes()).hexdigest()
            checksum.write_text(
                checksum_contents or f"{digest}  production.symvers\n"
            )
            return subprocess.run(
                [VALIDATOR, "profile", profile, checksum],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_accepts_minimal_profile(self):
        result = self.validate(
            "0xb17bc4cf\tmodule_layout\tvmlinux\tEXPORT_SYMBOL\n"
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_duplicate_symbol(self):
        line = "0xb17bc4cf\tmodule_layout\tvmlinux\tEXPORT_SYMBOL\n"
        result = self.validate(line + line)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate production symbol", result.stderr)

    def test_rejects_untrusted_checksum_filename(self):
        result = self.validate(
            "0xb17bc4cf\tmodule_layout\tvmlinux\tEXPORT_SYMBOL\n",
            "0" * 64 + "  ../production.symvers\n",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid production.symvers.sha256", result.stderr)

    def test_rejects_checksum_mismatch(self):
        result = self.validate(
            "0xb17bc4cf\tmodule_layout\tvmlinux\tEXPORT_SYMBOL\n",
            "0" * 64 + "  production.symvers\n",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)

if __name__ == "__main__":
    unittest.main()
