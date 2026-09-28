# SPDX-License-Identifier: MPL-2.0
"""The single preparation path preserves existing audio across upgrades."""
import array
import json
import pathlib
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

from package_fixture import isolate, wave_fixture
from app.services import stems as service
from app.stems import cache, job, migration, package, processes, provisioning, rekordbox, safety, separation, stem, waveform


class UnifiedPreparationTests(unittest.TestCase):
    def setUp(self):
        isolate(self)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.output = self.root / 'RX3_STEMS'; self.output.mkdir()
        self.source = self.root / 'track.wav'
        with wave.open(str(self.source), 'wb') as out:
            out.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
            out.writeframes(array.array('h', [1000, -1000] * 4410).tobytes())
        self.track = rekordbox.Track('1', 'Track', '', 1, self.source, True)
        self.playlist = rekordbox.Playlist('1', 'List', 'List', (self.track,))
        self.collection = rekordbox.Collection(self.root / 'library.xml', 1, (self.playlist,))
        self.vocal = self.root / 'vocal.pcm'; self.drum = self.root / 'drum.pcm'
        for path, value in ((self.vocal, 200), (self.drum, 100)):
            path.write_bytes(stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, 4410, b'\0'*32) +
                             array.array('h', [value, -value] * 4410).tobytes())
        self.target = self.output / 'track.rx3stem'
        self.addCleanup(patch.stopall)
        patch.object(safety, 'require_library_closed').start()
        patch.object(waveform, 'build', side_effect=wave_fixture).start()
        patch.object(job, 'runtime_identity', return_value={'adapter': 2}).start()

    def package(self, drums=False, waves=False, **metadata):
        inputs = {'vocals': self.vocal}
        if drums: inputs['drums'] = self.drum
        local = package.build(self.track, self.root, inputs, self.root, safety.digest(self.source),
                              metadata={'processing': {'preset': 'quality'}, **metadata}, waveforms=waves)
        package.publish(local, self.target)

    def make_job(self):
        return job.StemJob(provisioning.detect(), self.collection, self.playlist, self.root,
                           roles=('vocals', 'drums'), upgrade_existing=True)

    def run_job(self):
        current = self.make_job()
        with patch.object(current, '_separate', side_effect=AssertionError('must not replace the vocal')), \
             patch.object(current, 'prepare_drum', return_value=self.drum) as drums:
            state = current.run()
        self.assertEqual(state.state, 'done', state.fatal)
        self.assertFalse(state.errors, state.errors)
        return state, drums.call_count

    def test_two_stem_package_adds_only_drums_and_then_skips(self):
        self.package(origin='imported', checks={'waveform': False})
        first, calls = self.run_job()
        self.assertEqual(calls, 1)
        parsed = package.read(self.target)
        self.assertEqual(parsed['roles'], ('vocals', 'drums'))
        with parsed['members'][0].open() as audio:
            self.assertEqual(audio.read(), self.vocal.read_bytes())
        self.assertEqual(parsed['manifest']['processing'], {'preset': 'quality'})
        self.assertEqual(first.results[0].processing, {'preset': 'quality'})
        self.assertIn('drum_processing', parsed['manifest'])
        before = self.target.read_bytes()
        second, calls = self.run_job()
        self.assertEqual(calls, 0)
        self.assertEqual(second.results[0].status, 'existing')
        self.assertEqual(self.target.read_bytes(), before)

    def test_complete_three_stems_survive_old_quality_and_missing_outer_manifest(self):
        self.package(drums=True, waves=True)
        before = self.target.read_bytes()
        result, calls = self.run_job()
        self.assertEqual(calls, 0)
        self.assertEqual(result.results[0].status, 'existing')
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(result.results[0].processing, {'preset': 'quality'})

    def test_three_stems_with_missing_waveforms_do_not_separate(self):
        self.package(drums=True)
        result, calls = self.run_job()
        self.assertEqual(calls, 0)
        self.assertEqual(result.results[0].status, 'migrated')
        self.assertTrue(package.read(self.target)['waveform'])

    def test_legacy_vocals_are_backed_up_and_upgraded_in_the_normal_job(self):
        self.target.write_bytes(self.vocal.read_bytes())
        result, calls = self.run_job()
        self.assertEqual(calls, 1)
        self.assertEqual(result.results[0].status, 'migrated')
        self.assertEqual((self.output/'backup-v0.5.2/track.rx3stem').read_bytes(), self.vocal.read_bytes())
        parsed = package.read(self.target)
        self.assertEqual(parsed['manifest']['separation_provenance'], 'legacy-unverified')
        with parsed['members'][0].open() as audio: self.assertEqual(audio.read(), self.vocal.read_bytes())
        self.assertEqual(self.run_job()[1], 0)

    def test_cancel_and_waveform_failure_preserve_previous_package(self):
        self.package()
        before = self.target.read_bytes()
        for error, status in ((processes.Cancelled(), 'cancelled'), (ValueError('wave failure'), 'done')):
            current = self.make_job()
            with patch.object(current, 'prepare_drum', return_value=self.drum), \
                 patch.object(package, 'build', side_effect=error):
                state = current.run()
            self.assertEqual(state.state, status)
            self.assertEqual(self.target.read_bytes(), before)
            self.assertFalse((self.output/safety.MANIFEST_NAME).exists())

    def test_changed_source_does_not_reuse_a_package(self):
        self.package(drums=True, waves=True)
        self.source.write_bytes(self.source.read_bytes()+b'changed')
        current = self.make_job()
        with patch.object(current, '_separate', side_effect=ValueError('expected separation')) as separate:
            state = current.run()
        separate.assert_called_once()
        self.assertEqual(len(state.errors), 1)

    def test_corrupt_package_is_reported_without_overwrite(self):
        self.package(drums=True, waves=True)
        data = bytearray(self.target.read_bytes()); data[500] ^= 1; self.target.write_bytes(data)
        current = self.make_job()
        with patch.object(current, '_separate') as separate:
            state = current.run()
        separate.assert_not_called()
        self.assertEqual(len(state.errors), 1)
        self.assertEqual(self.target.read_bytes(), data)

    def test_new_track_prepares_both_roles_and_is_reused_on_second_run(self):
        current = self.make_job()
        def encode(source, target, **kwargs):
            target.write_bytes(source.read_bytes())
            return stem.StemResult(target, 4410, .1, 17640)
        with patch.object(current, '_separate', return_value={'vocals':self.vocal,'drums':self.drum}) as separate, \
             patch.object(job, 'write_stem', side_effect=encode):
            state=current.run()
        self.assertFalse(state.errors, state.errors)
        separate.assert_called_once()
        self.assertEqual(package.read(self.target)['roles'], ('vocals','drums'))
        self.assertEqual(self.run_job()[1], 0)

    def test_additional_export_reuses_existing_rx3_and_keeps_it_on_failure(self):
        self.package(drums=True, waves=True)
        before = self.target.read_bytes()
        for failure in (None, ValueError('USB export failed'), processes.Cancelled()):
            current = self.make_job()
            current.overcue_export = Mock(side_effect=failure)
            with patch.object(current, '_separate', side_effect=AssertionError('do not separate twice')):
                state = current.run()
            current.overcue_export.assert_called_once()
            self.assertEqual(current.overcue_export.call_args.args[1], self.target)
            self.assertEqual(self.target.read_bytes(), before)
            self.assertTrue((self.output/safety.MANIFEST_NAME).is_file())
            self.assertEqual(len(state.results), 1)
            self.assertEqual(state.state, 'cancelled' if isinstance(failure, processes.Cancelled) else 'done')
            self.assertEqual(len(state.errors), int(isinstance(failure, ValueError)))

    def test_default_preparation_does_not_export_overcue(self):
        self.package(drums=True, waves=True)
        current = self.make_job()
        self.assertIsNone(current.overcue_export)
        state = current.run()
        self.assertFalse(state.errors)
        self.assertFalse((self.root/'CDJMODS').exists())


