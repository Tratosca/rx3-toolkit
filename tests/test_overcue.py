# SPDX-License-Identifier: MPL-2.0
"""The same C reader runs in the prototype hook and these signal tests."""
import array
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
import wave

from app.stems import overcue

ROOT = Path(__file__).resolve().parents[1]


def fixture(root, seconds=1, media='/Contents/Essai \u00e9/fixture.wav', frequency=1000):
    source = root / media.lstrip('/')
    source.parent.mkdir(parents=True, exist_ok=True)
    count = round(seconds * 96000)
    pcm = {}
    for role, mask in zip(overcue.ROLES, overcue.MASKS):
        raw = root / (role + '.s16')
        values = array.array('h')
        for i in range(count):
            left = sum(1400 * math.sin(2 * math.pi * frequency * (j+1) * i / 96000)
                       for j in range(3) if mask & (1 << j))
            values.extend((round(left), round(left * .7)))
        if os.sys.byteorder != 'little': values.byteswap()
        raw.write_bytes(values.tobytes())
        pcm[role] = raw
    with wave.open(str(source), 'wb') as stream:
        stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(96000)
        stream.writeframes(pcm['full-mix'].read_bytes())
    entry = overcue.publish(root, media, '17', pcm)
    return media, entry, pcm


@unittest.skipUnless(shutil.which('cc'), 'C compiler required')
class OvercueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        lib = Path(cls.work.name) / 'overcue.so'
        subprocess.run(['cc', '-DRX3_OVERCUE_HOST', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-fPIC', '-shared', str(ROOT / 'mod/modules/stems/overcue/overcue.c'),
                        '-lz', '-lm', '-pthread', '-o', str(lib)], check=True)
        cls.lib = ctypes.CDLL(str(lib))
        cls.lib.oc_test_read.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint,
                                        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        cls.lib.rx3_overcue_track.argtypes = [ctypes.c_uint, ctypes.c_char_p]
        cls.lib.rx3_overcue_render.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                              ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        cls.bank = Path(cls.work.name) / 'bank'
        cls.bank.mkdir()
        cls.media, cls.entry, cls.pcm = fixture(cls.bank)

    @classmethod
    def tearDownClass(cls):
        cls.lib.rx3_overcue_stop()
        cls.work.cleanup()

    def read(self, root=None, media=None, mask=7, pos=0, frames=44100):
        output = (ctypes.c_float * (frames * 2))()
        ok = self.lib.oc_test_read(os.fsencode(root or self.bank), (media or self.media).encode(),
                                   mask, pos, frames, output)
        return ok, output

    def test_neon_matches_scalar_reference(self):
        reference = Path(self.work.name) / 'scalar.so'
        subprocess.run(['cc', '-DRX3_OVERCUE_HOST', '-DRX3_OVERCUE_SCALAR',
                        '-O2', '-fPIC', '-shared',
                        str(ROOT / 'mod/modules/stems/overcue/overcue.c'),
                        '-lz', '-lm', '-pthread', '-o', str(reference)], check=True)
        lib = ctypes.CDLL(str(reference))
        lib.oc_test_read.argtypes = self.lib.oc_test_read.argtypes
        for mask in (1, 2, 4, 7):
            for start in (0, 14301, 40000):
                ok, actual = self.read(mask=mask, pos=start, frames=4096)
                expected = (ctypes.c_float * 8192)()
                self.assertEqual(lib.oc_test_read(os.fsencode(self.bank), self.media.encode(),
                                                 mask, start, 4096, expected), 1)
                self.assertEqual(ok, 1)
                self.assertLess(max(abs(a-b) for a, b in zip(actual, expected)), 1e-6)

    def test_seven_masks_stereo_and_page_boundaries(self):
        for mask in range(1, 8):
            ok, output = self.read(mask=mask)
            self.assertEqual(ok, 1)
            for i in (512, 8191, 15052, 15053, 30105, 32000, 40000):
                expected = sum(1400 / 32768 * math.sin(2 * math.pi * 1000 * (j+1) * i / 44100)
                               for j in range(3) if mask & (1 << j))
                self.assertAlmostEqual(output[i*2], expected, delta=.00012)
                self.assertAlmostEqual(output[i*2+1], expected*.7, delta=.00012)

    def test_arbitrary_seek_is_identical_to_continuous_conversion(self):
        ok, reference = self.read()
        self.assertEqual(ok, 1)
        for start in (14301, 13, 32800, 44100-500):
            ok, actual = self.read(pos=start, frames=500)
            self.assertEqual(ok, 1)
            self.assertEqual(bytes(actual), bytes(reference)[start*8:(start+500)*8])

    def test_ultrasonic_input_is_filtered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            media, _, _ = fixture(root, seconds=.2, frequency=30000)
            ok, output = self.read(root, media, mask=1, frames=8820)
            self.assertEqual(ok, 1)
            rms = math.sqrt(sum(v*v for v in output[512:-512])/len(output[512:-512]))
            self.assertLess(rms, .000025)

    def test_bad_identity_corrupt_tables_and_pages_are_rejected(self):
        self.assertEqual(self.read(media='/Contents/Other/fixture.wav', frames=100)[0], 0)
        for corruption in ('source', 'table', 'page', 'bundle', 'bundle_hash', 'frames', 'duplicate'):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'copy'
                shutil.copytree(self.bank, root)
                index = root/'CDJMODS/index.json'
                data = json.loads(index.read_text())
                entry = data['tracks']['17']
                if corruption == 'source':
                    (root/self.media.lstrip('/')).write_bytes(b'wrong source')
                elif corruption in ('table', 'page'):
                    p = root/'CDJMODS/stems'/entry['bundle']/'stems-sidecar-full-mix.s16le.pgz'
                    raw = bytearray(p.read_bytes())
                    raw[40 if corruption == 'table' else -1] ^= 1
                    p.write_bytes(raw)
                elif corruption == 'bundle': entry['bundle'] = '../../escape'
                elif corruption == 'bundle_hash':
                    old = root/'CDJMODS/stems'/entry['bundle']
                    entry['bundle'] = '0'*16
                    old.rename(old.parent/entry['bundle'])
                elif corruption == 'frames': entry['frames'] += 1
                else:
                    data['tracks_onelibrary']['19'] = dict(entry, full_mix_sha256='0'*64)
                index.write_text(json.dumps(data))
                self.assertEqual(self.read(root, frames=44100)[0], 0)

    def test_symlink_and_escaped_unicode_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'copy';shutil.copytree(self.bank, root)
            index = root/'CDJMODS/index.json'
            index.write_text(json.dumps(json.loads(index.read_text()), ensure_ascii=True))
            self.assertEqual(self.read(root, frames=1000)[0], 1)
            file = root/self.media.lstrip('/')
            file.unlink();file.symlink_to(self.bank/self.media.lstrip('/'))
            self.assertEqual(self.read(root, frames=1000)[0], 0)

    def test_two_decks_async_cache_seek_and_track_replacement(self):
        previous = os.environ.get('RX3_OVERCUE_ROOT')
        os.environ['RX3_OVERCUE_ROOT'] = str(self.bank)
        try:
            self.assertEqual(self.lib.rx3_overcue_start(), 1)
            for deck in (0,1): self.lib.rx3_overcue_track(deck, self.media.encode())
            for deck, mask, pos in ((0,2,0),(1,4,18000),(0,1,29000),(1,7,0),(0,0,1000)):
                output = (ctypes.c_float*1024)(*[.1]*1024)
                deadline = time.monotonic()+5
                while not self.lib.rx3_overcue_render(deck,pos,output,512,mask):
                    self.assertLess(time.monotonic(),deadline)
                    time.sleep(.01)
                if not mask:self.assertEqual(list(output)[512:],[0.]*512)
                else:
                    ok, expected = self.read(mask=mask,pos=pos,frames=512)
                    self.assertEqual(ok,1)
                    self.assertEqual(bytes(output)[256*8:], bytes(expected)[256*8:])
            class Stats(ctypes.Structure):
                _fields_ = [('cpu_us', ctypes.c_ulonglong), ('wall_us', ctypes.c_ulonglong)] + [
                    (n, ctypes.c_uint) for n in ('timed_blocks', 'max_cpu_us', 'max_wall_us',
                                                'clock_errors', 'hits', 'misses', 'blocks')]
            stats = Stats()
            deadline = time.monotonic()+2
            while not self.lib.rx3_overcue_stats(1, ctypes.byref(stats)):
                self.assertLess(time.monotonic(), deadline)
            self.assertGreater(stats.blocks, 0)
            self.assertGreater(stats.cpu_us, 0)
            self.assertGreater(stats.max_wall_us, 0)
            self.assertEqual(stats.clock_errors, 0)
            self.lib.rx3_overcue_track(0,b'/Contents/absent.wav')
            output = (ctypes.c_float*1024)(*[.123]*1024)
            before = bytes(output)
            self.assertEqual(self.lib.rx3_overcue_render(0,0,output,512,2),0)
            self.assertEqual(bytes(output),before)
        finally:
            self.lib.rx3_overcue_stop()
            if previous is None: os.environ.pop('RX3_OVERCUE_ROOT',None)
            else: os.environ['RX3_OVERCUE_ROOT'] = previous

    def test_publish_preserves_unrelated_tracks_and_refuses_wrong_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'copy';shutil.copytree(self.bank,root)
            index = root/'CDJMODS/index.json';before = index.read_bytes()
            with self.assertRaises(ValueError):
                overcue.publish(root,'/Contents/other.wav','17',self.pcm)
            self.assertEqual(index.read_bytes(),before)
            previous = json.loads(index.read_text())
            previous['tracks']['17']['separation'] = 'other-writer/model'
            previous['tracks']['17']['loudness_policy'] = 'other-writer/policy'
            index.write_text(json.dumps(previous))
            entry = overcue.publish(root,self.media,'17',self.pcm)
            self.assertEqual(entry['bundle'],self.entry['bundle'])
            current = json.loads(index.read_text())['tracks']['17']
            self.assertEqual(current['separation'], 'manual/rx3-toolkit/prepared-stems/1')
            self.assertEqual(current['loudness_policy'], 'precomputed/1')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_export_reuses_package_pcm_and_writes_readable_selections(self):
        from app.stems import package, stem
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/self.media.lstrip('/')
            source.parent.mkdir(parents=True)
            shutil.copyfile(self.bank/self.media.lstrip('/'),source)
            stems={}
            for role, key in (('vocals','vocal'),('drums','drums')):
                wav=root/(role+'.wav')
                subprocess.run(['ffmpeg','-v','error','-f','s16le','-ar','96000','-ac','2',
                                '-i',str(self.pcm[key]),str(wav)],check=True)
                stems[role]=root/(role+'.rx3stem')
                stem.write_stem(wav,stems[role],sample_format='s16_gain',match_full=source)
            packed=root/'package.rx3stem'
            package.write(packed,stems,None,{'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
            entry=overcue.export_package(root,self.media,'17',packed)
            self.assertEqual(entry['frames'],96000)
            self.assertEqual(entry['loudness_policy'], 'full-mix-ceiling/2')
            from app.stems.analysis import tags
            bundle = root/'CDJMODS/stems'/entry['bundle']
            manifest = json.loads((bundle/'overcue-manifest.json').read_text())
            self.assertEqual(len(manifest['waveforms']), 6)
            for name in manifest['waveforms']:
                columns = tags((bundle/name).read_bytes())[b'PWV5']
                self.assertEqual(len(columns), 300)
                self.assertTrue(any(columns))
            for mask in range(1,8):
                ok,result=self.read(root,mask=mask,pos=4000,frames=1000)
                self.assertEqual(ok,1)
                for i in (100,500,900):
                    expected=sum(1400/32768*math.sin(2*math.pi*1000*(j+1)*(4000+i)/44100)
                                 for j in range(3) if mask&(1<<j))
                    self.assertAlmostEqual(result[i*2],expected,delta=.0005)


if __name__ == '__main__':
    unittest.main()
