# SPDX-License-Identifier: MPL-2.0
"""Per-drive waveform choice and opaque, bounded My Settings change detection.

No unverified byte offset is interpreted as a waveform colour. A settings change
requires the DJ to confirm the display format; unrelated changes need no rebuild.
"""
import hashlib
import json
import pathlib
import tempfile
from app.stems import safety
from app.localization import LocalizedError

FORMATS = {'blue': b'PWV3', 'rgb': b'PWV5', '3band': b'PWV7'}
PROFILE = 'waveform-settings.json'


def fingerprint(drive):
    digest = hashlib.sha256()
    present = False
    for name in ('MYSETTING.DAT', 'MYSETTING2.DAT', 'DEVSETTING.DAT'):
        path = pathlib.Path(drive) / 'PIONEER' / name
        safety.check_target(path)
        if not path.exists():
            continue
        if not path.is_file() or path.stat().st_size > 4096:
            raise LocalizedError('stems.waveSettingsUnreadable')
        digest.update(name.encode()); digest.update(path.read_bytes())
        present = True
    return digest.hexdigest() if present else ''


def choice(drive):
    path = pathlib.Path(drive) / 'RX3_STEMS' / PROFILE
    safety.check_target(path)
    if not path.exists():
        return {'format': '3band', 'fingerprint': None, 'confirmed': False}
    try:
        if path.stat().st_size > 4096:
            raise ValueError()
        value = json.loads(path.read_text())
        if value.get('format') not in FORMATS or not isinstance(value.get('fingerprint'), str):
            raise ValueError()
        return dict(value, confirmed=True)
    except (OSError, ValueError, AttributeError):
        raise LocalizedError('stems.waveSettingsUnreadable') from None


def inspect(drive):
    selected = choice(drive)
    current = fingerprint(drive)
    return dict(selected, currentFingerprint=current,
                changed=selected['confirmed'] and selected['fingerprint'] != current,
                settingsPresent=bool(current))


def save(drive, format, expected):
    drive = pathlib.Path(drive)
    if format not in FORMATS or not drive.is_dir():
        raise LocalizedError('stems.waveSelection')
    current = fingerprint(drive)
    if current != expected:
        raise LocalizedError('stems.waveSettingsChanged')
    target = drive / 'RX3_STEMS' / PROFILE
    safety.check_target(target)
    target.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rx3-wave-choice-') as directory:
        local = pathlib.Path(directory) / PROFILE
        local.write_text(json.dumps({'format':format, 'fingerprint':current})+'\n')
        safety.publish(local, target)
    return inspect(drive)


def supports(info, format=None):
    return bool(info and (info['version'] == 3 or
                         format is not None and info['version'] == 4 and info['format'] == FORMATS[format]))
