# SPDX-License-Identifier: MPL-2.0
import array
import pathlib
import tempfile
import shutil
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch, Mock

from app.stems import migration, package, stem, safety, processes


class MigrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.drive = pathlib.Path(tmp.name)
        self.folder = self.drive / 'RX3_STEMS';self.folder.mkdir()
        self.source = self.drive / 'song.wav'
        with wave.open(str(self.source), 'wb') as output:
            output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
            output.writeframes(array.array('h', [700, -900] * 5000).tobytes())
        self.track = SimpleNamespace(location=self.source, title='song', duration=1, artist='', track_id='1')
        self.old = self.folder / 'song.rx3stem'
        self.audio = stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, 5000, b'\0'*32) + array.array('h',[100,-200]*5000).tobytes()
        self.old.write_bytes(self.audio)
        self.addCleanup(patch.stopall)
        patch.object(safety, 'require_library_closed').start()

    @staticmethod
    def build(track, drive, inputs, workspace, source_hash, ffmpeg, checkpoint, metadata, progress=None):
        checkpoint()
        return package.write(workspace/'result.rx3stem', inputs, None,
                             dict(metadata,source_sha256=source_hash))

    def test_remux_preserves_bytes_and_backup_and_is_idempotent(self):
        with patch.object(package,'build',side_effect=self.build), patch.object(stem,'write_stem') as encode:
            self.assertTrue(migration.migrate(self.track,self.drive))
            encode.assert_not_called()
        parsed=package.read(self.old)
        with parsed['members'][0].open() as stream:self.assertEqual(stream.read(),self.audio)
        self.assertEqual((self.folder/'backup-v0.5.2/song.rx3stem').read_bytes(),self.audio)
        self.assertFalse(migration.migrate(self.track,self.drive))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'local waveform decoder required')
    def test_real_waveform_build_remuxes_pcm_without_encoder(self):
        events=[]
        with patch.object(stem, 'write_stem') as encode:
            self.assertTrue(migration.migrate(self.track,self.drive,ffmpeg=shutil.which('ffmpeg'),progress=lambda stage,value:events.append((stage,value))))
            encode.assert_not_called()
        parsed=package.read(self.old)
        self.assertEqual(events[-1],('done',1))
        self.assertTrue(any(stage=='waveforms' and .1<value<.8 for stage,value in events))
        self.assertEqual([v for _,v in events],sorted(v for _,v in events))
        self.assertEqual(parsed['waveform']['version'],3)
        self.assertEqual(parsed['waveform']['format'],b'MULTI')
        self.assertEqual(parsed['waveform']['available'],3)
        with parsed['members'][0].open() as stream:self.assertEqual(stream.read(),self.audio)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'local waveform decoder required')
    def test_cancel_during_real_waveform_analysis_keeps_legacy_file(self):
        def progress(stage,value):
            if stage=='waveforms' and value>.2:
                raise processes.Cancelled()
        with self.assertRaises(processes.Cancelled):
            migration.migrate(self.track,self.drive,ffmpeg=shutil.which('ffmpeg'),progress=progress)
        self.assertEqual(self.old.read_bytes(),self.audio)
        self.assertFalse((self.folder/'backup-v0.5.2').exists())

    def test_add_drums_preserves_original_vocals(self):
        drums = self.audio[:64] + array.array('h',[25,-50]*5000).tobytes()
        def prepare(track,workspace):
            path=workspace/'drums.rx3stem';path.write_bytes(drums);return path
        with patch.object(package,'build',side_effect=self.build):
            migration.migrate(self.track,self.drive,prepare_drum=prepare)
        members=package.read(self.old)['members']
        with members[0].open() as stream:self.assertEqual(stream.read(),self.audio)
        with members[1].open() as stream:self.assertEqual(stream.read(),drums)

    def test_failed_analysis_or_cancel_leaves_old_file(self):
        for error in (RuntimeError('analysis'),processes.Cancelled()):
            with patch.object(package,'build',side_effect=error), self.assertRaises(type(error)):
                migration.migrate(self.track,self.drive)
            self.assertEqual(self.old.read_bytes(),self.audio)

    def test_different_backup_refuses_overwrite(self):
        backup=self.folder/'backup-v0.5.2';backup.mkdir();saved=backup/self.old.name;saved.write_bytes(b'keep')
        with patch.object(package,'build',side_effect=self.build), self.assertRaises(Exception):
            migration.migrate(self.track,self.drive)
        self.assertEqual(saved.read_bytes(),b'keep');self.assertEqual(self.old.read_bytes(),self.audio)

    def test_legacy_warning_detection_does_not_require_an_open_library(self):
        from app.ui.bridge import Bridge
        result=Bridge().stems_migration_status(str(self.drive))
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['value']['items']),1)
        self.assertFalse(result['value']['items'][0]['available'])

    def test_drive_inventory_and_only_checked_tracks_are_migrated(self):
        from app.ui.bridge import Bridge
        other = SimpleNamespace(location=self.drive/'other.wav',title='Other',artist='',track_id='2')
        other.location.write_bytes(self.source.read_bytes())
        (self.folder/'other.rx3stem').write_bytes(self.audio)
        bridge=Bridge()
        library=SimpleNamespace(source=self.drive,collection=SimpleNamespace(playlists=[SimpleNamespace(tracks=[self.track]),SimpleNamespace(tracks=[other])]))
        bridge._library=library
        bridge._held=lambda:library
        bridge._stem_track=lambda key:{'1':self.track,'2':other}[key]
        items=bridge.stems_migration_status(str(self.drive))['value']['items']
        self.assertEqual({row['id'] for row in items},{'1','2'})
        with patch('app.ui.bridge.threading.Thread') as thread, \
             patch('app.services.stems.job') as build_job:
            result=bridge.stems_migrate(['2','2'],str(self.drive),False)
        self.assertTrue(result['value']['started'])
        self.assertEqual(build_job.call_args.kwargs['tracks'],(other,))
        self.assertIs(thread.call_args.kwargs['args'][0],build_job.return_value)
        thread.return_value.start.assert_called_once()

    def test_battery_preparation_encodes_only_new_drum_output(self):
        from app.stems.job import StemJob
        job=StemJob.__new__(StemJob)
        job.runtime=SimpleNamespace(ffmpeg='ffmpeg');job.settings=None;job.architecture=None
        job._check_limits=Mock();job._checkpoint=Mock();job._engine=Mock()
        drum=self.drive/'new-drum.wav';vocal=self.drive/'discarded-vocal.wav'
        job._separate=Mock(return_value={'drums':drum,'vocals':vocal})
        with patch('app.stems.job.input_normalization',return_value=1),patch('app.stems.job.write_stem') as encode:
            job.prepare_drum(self.track,self.drive)
        self.assertEqual(encode.call_count,1)
        self.assertEqual(encode.call_args.args[0],drum)
        job._engine.close.assert_called_once()

    def test_drum_length_mismatch_refuses_before_publication(self):
        def prepare(track,workspace):
            path=workspace/'drums';path.write_bytes(stem.HEADER.pack(stem.MAGIC,44100,2,2,64,4999,b'\0'*32)+b'\0'*(4999*4));return path
        with self.assertRaises(Exception):migration.migrate(self.track,self.drive,prepare_drum=prepare)
        self.assertEqual(self.old.read_bytes(),self.audio)
