# SPDX-License-Identifier: MPL-2.0
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from app.stems.overcue_loudness import Measurement, gains, measure


class CeilingTests(unittest.TestCase):
    def test_cancellation_cannot_make_selection_louder_than_full_mix(self):
        full = Measurement(tuple([(-23., -25.)] * 50), .3)
        loud = Measurement(tuple([(-12., -14.)] * 50), .8)
        quiet = Measurement(tuple([(-33., -35.)] * 50), .1)
        values = {'full-mix': full, 'drums': loud, 'vocal': quiet}
        result = gains(values, .9)
        self.assertEqual(result['full-mix'], 1.)
        self.assertEqual(result['vocal'], 1.)
        self.assertLess(result['drums'], .29)
        for name, value in values.items():
            gain = result[name]
            self.assertLessEqual(gain, 1.)
            self.assertLessEqual(value.integrated(20*math.log10(gain)), full.integrated()+1e-9)

    def test_silence_and_short_track(self):
        silent = Measurement(tuple([(-120., -120.)] * 2), 0.)
        tone = Measurement(tuple([(-20., -30.)] * 2), .2)
        self.assertEqual(gains({'full-mix': silent, 'vocal': tone, 'drums': silent}, 1.),
                         {'full-mix': 1., 'vocal': 0., 'drums': 1.})

    def test_integrated_gate_recomputed_after_attenuation(self):
        value = Measurement(tuple([(-75., -75.)]*3+[(-20., -20.)]*20+[(-68., -68.)]*20), .5)
        gain = gains({'full-mix': Measurement(tuple([(-50., -50.)]*43), .1), 'vocal': value}, .9)['vocal']
        self.assertLessEqual(value.integrated(20*math.log10(.9*gain)), -50+20*math.log10(.9)-.099)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_ffmpeg_windows_and_partial_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tone.f32'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=1000:duration=1.05:sample_rate=96000',
                            '-ac', '2', '-f', 'f32le', str(path)], check=True)
            value = measure(path)
            self.assertEqual(len(value.windows), 11)
            self.assertGreater(value.peak, .08)
            self.assertLess(value.peak, .13)
            self.assertAlmostEqual(value.windows[3][0]-value.windows[0][0],
                                   10*math.log10(4), delta=.04)
            self.assertGreater(value.integrated(), -30)
