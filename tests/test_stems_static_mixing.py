# SPDX-License-Identifier: MPL-2.0
"""Byte-exact fixed-mask reconstruction against the player reference path."""
import array
import random
import unittest

from app.stems import mixing
from app.localization import LocalizedError


class StaticMixingTests(unittest.TestCase):
    def test_all_masks_match_reference_bytes(self):
        rng = random.Random(941)
        # Signed zero, subnormals, cancellation, clipping and ordinary samples.
        mix = array.array('f', [0., -0., -0., 0., 0., 0.5, 1., -1.,
                                2**-149, -2**-149, 32767/32768, -1.])
        mix.extend(rng.uniform(-2, 2) for _ in range(8192))
        roles = [array.array('h', (rng.randrange(-32768, 32768)
                                  for _ in mix)) for _ in range(2)]
        for count in (1, 2):
            for mask in range(1 << (count + 1)):
                with self.subTest(count=count, mask=mask):
                    levels = [float(bool(mask & (1 << i))) for i in range(4)]
                    state = mixing.MixState(levels[:], levels[:], levels[:])
                    expected = mixing.reconstruct(mix, roles[:count], mask, state)
                    actual = mixing.reconstruct_static(mix, roles[:count], mask)
                    self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_rejects_unsupported_roles_masks_and_lengths(self):
        for mix, roles, mask in [([0., 0.], [], 0), ([0., 0.], [[0, 0]]*3, 1),
                                 ([0.], [[0]], 1), ([0., 0.], [[0]], 1),
                                 ([0., 0.], [[0, 0]], 4),
                                 ([0., 0.], [[0, 0]], -1)]:
            with self.subTest(mask=mask, roles=len(roles)):
                with self.assertRaises(LocalizedError):
                    mixing.reconstruct_static(mix, roles, mask)
