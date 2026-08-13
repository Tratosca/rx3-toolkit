# SPDX-License-Identifier: MPL-2.0
"""Cross-checks for facts that are stated twice in two different languages.

Each duplication below is deliberate: the device applies patches from shell at
boot, while the offline patcher rewrites a file on a workstation, and the
sidecar container is written by Python but parsed by C on the deck. Nothing in
the build makes the two copies agree, so these tests do.

Modules are located through their manifest rather than by path, so moving a
module directory does not silently disable a guard.
"""

import re
import struct
import sys
import unittest
from importlib import import_module
from pathlib import Path

REPOSITORY = Path(__file__).parents[1]
PATCHER_PACKAGE = REPOSITORY / "tools/rx3_patcher"
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "tools"))

from rx3_runtime.build import discover_patches  # noqa: E402
from rx3_stems import sidecar  # noqa: E402


REGISTER_PATCH = re.compile(
    r"^register_patch\s+(\d+)\s+'([^']*)'\s+'([^']*)'\s+(\S+)",
    re.MULTILINE,
)
OCTAL_BYTE = re.compile(r"\\([0-7]{1,3})")
C_FIELD = re.compile(r"^\s*(\w+)\s+(\w+)\s*(?:\[(\d+)\])?\s*;", re.MULTILINE)
C_SCALARS = {"uint8_t": "B", "uint32_t": "I", "uint64_t": "Q"}


def shell_bytes(literal):
    """Decode the octal escapes `register_patch` hands to printf."""
    decoded = OCTAL_BYTE.sub(lambda match: chr(int(match.group(1), 8)), literal)
    return decoded.encode("latin-1")


def modules_by_id():
    return {patch.patch_id: patch for patch in discover_patches()}


class OfflinePatcherTests(unittest.TestCase):
    """The offline patchers and `module.sh` must rewrite the same words."""

    def test_offline_tables_match_the_device_registrations(self):
        definitions = modules_by_id()
        checked = 0
        for patcher in sorted(PATCHER_PACKAGE.glob("*.py")):
            if patcher.name.startswith("_") or patcher.name == "patchlib.py":
                continue
            imported = import_module(f"tools.rx3_patcher.{patcher.stem}")
            patch_id = imported.MODULE_ID

            self.assertIn(
                patch_id, definitions,
                f"{patcher.name}: MODULE_ID {patch_id!r} matches no manifest",
            )
            definition = definitions[patch_id]
            offline = {
                offset: (bytes.fromhex(stock), bytes.fromhex(patched))
                for offset, stock, patched, _label in imported.PATCHES
            }

            module_script = definition.directory / "module.sh"
            device = {
                int(offset): (shell_bytes(stock), shell_bytes(patched))
                for offset, stock, patched, _label in REGISTER_PATCH.findall(
                    module_script.read_text(encoding="utf-8")
                )
            }

            with self.subTest(module=patch_id):
                self.assertEqual(
                    sorted(offline), sorted(device),
                    f"{patch_id}: patch.py and module.sh disagree on which "
                    f"offsets are patched",
                )
                for offset in sorted(offline):
                    self.assertEqual(
                        offline[offset], device[offset],
                        f"{patch_id}: offset {offset} (0x{offset:X}) has "
                        f"different stock/patched words in patch.py and module.sh",
                    )
                for stock, patched in offline.values():
                    self.assertEqual(len(stock), 4)
                    self.assertEqual(len(patched), 4)
                    self.assertNotEqual(stock, patched)
            checked += 1

        self.assertTrue(checked, "no offline patcher was found to cross-check")


class SidecarHeaderTests(unittest.TestCase):
    """The `.rx3stem` header is declared in Python and parsed in C."""

    def test_declared_layout_matches_the_device_struct(self):
        declaration = modules_by_id()["stems"].directory / "rx3_stems_decl.h"
        text = declaration.read_text(encoding="utf-8")
        body = re.search(
            r"struct\s+__attribute__\(\(packed\)\)\s+sidecar_header\s*\{(.*?)\}",
            text, re.DOTALL,
        )
        self.assertIsNotNone(body, "sidecar_header is no longer declared in C")

        fields = []
        for ctype, _name, count in C_FIELD.findall(body.group(1)):
            if ctype == "char":
                fields.append(f"{count or 1}s")
            else:
                self.assertIn(ctype, C_SCALARS, f"unmapped C type {ctype}")
                code = C_SCALARS[ctype]
                # A uint8_t array is an opaque blob on both sides, not a count.
                fields.append(f"{count}s" if count and code == "B" else code * int(count or 1))

        self.assertEqual(
            "<" + "".join(fields), sidecar.HEADER.format,
            "the C struct and sidecar.HEADER no longer describe the same bytes",
        )
        self.assertEqual(struct.calcsize("<" + "".join(fields)), sidecar.HEADER.size)

    def test_magic_is_the_one_the_core_compares(self):
        hook = (modules_by_id()["core"].directory / "rx3_core_hook.c").read_text(
            encoding="utf-8"
        )
        compared = re.search(r'memcmp\(header\.magic,\s*"([^"]+)",\s*(\d+)\)', hook)
        self.assertIsNotNone(compared, "the core no longer compares the sidecar magic")
        literal, length = compared.group(1), int(compared.group(2))
        self.assertEqual(sidecar.MAGIC[:length].decode("ascii"), literal)
        self.assertLessEqual(length, len(sidecar.MAGIC))


if __name__ == "__main__":
    unittest.main()
