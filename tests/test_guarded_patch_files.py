# SPDX-License-Identifier: MPL-2.0
"""File-backed patches share the runtime's identity and safety transaction."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_API = ROOT / "mod/lib/module-api.sh"
AUTOEXEC = (ROOT / "mod/autoexec.sh").read_text(encoding="utf-8")

HARNESS = r'''
say() { :; }
PATCH_TABLE=""
PATCH_FILE_TABLE=""
PATCH_OFFSETS=""
PATCH_SPANS=""
LOADED_MODULES=""
CURRENT_MODULE=""
CURRENT_NAMESPACE=""
MODULE_LOAD_FAILED=0
. "$MODULE_API"
module_begin holder holder
'''


def run_shell(body: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", HARNESS + body],
        text=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "MODULE_API": str(MODULE_API), **env},
    )


class GuardedPatchFileTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        stock = root / "stock.bin"
        patched = root / "patched.bin"
        binary = root / "rbp"
        stock.write_bytes(b"stock-RX3-table!")
        patched.write_bytes(b"curve-RX3-table!")
        binary.write_bytes(b"prefix!!" + stock.read_bytes() + b"suffix!!")
        self.assertEqual(stock.stat().st_size, 16)
        return stock, patched, binary

    def test_stock_and_patched_ranges_normalise_to_the_stock_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock, patched, binary = self.fixture(root)
            expected = hashlib.sha1(binary.read_bytes()).hexdigest()
            workspace = root / "workspace"
            workspace.mkdir()
            body = r'''
register_patch_file 8 16 "$STOCK" "$PATCHED" table
extract_guarded_words "$WORKSPACE" || exit 20
normalized_rbp_sha1 "$BINARY" "$WORKSPACE"
'''
            environment = {
                "STOCK": str(stock), "PATCHED": str(patched),
                "BINARY": str(binary), "WORKSPACE": str(workspace),
            }
            stock_result = run_shell(body, environment)
            self.assertEqual(stock_result.returncode, 0, stock_result.stderr)
            self.assertEqual(stock_result.stdout.strip(), expected)

            image = bytearray(binary.read_bytes())
            image[8:24] = patched.read_bytes()
            binary.write_bytes(image)
            patched_result = run_shell(body, environment)
            self.assertEqual(patched_result.returncode, 0, patched_result.stderr)
            self.assertEqual(patched_result.stdout.strip(), expected)

    def test_partial_or_foreign_range_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock, patched, binary = self.fixture(root)
            image = bytearray(binary.read_bytes())
            image[8:12] = patched.read_bytes()[:4]
            binary.write_bytes(image)
            result = run_shell(
                'guarded_patch_file_state "$BINARY" 8 16 "$STOCK" "$PATCHED"\n',
                {"STOCK": str(stock), "PATCHED": str(patched), "BINARY": str(binary)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "unknown")

    def test_write_verify_and_rollback_use_the_exact_guarded_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock, patched, binary = self.fixture(root)
            result = run_shell(
                r'''
write_guarded_patch_file "$BINARY" 8 16 "$PATCHED" || exit 20
guarded_patch_file_matches "$BINARY" 8 16 "$PATCHED" || exit 21
guarded_patch_file_matches "$BINARY" 8 16 "$STOCK" && exit 22
write_guarded_patch_file "$BINARY" 8 16 "$STOCK" || exit 23
guarded_patch_file_matches "$BINARY" 8 16 "$STOCK" || exit 24
''',
                {"STOCK": str(stock), "PATCHED": str(patched), "BINARY": str(binary)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(binary.read_bytes(), b"prefix!!" + stock.read_bytes() + b"suffix!!")

    def test_ranges_reject_overlap_with_words_and_other_ranges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock, patched, _binary = self.fixture(root)
            result = run_shell(
                r'''
register_patch 12 '\001\002\003\004' '\005\006\007\010' word || exit 20
register_patch_file 8 16 "$STOCK" "$PATCHED" overlap && exit 21
[ "$MODULE_LOAD_FAILED" = 1 ] || exit 22
''',
                {"STOCK": str(stock), "PATCHED": str(patched)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            result = run_shell(
                r'''
register_patch_file 8 16 "$STOCK" "$PATCHED" first || exit 30
register_patch_file 20 16 "$STOCK" "$PATCHED" overlap && exit 31
[ "$MODULE_LOAD_FAILED" = 1 ] || exit 32
''',
                {"STOCK": str(stock), "PATCHED": str(patched)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ranges_require_aligned_exact_sized_safe_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock, patched, _binary = self.fixture(root)
            cases = (
                f'register_patch_file 9 16 "{stock}" "{patched}" bad',
                f'register_patch_file 8 15 "{stock}" "{patched}" bad',
                f'register_patch_file 8 20 "{stock}" "{patched}" bad',
                'register_patch_file 8 16 /etc/passwd /etc/passwd bad',
            )
            for command in cases:
                with self.subTest(command=command):
                    result = run_shell(command + " && exit 21\nexit 0\n", {})
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_orchestrator_applies_verifies_and_rolls_back_both_patch_kinds(self):
        required = (
            "PATCH_FILE_TABLE", "guarded_patch_file_state", "write_files",
            "verify_files", "write_patches patched", "write_patches previous",
            "write_patches stock", "verify_recovery_patches_or_halt stock",
            'recovery_failed=$(verify_patches "$1")',
            'extract_guarded_words "$TMP" ||',
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, AUTOEXEC)


if __name__ == "__main__":
    unittest.main()
