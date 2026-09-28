# SPDX-License-Identifier: MPL-2.0
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.stems import wave_settings as settings, wave_conversion, waveform, package, stem, safety
from app.stems.rekordbox import Track, Playlist
from app.localization import LocalizedError
from package_fixture import wave_fixture
REAL_BUILD=waveform.build

class WaveSettingsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=pathlib.Path(temp.name)
        (self.root/'PIONEER').mkdir()
        self.my=self.root/'PIONEER/MYSETTING.DAT';self.my.write_bytes(b'opaque configuration')
        self.source=self.root/'track.wav';self.source.write_bytes(b'original mix')
        self.track=Track('1','Track','Artist',1,self.source,True)
        self.collection=SimpleNamespace(playlists=[Playlist('p','P','P',(self.track,))])
        self.pcm=self.root/'vocal';self.pcm.write_bytes(stem.HEADER.pack(stem.MAGIC,44100,2,2,64,4410,b'\0'*32)+b'\0'*17640)
        self.target=self.root/'RX3_STEMS/track.rx3stem';self.target.parent.mkdir()
        p=patch.object(waveform,'build',side_effect=wave_fixture);p.start();self.addCleanup(p.stop)
        p=patch.object(safety,'require_library_closed');p.start();self.addCleanup(p.stop)

    def build(self,format):
        settings.save(self.root,format,settings.fingerprint(self.root))
        local=package.build(self.track,self.root,{'vocals':self.pcm},self.root,safety.digest(self.source),wave_format=format)
        package.publish(local,self.target)

    def test_settings_change_acknowledgement_and_format_mismatch(self):
        self.build('blue')
        self.assertFalse(wave_conversion.status(self.root,self.collection,'blue')['items'])
        before=self.target.read_bytes()
        self.my.write_bytes(b'changed, format field deliberately unknown')
        report=wave_conversion.status(self.root,self.collection,'blue')
        self.assertTrue(report['changed'])
        with self.assertRaises(LocalizedError):settings.save(self.root,'blue','stale')
        settings.save(self.root,'blue',report['currentFingerprint'])
        self.assertFalse(wave_conversion.status(self.root,self.collection,'blue')['changed'])
        self.assertFalse(wave_conversion.status(self.root,self.collection,'blue')['items'])
        # Confirming a changed unrelated setting does not rewrite stems.
        self.assertEqual(self.target.read_bytes(),before)
        report=wave_conversion.status(self.root,self.collection,'rgb')
        self.assertEqual(len(report['items']),1);self.assertTrue(report['items'][0]['available'])
        self.assertEqual(self.target.read_bytes(),before)

    def test_conversion_preserves_pcm_and_format_missing_decline_is_read_only(self):
        self.build('blue')
        parsed=package.read(self.target)
        with parsed['members'][0].open() as stream:before=stream.read()
        settings.save(self.root,'3band',settings.fingerprint(self.root))
        self.assertEqual(package.read(self.target)['waveform']['format'],b'PWV3')
        report=wave_conversion.run([self.track],self.root,'3band',settings.fingerprint(self.root),'ffmpeg',lambda:None,lambda *args:None)
        self.assertEqual(report,{'waveforms':['1'],'errors':[]})
        parsed=package.read(self.target)
        self.assertEqual(parsed['waveform']['format'],b'PWV7')
        with parsed['members'][0].open() as stream:self.assertEqual(stream.read(),before)

    def test_settings_change_during_calculation_never_publishes(self):
        self.build('blue');before=self.target.read_bytes()
        settings.save(self.root,'rgb',settings.fingerprint(self.root));expected=settings.fingerprint(self.root)
        def changed(*args,**kwargs):
            result=wave_fixture(*args,**kwargs)
            self.my.write_bytes(b'changed while calculating')
            return result
        with patch.object(waveform,'build',side_effect=changed):
            result=wave_conversion.run([self.track],self.root,'rgb',expected,'ffmpeg',lambda:None,lambda *args:None)
        self.assertTrue(result['errors']);self.assertEqual(self.target.read_bytes(),before)

    def test_missing_source_and_ambiguous_track_cannot_be_converted(self):
        self.build('blue');self.source.unlink()
        report=wave_conversion.status(self.root,self.collection,'rgb')
        self.assertFalse(report['items'][0]['available'])

    def test_default_all_formats_ignores_settings_and_is_reusable(self):
        # Broken legacy profiles and changed My Settings cannot block new packages.
        (self.target.parent/settings.PROFILE).write_text('invalid old settings')
        self.my.write_bytes(b'new configuration')
        local=package.build(self.track,self.root,{'vocals':self.pcm},self.root,safety.digest(self.source))
        package.publish(local,self.target)
        parsed=package.read(self.target)
        self.assertEqual(parsed['waveform']['format'],b'MULTI')
        self.assertFalse(wave_conversion.status(self.root,self.collection)['items'])
        self.assertFalse(wave_conversion.status(self.root,self.collection)['changed'])

    def test_single_format_completion_preserves_pcm(self):
        self.build('blue')
        with package.read(self.target)['members'][0].open() as f:before=f.read()
        report=wave_conversion.status(self.root,self.collection)
        self.assertEqual(len(report['items']),1)
        self.my.write_bytes(b'changed but irrelevant')
        result=wave_conversion.run([self.track],self.root,None,None,'ffmpeg',lambda:None,lambda *args:None)
        self.assertFalse(result['errors'])
        parsed=package.read(self.target)
        self.assertEqual(parsed['waveform']['format'],b'MULTI')
        with parsed['members'][0].open() as f:self.assertEqual(f.read(),before)
        self.assertFalse(wave_conversion.status(self.root,self.collection)['items'])

    def test_real_single_format_conversion_preserves_audio(self):
        import wave, shutil, math, array
        if not shutil.which('ffmpeg'):self.skipTest('ffmpeg required')
        with wave.open(str(self.source),'wb') as output:
            output.setparams((2,2,44100,0,'NONE','not compressed'))
            output.writeframes(array.array('h',(int(8000*math.sin(i*math.pi/100)) for i in range(8820))).tobytes())
        with patch.object(waveform,'build',REAL_BUILD):
            self.build('blue')
            before=package.read(self.target)
            with before['members'][0].open() as audio:pcm=audio.read()
            for format in ('rgb','3band'):
                settings.save(self.root,format,settings.fingerprint(self.root))
                result=wave_conversion.run([self.track],self.root,format,settings.fingerprint(self.root),'ffmpeg',lambda:None,lambda *args:None)
                self.assertFalse(result['errors'])
                parsed=package.read(self.target)
                self.assertEqual(parsed['waveform']['format'],settings.FORMATS[format])
                with parsed['members'][0].open() as audio:self.assertEqual(audio.read(),pcm)
