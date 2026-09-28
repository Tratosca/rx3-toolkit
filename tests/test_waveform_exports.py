# SPDX-License-Identifier: MPL-2.0
"""Optional byte comparison against an operator-owned, hash-pinned export corpus."""
import hashlib
import json
import os
import pathlib
import tempfile
import unittest

from app.stems import analysis, importing, wave_dsp


@unittest.skipUnless(os.environ.get('RX3_WAVE_EXPORT_MANIFEST'), 'local export corpus not configured')
class ExportWaveformTests(unittest.TestCase):
    def test_rgb_matches_exported_reference_bytes(self):
        manifest = pathlib.Path(os.environ['RX3_WAVE_EXPORT_MANIFEST']).resolve()
        entries = json.loads(manifest.read_text())
        self.assertTrue(entries)
        for entry in entries:
            with self.subTest(source=entry['source']):
                paths = {}
                for name in ('source', 'dat', 'ext'):
                    path = manifest.parent / entry[name]
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry[name + '_sha256'])
                    paths[name] = path
                template = analysis.parse(paths['dat'].read_bytes(), paths['ext'].read_bytes())
                self.assertIsNotNone(template)
                self.assertEqual(template.tag, b'PWV5')
                with tempfile.TemporaryDirectory() as directory:
                    pcm = pathlib.Path(directory) / 'mix.f32'
                    frames = importing.decode(paths['source'], pcm, 'ffmpeg', untrimmed=True)
                    actual = wave_dsp.columns(pcm, frames, template.tag, template.count)
                self.assertEqual(actual, template.columns)


@unittest.skipUnless(os.environ.get('RX3_WAVE_3BAND_MANIFEST'), 'local three-band corpus not configured')
class ThreeBandExportTests(unittest.TestCase):
    def test_three_band_matches_complete_real_exports(self):
        import struct
        manifest = pathlib.Path(os.environ['RX3_WAVE_3BAND_MANIFEST'])
        for entry in json.loads(manifest.read_text()):
            with self.subTest(source=entry['source']):
                paths = {}
                for name, identity in entry['paths'].items():
                    path = pathlib.Path(identity['path'])
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), identity['sha256'])
                    paths[name] = path
                refs = analysis.tags(paths['ext'].read_bytes())
                data = paths['2ex'].read_bytes()
                self.assertEqual(data[:4], b'PMAI')
                offset, total = struct.unpack_from('>II', data, 4)
                self.assertEqual(total, len(data))
                while offset < total:
                    tag, header, size = struct.unpack_from('>4sII', data, offset)
                    self.assertTrue(12 <= header <= size <= total - offset)
                    if tag == b'PWV7':
                        self.assertEqual(header, 24)
                        stride, count, cadence = struct.unpack_from('>III', data, offset + 12)
                        self.assertEqual((stride, cadence), (3, 150 << 16))
                        self.assertEqual(size, header + count * 3)
                        refs[tag] = data[offset + header:offset + size]
                    offset += size
                self.assertIn(b'PWV7', refs)
                with tempfile.TemporaryDirectory() as directory:
                    pcm = pathlib.Path(directory) / 'mix.f32'
                    rate = entry.get('rate', 44100)
                    if rate == 44100:
                        frames = importing.decode(paths['source'], pcm, 'ffmpeg', untrimmed=True)
                    else:
                        import subprocess
                        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-flags2', '+skip_manual',
                                        '-i', str(paths['source']), '-ac', '2', '-ar', str(rate),
                                        '-f', 'f32le', str(pcm)], check=True, capture_output=True)
                        frames = pcm.stat().st_size // 8
                    actual = wave_dsp.columns(pcm, frames, None, len(refs[b'PWV7']) // 3, rate=rate)
                for tag in (b'PWV7',):
                    self.assertEqual(actual[tag], refs[tag], tag.decode())
