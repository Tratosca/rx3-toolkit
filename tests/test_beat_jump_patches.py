# SPDX-License-Identifier: MPL-2.0
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).parents[1]
PATCH_32_BARS = REPOSITORY / "runtime/modules/beatjump/beatjump-32bars/1.19/patch.py"
PATCH_NO_QUANTIZE = REPOSITORY / "runtime/modules/beatjump/beatjump-no-quantize/1.19/patch.py"


def load_patch_table(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PATCHES


class BeatJumpPatchTests(unittest.TestCase):
    def test_patch_sets_are_independent_and_reversible(self):
        patch_32_bars = load_patch_table(PATCH_32_BARS, "patch_32_bars")
        patch_no_quantize = load_patch_table(PATCH_NO_QUANTIZE, "patch_no_quantize")
        self.assertEqual(len(patch_32_bars), 12)
        self.assertEqual(len(patch_no_quantize), 1)
        self.assertTrue(
            {entry[0] for entry in patch_32_bars}.isdisjoint(
                {entry[0] for entry in patch_no_quantize}
            )
        )

        patches = patch_32_bars + patch_no_quantize
        image = bytearray(max(entry[0] for entry in patches) + 4)
        for offset, stock, _patched, _label in patches:
            image[offset:offset + 4] = bytes.fromhex(stock)

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            stock = directory / "rbp.stock"
            bars = directory / "rbp.32bars"
            complete = directory / "rbp.complete"
            bars_restored = directory / "rbp.32bars-restored"
            stock_restored = directory / "rbp.stock-restored"
            stock.write_bytes(image)

            commands = [
                [sys.executable, PATCH_32_BARS, stock, "-o", bars],
                [sys.executable, PATCH_NO_QUANTIZE, bars, "-o", complete],
                [sys.executable, PATCH_NO_QUANTIZE, complete, "--revert", "-o", bars_restored],
                [sys.executable, PATCH_32_BARS, bars_restored, "--revert", "-o", stock_restored],
            ]
            for command in commands:
                subprocess.run([str(argument) for argument in command], check=True, capture_output=True)

            self.assertEqual(stock_restored.read_bytes(), stock.read_bytes())


if __name__ == "__main__":
    unittest.main()
