"""Host checks for the RX3 audio-thread mailbox and wire framing."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct

from scripts.receive_live_audio import parse_packet


ROOT = Path(__file__).resolve().parents[1]


class AudioStreamTests(unittest.TestCase):
    def test_wire_packet_rejects_malformed_and_decodes_identity(self):
        raw = struct.pack("<4sBBHIIIiIHH", b"RX3A", 1, 2, 0, 22050,
                          4, 9, 44100, 3, 2, 0) + struct.pack("<hh", -123, 456)
        packet = parse_packet(raw)
        self.assertEqual((packet["deck"], packet["generation"], packet["source_position"]),
                         (2, 9, 44100))
        self.assertEqual(packet["pcm"], struct.pack("<hh", -123, 456))
        for malformed in (raw[:-1], raw[:3], b"BAD!" + raw[4:], raw[:28] + b"\0\0" + raw[30:]):
            with self.assertRaises(ValueError):
                parse_packet(malformed)

    def test_fixed_ring_conversion_backpressure_and_order(self):
        source = r'''
#include <assert.h>
#include <stdint.h>
struct rx3_stereo { float left, right; };
#include "rx3_audio_stream.h"
int main(void) {
    struct audio_ring ring = {0};
    struct rx3_stereo pcm[1024];
    for (unsigned i=0;i<1024;i++) pcm[i]=(struct rx3_stereo){1.0f,-1.0f};
    pcm[0]=(struct rx3_stereo){1.0f,1.0f};
    pcm[2]=(struct rx3_stereo){-1.0f,-1.0f};
    for (unsigned i=0;i<AUDIO_RING_SLOTS;i++)
        audio_enqueue(&ring,7,1000+(int)(1024*i),pcm,1024);
    audio_enqueue(&ring,7,9999,pcm,1024);
    assert(ring.dropped==1 && ring.head==AUDIO_RING_SLOTS);
    for (unsigned i=0;i<AUDIO_RING_SLOTS;i++) {
        struct audio_packet p={0};
        assert(audio_dequeue(&ring,&p));
        assert(p.sequence==i && p.generation==7 && p.source_position==1000+(int)(1024*i));
        assert(p.count==512 && p.samples[0]==32767 && p.samples[1]==-32768);
    }
    { struct audio_packet p; assert(!audio_dequeue(&ring,&p)); }
    audio_enqueue(&ring,8,42,pcm,1024);
    { struct audio_packet p; assert(audio_dequeue(&ring,&p));
      assert(p.sequence==32 && p.generation==8 && p.dropped==1); }
    audio_enqueue(&ring,8,1066,pcm,4096);
    { struct audio_packet p; assert(audio_dequeue(&ring,&p));
      assert(p.count==512 && p.dropped==2); }
    /* Two native render paths can interleave at an offset. The older
     * overlapping path is ignored without incrementing queue-drop count. */
    struct audio_ring doubled = {0};
    audio_enqueue(&doubled,1,936505,pcm,512);
    audio_enqueue(&doubled,1,934346,pcm,512);
    audio_enqueue(&doubled,1,937017,pcm,512);
    audio_enqueue(&doubled,1,934858,pcm,512);
    assert(doubled.head==2 && doubled.dropped==0);
    audio_enqueue(&doubled,1,800000,pcm,512); /* loop/cue rewind */
    assert(doubled.head==3);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(source)
            subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "mod/modules/position-diagnostic"),
                            str(path / "test.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)
