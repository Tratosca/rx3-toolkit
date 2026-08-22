# SPDX-License-Identifier: MPL-2.0
"""A name says what a file is for, never where it came from.

The resolver that carried this rule moved to the emulator repository with the
scripts that used it. The rule did not move: it is a commitment in LEGAL.md,
and it applies to every path and every identifier here. `extracted_rbp` names
an act; `rbp` names a file. Only one of the two is anybody's business.
"""
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]

# Each word is refused where it qualifies a noun, because that is where it
# stops describing a file and starts describing how someone came by it.
ORIGIN = re.compile(
    r"\b(extracted|decrypted|dumped|ripped|leaked|unpacked|cracked)"
    r"[_-]?[a-z0-9]",
    re.I,
)


def tracked_files():
    listing = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return listing.stdout.split()


class NamesTests(unittest.TestCase):
    def test_no_tracked_path_asserts_an_origin(self):
        offences = [path for path in tracked_files() if ORIGIN.search(path)]
        self.assertEqual(offences, [], "path names an origin")

    def test_no_python_name_asserts_an_origin(self):
        offences = []
        for path in tracked_files():
            if not path.endswith(".py"):
                continue
            text = (ROOT / path).read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                found = re.search(
                    r"^\s*(?:def|class)\s+\w*|"
                    r"^\s*([A-Za-z_]\w*)\s*=", line
                )
                if found and ORIGIN.search(line.split("#")[0]):
                    offences.append(f"{path}:{number}: {line.strip()[:70]}")
        self.assertEqual(offences, [], "identifier names an origin")

    def test_the_guard_would_actually_catch_a_regression(self):
        """A guard nobody has seen fail is a guard nobody knows works."""
        for name in ("extracted_rbp", "tools/dumped-imagedata", "decryptedKey",
                     "ripped_assets", "unpacked_rootfs"):
            with self.subTest(name=name):
                self.assertTrue(ORIGIN.search(name), f"guard missed {name!r}")
        for name in ("rbp", "imagedata", "extract_labels", "unpack(", "extraction"):
            with self.subTest(name=name):
                self.assertIsNone(ORIGIN.search(name), f"guard over-reached on {name!r}")


if __name__ == "__main__":
    unittest.main()
