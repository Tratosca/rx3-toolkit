# SPDX-License-Identifier: MPL-2.0
"""Add waveforms to verified audio packages without invoking a separator."""
import json
import pathlib
import struct
import tempfile

from app.localization import LocalizedError, Message
from app.stems import cache, limits, package, safety, wave_settings
from app.stems.rekordbox import export_stem


def target_for(track, drive):
    return drive / 'RX3_STEMS' / (export_stem(track.location.stem) + '.rx3stem')


def status(track, drive):
    target = target_for(track, drive)
    safety.check_target(target)
    if not target.is_file():
        return 'missing'
    try:
        # Advisory only: full CRC and source identity checks run in the job.
        parsed = package.read(target, verify=False)
        return 'ready' if wave_settings.supports(parsed['waveform']) else 'pending'
    except (OSError, ValueError, struct.error):
        return 'invalid'


def upgrade(track, drive, ffmpeg='ffmpeg', checkpoint=lambda: None, *, force=False, format=None, progress=lambda value: None, expected_settings=None):
    safety.require_library_closed()
    target = target_for(track, drive)
    if not target.is_file():
        raise LocalizedError('stems.waveAudioMissing', name=track.title)
    checkpoint()
    before = safety.source_stamp(target)
    parsed = package.read(target)
    if not track.location.is_file():
        raise LocalizedError('stems.sourceMissing', name=track.location.name)
    source = safety.source_stamp(track.location)
    if source[2] != parsed['manifest']['source_sha256']:
        raise LocalizedError('stems.waveSourceChanged', name=track.title)
    if not force and wave_settings.supports(parsed['waveform'], format):
        return False
    limits.require(parsed['frames'], len(parsed['roles']))
    safety.require_space(target.parent, limits.package_bytes(parsed['frames'], len(parsed['roles'])))
    with tempfile.TemporaryDirectory(prefix='rx3-add-waveforms-') as directory:
        work = pathlib.Path(directory)
        inputs = dict(zip(parsed['roles'], parsed['members'][:-2]))
        metadata = dict(parsed['manifest'])
        if isinstance(metadata.get('checks'), dict):
            metadata['checks'] = dict(metadata['checks'], waveform=True)
        local = package.build(track, drive, inputs, work, source[2], ffmpeg, checkpoint, metadata,
                              wave_format=format, progress=progress)
        checkpoint()
        safety.check_source(track.location, source)
        safety.check_source(target, before)
        entries, _ = cache.read_manifest(drive)
        previous = next((entry for entry in entries if entry.get('stem') == target.name), {})
        entry = dict(previous, stem=target.name, trackId=track.track_id, title=track.title,
                     artist=track.artist, source_sha256=source[2], source_bytes=source[0])
        for key in ('origin', 'processing', 'checks', 'gainCorrection', 'encoderDelayFrames'):
            if key in parsed['manifest']:
                entry[key] = parsed['manifest'][key]
        if isinstance(entry.get('checks'), dict):
            entry['checks'] = dict(entry['checks'], waveform=True)
        digest = safety.digest(local)
        entry['stems'] = [dict(next((item for item in previous.get('stems', [])
                                    if item.get('role') == role), {}), role=role,
                               file=target.name, bytes=local.stat().st_size, sha256=digest)
                          for role in parsed['roles']]
        manifest = work / safety.MANIFEST_NAME
        manifest.write_text(json.dumps({'format': 2, 'tracks':
            [item for item in entries if item.get('stem') != target.name] + [entry]}, indent=2) + '\n')
        checkpoint()
        # No cancellation between these two atomic publications. The audio
        # remains usable even if a filesystem failure prevents manifest update.
        if expected_settings is not None and wave_settings.fingerprint(drive) != expected_settings:
            raise LocalizedError("stems.waveSettingsChanged")
        package.publish(local, target)
        safety.publish(manifest, target.parent / safety.MANIFEST_NAME)
    return True


def run(playlist, drive, ffmpeg, checkpoint, progress, *, track_id=None):
    results, errors = [], []
    tracks = [track for track in playlist.tracks if track_id is None or track.track_id == track_id]
    if track_id is not None and not tracks:
        raise LocalizedError("stems.waveSelection")
    for index, track in enumerate(tracks):
        checkpoint()
        if track_id is None and status(track, drive) != 'pending':
            continue
        progress(Message('stems.waveTrack', name=track.title), round(index * 100 / max(1, len(tracks))))
        # Cancellation must propagate, never become an ordinary track error.
        from app.stems.processes import Cancelled
        try:
            if upgrade(track, drive, ffmpeg, checkpoint, force=track_id is not None):
                results.append(track.track_id)
        except Cancelled:
            raise
        except Exception as error:
            from app.localization import error_message
            errors.append({'track': track.title, 'error': error_message(error)})
    return {'waveforms': results, 'errors': errors}
