# SPDX-License-Identifier: MPL-2.0
import math
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.rx3_stems import estimate, provisioning, separation, sidecar
from tools.rx3_stems import job as job_module
from tools.rx3_stems.job import JobState, StemJob, failure_detail
from tools.rx3_stems.rekordbox import (
    EXPORT_STEM_LIMIT, export_stem, file_url_to_path, parse_collection, safe_stem,
)


def write_export(root: pathlib.Path, tracks: list[tuple[str, str, str, pathlib.Path]]) -> pathlib.Path:
    entries = "".join(
        f'<TRACK TrackID="{track_id}" Name="{name}" Artist="{artist}" TotalTime="123" '
        f'Location="{location.as_uri()}"/>'
        for track_id, name, artist, location in tracks
    )
    references = "".join(f'<TRACK Key="{track_id}"/>' for track_id, *_ in tracks)
    xml = root / "rekordbox.xml"
    xml.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="{len(tracks)}">{entries}</COLLECTION>'
        '<PLAYLISTS><NODE Type="0" Name="ROOT"><NODE Type="1" Name="RX3 Stems" '
        f'Entries="{len(tracks)}">{references}</NODE></NODE></PLAYLISTS></DJ_PLAYLISTS>',
        encoding="utf-8",
    )
    return xml


