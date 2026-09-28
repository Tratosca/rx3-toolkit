# SPDX-License-Identifier: MPL-2.0
import array
import dataclasses
import math
import pathlib
import shutil
import struct
import tempfile
import unittest
from unittest import mock
import wave

from app.stems import analysis, pdb, safety, stem, wave_dsp, waveform
from app.stems.rekordbox import Track


def tag(name, header, body):
    return struct.pack(">4sII", name, 12 + len(header), 12 + len(header) + len(body)) + header + body


def file_of(*parts):
    body = b"".join(parts)
    return b"PMAI" + struct.pack(">II", 12, 12 + len(body)) + body


def fixture(count=15, rgb=False):
    dat = file_of(tag(b"PQTZ", struct.pack(">III", 0, 0x80000, 1), struct.pack(">HHI", 1, 12000, 0)))
    payload = b"\x1f" * count
    ext = file_of(tag(b"PWV3", struct.pack(">III", 1, count, 150 << 16), payload))
    if rgb:
        ext = file_of(tag(b"PWV3", struct.pack(">III", 1, count, 150 << 16), payload),
                      tag(b"PWV5", struct.pack(">III", 2, count, 150 << 16), b"\0\0" * count))
    return dat, ext


class AnalysisTests(unittest.TestCase):
    def test_observed_rgb_header_and_repeated_cue_sections(self):
        dat, _ = fixture()
        cue = tag(b"PCOB", struct.pack(">III", 1, 0, 0xffffffff), b"")
        ext = file_of(cue, cue,
                      tag(b"PWV3", struct.pack(">III", 1, 15, 0x00960000), b"\x1f" * 15),
                      tag(b"PWV5", struct.pack(">III", 2, 15, 0x00960305), b"\0\0" * 15))
        result = analysis.parse(dat, ext)
        self.assertIsNotNone(result)
        self.assertEqual((result.tag, result.count), (b"PWV5", 15))
        self.assertIsNone(analysis.parse(dat, ext.replace(b"\x00\x96\x03\x05", b"\x00\x96\xff\xff")))

    def test_axis_and_beats_are_read_without_guessing_duration(self):
        result = analysis.parse(*fixture(rgb=True))
        self.assertEqual((result.count, result.tag, result.beats), (15, b"PWV5", ((1, 12000, 0),)))

    def test_malformed_or_disagreeing_tags_disable_the_track(self):
        dat, ext = fixture()
        for broken in (ext[:-1], ext + b"x", b"bad", file_of(tag(b"PWV3", struct.pack(">III", 1, 15, 75 << 16), b"x" * 15)),
                       file_of(tag(b"PWV5", struct.pack(">III", 2, 16, 150 << 16), b"x" * 32), ext[12:]),
                       file_of(ext[12:], ext[12:])):
            with self.subTest(length=len(broken)):
                self.assertIsNone(analysis.parse(dat, broken))
        self.assertIsNone(analysis.parse(dat[:-1], ext))
        self.assertIsNone(analysis.parse(file_of(), ext))

    def test_analysis_string_uses_the_pdb_reference(self):
        row = bytearray(512)
        struct.pack_into("<I", row, pdb.TRACK_ID, 7)
        for index, text in ((14, '/PIONEER/USBANLZ/test/ANLZ0000.DAT'), (17, 'Track'), (20, '/Contents/track.wav')):
            value = text.encode('ascii')
            offset = 160 + (index - 14) * 40
            struct.pack_into('<H', row, pdb.TRACK_FIXED_SIZE + index * 2, offset)
            row[offset:offset + len(value) + 1] = bytes([(len(value) + 1) * 2 + 1]) + value
        track = pdb.parse_track(pdb.Row(memoryview(row), 0))
        self.assertEqual(track.analysis_path, '/PIONEER/USBANLZ/test/ANLZ0000.DAT')
        self.assertEqual(track.file_path, '/Contents/track.wav')

    def test_analysis_paths_cannot_escape_the_drive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for name in ('../foreign.DAT', 'folder/../../foreign.DAT', 'C:/foreign.DAT'):
                with self.assertRaises(ValueError):
                    analysis.contained(root, name)
            (root / 'link').symlink_to('/tmp')
            with self.assertRaises(ValueError):
                analysis.contained(root, 'link/foreign.DAT')


