# SPDX-License-Identifier: MPL-2.0
import pathlib
import sys
import unittest

try:
    import numpy as np
    import scipy  # noqa: F401
except ImportError:
    np = None

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(np is not None, "numpy and scipy live in the separation runtime")
class BankTests(unittest.TestCase):
    def test_a_length_ending_on_a_millisecond_boundary_leaves_an_empty_last_cell(self):
        sys.path.insert(0, str(ROOT / "app/stems"))
        self.addCleanup(sys.path.remove, str(ROOT / "app/stems"))
        import wave_memory

        # 101 ms start at sample 4455, which is also where this audio stops, so
        # the last millisecond cell holds nothing. About one track in forty.
        frames = 4455
        noise = np.random.default_rng(1).uniform(-.5, .5, (frames, 2)).astype("<f4")
        columns = wave_memory.columns_from_blocks([noise], frames)
        self.assertEqual(sorted(columns), [b"PWV3", b"PWV5", b"PWV7"])


if __name__ == "__main__":
    unittest.main()
