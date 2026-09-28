# SPDX-License-Identifier: MPL-2.0
import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "rx3_kernel" / "validate-symvers.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("validate_symvers", VALIDATOR)
VALIDATE_SYMVERS = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATE_SYMVERS)


def symvers_line(symbol, crc):
    return f"0x{crc:08x}\t{symbol}\tvmlinux\tEXPORT_SYMBOL\n"


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


class ModuleSymversValidationTest(unittest.TestCase):
    def validate(self, profile, versions, exports=None):
        exports = exports or {}

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            profile_path = directory / "production.symvers"
            modules_path = directory / "modules.list"
            output = directory / "output"
            output.mkdir()

            profile_path.write_text(
                "".join(symvers_line(symbol, crc) for symbol, crc in profile.items())
            )
            modules_path.write_text("".join(f"{module}\n" for module in versions))

            for module in versions:
                (output / module).touch()

            with mock.patch.object(
                VALIDATE_SYMVERS,
                "module_versions",
                side_effect=lambda path: versions[path.name],
            ), mock.patch.object(
                VALIDATE_SYMVERS,
                "module_exports",
                side_effect=lambda path: exports.get(path.name, set()),
            ):
                VALIDATE_SYMVERS.validate_modules(
                    profile_path, modules_path, output
                )

    def test_accepts_exact_external_imports(self):
        self.validate(
            {"module_layout": 0xB17BC4CF, "printk": 0x27E1A049},
            {
                "first.ko": {"module_layout": 0xB17BC4CF},
                "second.ko": {
                    "module_layout": 0xB17BC4CF,
                    "printk": 0x27E1A049,
                },
            },
        )

    def test_rejects_missing_production_symbol(self):
        with self.assertRaisesRegex(
            SystemExit, "production symbols missing from profile: printk"
        ):
            self.validate(
                {"module_layout": 0xB17BC4CF},
                {
                    "example.ko": {
                        "module_layout": 0xB17BC4CF,
                        "printk": 0x27E1A049,
                    }
                },
            )

    def test_rejects_unused_production_symbol(self):
        with self.assertRaisesRegex(
            SystemExit, "unused production symbols in profile: printk"
        ):
            self.validate(
                {"module_layout": 0xB17BC4CF, "printk": 0x27E1A049},
                {"example.ko": {"module_layout": 0xB17BC4CF}},
            )

    def test_rejects_mismatched_production_crc(self):
        with self.assertRaisesRegex(
            SystemExit, "production symbol CRC mismatch: module_layout"
        ):
            self.validate(
                {"module_layout": 0xB17BC4CF},
                {"example.ko": {"module_layout": 0x12345678}},
            )

    def test_rejects_inconsistent_module_crcs(self):
        with self.assertRaisesRegex(
            SystemExit, "inconsistent module CRC for module_layout"
        ):
            self.validate(
                {"module_layout": 0xB17BC4CF},
                {
                    "first.ko": {"module_layout": 0xB17BC4CF},
                    "second.ko": {"module_layout": 0x12345678},
                },
            )

    def test_excludes_symbols_exported_by_sibling_module(self):
        self.validate(
            {"module_layout": 0xB17BC4CF},
            {
                "provider.ko": {
                    "module_layout": 0xB17BC4CF,
                    "feature_helper": 0x12345678,
                },
                "consumer.ko": {
                    "module_layout": 0xB17BC4CF,
                    "feature_helper": 0x12345678,
                },
            },
            {"provider.ko": {"feature_helper"}},
        )


if __name__ == "__main__":
    unittest.main()
