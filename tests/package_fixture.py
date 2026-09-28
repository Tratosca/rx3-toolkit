# SPDX-License-Identifier: MPL-2.0
"""A bounded waveform fixture; package writing and verification remain real."""
import os
import tempfile
from unittest.mock import patch

from app.stems import audition, cache, waveform


def isolate(case):
    """Keep a test away from the operator's stem cache and mounted drives.

    A job reuses whatever the per-user cache or a mounted drive holds for the
    same source hash, so a test that reads them depends on earlier runs.
    """
    home = tempfile.TemporaryDirectory(prefix="rx3-test-home-")
    case.addCleanup(home.cleanup)
    for patcher in (patch.dict(os.environ, {"RX3_STEM_STUDIO_HOME": home.name}),
                    patch.object(cache, "mounted_roots", return_value=())):
        patcher.start()
        case.addCleanup(patcher.stop)

def wave_fixture(track, drive, template, source_hash, ffmpeg, workspace, checkpoint, *, files, format=None, progress=lambda value: None):
    frames = audition.header(files[0])
    data = {None:b'\x1f\x1c\x00\x08\x09\x0a', b'PWV3':b'\x1f', b'PWV5':b'\x1c\x00', b'PWV7':b'\x08\x09\x0a'}[format] * template.count
    masks = 3 if len(files) == 1 else 7
    combinations = {mask: (data, '11'*32) for mask in range(1, masks+1)}
    path = workspace/'fixture.rx3wave'
    waveform.write_combinations(path, template, frames, source_hash, combinations, format)
    return path
