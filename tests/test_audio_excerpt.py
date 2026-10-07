from array import array
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audio_excerpt import RATE, analyze_pcm16_mono  # noqa: E402


class ExcerptTests(unittest.TestCase):
    def test_source_window_energy_and_timing(self):
        samples = array("h")
        for i in range(RATE):
            gain = 0.03 if i < RATE // 2 else 0.4
            samples.append(int(32767 * gain * math.sin(2 * math.pi * 100 * i / RATE)))
        if sys.byteorder != "little":
            samples.byteswap()
        result = analyze_pcm16_mono(samples.tobytes(), 30.0)
        self.assertEqual(len(result["windows"]), 4)
        self.assertEqual(result["windows"][0]["start_s"], 30.0)
        self.assertEqual(result["windows"][-1]["end_s"], 31.0)
        self.assertGreater(result["windows"][2]["rms_dbfs"],
                           result["windows"][0]["rms_dbfs"] + 15)
        self.assertGreater(result["windows"][2]["onset"],
                           result["windows"][1]["onset"])
        self.assertGreater(result["windows"][2]["low"],
                           result["windows"][2]["high"])
        self.assertFalse(result["live_audio"])

    def test_empty_and_oversized_are_rejected(self):
        with self.assertRaises(ValueError):
            analyze_pcm16_mono(b"", 0)
        with self.assertRaises(ValueError):
            analyze_pcm16_mono(b"\0" * (RATE * 6 * 2), 0)


if __name__ == "__main__":
    unittest.main()
