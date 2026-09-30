# SPDX-License-Identifier: MPL-2.0
"""Separated peaks above unity must survive storage and cancellation."""
import array
import io
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from app.stems import audition, stem, mixing, preview


class GainTests(unittest.TestCase):
    def test_gain_headers_reject_unknown_nonfinite_and_reserved(self):
        self.assertEqual(audition.pcm_gain(2, bytes(32)), 1)
        self.assertEqual(audition.pcm_gain(3, struct.pack('<f', 1.25)+bytes(28)), 1.25)
        for value in [0, .99, 65, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                audition.pcm_gain(3, struct.pack('<f', value)+bytes(28))
        with self.assertRaises(ValueError): audition.pcm_gain(2, struct.pack('<f', 1)+bytes(28))
        with self.assertRaises(ValueError): audition.pcm_gain(3, struct.pack('<f', 1)+bytes(27)+b'x')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_peak_preserved_without_clipping_and_cancels_in_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            source=root/'source.wav'
            values=array.array('f', [1.25,-1.25,.8,-.6,.25,-.2]*2000)
            source.write_bytes(audition.float_wav(values))
            target=root/'drums.rx3stem'
            result=stem.write_stem(source,target,sample_format='s16_gain',match_full=source)
            self.assertGreater(result.playback_gain,1.25)
            self.assertEqual(audition.header(target),len(values)//2)
            with target.open('rb') as stream:
                stream.seek(64)
                decoded=audition.read_pcm(stream,len(values)//2,audition.gain(target))
            restored=array.array('f',(v/32768 for v in decoded))
            self.assertLess(max(abs(a-b) for a,b in zip(values,restored)),.00004)
            self.assertGreater(max(restored),1.24)
            mixed=mixing.reconstruct_static(values,[decoded],1)
            self.assertLess(max(map(abs,mixed)),.00004)
            # Preview transport contains the restored amplitude, including >1.
            with_preview=preview.Preview(source,files=[target])
            try:
                import base64
                transported=array.array('f',base64.b64decode(with_preview.chunk(0)['pcm'][1]))
                self.assertEqual(transported.tobytes(),restored.tobytes())
            finally: with_preview.close()

    def test_scaled_waveform_matches_reference_all_masks(self):
        raw=array.array('h',[32000,-31000,1200,-4000]*200)
        data=audition.read_pcm(io.BytesIO(raw.tobytes()),len(raw)//2,1.253)
        full=array.array('f',(v/32768+.1 for v in data))
        for mask in range(8):
            roles=[data,data]
            levels=[float(bool(mask&(1<<i))) for i in range(4)]
            state=mixing.MixState(levels[:],levels[:],levels[:])
            self.assertEqual(mixing.reconstruct_static(full,roles,mask).tobytes(),
                             mixing.reconstruct(full,roles,mask,state).tobytes())

    def test_native_gain_and_mix(self):
        if not shutil.which('cc'): self.skipTest('C compiler required')
        root=pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            src=pathlib.Path(directory)/'gain.c';exe=src.with_suffix('')
            src.write_text('''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#include <math.h>
#include <pthread.h>
typedef struct rx3_stereo Float2;
#include "stems/rx3_stems_decl.h"
#define RX3_PLATFORM_H
#include "stems/rx3_stems_audio.h"
int main(void) {
 struct stem_header h={.format=FORMAT_S16_GAIN};float scale=1.25f;
 memcpy(h.reserved,&scale,4); assert(stems_pcm_gain(&h)==scale);
 struct stems_deck_context c={0};Short2 pcm={32760,-32760};
 c.payload_count=1;c.selection=0x33;
 c.payloads[0].data=&pcm;c.payloads[0].frames=1;
 c.payloads[0].format=FORMAT_S16_GAIN;c.payloads[0].pcm_gain=scale;
 stems_reset_mix(&c);stems_set_mask(&c,1);
 c.gain[0]=c.target[0]=1;c.gain[1]=c.target[1]=0;c.transition_cursor=256;
 Float2 output={32760*scale/32768,-32760*scale/32768};
 stems_mix(&c,0,&output,1); assert(output.left==0 && output.right==0);
 scale=NAN;memcpy(h.reserved,&scale,4);assert(!stems_pcm_gain(&h));
 return 0;
}
''')
            subprocess.run(['cc','-std=c11','-ffp-contract=off','-I',str(root/'mod/modules'),str(src),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