class RekordboxTests(unittest.TestCase):
    def test_parse_resolves_playlist_paths_and_missing_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            present = root / "Artist - Track.aiff"
            present.write_bytes(b"fixture")
            xml = write_export(root, [
                ("1", "Track", "Artist", present),
                ("2", "Gone", "Artist", root / "absent.aiff"),
            ])
            collection = parse_collection(xml)
            playlist = collection.playlists[0]
            self.assertEqual(collection.track_count, 2)
            self.assertEqual(playlist.path, "RX3 Stems")
            self.assertEqual(playlist.missing_count, 1)
            self.assertTrue(playlist.tracks[0].exists)

    def test_the_root_container_is_dropped_from_playlist_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            audio = root / "Artist - Track.aiff"
            audio.write_bytes(b"fixture")
            xml = root / "rekordbox.xml"
            xml.write_text(
                '<?xml version="1.0"?><DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="1">'
                f'<TRACK TrackID="1" Name="T" Artist="A" Location="{audio.as_uri()}"/>'
                '</COLLECTION><PLAYLISTS><NODE Type="0" Name="ROOT">'
                '<NODE Type="1" Name="Top" Entries="1"><TRACK Key="1"/></NODE>'
                '<NODE Type="0" Name="Gigs">'
                '<NODE Type="1" Name="Nested" Entries="1"><TRACK Key="1"/></NODE>'
                '</NODE></NODE></PLAYLISTS></DJ_PLAYLISTS>',
                encoding="utf-8",
            )
            paths = [playlist.path for playlist in parse_collection(xml).playlists]
            self.assertEqual(paths, ["Top", "Gigs / Nested"])

    def test_rejects_a_file_that_is_not_a_rekordbox_export(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = pathlib.Path(directory) / "other.xml"
            xml.write_text("<PLAYLIST/>", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_collection(xml)

    def test_locations_resolve_per_platform_and_reject_remote_urls(self):
        # Rekordbox on Windows writes this exact form: the drive letter loses
        # the leading slash of the URL, a POSIX path keeps it.
        windows = file_url_to_path("file://localhost/C:/Music/Artist%20-%20Track.aiff")
        self.assertEqual(pathlib.PurePath(windows).parts[0].rstrip("\\/"), "C:")
        self.assertEqual(pathlib.PurePath(windows).name, "Artist - Track.aiff")

        posix = file_url_to_path("file://localhost/Users/dj/Music/Track.aiff")
        self.assertEqual(pathlib.PurePath(posix).parts[1], "Users")

        with self.assertRaises(ValueError):
            file_url_to_path("https://example.invalid/Track.aiff")

    def test_safe_stem_strips_separators_and_control_characters(self):
        self.assertEqual(safe_stem("A/B:C\x01 "), "A_B_C")
        self.assertEqual(safe_stem("   "), "track")

    def test_export_stem_reproduces_the_drive_truncation(self):
        # A name Rekordbox shortens on export, cut where the deck cuts it,
        # trailing space included.
        long_name = "Air Force Blanche - Gims, Jul (Extended Mix By Fuvi Clan)"
        self.assertEqual(export_stem(long_name), "Air Force Blanche - Gims, Jul (Extended Mix ")
        self.assertEqual(len(export_stem(long_name)), EXPORT_STEM_LIMIT)
        # A name already within the limit is exported as it stands.
        self.assertEqual(export_stem("B.M.S (by my side) - Rambo goyard"),
                         "B.M.S (by my side) - Rambo goyard")
        self.assertEqual(export_stem("   "), "track")


class JobTests(unittest.TestCase):
    def runtime(self) -> provisioning.Runtime:
        return provisioning.detect()

    def test_existing_sidecar_is_kept_and_manifest_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            audio = root / "Artist - Track.aiff"
            audio.write_bytes(b"fixture")
            xml = write_export(root, [("1", "Track", "Artist", audio)])
            collection = parse_collection(xml)
            output = root / "export"
            (output / "RX3_STEMS").mkdir(parents=True)
            (output / "RX3_STEMS/Artist - Track.rx3stem").write_bytes(b"x" * 128)

            state = StemJob(self.runtime(), collection, collection.playlists[0], output).run()
            self.assertEqual(state.state, "done")
            self.assertEqual(state.results[0].status, "existing")
            self.assertEqual(state.errors, ())
            self.assertTrue((output / "rx3-stems-manifest.json").is_file())

    def test_the_sidecar_carries_the_name_the_drive_export_gives_the_track(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            audio = root / "Air Force Blanche - Gims, Jul (Extended Mix By Fuvi Clan).aiff"
            audio.write_bytes(b"fixture")
            xml = write_export(root, [("1", "Air Force Blanche", "Gims", audio)])
            collection = parse_collection(xml)
            output = root / "export"
            stems = output / "RX3_STEMS"
            stems.mkdir(parents=True)
            # Named as the deck will ask for it, not as the library holds it.
            existing = stems / "Air Force Blanche - Gims, Jul (Extended Mix .rx3stem"
            existing.write_bytes(b"x" * 128)

            state = StemJob(self.runtime(), collection, collection.playlists[0], output).run()
            self.assertEqual(state.errors, ())
            self.assertEqual(state.results[0].status, "existing")
            self.assertEqual(state.results[0].sidecar, existing.name)

    def test_two_sources_that_collide_only_once_truncated_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            sources = []
            for folder, suffix in (("one", "first mix"), ("two", "second mix")):
                source = root / folder / f"A Very Long Title That Rekordbox Will Cut - {suffix}.aiff"
                source.parent.mkdir()
                source.write_bytes(b"fixture")
                sources.append(source)
            self.assertEqual(export_stem(sources[0].stem), export_stem(sources[1].stem))
            xml = write_export(root, [
                ("1", "One", "A", sources[0]),
                ("2", "Two", "B", sources[1]),
            ])
            collection = parse_collection(xml)
            output = root / "export"
            (output / "RX3_STEMS").mkdir(parents=True)
            (output / f"RX3_STEMS/{export_stem(sources[0].stem)}.rx3stem").write_bytes(b"x" * 128)

            state = StemJob(self.runtime(), collection, collection.playlists[0], output).run()
            self.assertEqual(len(state.results), 1)
            self.assertEqual(len(state.errors), 1)
            self.assertIn("Ambiguous filename", state.errors[0].error)

    def test_missing_source_is_reported_without_stopping_the_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            present = root / "Artist - Track.aiff"
            present.write_bytes(b"fixture")
            xml = write_export(root, [
                ("1", "Gone", "Artist", root / "absent.aiff"),
                ("2", "Track", "Artist", present),
            ])
            collection = parse_collection(xml)
            output = root / "export"
            (output / "RX3_STEMS").mkdir(parents=True)
            (output / "RX3_STEMS/Artist - Track.rx3stem").write_bytes(b"x" * 128)

            state = StemJob(self.runtime(), collection, collection.playlists[0], output).run()
            self.assertEqual(state.state, "done")
            self.assertEqual(len(state.results), 1)
            self.assertEqual(len(state.errors), 1)


    def test_an_unwritable_destination_is_explained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            audio = root / "Artist - Track.aiff"
            audio.write_bytes(b"fixture")
            xml = write_export(root, [("1", "Track", "Artist", audio)])
            collection = parse_collection(xml)
            # A regular file as the destination fails the same way everywhere;
            # Windows ignores the permission bits that would express this on POSIX.
            output = root / "not-a-directory"
            output.write_bytes(b"")
            state = StemJob(
                self.runtime(), collection, collection.playlists[0], output
            ).run()
            self.assertEqual(state.state, "failed")
            self.assertIn("could not be created", state.fatal)
            self.assertIn("writable output folder", state.fatal)


class SidecarGainTests(unittest.TestCase):
    """The deck computes `full mix − vocal`, so the stem has to come back in the
    gain domain of the source file whatever the separator did to it."""

    RATE = 44100
    FRAMES = RATE // 5

    def signals(self):
        """A mix that reconstructs above full scale, and its isolated vocal."""
        full, vocal = bytearray(), bytearray()
        for index in range(self.FRAMES):
            voice = 0.5 * math.sin(2 * math.pi * 440 * index / self.RATE)
            rest = 0.7 * math.sin(2 * math.pi * 110 * index / self.RATE + 1.0)
            full += struct.pack("<ff", voice + rest, voice + rest)
            vocal += struct.pack("<ff", voice, voice)
        return bytes(full), bytes(vocal)

    def encode(self, root, name, samples):
        raw = root / f"{name}.f32"
        raw.write_bytes(samples)
        wav = root / f"{name}.wav"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le",
             "-ar", str(self.RATE), "-ac", "2", "-i", str(raw), "-c:a", "pcm_f32le",
             str(wav)],
            check=True,
        )
        return wav

    def worst_error(self, path, expected):
        payload = path.read_bytes()[sidecar.HEADER.size:]
        return max(
            abs(struct.unpack_from("<h", payload, 4 * index)[0] / 32768.0
                - struct.unpack_from("<f", expected, 8 * index)[0])
            for index in range(0, self.FRAMES, 7)
        )

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_the_mix_scaling_of_mdxc_is_undone(self):
        full, vocal = self.signals()
        peak = max(
            abs(struct.unpack_from("<f", full, 4 * index)[0])
            for index in range(2 * self.FRAMES)
        )
        self.assertGreater(peak, 1.0, "the fixture has to overshoot to be meaningful")
        # What an MDX or MDXC separator returns: the vocal carrying the same
        # threshold/peak factor it applied to the mix before inference.
        scaled = b"".join(
            struct.pack("<ff", *(2 * [
                struct.unpack_from("<f", vocal, 8 * index)[0] / peak
            ]))
            for index in range(self.FRAMES)
        )

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            mix_file = self.encode(root, "full", full)
            stem_file = self.encode(root, "vocal", scaled)

            uncorrected = root / "uncorrected.rx3stem"
            sidecar.write_sidecar(stem_file, uncorrected, match_full=mix_file)
            corrected = root / "corrected.rx3stem"
            result = sidecar.write_sidecar(
                stem_file, corrected, match_full=mix_file, separator_normalization=1.0,
            )

            self.assertAlmostEqual(result.gain, peak, places=3)
            self.assertEqual(result.clipped, 0)
            # Left alone, the stem is quiet by 1 - 1/peak; the deck leaves that
            # much vocal in the instrumental.
            self.assertAlmostEqual(
                self.worst_error(uncorrected, vocal), 0.5 * (1.0 - 1.0 / peak), places=3
            )
            # Corrected, only s16 quantisation separates the two.
            self.assertLess(self.worst_error(corrected, vocal), 1e-3)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_an_architecture_that_leaves_the_mix_alone_is_not_corrected(self):
        full, vocal = self.signals()
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            mix_file = self.encode(root, "full", full)
            stem_file = self.encode(root, "vocal", vocal)
            result = sidecar.write_sidecar(
                stem_file, root / "stem.rx3stem", match_full=mix_file,
                separator_normalization=None,
            )
            self.assertEqual(result.gain, 1.0)
            self.assertLess(self.worst_error(root / "stem.rx3stem", vocal), 1e-3)

    def test_the_peak_is_read_through_the_ffmpeg_line_prefix(self):
        """astats prefixes every line, so an anchored pattern silently reads
        nothing and no correction is ever applied."""
        report = (
            "[Parsed_astats_2 @ 0x906c48a80] Peak level dB: -6.020600\n"
            "[Parsed_astats_2 @ 0x906c48a80] Peak level dB: 1.583623\n"
        )
        self.assertAlmostEqual(sidecar._peak_amplitude(report), 1.2, places=3)
        self.assertIsNone(sidecar._peak_amplitude("nothing to report"))
        self.assertEqual(
            sidecar._peak_amplitude("[x] Peak level dB: -inf"), 0.0
        )

    def test_only_the_input_normalizing_architectures_are_corrected(self):
        settings = separation.Settings()
        for architecture in ("MDX", "MDXC"):
            self.assertEqual(
                separation.input_normalization(settings, architecture), 1.0
            )
        for architecture in ("Demucs", "VR", None, "future"):
            self.assertIsNone(separation.input_normalization(settings, architecture))


class SidecarAlignmentTests(unittest.TestCase):
    """The deck indexes the sidecar by the position of its own decoder, which
    plays the encoder padding that ffmpeg drops on the way into the separator."""

    RATE = 44100
    SECONDS = 3

    def decode(self, path, *, untrimmed):
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             *(sidecar.UNTRIMMED if untrimmed else ()), "-i", str(path),
             "-map", "0:a:0", "-vn", "-ar", str(self.RATE), "-ac", "2",
             "-f", "s16le", "-"],
            check=True, capture_output=True,
        )
        return result.stdout

    def fixture(self, root):
        """A padded mp3, and the stem a separator returns for it.

        The separator sees ffmpeg's trimmed decode, so handing that decode back
        as the stem makes any residue against the mix pure misalignment.
        """
        raw = root / "tone.s16le"
        with raw.open("wb") as destination:
            for index in range(self.RATE * self.SECONDS):
                value = int(12000 * math.sin(2 * math.pi * 220 * index / self.RATE))
                destination.write(struct.pack("<hh", value, value))
        source = root / "source.mp3"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le",
             "-ar", str(self.RATE), "-ac", "2", "-i", str(raw), "-c:a", "libmp3lame",
             "-b:a", "320k", str(source)],
            check=True,
        )
        stem = root / "vocal.wav"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
             "-map", "0:a:0", "-vn", "-ar", str(self.RATE), "-ac", "2", str(stem)],
            check=True,
        )
        return source, stem

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_the_encoder_padding_of_a_lossy_source_is_put_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source, stem = self.fixture(root)
            mix = self.decode(source, untrimmed=True)
            self.assertGreater(
                len(mix), len(self.decode(source, untrimmed=False)),
                "the fixture has to declare padding to be meaningful",
            )

            output = root / "aligned.rx3stem"
            result = sidecar.write_sidecar(stem, output, match_full=source)

            self.assertTrue(result.aligned)
            self.assertGreater(result.delay, 0)
            self.assertEqual(result.frames, len(mix) // 4)
            # The stem is the mix here, so anything left over is offset. The
            # padding itself is silent in the stem: the separator never saw it,
            # and 25 ms of encoder ramp-in is not part of the vocal.
            payload = output.read_bytes()[sidecar.HEADER.size:]
            worst = max(
                abs(struct.unpack_from("<h", payload, offset)[0]
                    - struct.unpack_from("<h", mix, offset)[0])
                for offset in range(result.delay * 4, len(payload), 2)
            )
            # The tone moves about 376 counts per frame, so a single frame of
            # offset would show here as two orders of magnitude more than the
            # codec's own round-trip noise.
            self.assertLess(worst, 100, "the stem does not sit on the deck's grid")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
    def test_a_source_without_padding_keeps_the_grid_it_already_had(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            raw = root / "tone.s16le"
            raw.write_bytes(struct.pack("<hh", 4000, 4000) * (self.RATE // 2))
            source = root / "source.wav"
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le",
                 "-ar", str(self.RATE), "-ac", "2", "-i", str(raw), str(source)],
                check=True,
            )
            result = sidecar.write_sidecar(source, root / "out.rx3stem", match_full=source)
            self.assertEqual(result.delay, 0)
            self.assertTrue(result.aligned)
            self.assertEqual(result.frames, self.RATE // 2)

    def test_an_unmeasurable_offset_leaves_the_stem_where_the_separator_put_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            trimmed, untrimmed = root / "trimmed", root / "untrimmed"
            # Silence matches at every offset, so no probe is ever unique.
            trimmed.write_bytes(b"\0" * 4 * sidecar.SAMPLE_RATE)
            untrimmed.write_bytes(b"\0" * 4 * (sidecar.SAMPLE_RATE + 512))
            self.assertIsNone(sidecar._encoder_delay(trimmed, untrimmed))
            # Identical lengths mean nothing was dropped, whatever the content.
            untrimmed.write_bytes(b"\0" * 4 * sidecar.SAMPLE_RATE)
            self.assertEqual(sidecar._encoder_delay(trimmed, untrimmed), 0)


FILTER_LISTING = """Filters:
  T.. aformat           A->A       Convert the input audio to one of the specified formats.
  ... apad              A->A       Pad audio with silence.
  ..C aresample         A->A       Resample audio data.
  T.. astats            A->A       Show time domain statistics about audio frames.
  ... atrim             A->A       Pick one continuous section from the input.
  TS. volume            A->A       Change input volume.
"""


if __name__ == "__main__":
    unittest.main()
