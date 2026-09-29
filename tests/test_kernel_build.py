# SPDX-License-Identifier: MPL-2.0
import hashlib
import importlib.util
import shutil
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


class SourcedKernelRecipeTest(unittest.TestCase):
    def test_fetches_verifies_and_prepares_external_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            tool = root / "tools/rx3_kernel"
            recipe = root / "recipe"
            cache = root / "cache"
            output = root / "output"
            kernel = root / "kernel"
            tool.mkdir(parents=True)
            recipe.mkdir()
            kernel.mkdir()
            shutil.copy2(ROOT / "tools/rx3_kernel/build-recipe.sh", tool)

            payload = b"pinned driver source\n"
            (recipe / "sources.sha256").write_text(
                f"{hashlib.sha256(payload).hexdigest()}  driver.tar\n"
            )
            (recipe / "fetch-sources.sh").write_text(
                "#!/bin/sh\nprintf 'pinned driver source\\n' > \"$1/driver.tar\"\n"
            )
            (recipe / "prepare-recipe.sh").write_text(
                "#!/bin/sh\nmkdir -p \"$2/driver\"\n"
                "cp \"$1/driver.tar\" \"$2/driver/source\"\n"
            )
            (tool / "build-modules.sh").write_text(
                "#!/bin/sh\nset -eu\n"
                "test -f \"$3/driver/source\"\n"
                "mkdir -p \"$4\"\n"
                "cp \"$3/driver/source\" \"$4/receipt\"\n"
            )
            for script in (
                tool / "build-recipe.sh",
                tool / "build-modules.sh",
                recipe / "fetch-sources.sh",
                recipe / "prepare-recipe.sh",
            ):
                script.chmod(0o755)

            result = subprocess.run(
                [
                    tool / "build-recipe.sh", "1.19", kernel, recipe,
                    cache, output,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / "receipt").read_bytes(), payload)

    def test_rejects_partial_source_hooks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            tool = root / "tools/rx3_kernel"
            recipe = root / "recipe"
            tool.mkdir(parents=True)
            recipe.mkdir()
            shutil.copy2(ROOT / "tools/rx3_kernel/build-recipe.sh", tool)
            (recipe / "sources.sha256").touch()

            result = subprocess.run(
                [
                    tool / "build-recipe.sh", "1.19", root / "kernel",
                    recipe, root / "cache", root / "output",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source hooks must include", result.stderr)


if __name__ == "__main__":
    unittest.main()
