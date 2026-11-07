# SPDX-License-Identifier: MPL-2.0
"""Runtime-built hooks must only import symbols the RX3 can resolve."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.runtime.build import _undefined_elf32_symbols, compile_arm_hook


SOURCE = r"""
typedef unsigned int size_t;
extern int memcmp(const void *, const void *, size_t);

__attribute__((visibility("default")))
int same_bytes(const void *left, const void *right, size_t length)
{
    return memcmp(left, right, length) == 0;
}
"""


class RuntimeHookSymbolTests(unittest.TestCase):
    def test_optimizer_does_not_replace_memcmp_with_bcmp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "hook.c"
            output = root / "hook.so"
            source.write_text(SOURCE, encoding="utf-8")

            compile_arm_hook(source, output)

            imports = _undefined_elf32_symbols(output.read_bytes())
            self.assertNotIn("bcmp", imports)
            self.assertNotIn("__memcmp_chk", imports)


if __name__ == "__main__":
    unittest.main()
