# SPDX-License-Identifier: MPL-2.0
"""The identity check must recognise an rbp this runtime has already patched.

Reinserting the drive meets a binary carrying the writes of the previous run.
Hashing it whole compares it against states nobody registered, so the guarded
words are put back to stock first. These drive the real shell functions of
`mod/lib/module-api.sh` against a synthetic binary, over every combination of
the modules that write to rbp.
"""

from __future__ import annotations

import hashlib
import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_API = ROOT / "mod/lib/module-api.sh"
MODULES = ROOT / "mod/modules"

HARNESS = r"""
say() { :; }
PATCH_TABLE=""
PATCH_OFFSETS=""
LOADED_MODULES=""
CURRENT_MODULE=""
MODULE_LOAD_FAILED=0
. "$1"
"""


def patch_words(module: str) -> list[tuple[int, bytes, bytes]]:
    """The (offset, stock, patched) triples a module registers on device."""
    words = []
    for line in (MODULES / module / "1.19/module.sh").read_text().splitlines():
        if not line.startswith("register_patch "):
            continue
        _, offset, stock, patched, _label = line.split(maxsplit=4)
        words.append((
            int(offset),
            octal_escapes(stock.strip("'")),
            octal_escapes(patched.strip("'")),
        ))
    return words


def octal_escapes(literal: str) -> bytes:
    """Decode the `\\314\\065` form the module tables are written in."""
    return bytes(int(part, 8) for part in literal.split("\\") if part)


PATCHING_MODULES = ["core", "beatjump-no-quantize", "beatjump-32bars"]
WORDS = {module: patch_words(module) for module in PATCHING_MODULES}


def run_shell(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-s", "--", str(MODULE_API)],
        input=HARNESS + body,
        text=True,
        capture_output=True,
        check=False,
    )


def registrations(selection: tuple[str, ...]) -> str:
    lines = ["module_begin holder holder"]
    for module in selection:
        for offset, stock, patched in WORDS[module]:
            lines.append(
                f"register_patch {offset} "
                f"'{escape(stock)}' '{escape(patched)}' {module}-word"
            )
    return "\n".join(lines)


def escape(word: bytes) -> str:
    return "".join(f"\\{byte:03o}" for byte in word)


class NormalisedIdentityTests(unittest.TestCase):
    """Every state a run of this runtime can leave rbp in must normalise back."""

    # Past the highest registered offset, and deliberately not a multiple of
    # the page the untouched spans stream in.
    SIZE = 6_000_003

    def stock_binary(self, directory: Path) -> Path:
        """A binary carrying the stock word at each registered offset."""
        image = bytearray(
            (index * 37 + 11) % 256 for index in range(self.SIZE)
        )
        for module in PATCHING_MODULES:
            for offset, stock, _patched in WORDS[module]:
                image[offset:offset + 4] = stock
        path = directory / "rbp"
        path.write_bytes(image)
        return path

    def normalised(self, binary: Path, selection: tuple[str, ...]) -> str:
        with tempfile.TemporaryDirectory() as workspace:
            result = run_shell(
                f"{registrations(selection)}\n"
                f'extract_guarded_words "{workspace}" || exit 20\n'
                f'normalized_rbp_sha1 "{binary}" "{workspace}"\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

    def test_every_reachable_patched_state_normalises_to_the_stock_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            binary = self.stock_binary(directory)
            stock_hash = hashlib.sha1(binary.read_bytes()).hexdigest()

            # The selection decides which modules are in the image; every
            # subset of the three that write to rbp is a state a build can
            # reach, and each has to be recognised on reinsertion.
            for count in range(len(PATCHING_MODULES) + 1):
                for applied in itertools.combinations(PATCHING_MODULES, count):
                    image = bytearray(binary.read_bytes())
                    for module in applied:
                        for offset, _stock, patched in WORDS[module]:
                            image[offset:offset + 4] = patched
                    patched_binary = directory / "rbp-patched"
                    patched_binary.write_bytes(image)

                    # The image only carries the tables of what it ships, so
                    # the runtime normalises with the selection it was built
                    # with, not with every patch that exists.
                    self.assertEqual(
                        self.normalised(patched_binary, applied),
                        stock_hash,
                        f"applied={applied or ('none',)}",
                    )

    def test_a_stock_binary_normalises_to_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            binary = self.stock_binary(directory)
            self.assertEqual(
                self.normalised(binary, tuple(PATCHING_MODULES)),
                hashlib.sha1(binary.read_bytes()).hexdigest(),
            )

    def test_a_word_that_is_neither_stock_nor_patched_still_normalises(self):
        """Normalisation cannot tell a foreign write from ours, which is why
        the word-by-word audit runs after it and stops before any write."""
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            binary = self.stock_binary(directory)
            stock_hash = hashlib.sha1(binary.read_bytes()).hexdigest()
            image = bytearray(binary.read_bytes())
            offset = WORDS["core"][0][0]
            image[offset:offset + 4] = b"\xde\xad\xbe\xef"
            foreign = directory / "rbp-foreign"
            foreign.write_bytes(image)
            self.assertEqual(self.normalised(foreign, ("core",)), stock_hash)

    def test_a_change_outside_a_guarded_word_is_still_caught(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            binary = self.stock_binary(directory)
            stock_hash = hashlib.sha1(binary.read_bytes()).hexdigest()
            image = bytearray(binary.read_bytes())
            image[WORDS["core"][0][0] + 64] ^= 0xFF
            elsewhere = directory / "rbp-elsewhere"
            elsewhere.write_bytes(image)
            self.assertNotEqual(
                self.normalised(elsewhere, tuple(PATCHING_MODULES)), stock_hash
            )

    def test_an_unaligned_offset_is_refused_rather_than_served_slowly(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            binary = self.stock_binary(directory)
            with tempfile.TemporaryDirectory() as workspace:
                result = run_shell(
                    "module_begin holder holder\n"
                    "register_patch 4098 '\\001\\002\\003\\004' "
                    "'\\005\\006\\007\\010' unaligned\n"
                    f'extract_guarded_words "{workspace}"\n'
                    f'normalized_rbp_sha1 "{binary}" "{workspace}" && exit 21\n'
                    "exit 0\n"
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