@unittest.skipUnless(shutil.which('ffmpeg'), 'audio filters required')
class WaveformTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.output = self.root / 'RX3_STEMS'
        self.output.mkdir()
        self.source = self.root / 'track.wav'
        self.frames = 4410
        self.pcm = array.array('h', [8192] * self.frames * 2)
        with wave.open(str(self.source), 'wb') as output:
            output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
            output.writeframes(self.pcm.tobytes())
        self.voice = self.output / 'track.rx3stem'
        self.voice.write_bytes(stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, self.frames, b'\0' * 32) + self.pcm.tobytes())
        self.track = Track('1', 'Track', 'Artist', 1, self.source, True)
        self.template = analysis.parse(*fixture())
        self.source_hash = safety.digest(self.source)

    def test_role_equal_to_mix_reproduces_independent_dc_columns(self):
        path = waveform.build(self.track, self.root, self.template, self.source_hash, 'ffmpeg', self.root, lambda: None)
        result = waveform.read(path, 15)
        self.assertEqual(result['source_sha256'], self.source_hash)
        with path.open('rb') as source:
            for role, start, length, _ in result['roles']:
                source.seek(start)
                data = source.read(length)
                if role in (2, 3):
                    self.assertEqual(data[::6], self.template.columns)
                else:
                    self.assertTrue(all(value & 31 == 0 for value in data[::6]))
                    self.assertEqual(data[3::6], bytes(15))
        self.assertIsNone(waveform.read(path, 16))

    def test_three_band_frequency_order_and_all_formats(self):
        for band, frequency in enumerate((60, 800, 8000)):
            pcm = self.root / 'tone.f32'
            pcm.write_bytes(array.array('f', (0.25 * math.sin(2 * math.pi * frequency * (i // 2) / 44100)
                                             for i in range(88200))).tobytes())
            data = wave_dsp.columns(pcm, 44100, None, 150)
            self.assertEqual({key: len(value) for key, value in data.items()},
                             {b'PWV3': 150, b'PWV5': 300, b'PWV7': 450})
            cell = data[b'PWV7'][300:303]
            self.assertEqual(cell.index(max(cell)), band)
            self.assertTrue(all(0 <= value <= 255 for value in cell))
            for tag in (b'PWV3', b'PWV5'):
                self.assertEqual(data[tag], wave_dsp.columns(pcm, 44100, tag, 150))

    def test_all_combinations_analyze_pcm_cancellation_not_envelope_sum(self):
        with wave.open(str(self.source), 'wb') as output:
            output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
            output.writeframes(array.array('h', [4096] * self.frames * 2).tobytes())
        drums = self.output / 'track.rx3drums'
        drums.write_bytes(stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, self.frames, bytes(32))
                          + array.array('h', [-8192] * self.frames * 2).tobytes())
        path = waveform.build(self.track, self.root, self.template, safety.digest(self.source),
                              'ffmpeg', self.root, lambda: None, files=[self.voice, drums])
        info = waveform.read(path)
        self.assertEqual((info['version'], info['available']), (3, 7))
        data = path.read_bytes()
        for mask, start, length, _ in info['roles']:
            columns = data[start:start+length]
            blue = [v & 31 for v in columns[::6]]
            rgb = [(v >> 2) & 31 for v in columns[2::6]]
            bands = [v for i, v in enumerate(columns) if i % 6 >= 3]
            if mask == 6:
                self.assertFalse(any(blue + rgb + bands))
            else:
                self.assertTrue(any(blue))
                self.assertTrue(any(rgb))
                self.assertTrue(any(bands))

    def test_combination_directory_and_band_bounds_are_checked(self):
        path = self.root / 'bad.rx3wave'
        combinations = {mask: (bytes([31, 0, 124, 10, 10, 10]) * 15, '22'*32)
                        for mask in range(1, 4)}
        waveform.write_combinations(path, self.template, self.frames, self.source_hash, combinations)
        self.assertIsNotNone(waveform.read(path))
        data = bytearray(path.read_bytes())
        data[:8] = b"RX3WAV2\0"
        data[8:12] = (2).to_bytes(4, "little")
        path.write_bytes(data)
        self.assertIsNotNone(waveform.read(path))
        data[128 + 3 * 64 + 3] = 32
        path.write_bytes(data)
        self.assertIsNone(waveform.read(path))
        with self.assertRaises(ValueError):
            waveform.write_combinations(path, self.template, self.frames, self.source_hash,
                                        {1: combinations[1], 3: combinations[3]})

    def test_audio_or_generated_column_count_mismatch_is_refused(self):
        with self.assertRaises(ValueError):
            waveform.build(self.track, self.root, dataclasses.replace(self.template, count=16),
                           self.source_hash, 'ffmpeg', self.root, lambda: None)
        with self.assertRaises(ValueError):
            waveform.write(self.root/'bad.rx3wave', self.template, self.frames, self.source_hash,
                           {'vocals': (b'x' * 16, self.source_hash), 'instrumental': (b'x' * 15, self.source_hash)})

    def test_rgb_peak_excluded_from_normalizer_saturates_without_wrapping(self):
        # Modjo 48 -> 44.1 kHz: normalizer 31840, excluded peak 32592.
        bands = ([9000] * 14, [5000] * 14, [3000] * 14)
        baseline = wave_dsp.encode([], [], [31840] * 14, *bands, 2, b'PWV5')
        for peak in (32592, 32767):
            full = [31840] * 14
            full[6] = peak  # Last millisecond of the first column is excluded.
            data = wave_dsp.encode([], [], full, *bands, 2, b'PWV5')
            word = struct.unpack_from('>H', data)[0]
            self.assertEqual((word >> 2) & 31, 31)
            self.assertEqual(word & ~124, struct.unpack_from('>H', baseline)[0] & ~124)
            self.assertEqual(data[2:], baseline[2:])
        silence = wave_dsp.encode([], [], [0] * 14, *bands, 2, b'PWV5')
        self.assertTrue(all((word >> 2) & 31 == 0 for word in struct.unpack('>2H', silence)))

    def test_rgb_filters_distinguish_low_and_high_frequencies(self):
        colours = []
        for frequency in (60, 7000):
            pcm = self.root/'tone.f32'
            values = array.array('f', (0.25 * math.sin(2 * math.pi * frequency * (i // 2) / 44100) for i in range(88200)))
            pcm.write_bytes(values.tobytes())
            data = wave_dsp.columns(pcm, 44100, b'PWV5', 150)
            word = struct.unpack_from('>H', data, 100 * 2)[0]
            colours.append(((word >> 13) & 7, (word >> 7) & 7))
        self.assertGreater(colours[0][0], colours[0][1])
        self.assertGreater(colours[1][1], colours[1][0])

    def test_partial_column_does_not_extend_rgb_envelope_time(self):
        pcm = self.root / 'partial.f32'
        frames = 6048
        pcm.write_bytes(array.array('f', [0.25] * frames * 2).tobytes())
        with mock.patch.object(wave_dsp, 'peaks', wraps=wave_dsp.peaks) as measured:
            output = wave_dsp.columns(pcm, frames, b'PWV5', 21)
        self.assertEqual(len(output), 42)
        for call in measured.call_args_list[2:]:
            bounds = call.args[1]
            self.assertEqual(bounds[-1], frames)
            self.assertEqual(len(bounds) - 1, 138)

    def test_rgb_middle_band_preserves_a_400_hz_tone(self):
        pcm = self.root / 'middle.f32'
        pcm.write_bytes(array.array('f', (0.25 * math.sin(2 * math.pi * 400 * (i // 2) / 44100)
                                         for i in range(88200))).tobytes())
        output = wave_dsp.columns(pcm, 44100, b'PWV5', 150)
        word = struct.unpack_from('>H', output, 200)[0]
        self.assertEqual(((word >> 13) & 7, (word >> 10) & 7, (word >> 7) & 7), (0, 7, 0))

    def test_native_rate_does_not_change_column_cadence(self):
        for rate in (32000, 48000):
            with self.subTest(rate=rate):
                pcm = self.root / 'native.f32'
                pcm.write_bytes(array.array('f', [0.25] * (rate // 10) * 2).tobytes())
                self.assertEqual(wave_dsp.columns(pcm, rate // 10, b'PWV3', 15, rate=rate), b'\x1f' * 15)
                with self.assertRaises(ValueError):
                    wave_dsp.columns(pcm, rate // 10, b'PWV3', 16, rate=rate)

    def test_output_analysis_requires_matching_audio_identity(self):
        library = self.root/'PIONEER/rekordbox/export.pdb'
        library.parent.mkdir(parents=True)
        library.write_bytes(b'fixture')
        dat, ext = fixture()
        (self.root/'track.DAT').write_bytes(dat)
        (self.root/'track.EXT').write_bytes(ext)
        entry = pdb.TrackRow(1, 1, 1, 'Track', '/track.wav', '/track.DAT')
        with mock.patch.object(pdb, 'read_tables'), mock.patch.object(pdb, 'iter_rows', return_value=[None]), mock.patch.object(pdb, 'parse_track', return_value=entry):
            self.assertIsNotNone(analysis.locate(self.track, self.root, self.source_hash))
            self.assertIsNone(analysis.locate(self.track, self.root, '0' * 64))
            (self.root/'track.EXT').write_bytes(ext[:-1])
            self.assertIsNone(analysis.locate(self.track, self.root, self.source_hash))

    def test_optional_failure_removes_a_stale_file_and_leaves_audio_intact(self):
        target = self.output/'track.rx3wave'
        target.write_bytes(b'old')
        original = self.voice.read_bytes()
        with mock.patch.object(safety, 'library_busy', return_value=False):
            self.assertFalse(waveform.prepare(self.track, self.root, self.source_hash))
        self.assertFalse(target.exists())
        self.assertEqual(self.voice.read_bytes(), original)

    def test_publication_reads_final_stems_and_preserves_analysis(self):
        dat, ext = fixture()
        files = [self.root/'test.DAT', self.root/'test.EXT']
        for path, data in zip(files, (dat, ext)):
            path.write_bytes(data)
        template = dataclasses.replace(self.template, files=tuple((p, safety.source_stamp(p)) for p in files))
        with mock.patch.object(analysis, 'locate', return_value=template), mock.patch.object(safety, 'library_busy', return_value=False):
            self.assertTrue(waveform.prepare(self.track, self.root, self.source_hash))
        self.assertIsNotNone(waveform.read(self.output/'track.rx3wave'))
        self.assertEqual([p.read_bytes() for p in files], [dat, ext])
        self.assertFalse(list(self.output.glob('*.partial')))
        # A change during the DSP work must not publish columns for old audio.
        original = wave_dsp.columns
        def changed(*args, **kwargs):
            data = original(*args, **kwargs)
            self.voice.write_bytes(self.voice.read_bytes()[:-2] + b'\x01\0')
            return data
        with mock.patch.object(analysis, 'locate', return_value=template), mock.patch.object(safety, 'library_busy', return_value=False), mock.patch.object(wave_dsp, 'columns', side_effect=changed), mock.patch('app.stems.wave_acceleration.open_worker', return_value=None):
            self.assertFalse(waveform.prepare(self.track, self.root, self.source_hash))
        self.assertFalse((self.output/'track.rx3wave').exists())

    def test_container_and_metadata_are_defensive(self):
        path = waveform.build(self.track, self.root, self.template, self.source_hash, 'ffmpeg', self.root, lambda: None)
        path.write_bytes(path.read_bytes()[:-1])
        self.assertIsNone(waveform.read(path))
        metadata = self.output/'._track.rx3wave'
        metadata.write_bytes(b'x')
        unrelated = self.output/'._notes.txt'
        unrelated.write_bytes(b'x')
        safety.clean_metadata(self.output)
        self.assertFalse(metadata.exists())
        self.assertTrue(unrelated.exists())
