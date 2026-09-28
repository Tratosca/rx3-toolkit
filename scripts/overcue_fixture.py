# SPDX-License-Identifier: MPL-2.0
"""Create a synthetic bank beside a COPY of an owner-local Rekordbox library.

Run from the repository with python -m scripts.overcue_fixture. The library
is read only. Its track names and analyses remain display placeholders;
the two generated audio files contain test tones, not the named recordings.
"""
import argparse
import array
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from app.stems import overcue, pdb


def make(source, output, seconds=90):
    if output.exists():
        raise ValueError('Use a new empty fixture destination')
    output.mkdir(parents=True)
    shutil.copytree(source/'PIONEER', output/'PIONEER')
    tables = pdb.read_tables((source/'PIONEER/rekordbox/export.pdb').read_bytes())
    tracks = [pdb.parse_track(row) for row in pdb.iter_rows(tables, 0)]
    tracks = [t for t in tracks if 'DO IT' in t.title or 'Stop This Flame' in t.title]
    if len(tracks) != 2:
        raise ValueError('This fixture expects the existing DO IT and Stop This Flame library entries')
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        pcm = {}
        for role, mask in zip(overcue.ROLES, overcue.MASKS):
            pattern = array.array('h')
            for i in range(96):
                sample = round(sum(1400 * math.sin(2*math.pi*(j+1)*i/96)
                                   for j in range(3) if mask & (1<<j)))
                pattern.extend((sample, round(sample*.7)))
            raw = work/(role+'.s16')
            raw.write_bytes(pattern.tobytes() * (1000*seconds))
            pcm[role] = raw
        for track in tracks:
            target = output/track.file_path.lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 's16le', '-ar', '96000',
                            '-ac', '2', '-i', str(pcm['full-mix']), '-ar', '44100',
                            '-c:a', 'pcm_s16be', str(target)], check=True)
            entry = overcue.publish(output, track.file_path, track.track_id, pcm,
                                   provenance={'fixture': '1000/2000/3000 Hz, masks INST/VOCAL/DRUMS'})
            print(track.track_id, track.file_path, entry['bundle'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=90)
    args = parser.parse_args()
    make(args.library.resolve(), args.output.resolve(), args.seconds)
