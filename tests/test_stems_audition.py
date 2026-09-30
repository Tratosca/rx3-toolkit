# SPDX-License-Identifier: MPL-2.0
import array
import base64
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave

from app.stems import audition, stem, mixing


@unittest.skipUnless(shutil.which("ffmpeg"), "audio decoder required")
class AuditionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.source = self.root / "track.wav"
        self.pcm = array.array("h", [1000, -2000] * 1000)
        with wave.open(str(self.source), "wb") as target:
            target.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
            target.writeframes(self.pcm.tobytes())
        (self.root / "RX3_STEMS").mkdir()

    def role(self, role, values):
        target = self.root / "RX3_STEMS" / ("track" + stem.ROLE_SUFFIXES[role])
        target.write_bytes(stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, len(values) // 2, b"\0" * 32) + values.tobytes())
        return target

    def settled(self, mask):
        values = [float(bool(mask & (1 << i))) for i in range(4)]
        return {"mask": mask, "state": mixing.MixState(values, values, values).as_dict()}

    def read(self, result):
        return array.array("f", base64.b64decode(result["audio"])[44:])

    def test_zero_vocal_makes_instrumental_equal_to_mix(self):
        self.role("vocals", array.array("h", [0] * len(self.pcm)))
        result = audition.on_drive(self.source, self.root, self.settled(1))
        self.assertEqual(self.read(result), array.array("f", (value / 32768 for value in self.pcm)))

    def test_mix_equal_to_voice_leaves_no_instrumental(self):
        self.role("vocals", self.pcm)
        result = audition.on_drive(self.source, self.root, self.settled(1))
        self.assertFalse(any(self.read(result)))

    def test_excerpt_at_end_is_clamped(self):
        self.role("vocals", self.pcm)
        result = audition.on_drive(self.source, self.root, "original", 900 / 44100, 30)
        self.assertEqual(len(self.read(result)), 200)
        result = audition.on_drive(self.source, self.root, "original", 1, 30)
        self.assertEqual(result["seconds"], 0)
        self.assertEqual(len(self.read(result)), 0)

    def test_mismatched_optional_length_is_rejected_like_the_loader(self):
        self.role("vocals", self.pcm)
        self.role("drums", self.pcm[:-2])
        self.role("bass", self.pcm)
        result = audition.on_drive(self.source, self.root, "original")
        self.assertEqual(result["available"], 3)
        self.assertEqual(result["rejected"], ["drums"])

    def test_missing_voice_has_an_empty_state(self):
        self.role("drums", self.pcm)
        result = audition.on_drive(self.source, self.root, "original")
        self.assertEqual(result["available"], 0)
        self.assertIsNone(result["audio"])


class BrowserAuditionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "browser harness requires Node")
    def test_selection_and_seek_preserve_position_and_mixer_state(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        subprocess.run(["node", "tests/stems_preview.cjs"], cwd=root, check=True, timeout=30)
