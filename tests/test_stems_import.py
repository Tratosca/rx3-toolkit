# SPDX-License-Identifier: MPL-2.0
"""Imports must fail before touching a drive when their audio is unsuitable."""
import array
import math
import pathlib
import random
import shutil
import sys
import tempfile
import time
import unittest
import wave

from app.localization import LocalizedError
from app.rx3_stems import importing, stem


def signal(frames, rate=44100):
    randomizer = random.Random(721)
    state = 0.0
    pcm = array.array("h")
    for i in range(frames):
        state = state * 0.83 + randomizer.uniform(-1, 1) * 0.17
        value = int(18000 * state + 3500 * math.sin(2 * math.pi * 379 * i / rate))
        pcm.extend((value, value))
    return pcm


def wav(path, pcm, rate=44100, channels=2):
    payload = array.array("h", pcm)
    if sys.byteorder != "little":
        payload.byteswap()
    with wave.open(str(path), "wb") as target:
        target.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        target.writeframes(payload.tobytes())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "audio tools required")
class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pcm = signal(44100 * 12)

    def run_import(self, modify=lambda pcm: pcm, suffix=".wav"):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source, supplied = root / "mix.wav", root / ("voice" + suffix)
            wav(source, self.pcm)
            wav(supplied, modify(array.array("h", self.pcm)))
            outputs, report = importing.prepare(source, {"vocals": supplied}, root)
            payload = outputs["vocals"].read_bytes()[64:]
            return payload, report

    def test_exact_stem_is_accepted_without_shift(self):
        payload, report = self.run_import()
        self.assertEqual(report["roles"]["vocals"]["shift"], 0)
        self.assertFalse(report["roles"]["vocals"]["gainCertified"])
        self.assertEqual(len(payload), len(self.pcm) * 2)

    def test_constant_37_frames_is_corrected_and_reported(self):
        payload, report = self.run_import(lambda pcm: array.array("h", [0] * 74) + pcm[:-74])
        self.assertEqual(report["roles"]["vocals"]["shift"], 37)
        self.assertAlmostEqual(report["roles"]["vocals"]["milliseconds"], 37 * 1000 / 44100)
        expected = self.pcm[:-74].tobytes()
        self.assertEqual(payload[:len(expected)], expected)

    def test_drifting_alignment_is_refused(self):
        def drift(pcm):
            result = array.array("h")
            frames = len(pcm) // 2
            for i in range(frames):
                at = max(0, i - i // 5000)
                result.extend(pcm[2 * at:2 * at + 2])
            return result
        with self.assertRaises(LocalizedError) as caught:
            self.run_import(drift)
        self.assertIn(caught.exception.message.key, ("stems.importDrift", "stems.importAlignment"))

    def test_gain_point_nine_is_refused_by_the_heuristic(self):
        with self.assertRaises(LocalizedError) as caught:
            self.run_import(lambda pcm: array.array("h", (int(v * 0.9) for v in pcm)))
        self.assertEqual(caught.exception.message.key, "stems.importGain")

    def test_short_stem_is_refused(self):
        with self.assertRaises(LocalizedError) as caught:
            self.run_import(lambda pcm: pcm[:-2])
        self.assertEqual(caught.exception.message.key, "stems.importShort")

    def test_extra_1105_frames_at_start_are_cut(self):
        payload, report = self.run_import(lambda pcm: array.array("h", [0] * 2210) + pcm)
        self.assertEqual(report["roles"]["vocals"]["trimStart"], 1105)
        self.assertEqual(report["roles"]["vocals"]["trimEnd"], 0)
        self.assertEqual(payload, self.pcm.tobytes())

    def test_mp3_extension_is_refused_even_if_content_is_lossless(self):
        with self.assertRaises(LocalizedError) as caught:
            self.run_import(suffix=".mp3")
        self.assertEqual(caught.exception.message.key, "stems.importLossless")

    def test_mono_is_duplicated_and_resampled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            original = root / "mono.wav"
            pcm = signal(48000 * 12, 48000)[::2]
            wav(original, pcm, rate=48000, channels=1)
            outputs, report = importing.prepare(original, {"vocals": original}, root)
            audio = array.array("h", outputs["vocals"].read_bytes()[64:])
            self.assertEqual(audio[::2], audio[1::2])
            self.assertEqual(report["frames"], 44100 * 12)
