#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""The hook must not need a symbol rbp cannot supply.

Both hook builds are `-nostdlib` shared objects that resolve their imports
against whatever rbp already has loaded. An import rbp does not export is not a
link error and not a warning: the library simply fails to load at run time, the
mod goes silent, and what is drawn is stock output that looks like a
different bug entirely. That failure has cost this project two long debugging
rounds -- once on a missing definition in the shim, once on `bcmp`.

`bcmp` is the specific trap. At -O2 clang rewrites `memcmp(a, b, n) == 0` into a
call to `bcmp`, which this glibc does not export. The rewrite happens in the
optimiser, after every diagnostic the front end could have produced, so nothing
says a word. `-fno-builtin-memcmp` in the Makefile suppresses it; this test is
what keeps that flag from being dropped by someone tidying up.
"""

from __future__ import annotations

import pathlib
import struct
import subprocess
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parent.parent
BUILD = REPOSITORY / "build"
HOOKS = ("librx3_core.so", "librx3_core_payload.so")

# Everything rbp itself is known to export. A new name here is a deliberate
# decision -- confirm rbp really provides it before adding one.
ALLOWED = {
    "__aeabi_uidiv", "__aeabi_uldivmod",
    "close", "getenv", "gettimeofday", "lseek",
    "memcmp", "memcpy", "memset",
    "mmap", "mprotect", "munmap", "open",
    "pthread_create", "pthread_detach",
    "read", "strlen", "sysconf", "usleep", "write",
}

# Names that must never appear, with why, so a failure explains itself.
FORBIDDEN = {
    "bcmp": "clang rewrote memcmp(...) == 0; restore -fno-builtin-memcmp",
    "__memcmp_chk": "fortified memcmp is not exported by rbp's libc",
    "memcmp@GLIBC_2.4": "versioned memcmp will not bind against rbp",
}


def undefined_symbols(path: pathlib.Path) -> set[str]:
    """Undefined names in an ARM ELF .dynsym, read without external tools."""
    data = path.read_bytes()
    if data[:4] != b"\x7fELF" or data[4] != 1:
        raise AssertionError(f"{path.name}: not a 32-bit ELF")
    e_shoff, = struct.unpack_from("<I", data, 0x20)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", data, 0x2E)

    def section(index: int) -> tuple[int, int, int, int, int]:
        base = e_shoff + index * e_shentsize
        sh_type, = struct.unpack_from("<I", data, base + 4)
        sh_offset, sh_size, sh_link = struct.unpack_from("<III", data, base + 0x10)
        sh_entsize, = struct.unpack_from("<I", data, base + 0x24)
        return sh_type, sh_offset, sh_size, sh_link, sh_entsize

    names: set[str] = set()
    for index in range(e_shnum):
        sh_type, sh_offset, sh_size, sh_link, sh_entsize = section(index)
        if sh_type != 11 or not sh_entsize:          # SHT_DYNSYM
            continue
        _, str_offset, _, _, _ = section(sh_link)
        for entry in range(sh_size // sh_entsize):
            base = sh_offset + entry * sh_entsize
            st_name, _, _, _, _, st_shndx = struct.unpack_from("<IIIBBH", data, base)
            if st_shndx != 0 or not st_name:          # SHN_UNDEF only
                continue
            end = data.index(b"\0", str_offset + st_name)
            names.add(data[str_offset + st_name:end].decode("ascii"))
    return names


class HookSymbolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Build rather than trusting whatever is lying in build/, so the test
        # measures the Makefile's current flags and not a stale artefact.
        result = subprocess.run(
            ["make", "hook", "payload-hook"],
            cwd=REPOSITORY, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise unittest.SkipTest(
                f"cannot build the hook here: {result.stderr.strip()[-200:]}"
            )

    def test_no_forbidden_imports(self) -> None:
        for name in HOOKS:
            with self.subTest(hook=name):
                symbols = undefined_symbols(BUILD / name)
                for bad, why in FORBIDDEN.items():
                    self.assertNotIn(bad, symbols, f"{name} imports {bad}: {why}")

    def test_imports_stay_within_the_known_set(self) -> None:
        for name in HOOKS:
            with self.subTest(hook=name):
                symbols = undefined_symbols(BUILD / name)
                unexpected = symbols - ALLOWED
                self.assertEqual(
                    unexpected, set(),
                    f"{name} imports {sorted(unexpected)}, which rbp may not "
                    f"export; confirm each one before widening ALLOWED",
                )

    def test_the_flag_that_prevents_bcmp_is_still_set(self) -> None:
        makefile = (REPOSITORY / "Makefile").read_text(encoding="utf-8")
        self.assertIn(
            "-fno-builtin-memcmp", makefile,
            "dropping -fno-builtin-memcmp lets clang emit bcmp again",
        )


if __name__ == "__main__":
    unittest.main()
