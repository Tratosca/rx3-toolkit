# SPDX-License-Identifier: MPL-2.0
"""Remux v0.5.2 PCM stems; only waveform analysis decodes the source mix."""
import pathlib
import tempfile

from app.localization import LocalizedError
from app.stems import audition, package, safety, stem, limits, wave_settings
from app.stems.rekordbox import export_stem


def legacy_files(track, drive):
    directory = pathlib.Path(drive) / 'RX3_STEMS'
    target = directory / (export_stem(track.location.stem) + '.rx3stem')
    safety.check_target(target)
    if not target.is_file() or package.is_package(target):
        return []
    files, _, rejected = audition.role_files(directory, export_stem(track.location.stem))
    if rejected or len(files) > 2:
        raise LocalizedError('stems.migrationInvalid', name=track.title)
    return files


def migrate(track, drive, ffmpeg='ffmpeg', checkpoint=lambda: None, prepare_drum=None, progress=lambda stage, value: None, *, processing=None):
    safety.require_library_closed()
    files = legacy_files(track, drive)
    if not files:
        return False
    progress("checking", 0)
    source_stamp = safety.source_stamp(track.location, lambda done, total: (checkpoint(), progress("checking", .04 * done / max(1, total))))
    stamps = []
    for index, path in enumerate(files):
        stamps.append(safety.source_stamp(path, lambda done, total: (checkpoint(), progress("checking", .04 + .06 * (index + done / max(1, total)) / len(files)))))
    target = files[0]
    safety.require_space(target.parent, sum(p.stat().st_size for p in files) * 3)
    with tempfile.TemporaryDirectory(prefix='rx3-remux-') as temporary:
        inputs = dict(zip(stem.PREPARED_ROLES, files))
        added_drums = prepare_drum is not None and "drums" not in inputs
        if added_drums:
            progress("drums", .1)
            inputs["drums"] = prepare_drum(track, pathlib.Path(temporary))
            if audition.header(inputs["drums"]) != audition.header(files[0]):
                raise LocalizedError("stems.auditionLength")
        local = package.build(track, pathlib.Path(drive), inputs,
                              pathlib.Path(temporary), source_stamp[2], ffmpeg, checkpoint,
                              metadata={'origin': 'remux-v0.5.2', 'separation_provenance': 'legacy-unverified',
                                        **({'drum_processing': processing} if added_drums else {})},
                              progress=lambda value: progress("waveforms", .1 + .7 * value))
        checkpoint()
        safety.check_source(track.location, source_stamp)
        for path, stamp in zip(files, stamps):
            safety.check_source(path, stamp)
        progress("backup", .8)
        # No source is replaced until every backup is durable. Existing different
        # backups are never overwritten. Retrying an interrupted run is safe.
        backup = target.parent / 'backup-v0.5.2'
        safety.check_target(backup)
        backup.mkdir(exist_ok=True)
        for path, stamp in zip(files, stamps):
            checkpoint()
            saved = backup / path.name
            safety.check_target(saved)
            if saved.exists():
                if safety.digest(saved) != stamp[2]:
                    raise LocalizedError('stems.migrationBackup', name=path.name)
            else:
                safety.publish(path, saved)
        checkpoint()
        safety.require_library_closed()
        safety.check_source(track.location, source_stamp)
        for path, stamp in zip(files, stamps):
            safety.check_source(path, stamp)
        progress("publishing", .95)
        safety.publish(local, target)
        progress("done", 1)
    return True


def ensure_three(track, drive, source_stamp, ffmpeg='ffmpeg', checkpoint=lambda: None,
                 prepare_drum=None, processing=None, progress=lambda stage, value: None):
    """Keep complete packages, upgrade two-part/legacy audio without replacing vocals.

    None means no reusable audio for this source. Corrupt packages are reported
    without overwriting them. The caller owns the playlist job and manifest.
    """
    drive = pathlib.Path(drive)
    target = drive / 'RX3_STEMS' / (export_stem(track.location.stem) + '.rx3stem')
    safety.check_target(target)
    if not target.is_file():
        return None
    checkpoint()
    if not package.is_package(target):
        def legacy_progress(stage, value):
            fraction = .5 + .4 * (value - .1) / .7 if stage == 'waveforms' else .9 if stage == 'backup' else value
            progress(stage, fraction)
        migrate(track, drive, ffmpeg, checkpoint, prepare_drum, legacy_progress, processing=processing)
        parsed = package.read(target)
        return 'migrated', parsed['manifest']
    before = safety.source_stamp(target)
    parsed = package.read(target)
    if parsed['manifest']['source_sha256'] != source_stamp[2]:
        return None
    if parsed['roles'] == stem.PREPARED_ROLES and wave_settings.supports(parsed['waveform']):
        safety.check_source(track.location, source_stamp)
        safety.check_source(target, before)
        return 'existing', parsed['manifest']
    limits.require(parsed['frames'], len(stem.PREPARED_ROLES))
    safety.require_space(target.parent, limits.package_bytes(parsed['frames'], len(stem.PREPARED_ROLES)))
    with tempfile.TemporaryDirectory(prefix='rx3-upgrade-') as directory:
        workspace = pathlib.Path(directory)
        inputs = dict(zip(parsed['roles'], parsed['members'][:-2]))
        metadata = dict(parsed['manifest'])
        if 'drums' not in inputs:
            progress('drums', .1)
            inputs['drums'] = prepare_drum(track, workspace)
            if audition.header(inputs['drums']) != parsed['frames']:
                raise LocalizedError('stems.auditionLength')
            # The old vocal did not come from the current separator. Preserve
            # its processing identity and record only the newly computed role.
            metadata['drum_processing'] = processing
        inputs = {role: inputs[role] for role in stem.PREPARED_ROLES}
        if isinstance(metadata.get('checks'), dict):
            metadata['checks'] = dict(metadata['checks'], waveform=True)
        local = package.build(track, drive, inputs, workspace, source_stamp[2], ffmpeg, checkpoint,
                              metadata, progress=lambda value: progress('waveforms', .5 + .4 * value))
        checkpoint()
        safety.require_library_closed()
        safety.check_source(track.location, source_stamp)
        safety.check_source(target, before)
        progress('publishing', .95)
        package.publish(local, target)
        return 'migrated', package.read(target)['manifest']
