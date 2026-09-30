#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Create private, deterministic hardware acceptance audio; never export to USB."""
import argparse
import array
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave
import zlib

RATE = 44100

def logo_png(light=False):
    width, height = 640, 160
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            if x < 4 or x >= width-4 or y < 4 or y >= height-4:
                pixel = (0, 0, 0, 255) if light else (255, 255, 255, 255)
            elif abs(x-width//2) < 2 or abs(y-height//2) < 2:
                pixel = (255, 0, 0, 255)
            elif 24 <= y < 64 and 24 <= x < 184:
                v = ((x-24)//40)*64
                pixel = (v, v, v, 255)
            else:
                pixel = (0, 0, 0, 0)
            raw.extend(pixel)
    def chunk(kind, body):
        return struct.pack('>I', len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

def pcm(seconds, signal):
    count = round(seconds * RATE)
    output = array.array('h')
    for i in range(count):
        t = i / RATE
        ramp = min(1.0, i / 220, (count - 1 - i) / 220)
        left, right = signal(t)
        for value in (left, right):
            output.append(round(max(-0.95, min(0.95, value * ramp)) * 32767))
    if sys.byteorder != 'little':
        output.byteswap()
    return output.tobytes()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    dest = args.output.expanduser().resolve()
    if dest.exists():
        parser.error('Output already exists; choose a new directory to preserve evidence.')
    dest.mkdir(parents=True)
    tracks = []
    def save(name, data, *, key='', bpm='', artist='RX3 Acceptance', purpose='track', title=None):
        path = dest / (name + '.wav')
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), 'wb') as handle:
            handle.setparams((2, 2, RATE, 0, 'NONE', 'not compressed'))
            handle.writeframes(data)
        tracks.append(dict(file=path.relative_to(dest).as_posix(), title=title or path.stem,
                           artist=artist, bpm=bpm, camelot=key, frames=len(data)//4,
                           seconds=len(data)/(4*RATE), purpose=purpose,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    tau = 2 * math.pi
    def transport(t):
        beat = int(t * 2)
        phase = t % 0.5
        click = 0.16 * math.exp(-phase * 100) * math.sin(tau * 1800 * t)
        marker = 0.14 * math.exp(-phase * 35) * math.sin(tau * 880 * t) if beat % 32 == 0 else 0
        return (0.12 * math.sin(tau * 440 * t) + click + marker,
                0.12 * math.sin(tau * 660 * t) + click + marker)
    save('01_TRANSPORT/Q01_120BPM_64s', pcm(64, transport), bpm=120)
    # Independent acoustic oracle: concert A=440 Hz, root + minor/major triad.
    minor = [56, 51, 58, 53, 60, 55, 62, 57, 64, 59, 54, 61]
    major = [59, 54, 61, 56, 63, 58, 65, 60, 67, 62, 57, 64]
    key_audio = []
    for letter, roots, third in [('A', minor, 3), ('B', major, 4)]:
        for number, midi in enumerate(roots, 1):
            freqs = [440 * 2 ** ((midi + interval - 69) / 12) for interval in (0, third, 7)]
            def chord(t, freqs=freqs):
                v = sum(0.065 * math.sin(tau*f*t) for f in freqs)
                return v, v
            data = pcm(8, chord)
            key_audio.append(data)
            save(f'02_KEY24/K{number:02d}{letter}', data, key=f'{number}{letter}', bpm=120)
    save('02_KEY24/K_UNKNOWN', key_audio[0], purpose='unknown_key')
    # Quantize components separately, then sum the integers: exact PCM identity.
    def vocal(t):
        v = 0.12 * math.sin(tau * 440 * t) * (0.6 + 0.4*math.sin(tau*1*t)**2)
        return v, v * 0.8
    def drums(t):
        v = 0.12 * math.exp(-(t % 0.5) * 70) * math.sin(tau*1800*t)
        return v, v
    def bass(t):
        return 0.10 * math.sin(tau*110*t), 0.10 * math.sin(tau*165*t)
    parts = [pcm(32, f) for f in (vocal, drums, bass)]
    values = [array.array('h', b) for b in parts]
    if sys.byteorder != 'little':
        for a in values: a.byteswap()
    mixed = array.array('h', (sum(v) for v in zip(*values)))
    assert max(map(abs, mixed)) < 32767
    if sys.byteorder != 'little': mixed.byteswap()
    save('03_STEMS/SYN3_mix', mixed.tobytes(), bpm=120)
    for name, data in zip(('vocals', 'drums', 'inst_reference'), parts):
        save('03_STEMS/SYN3_' + name, data, purpose='manual_import_oracle', bpm=120)
    banks = []
    for index, (mode, seconds, gain) in enumerate(zip(
            ('once','hold','loop','latch','once','hold','loop','once'),
            (2,8,1,8,0.1,8,0.25,9), (100,100,100,50,0,100,200,100)), 1):
        freq = 220 + 110 * index
        data = pcm(seconds, lambda t, f=freq: (0.08*math.sin(tau*f*t), 0.08*math.sin(tau*f*t)))
        name = f'06_SAMPLES/P{index}_{mode}_{seconds}s'
        save(name, data, purpose='sample_source')
        banks.append(dict(pad=index,source=name+'.wav',mode=mode,gain=gain,
                          colour=['#ff0000','#00ff00','#0000ff','#ffff00','#ff00ff','#00ffff','#ffffff','#ff8000'][index-1]))
    for i in range(100):
        frames = RATE * (1 + i % 16) // 2
        save(f'04_SORT/SORT_{i:03d}', key_audio[i%24][:frames*4],
             key=f'{i%12+1}{"A" if i%2 else "B"}', bpm=(80,100,128,140)[i%4],
             artist=('Zèbre','Alpha','Artiste très long pour tester le défilement jusqu’au bout','')[i%4],
             title=('Titre identique' if i%10==0 else f'{99-i:03d} Titre tri {i}'), purpose='sort_metadata')
    for title in ('NIÑO','CORAZÓN','Bébé','Straße','Ðelta','Þorn','NINO témoin','CORAZON témoin'):
        save('05_SEARCH/'+title,key_audio[0][:RATE*4],title=title,purpose='search_metadata')
    for light in (False, True):
        (dest/('logo-light.png' if light else 'logo-dark.png')).write_bytes(logo_png(light))
    (dest/'bank-spec.json').write_text(json.dumps(dict(default_volume=50,bank_B1_shift_silence=True,
        bank_B2_shift_silence=False,pads=banks),ensure_ascii=False,indent=2)+'\n')
    with (dest/'tracks.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(tracks[0]));writer.writeheader();writer.writerows(tracks)
    manifest=dict(format='rx3-hardware-fixtures/1',sample_rate=RATE,sample_width=2,channels=2,
                  generated=True,rekordbox_exported=False,stems_prepared=False,samples_exported=False,
                  notes=['Metadata CSV must be imported/assigned and checked in a dedicated library.',
                         'SORT keys are intentional metadata fixtures, not acoustic key assertions.',
                         'SYN3 is not a music separation quality test.',
                         'P8 source is 9 seconds: app output must be truncated to 8 seconds.',
                         'Logo PNGs are sources to frame/export in the app, not device-ready assets.'],tracks=tracks)
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(directory=str(dest),wav_files=len(tracks),bytes=sum((dest/t['file']).stat().st_size for t in tracks))))

if __name__ == '__main__':
    main()
