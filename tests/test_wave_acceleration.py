# SPDX-License-Identifier: MPL-2.0
import array
import math
import pathlib
import random
import shutil
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.stems import analysis, audition, importing, processes, safety, stem, wave_acceleration, wave_dsp, waveform


class WaveAccelerationTests(unittest.TestCase):
    def setUp(self):
        self.worker = wave_acceleration.open_worker()
        if self.worker is None:
            self.skipTest('Installed NumPy separation runtime required')
        self.addCleanup(self.worker.close)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.frames = 44100 + 137
        rng = random.Random(44)
        mix = array.array('f', (rng.uniform(-.8,.8) for _ in range(self.frames*2)))
        mix[:4] = array.array('f', [0., -0., -0., 0.])
        self.pcm = self.root/'mix.f32'; self.pcm.write_bytes(mix.tobytes())
        self.files=[]
        for role,gain in [('vocals',1.),('drums',1.247978925704956)]:
            path=self.root/role
            pcm=array.array('h',(rng.randrange(-32768,32768) for _ in range(self.frames*2)))
            path.write_bytes(stem.HEADER.pack(stem.MAGIC,44100,2,3,64,self.frames,
                             struct.pack('<f',gain)+b'\0'*28)+pcm.tobytes())
            self.files.append(path)

    def test_all_formats_and_masks_match_reference_with_gains(self):
        from app.stems import mixing
        outputs={mask:self.root/f'mask-{mask}.f32' for mask in range(1,8)}
        self.worker.mix(self.pcm,self.files,list(map(audition.gain,self.files)),self.frames,outputs)
        mix=array.array('f');mix.frombytes(self.pcm.read_bytes())
        parts=[]
        for path in self.files:
            with path.open('rb') as f:
                f.seek(64);parts.append(audition.read_pcm(f,self.frames,audition.gain(path)))
        count=(self.frames+293)//294
        for mask,path in outputs.items():
            self.assertEqual(path.read_bytes(),mixing.reconstruct_static(mix,parts,mask).tobytes())
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg required')
        for tag in (b'PWV3',b'PWV5',b'PWV7',None):
            with self.subTest(tag=tag):
                expected=wave_dsp.columns(outputs[5],self.frames,tag,count)
                actual=wave_dsp.columns(outputs[5],self.frames,tag,count,accelerator=self.worker)
                self.assertEqual(actual,expected)

    def test_three_band_envelopes_varied_lengths(self):
        rng=random.Random(51)
        for length,count in ((100,15),(101,16),(1003,151),(3041,457)):
            bands=[[rng.randrange(32768) if i%11 else 0 for i in range(length)] for _ in range(3)]
            self.assertEqual(wave_dsp.three_band(bands,count),
                             wave_dsp.three_band(bands,count,accelerator=self.worker))

    def test_worker_errors_are_not_silently_retried(self):
        with self.assertRaises(RuntimeError):
            self.worker.mix(self.root/'missing',self.files,[1,1],self.frames,{1:self.root/'out'})

    def test_parallel_build_matches_fallback_and_progress_is_monotonic(self):
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg required')
        import subprocess
        audio=self.root/'source.wav'
        subprocess.run(['ffmpeg','-v','error','-f','f32le','-ar','44100','-ac','2','-i',str(self.pcm),
                        '-c:a','pcm_f32le',str(audio)],check=True)
        track=SimpleNamespace(location=audio)
        template=analysis.Template(b'PWV5',b'',(self.frames+293)//294,(),'00'*32)
        def decode(source,target,*args,**kwargs):
            shutil.copyfile(self.pcm,target);return self.frames
        outputs=[]
        for fast in (False,True):
            workspace=self.root/str(fast);workspace.mkdir();progress=[]
            # The function owns the worker; create a separate one for this build.
            with patch.object(importing,'decode',decode), patch.object(wave_acceleration,'open_worker',
                    return_value=wave_acceleration.open_worker() if fast else None):
                path=waveform.build(track,self.root,template,safety.digest(audio),'ffmpeg',workspace,
                                    lambda:None,files=self.files,format=None,progress=progress.append)
            outputs.append(path.read_bytes())
            self.assertEqual(progress,sorted(progress));self.assertEqual(progress[-1],1)
            self.assertFalse(list(workspace.glob('combination*')))
            if fast and self.worker.memory:
                self.assertFalse((workspace/'mix.f32').exists())
        self.assertEqual(*outputs)

    def test_streaming_build_cancellation_removes_partial_output(self):
        if not self.worker.memory or not shutil.which('ffmpeg'):
            self.skipTest('SciPy and FFmpeg required')
        import subprocess
        audio=self.root/'cancel.wav'
        subprocess.run(['ffmpeg','-v','error','-f','f32le','-ar','44100','-ac','2','-i',str(self.pcm),
                        '-c:a','pcm_f32le',str(audio)],check=True)
        control=processes.Control()
        with control.bind():
            worker=wave_acceleration.open_worker()
            try:
                def cancel(value):
                    control.cancel()
                    control.checkpoint()
                with self.assertRaises(processes.Cancelled):
                    worker.build(audio,self.files,self.frames,'ffmpeg',self.root,cancel)
                self.assertIsNotNone(worker.process.poll())
                self.assertFalse((self.root/'wave-columns.bin').exists())
            finally:worker.close()

    def test_memory_budget_limits_are_bounded(self):
        from app.stems.wave_encoding import required_memory
        self.assertLess(required_memory(44100*324,7),512*1024**2)
        self.assertGreater(required_memory(0x5000000,7),512*1024**2)

    def test_multi_format_parallel_and_low_space_match(self):
        if not shutil.which('ffmpeg'): self.skipTest('FFmpeg required')
        template=analysis.Template(b'PWV5',b'',(self.frames+293)//294,(),'00'*32)
        outputs=[]
        for free in (0,10**12):
            with patch('shutil.disk_usage',return_value=SimpleNamespace(free=free)):
                result=waveform.accelerated_combinations(self.pcm,self.files,self.frames,7,template,
                    None,'ffmpeg',self.root,lambda:None,lambda value:None,self.worker)
            outputs.append(result)
        self.assertEqual(*outputs)

    def test_cancellation_owns_worker(self):
        control=processes.Control()
        with control.bind():
            worker=wave_acceleration.open_worker()
            self.assertIsNotNone(worker)
            try:
                control.cancel()
                with self.assertRaises(processes.Cancelled):worker.call('peaks')
                self.assertIsNotNone(worker.process.poll())
            finally:worker.close()

    def test_missing_runtime_retains_fallback(self):
        with patch('app.stems.provisioning.detect',return_value=SimpleNamespace(ready=False)):
            self.assertIsNone(wave_acceleration.open_worker())