class FixedPolicyTests(unittest.TestCase):
    def test_saved_presets_and_custom_values_cannot_change_the_policy(self):
        catalogue=separation.Catalogue((separation.Model('Demucs','htdemucs.yaml','htdemucs.yaml',('Vocals','Drums','Bass','Other'),None),))
        for mode in ('quality','normal','quick','custom','fast'):
            previous=separation.Settings(model='old.ckpt',mode=mode,accelerator='cpu',values={'demucs_shifts':12,'normalization':.2})
            current=service.preparation_settings(previous,catalogue)
            self.assertEqual((current.mode,current.model,current.accelerator),('quick','htdemucs.yaml','cpu'))
            self.assertEqual(current.values,{'demucs_shifts':1})
            self.assertEqual(service.prepared_roles(['vocals']),('vocals','drums'))

    def test_service_job_fixes_roles_quality_and_waveforms_for_stale_callers(self):
        library=service.Library(pathlib.Path('x'),0,(),rekordbox.Collection(pathlib.Path('x'),0,(rekordbox.Playlist('1','List','List',()),)))
        with patch.object(service,'_catalogue',return_value=None), patch.object(service,'drums_blocked',return_value=None), \
             patch.object(provisioning,'detect',return_value=Mock(ready=True)), patch.object(safety,'require_library_closed'), \
             patch.object(service,'StemJob') as built:
            service.job(library,'1',pathlib.Path('.'),settings=separation.Settings(mode='quality'),roles=['vocals'],waveforms=False)
        self.assertEqual(built.call_args.kwargs['roles'],('vocals','drums'))
        self.assertEqual(built.call_args.kwargs['settings'].mode,'quick')
        self.assertTrue(built.call_args.kwargs['waveforms'])
        self.assertTrue(built.call_args.kwargs['upgrade_existing'])
