# SPDX-License-Identifier: MPL-2.0
"""Compare two prepared bundles without playing audio or trusting stored hashes.

Run with python -m scripts.overcue_compare REFERENCE CANDIDATE. Exit status is
0 for identical PCM and processing parameters, 1 for differences, 2 for an
invalid bundle. Compression and preview identity are reported separately.
"""
import argparse
import array
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct
import sys
import zlib

from app.stems.overcue import ROLES, PAGE_BYTES, MAX_FRAMES


def pages(path, record):
    """Validate every page and the manifest before accepting a PCM identity."""
    with path.open('rb') as stream:
        header = stream.read(24)
        if len(header) != 24 or header[:8] != b'OVPGZ001':
            raise ValueError(f'{path.name}: invalid header')
        size, count, total = struct.unpack('>IIQ', header[8:])
        if (size != PAGE_BYTES or not total or total % 4 or
                total > MAX_FRAMES * 4 or count != (total + size - 1) // size):
            raise ValueError(f'{path.name}: invalid page layout')
        table = stream.read(count * 48)
        if len(table) != count * 48 or hashlib.sha256(header + table).hexdigest() != record['page_table_sha256']:
            raise ValueError(f'{path.name}: page table hash mismatch')
        digest = hashlib.sha256()
        expected_offset = 24 + len(table)
        file_size = path.stat().st_size
        for number in range(count):
            offset, packed, raw, checksum = struct.unpack_from('>QII32s', table, number * 48)
            expected = min(size, total - number * size)
            if (offset != expected_offset or raw != expected or not packed or
                    packed > size + 1024 or offset + packed > file_size):
                raise ValueError(f'{path.name}: invalid page {number}')
            stream.seek(offset)
            decoder = zlib.decompressobj()
            data = decoder.decompress(stream.read(packed), raw + 1)
            if (len(data) != raw or not decoder.eof or decoder.unused_data or
                    decoder.unconsumed_tail or hashlib.sha256(data).digest() != checksum):
                raise ValueError(f'{path.name}: corrupt page {number}')
            digest.update(data)
            expected_offset = offset + packed
            yield data
        if (expected_offset != file_size or record['bytes'] != total or
                digest.hexdigest() != record['sha256']):
            raise ValueError(f'{path.name}: PCM hash or size mismatch')


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def f32(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Invalid gain')
    return struct.pack('<f', value).hex()


def compare(reference, candidate):
    roots = (Path(reference), Path(candidate))
    manifests = [json.loads((p / 'overcue-manifest.json').read_text()) for p in roots]
    for manifest in manifests:
        runtime = manifest['runtime']
        if (manifest['schema'] != 'overcue-stems/4' or
                (runtime['sample_rate'], runtime['channels'], runtime['format'], runtime['page_bytes']) !=
                (96000, 2, 's16le', PAGE_BYTES)):
            raise ValueError('Unsupported bundle format')
        if any(manifest['roles'][r]['bytes'] != runtime['frames'] * 4 for r in ROLES):
            raise ValueError('Manifest role timeline mismatch')
    left, right = manifests
    parameters = {
        'source_sha256': left['source']['sha256'] == right['source']['sha256'],
        'runtime': left['runtime'] == right['runtime'],
        'headroom_f32': f32(left['headroom']) == f32(right['headroom']),
        'loudness_policy': left['loudness_policy'] == right['loudness_policy'],
    }
    roles = {}
    for role in ROLES:
        records = [m['roles'][role] for m in manifests]
        paths = [root / f'stems-sidecar-{role}.s16le.pgz' for root in roots]
        different = 0
        first = None
        max_delta = 0
        position = 0
        for a, b in itertools.zip_longest(*(pages(p, r) for p, r in zip(paths, records)), fillvalue=b''):
            if a != b:
                samples = [array.array('h', data) for data in (a, b)]
                if sys.byteorder != 'little':
                    for values in samples:
                        values.byteswap()
                for index, (x, y) in enumerate(itertools.zip_longest(*samples)):
                    if x != y:
                        different += 1
                        if first is None:
                            first = {'frame': (position + index) // 2,
                                     'channel': (position + index) % 2,
                                     'reference': x, 'candidate': y}
                        if x is not None and y is not None:
                            max_delta = max(max_delta, abs(x-y))
            position += max(len(a), len(b)) // 2
        roles[role] = {
            'pcm_identical': different == 0,
            'different_samples': different,
            'max_delta_lsb_overlapping_samples': max_delta,
            'first_difference': first,
            'gain_f32_identical': f32(records[0]['loudness_gain']) == f32(records[1]['loudness_gain']),
            'pgz_identical': file_hash(paths[0]) == file_hash(paths[1]),
        }
    previews = {}
    for name in sorted(set(left.get('waveforms', [])) | set(right.get('waveforms', []))):
        if Path(name).name != name or not name.startswith('stems-') or Path(name).suffix not in ('.EXT', '.2EX'):
            raise ValueError('Invalid preview filename')
        paths = [p / name for p in roots]
        previews[name] = all(p.is_file() for p in paths) and file_hash(paths[0]) == file_hash(paths[1])
    return {'audio_1_to_1': all(parameters.values()) and
            all(r['pcm_identical'] and r['gain_f32_identical'] for r in roles.values()),
            'parameters': parameters, 'roles': roles, 'previews': previews}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    try:
        report = compare(args.reference, args.candidate)
    except (OSError, ValueError, KeyError, TypeError, OverflowError, zlib.error) as error:
        print(json.dumps({'error': str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['audio_1_to_1'] else 1


if __name__ == '__main__':
    sys.exit(main())
