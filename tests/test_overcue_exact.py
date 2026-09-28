# SPDX-License-Identifier: MPL-2.0
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from app.stems.overcue_exact import f32
from app.stems.overcue_loudness import Measurement, gains

HELPER = Path(__file__).resolve().parents[1] / 'build/overcue-audio/release/rx3-overcue-audio'


class ExactPolicyTests(unittest.TestCase):
    def test_partial_tail_does_not_enter_integrated_gate(self):
        windows = tuple([(-20., -20.)] * 4 + [(0., 0.)])
        value = Measurement(windows, .5, 4)
        self.assertAlmostEqual(value.integrated(), -20.)
        self.assertEqual(len(value.windows), 5)

    def test_exact_ceiling_does_not_attenuate_identical_roles(self):
        value = Measurement(tuple([(-20., -25.)] * 40), .5, 40)
        result = gains({'full-mix': value, 'vocal': value}, f32(.75), rounded_metadata=False)
        self.assertEqual(result, {'full-mix': 1., 'vocal': 1.})

    def test_absolute_gate_excludes_its_boundary(self):
        value = Measurement(tuple([(-70., -70.)] * 4), .0001, 4)
        self.assertEqual(value.integrated(), -math.inf)


@unittest.skipUnless(HELPER.is_file(), 'Build native/overcue-audio first')
class NativeAudioTests(unittest.TestCase):
    def run_helper(self, *args):
        return subprocess.run([str(HELPER), *map(str, args)], check=True,
                              capture_output=True, text=True)

    def test_quantization_clamps_and_rounds_half_away_from_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            incoming, output = Path(temporary) / 'in.f32', Path(temporary) / 'out.s16'
            values = [2., -2., 0.5, -0.5, 0., -0., 1., -1.]
            incoming.write_bytes(struct.pack('<8f', *values))
            self.run_helper('quantize', incoming, output, 1.)
            self.assertEqual(struct.unpack('<8h', output.read_bytes()),
                             (32767, -32767, 16384, -16384, 0, 0, 32767, -32767))

    def test_phase_order_and_floor_frame_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming, output, coefficients = root / 'in.f32', root / 'out.f32', root / 'coeff.f32'
            # A one-frame delay, with a distinct gain for every phase, makes
            # phase reversal, delay compensation and ceil lengths observable.
            h = [0.] * (320 * 59)
            h[320:640] = [i / 320 for i in range(320)]
            coefficients.write_bytes(struct.pack('<18880f', *h))
            samples = [value for i in range(149) for value in (float(i + 1), -float(i + 1))]
            incoming.write_bytes(struct.pack('<298f', *samples))
            self.run_helper('resample', incoming, output, coefficients)
            result = output.read_bytes()
            self.assertEqual(len(result), (149 * 320 // 147) * 8)
            values = struct.unpack('<' + 'f' * (len(result) // 4), result)
            for frame in range(len(values) // 2):
                center, phase = divmod(frame * 147, 320)
                expected = f32(center * f32(phase / 320)) if center else 0.
                self.assertEqual(values[2 * frame], expected)
                self.assertEqual(values[2 * frame + 1], -expected)

    def test_partial_measurement_and_nonfinite_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            incoming = Path(temporary) / 'in.f32'
            incoming.write_bytes(bytes(9601 * 8))
            rows = self.run_helper('measure', incoming).stdout.splitlines()
            self.assertEqual(len(rows), 3)
            self.assertTrue(rows[0].endswith('true'))
            self.assertTrue(rows[1].endswith('false'))
            incoming.write_bytes(struct.pack('<2f', math.nan, 0.))
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_helper('measure', incoming)
