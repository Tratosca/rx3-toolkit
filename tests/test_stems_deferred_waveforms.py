# SPDX-License-Identifier: MPL-2.0
import json
import pathlib
import struct
import tempfile
import unittest
from unittest.mock import patch

from app.localization import LocalizedError
from app.stems import cache, deferred_waveforms as deferred, limits, package, safety, stem, waveform
from app.stems.processes import Cancelled
from app.stems.rekordbox import Track, Playlist
from package_fixture import wave_fixture


class DeferredWaveformTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.source = self.root / 'mix.wav'
        self.source.write_bytes(b'original source identity')
        self.track = Track('1', 'Track', 'Artist', 1, self.source, True)
        self.inputs = {}
        for role in ('vocals', 'drums'):
            path = self.root / role
            path.write_bytes(stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, 4410, b'\0'*32)
                             + struct.pack('<hh', 100, -100)*4410)
            self.inputs[role] = path
        (self.root / 'RX3_STEMS').mkdir()
        self.target = deferred.target_for(self.track, self.root)
        package.write(self.target, self.inputs, None,
                      {'source_sha256': safety.digest(self.source), 'origin': 'imported',
                       'processing': {'origin': 'imported'}, 'checks': {'aligned': True}})
        for patcher in (patch.object(safety, 'require_library_closed'),
                        patch.object(waveform, 'build', side_effect=wave_fixture)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_optional_section_is_explicit_and_crc_checked(self):
        parsed = package.read(self.target)
        self.assertIsNone(parsed['waveform'])
        self.assertEqual(parsed['manifest']['version'], 3)
        self.assertEqual(parsed['members'][-2].length, 0)
        self.assertEqual(deferred.status(self.track, self.root), 'pending')
        data = bytearray(self.target.read_bytes())
        # A v2 package cannot use the absent-waveform representation.
        struct.pack_into('<I', data, 8, 2)
        self.target.write_bytes(data)
        with self.assertRaises(ValueError):
            package.read(self.target)
        self.assertEqual(deferred.status(self.track, self.root), 'invalid')

    def test_upgrade_and_recalculate_preserve_pcm_and_provenance(self):
        self.assertTrue(deferred.upgrade(self.track, self.root))
        self.assertEqual(deferred.status(self.track, self.root), 'ready')
        parsed = package.read(self.target)
        self.assertEqual(parsed['manifest']['origin'], 'imported')
        self.assertEqual(parsed['manifest']['processing'], {'origin': 'imported'})
        for member, original in zip(parsed['members'], self.inputs.values()):
            self.assertEqual(safety.digest(member), safety.digest(original))
        entries, _ = cache.read_manifest(self.root)
        self.assertIsNotNone(cache.verified_files(self.target.parent, entries[0], tuple(self.inputs)))
        self.assertFalse(deferred.upgrade(self.track, self.root))
        self.assertTrue(deferred.upgrade(self.track, self.root, force=True))

    def test_failure_and_cancellation_preserve_the_usable_package(self):
        before = self.target.read_bytes()
        with patch.object(waveform, 'build', side_effect=ValueError('failed DSP')):
            with self.assertRaises(ValueError):
                deferred.upgrade(self.track, self.root)
        self.assertEqual(self.target.read_bytes(), before)
        checkpoints = []
        def cancel():
            checkpoints.append(True)
            if len(checkpoints) == 2:
                raise Cancelled()
        with self.assertRaises(Cancelled):
            deferred.upgrade(self.track, self.root, checkpoint=cancel)
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(self.target.read_bytes(), before)
        self.source.write_bytes(b'different mix')
        with self.assertRaises(LocalizedError):
            deferred.upgrade(self.track, self.root)
        self.assertEqual(self.target.read_bytes(), before)

    def test_audio_only_build_does_not_analyze_audio(self):
        with patch.object(waveform, 'build', side_effect=AssertionError('must not calculate')):
            out = package.build(self.track, self.root, self.inputs, self.root,
                                safety.digest(self.source), waveforms=False)
        self.assertIsNone(package.read(out)['waveform'])

    def test_requested_track_only_is_recalculated(self):
        other = Track('2', 'Other', '', 1, self.source, True)
        playlist = Playlist('p', 'Playlist', 'Playlist', (self.track, other))
        with patch.object(deferred, 'upgrade', return_value=True) as upgrade:
            result = deferred.run(playlist, self.root, 'ffmpeg', lambda: None,
                                  lambda *args: None, track_id='1')
        self.assertEqual(result, {'waveforms': ['1'], 'errors': []})
        self.assertEqual(upgrade.call_count, 1)
        self.assertEqual(upgrade.call_args.kwargs, {'force': True})

    def test_batch_skips_completed_tracks_even_when_source_is_unavailable(self):
        deferred.upgrade(self.track, self.root)
        self.source.unlink()
        playlist = Playlist('p', 'Playlist', 'Playlist', (self.track,))
        with patch.object(deferred, 'upgrade', side_effect=AssertionError('already complete')):
            result = deferred.run(playlist, self.root, 'ffmpeg', lambda: None, lambda *args: None)
        self.assertEqual(result, {'waveforms': [], 'errors': []})

    def test_audio_only_limits_and_actual_size(self):
        parsed = package.read(self.target)
        self.assertEqual(limits.package_bytes(4410, 2, waveforms=False,
                         manifest=parsed['members'][-1].length), self.target.stat().st_size)
        self.assertLess(limits.package_bytes(4410, 2, waveforms=False), limits.package_bytes(4410, 2))
        self.assertGreater(limits.max_frames(2, waveforms=False), limits.max_frames(2))
