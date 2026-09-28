# SPDX-License-Identifier: MPL-2.0
"""Drive-wide waveform format changes; PCM roles are copied, never separated."""
import pathlib
import struct
from app.localization import LocalizedError, Message, error_message
from app.stems import package, wave_settings, deferred_waveforms, processes
from app.stems.rekordbox import export_stem


def tracks_by_name(collection):
    result = {}
    for playlist in collection.playlists if collection else []:
        for track in playlist.tracks:
            result.setdefault(export_stem(track.location.stem).casefold(), {})[str(track.location)] = track
    return result


def status(drive, collection=None, format=None):
    drive = pathlib.Path(drive)
    state = wave_settings.inspect(drive) if format else {'format': 'all', 'confirmed': True, 'changed': False}
    selected = format
    if selected is not None and selected not in wave_settings.FORMATS:
        raise LocalizedError('stems.waveSelection')
    lookup = tracks_by_name(collection)
    items = []
    for path in sorted((drive/'RX3_STEMS').glob('*.rx3stem')):
        from app.stems import safety
        safety.check_target(path)
        try:
            if not package.is_package(path):
                continue
            parsed = package.read(path, verify=False)
            recorded = parsed['manifest'].get('waveform_settings')
            if not state['confirmed'] and recorded is not None and recorded != state['currentFingerprint']:
                state['changed'] = True
            if wave_settings.supports(parsed['waveform'], selected):
                continue
            matches = list(lookup.get(path.stem.casefold(), {}).values())
            track = matches[0] if len(matches) == 1 else None
            items.append({'id': track.track_id if track else '',
                          'title': parsed['manifest'].get('title',path.stem),
                          'available': bool(track and track.location.is_file())})
        except (OSError, ValueError, struct.error):
            items.append({'id':'','title':path.stem,'available':False})
    return dict(state, format=selected, items=items)


def run(tracks, drive, format, expected, ffmpeg, checkpoint, progress):
    results, errors = [], []
    for index, track in enumerate(tracks):
        checkpoint()
        if expected is not None and wave_settings.fingerprint(drive) != expected:
            raise LocalizedError('stems.waveSettingsChanged')
        try:
            if deferred_waveforms.upgrade(track, drive, ffmpeg, checkpoint, format=format, expected_settings=expected,
                    progress=lambda value: progress(Message('stems.waveTrack',name=track.title),
                                                     100*(index+value)/max(1,len(tracks)))):
                results.append(track.track_id)
        except processes.Cancelled:
            raise
        except Exception as error:
            errors.append({'track':track.title,'error':error_message(error)})
    return {'waveforms':results,'errors':errors}
