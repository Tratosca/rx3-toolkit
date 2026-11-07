# SPDX-License-Identifier: MPL-2.0
"""Which prepared stems came out early, and must be made again."""

import pathlib
import tempfile
import unittest

from app.stems import stem


def mp3(signature: bytes | None, delay: int = 576) -> bytes:
    """One MPEG-1 Layer III 320 kbps stereo frame, with an Info tag when `signature` is set."""
    frame = bytearray(1044)
    frame[:4] = bytes.fromhex("fffbe000")
    if signature is not None:
        tag = 4 + 32
        frame[tag:tag + 8] = b"Info" + (15).to_bytes(4, "big")
        extension = tag + 8 + 4 + 4 + 100 + 4
        frame[extension:extension + 9] = signature.ljust(9, b"\0")
        frame[extension + 21:extension + 24] = bytes([delay >> 4, (delay & 15) << 4, 0])
    return b"ID3\x04\0\0\0\0\0\0" + bytes(frame) + bytes.fromhex("fffbe000") + bytes(1040)


class GridTests(unittest.TestCase):
    def differs(self, data: bytes) -> bool:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "track.mp3"
            path.write_bytes(data)
            return stem.separator_grid_differs(path)

    def test_a_delay_ffmpeg_ignores_marks_the_stem_early(self):
        # Seen in the field: LAME 3.100 signed "Lame3.100", 576 frames of delay.
        self.assertTrue(self.differs(mp3(b"Lame3.100")))

    def test_sources_both_decoders_agree_on_keep_their_stems(self):
        self.assertFalse(self.differs(mp3(b"LAME3.100")))
        self.assertFalse(self.differs(mp3(b"Lavc61.19")))
        self.assertFalse(self.differs(mp3(None)))
        self.assertFalse(self.differs(mp3(b"Lame3.100", delay=0)))
        self.assertFalse(self.differs(b"RIFF" + bytes(64)))


if __name__ == "__main__":
    unittest.main()
