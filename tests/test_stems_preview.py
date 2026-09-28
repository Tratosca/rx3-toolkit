# SPDX-License-Identifier: MPL-2.0
import array
import base64
import pathlib
import shutil
import tempfile
import unittest
import wave
from unittest.mock import patch

from app.localization import LocalizedError
from app.stems import preview, stem


@unittest.skipUnless(shutil.which('ffmpeg'), 'audio decoder required')
class PreviewTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=pathlib.Path(folder.name)
        self.source=self.root/'mix.wav'
        pcm=array.array('h',[1000,-2000,0,0]*2500)
        with wave.open(str(self.source),'wb') as out:
            out.setparams((2,2,44100,0,'NONE','not compressed'))
            out.writeframes(pcm.tobytes())
        self.role=self.root/'vocal.rx3stem'
        self.role.write_bytes(stem.HEADER.pack(stem.MAGIC,44100,2,2,64,5000,b'\0'*32)+array.array('h',[500,500]*5000).tobytes())

    def open(self):
        result=preview.Preview(self.source,[self.role]);self.addCleanup(result.close);return result

    def test_whole_track_metadata_and_role_pcm(self):
        result=self.open();info=result.describe()
        self.assertEqual(info['frames'],5000);self.assertEqual(info['available'],3)
        self.assertGreater(len(info['peaks']),1)
        chunk=result.chunk(0)
        source,voice=[array.array('f',base64.b64decode(value)) for value in chunk['pcm']]
        self.assertEqual(source[:4],array.array('f',[1000/32768,-2000/32768,0,0]))
        self.assertEqual(voice[:4],array.array('f',[500/32768,500/32768,0,0]))
        self.assertEqual(chunk['frames'],5000)

    def test_chunk_boundary_seek_and_cleanup(self):
        result=self.open();directory=pathlib.Path(result.directory.name)
        with patch.object(preview,'CHUNK_FRAMES',3000):
            self.assertEqual(result.chunk(0)['frames'],3000)
            self.assertEqual(result.chunk(3000)['frames'],2000)
        for invalid in [-1,5000,True,0.5]:
            with self.assertRaises(LocalizedError):result.chunk(invalid)
        result.close();self.assertFalse(directory.exists())

    def test_bridge_session_transfer_and_stale_token(self):
        from types import SimpleNamespace
        from app.ui.bridge import Bridge
        directory=self.root/'RX3_STEMS';directory.mkdir()
        (directory/('mix'+stem.ROLE_SUFFIXES['vocals'])).write_bytes(self.role.read_bytes())
        bridge=Bridge();bridge._stem_track=lambda _: SimpleNamespace(location=self.source)
        with patch('app.stems.provisioning.detect',return_value=SimpleNamespace(ffmpeg=shutil.which('ffmpeg'))):
            opened=bridge.stems_preview_open(str(self.root),'track')
        self.assertTrue(opened['ok'])
        info=opened['value'];self.assertEqual(info['available'],3)
        self.assertEqual(bridge.stems_preview_chunk(info['token'],0)['value']['frames'],5000)
        self.assertIsNone(bridge.stems_preview_chunk('stale',0)['value'])
        temporary=pathlib.Path(bridge._preview.directory.name)
        bridge.stems_preview_close('stale');self.assertTrue(temporary.exists())
        bridge.stems_preview_close(info['token']);self.assertFalse(temporary.exists())

    def test_changed_role_does_not_mix_two_revisions(self):
        result=self.open()
        self.role.write_bytes(self.role.read_bytes()+b"changed")
        with self.assertRaises(LocalizedError):result.chunk(0)

    def test_memory_budget_refuses_before_decoding(self):
        with patch.object(preview,'MAX_BUFFER_BYTES',1),patch.object(preview.importing,'decode') as decode:
            with self.assertRaises(LocalizedError):self.open()
            decode.assert_not_called()

    def test_missing_roles_does_not_decode(self):
        with patch.object(preview.importing,'decode') as decode:
            result=preview.Preview(self.source,[]);self.addCleanup(result.close)
            self.assertEqual(result.describe()['available'],0);decode.assert_not_called()

    def test_embedded_waveforms_reused_only_for_matching_source(self):
        from types import SimpleNamespace
        from app.stems import waveform, package, safety
        frames=5000;count=(frames+293)//294
        wavefile=self.root/'track.rx3wave'
        data=b'\x1f\x1c\x00\x08\x09\x0a'*count
        waveform.write_combinations(wavefile,SimpleNamespace(count=count,sha256='11'*32),
                                    frames,safety.digest(self.source),
                                    {mask:(data,'22'*32) for mask in range(1,4)})
        target=self.root/'track.rx3stem'
        package.write(target,{'vocals':self.role},wavefile,{})
        files=package.read(target)['members'][:-2]
        result=preview.Preview(self.source,files);self.addCleanup(result.close)
        self.assertEqual(result.peaks,[])
        self.assertEqual(set(result.describe()['waveforms']),{'1','2','3'})
        self.assertEqual(base64.b64decode(result.waveforms['1']),data)
        with wave.open(str(self.source),'wb') as out:
            out.setparams((2,2,44100,0,'NONE','not compressed'))
            out.writeframes(array.array('h',[1,-1]*frames).tobytes())
        changed=preview.Preview(self.source,files);self.addCleanup(changed.close)
        self.assertIsNone(changed.waveforms)
        self.assertTrue(changed.peaks)

    def streaming(self):
        from types import SimpleNamespace
        from app.stems import waveform, package, safety
        count=(5000+293)//294
        wavefile=self.root/'stream.rx3wave'
        waveform.write_combinations(wavefile,SimpleNamespace(count=count,sha256='11'*32),
                                    5000,safety.digest(self.source),
                                    {mask:(b'\x01'*count*6,'22'*32) for mask in range(1,4)})
        target=self.root/'stream.rx3stem'
        package.write(target,{'vocals':self.role},wavefile,{})
        result=preview.Preview(self.source,package.read(target)['members'][:-2],streaming=True)
        self.addCleanup(result.close)
        return result

    def test_binary_http_matches_source_and_pcm_without_base64(self):
        import urllib.request, urllib.error, struct
        result=self.streaming();info=result.describe()
        self.assertEqual(info['pcmLayout'],'f32-source-s16-roles-v1')
        with urllib.request.urlopen(urllib.request.Request(info['binaryURL']+'0',headers={'Origin':'file://'}),timeout=5) as response:
            self.assertEqual(response.headers['Access-Control-Allow-Origin'],'file://')
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            data=response.read()
        first,count=struct.unpack('<II',data[:8])
        self.assertEqual((first,count),(0,5000))
        self.assertEqual(len(data),8+5000*12)
        self.assertEqual(struct.unpack('<4f',data[8:24]),(1000/32768,-2000/32768,0,0))
        self.assertEqual(struct.unpack('<4h',data[8+5000*8:16+5000*8]),(500,500,500,500))
        for url,headers in [(info['binaryURL'].replace(info['token'],'wrong')+'0',{}),
                            (info['binaryURL']+'0',{'Origin':'https://untrusted.example'}),
                            (info['binaryURL']+'0',{'Host':'untrusted.example'}),
                            (info['binaryURL']+'1',{})]:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=5)
            caught.exception.close()
        result.close();self.assertIsNotNone(result.process.poll())
        self.assertFalse(pathlib.Path(result.directory.name).exists())

    def test_binary_rejects_changed_source_and_bad_decoded_length(self):
        result=self.streaming()
        result.process.wait(timeout=5)
        result.raw.write_bytes(b'short')
        with self.assertRaises(LocalizedError): result.binary_chunk(0)
        result.close()
        result=self.streaming()
        self.source.touch()
        with self.assertRaises(LocalizedError): result.binary_chunk(0)
