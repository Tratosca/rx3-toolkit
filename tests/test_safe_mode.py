# SPDX-License-Identifier: MPL-2.0
"""The shipped probe must recognize both deck SHIFT bits before startup work."""

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "mod/lib/safe-mode.sh"
AUTOEXEC = ROOT / "mod/autoexec.sh"


class SafeModeTests(unittest.TestCase):
    def probe(self, frame: bytes) -> subprocess.CompletedProcess[bytes]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eup.frame"
            path.write_bytes(frame)
            return subprocess.run(
                ["sh", str(PROBE), str(path)], capture_output=True, check=False
            )

    def test_both_shift_buttons_bypass_mods(self):
        for length in (100, 104):
            with self.subTest(length=length):
                idle = bytearray(length)
                idle[:4] = bytes((0, 0, 0, 1))
                normal = self.probe(idle)
                self.assertEqual(normal.returncode, 0)
                self.assertIn(b"SHIFT released", normal.stdout)
                for offset in (18, 34):
                    pressed = bytearray(idle)
                    pressed[offset] |= 1
                    result = self.probe(pressed)
                    self.assertEqual(result.returncode, 10)
                    self.assertIn(b"SHIFT held", result.stdout)

    def test_invalid_or_unavailable_frame_fails_closed(self):
        bad_header = self.probe(bytes(100))
        self.assertEqual(bad_header.returncode, 11)
        self.assertIn(b"panel header", bad_header.stdout)
        short = self.probe(bytes((0, 0, 0, 1)))
        self.assertEqual(short.returncode, 11)
        self.assertIn(b"panel frame length=4", short.stdout)
        self.assertIn(b"records in", short.stdout)
        result = subprocess.run(
            ["sh", str(PROBE), "/nonexistent/eup"], check=False
        )
        self.assertEqual(result.returncode, 11)

    def test_probe_precedes_runtime_side_effects(self):
        source = AUTOEXEC.read_text()
        probe = PROBE.read_text()
        self.assertIn('bs=104 count=1', probe)
        self.assertIn('hexdump -v -e', probe)
        self.assertLess(source.index("sh /mnt/iso/lib/safe-mode.sh"),
                        source.index("OUT=\"$USB/RX3_RUNTIME\""))
        self.assertLess(source.index("sh /mnt/iso/lib/safe-mode.sh"),
                        source.index("mkdir -p \"$OUT\""))


if __name__ == "__main__":
    unittest.main()
