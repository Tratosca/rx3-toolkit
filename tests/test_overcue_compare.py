# SPDX-License-Identifier: MPL-2.0
import json
from pathlib import Path
import struct
import tempfile
import unittest

from app.stems.overcue import ROLES, PAGE_BYTES, write_role
from scripts.overcue_compare import compare


class CompareTests(unittest.TestCase):
    def bundle(self, root, samples):
        root.mkdir()
        raw = root / 'audio.s16'
        raw.write_bytes(struct.pack('<' + 'h' * len(samples), *samples))
        manifest = {'schema': 'overcue-stems/4', 'source': {'sha256': 'a' * 64},
                    'headroom': 1., 'loudness_policy': 'full-mix-ceiling/2',
                    'runtime': {'sample_rate': 96000, 'channels': 2, 'format': 's16le',
                                'page_bytes': PAGE_BYTES, 'frames': len(samples) // 2,
                                'latency_pad_frames': 0}, 'roles': {}}
        for role in ROLES:
            digest, table = write_role(raw, root / f'stems-sidecar-{role}.s16le.pgz')
            manifest['roles'][role] = {'sha256': digest, 'page_table_sha256': table,
                                       'bytes': raw.stat().st_size, 'loudness_gain': 1.}
        (root / 'overcue-manifest.json').write_text(json.dumps(manifest))
        return root

    def test_identical_and_single_lsb_difference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = self.bundle(root / 'reference', [0, -300, 32767, -32768])
            self.assertTrue(compare(reference, reference)['audio_1_to_1'])
            candidate = self.bundle(root / 'candidate', [0, -300, 32766, -32768])
            result = compare(reference, candidate)
            self.assertFalse(result['audio_1_to_1'])
            role = result['roles']['vocal']
            self.assertEqual(role['different_samples'], 1)
            self.assertEqual(role['max_delta_lsb_overlapping_samples'], 1)
            self.assertEqual(role['first_difference'],
                             {'frame': 1, 'channel': 0, 'reference': 32767, 'candidate': 32766})

    def test_missing_tail_is_a_difference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = self.bundle(root / 'reference', [0, 0, 0, 0])
            candidate = self.bundle(root / 'candidate', [0, 0])
            report = compare(reference, candidate)
            self.assertFalse(report['audio_1_to_1'])
            self.assertEqual(report['roles']['drums']['different_samples'], 2)

    def test_identical_corrupt_files_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.bundle(Path(temporary) / 'reference', [0, 123])
            path = root / 'stems-sidecar-vocal.s16le.pgz'
            data = bytearray(path.read_bytes())
            data[40] ^= 1
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                compare(root, root)

    def test_matching_pcm_with_different_gain_is_not_one_to_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = self.bundle(root / 'reference', [0, 0])
            candidate = self.bundle(root / 'candidate', [0, 0])
            path = candidate / 'overcue-manifest.json'
            data = json.loads(path.read_text())
            data['headroom'] = .95
            path.write_text(json.dumps(data))
            self.assertFalse(compare(reference, candidate)['audio_1_to_1'])
