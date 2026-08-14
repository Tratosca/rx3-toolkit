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


class InferenceDeviceTests(unittest.TestCase):
    """A GPU run that quietly falls back to the CPU only shows as a job that
    takes an order of magnitude longer, so it has to be reported."""

    def job(self, accelerator):
        job = StemJob.__new__(StemJob)
        job._lock = threading.Lock()
        job._state = JobState()
        job.observer = lambda state: None
        job.acceleration = provisioning.ACCELERATIONS[accelerator]
        return job

    def test_a_cpu_fallback_under_an_accelerator_is_reported(self):
        job = self.job("cuda")
        job._note_inference_device(
            f"PyTorch Version: 2.13.0\n{job_module.CPU_FALLBACK}, running in CPU mode\n"
        )
        self.assertEqual(len(job.state.notices), 1)
        self.assertIn("NVIDIA CUDA", job.state.notices[0])

    def test_the_same_fallback_is_reported_once_for_a_whole_playlist(self):
        job = self.job("cuda")
        for _ in range(5):
            job._note_inference_device(f"{job_module.CPU_FALLBACK}, running in CPU mode")
        self.assertEqual(len(job.state.notices), 1)

    def test_nothing_is_reported_when_the_cpu_is_where_the_run_belongs(self):
        accelerated = self.job("cuda")
        accelerated._note_inference_device(
            "CUDA is available in Torch, setting Torch device to CUDA"
        )
        self.assertEqual(accelerated.state.notices, ())

        # The CPU profile running on the CPU is not a fallback.
        cpu = self.job("cpu")
        cpu._note_inference_device(f"{job_module.CPU_FALLBACK}, running in CPU mode")
        self.assertEqual(cpu.state.notices, ())


class FailureDetailTests(unittest.TestCase):
    def test_progress_bars_are_dropped_and_the_exception_survives(self):
        transcript = (
            "Separating track /music/Track.aiff\r"
            "  0%|          | 0.0/356.8 [00:00<?, ?seconds/s]\r"
            " 50%|#####     | 178.4/356.8 [01:10<01:10,  2.5seconds/s]\r"
            "Traceback (most recent call last):\n"
            "  File \"audio_separator/separator/common_separator.py\", line 292\n"
            "RuntimeError: Couldn't find appropriate backend to handle uri vocals.wav\n"
        )
        detail = failure_detail(transcript)
        self.assertIn("RuntimeError: Couldn't find appropriate backend", detail)
        self.assertNotIn("%|", detail)

    def test_a_silent_separator_is_reported_as_such(self):
        self.assertEqual(failure_detail("  0%|   | 0.0/10 [00:00<?, ?s/s]\r"), "no output")


class SeparationTests(unittest.TestCase):
    CATALOGUE = {
        "MDXC": {"Roformer": {
            "filename": "model_bs_roformer.ckpt", "stems": ["Vocals", "Instrumental"],
            "scores": {"vocals": {"SDR": 11.77}},
        }},
        "VR": {"HP-UVR": {
            "filename": "1_HP-UVR.pth", "stems": ["Instrumental", "Vocals"],
            "scores": {"vocals": {"SDR": 7.90}},
        }},
        "Demucs": {"Drums only": {"filename": "drums.yaml", "stems": ["Drums"]}},
    }

    def catalogue(self) -> separation.Catalogue:
        return separation.parse_catalogue(self.CATALOGUE)

    def test_only_vocal_models_are_offered_best_score_first(self):
        catalogue = self.catalogue()
        self.assertEqual(
            [model.filename for model in catalogue.models],
            ["model_bs_roformer.ckpt", "1_HP-UVR.pth"],
        )
        self.assertEqual(catalogue.architecture_of("1_HP-UVR.pth"), "VR")
        self.assertIsNone(catalogue.by_filename("drums.yaml"))

    def test_arguments_exclude_other_architectures(self):
        settings = separation.Settings(model="model_bs_roformer.ckpt")
        settings = settings.with_value(separation.COMMON_OPTIONS[0], 0.7)
        for option in separation.ARCHITECTURE_OPTIONS["MDXC"]:
            if option.name == "mdxc_overlap":
                settings = settings.with_value(option, 16)
        for option in separation.ARCHITECTURE_OPTIONS["VR"]:
            if option.name == "vr_aggression":
                settings = settings.with_value(option, 9)

        mdxc = settings.arguments("MDXC")
        self.assertIn("--mdxc_overlap=16", mdxc)
        self.assertIn("--normalization=0.7", mdxc)
        self.assertNotIn("--vr_aggression=9", mdxc)
        self.assertNotIn("--mdxc_overlap=16", settings.arguments("VR"))
        self.assertNotIn("--mdxc_overlap=16", settings.arguments(None))

    def test_separator_defaults_are_never_passed_on_the_command_line(self):
        settings = separation.Settings()
        implied = [
            option for _, options in settings.options("MDXC") for option in options
            if settings.value(option) == option.implied
        ]
        arguments = settings.arguments("MDXC")
        for option in implied:
            self.assertFalse([item for item in arguments if item.startswith(option.flag)])
        option = separation.COMMON_OPTIONS[0]
        self.assertEqual(settings.with_value(option, option.default).values, {})

    def test_normalization_stays_in_the_source_gain_domain(self):
        """The deck subtracts the vocal from the untouched mix, so no stage of
        the separator may rescale it."""
        normalization = next(
            option for option in separation.COMMON_OPTIONS if option.name == "normalization"
        )
        self.assertEqual(normalization.default, 1.0)
        self.assertIn("--normalization=1.0", separation.Settings().arguments("MDXC"))

    def test_flags_carry_no_value_and_out_of_range_values_are_refused(self):
        denoise = next(o for o in separation.ARCHITECTURE_OPTIONS["MDX"] if o.kind == "flag")
        self.assertIn(
            denoise.flag, separation.Settings().with_value(denoise, True).arguments("MDX")
        )
        overlap = next(
            o for o in separation.ARCHITECTURE_OPTIONS["MDXC"] if o.name == "mdxc_overlap"
        )
        with self.assertRaises(ValueError):
            separation.Settings().with_value(overlap, 999).arguments("MDXC")

    def test_settings_round_trip_and_drop_unknown_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "separation.json"
            settings = separation.Settings(model="a.ckpt", accelerator="cuda")
            settings = settings.with_value(separation.COMMON_OPTIONS[0], 0.5)
            separation.save_settings(path, settings)
            self.assertEqual(separation.load_settings(path), settings)

            path.write_text(
                '{"model": "b.ckpt", "values": {"from_the_future": 1}}', encoding="utf-8"
            )
            restored = separation.load_settings(path)
            self.assertEqual(restored.model, "b.ckpt")
            self.assertEqual(restored.values, {})
            self.assertEqual(restored.accelerator, "auto")

            self.assertEqual(
                separation.load_settings(path.with_name("absent.json")),
                separation.Settings(),
            )


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


class ModelFileTests(unittest.TestCase):
    def model(self, downloads: tuple[str, ...]) -> separation.Model:
        return separation.Model(
            architecture="MDXC", name="Roformer", filename="model.ckpt",
            stems=("Vocals",), vocal_sdr=12.6, download_files=downloads,
        )

    def test_a_url_entry_is_local_under_its_basename(self):
        with tempfile.TemporaryDirectory() as directory:
            models = pathlib.Path(directory)
            model = self.model((
                "model.ckpt", "https://example.invalid/models/weights.th",
            ))
            self.assertEqual(
                [path.name for path in model.local_files(models)],
                ["model.ckpt", "weights.th"],
            )
            self.assertFalse(model.is_downloaded(models))
            (models / "model.ckpt").write_bytes(b"x" * 10)
            self.assertFalse(model.is_downloaded(models), "one file is not enough")
            (models / "weights.th").write_bytes(b"y" * 6)
            self.assertTrue(model.is_downloaded(models))
            self.assertEqual(model.size(models), 16)

    def test_delete_removes_every_file_and_reports_the_space(self):
        with tempfile.TemporaryDirectory() as directory:
            models = pathlib.Path(directory)
            model = self.model(("model.ckpt", "config.yaml"))
            (models / "model.ckpt").write_bytes(b"x" * 100)
            (models / "config.yaml").write_bytes(b"y" * 20)
            other = models / "keep.ckpt"
            other.write_bytes(b"z")
            self.assertEqual(separation.delete_model(models, model), 120)
            self.assertFalse(model.is_downloaded(models))
            self.assertTrue(other.is_file(), "another model must be left alone")
            self.assertEqual(separation.delete_model(models, model), 0)

    def test_the_default_model_is_the_best_scoring_vocal_model(self):
        catalogue = separation.parse_catalogue({
            "MDXC": {
                "Best": {"filename": separation.DEFAULT_MODEL, "stems": ["Vocals"],
                         "scores": {"vocals": {"SDR": 12.6}}},
                "Worse": {"filename": "other.ckpt", "stems": ["Vocals"],
                          "scores": {"vocals": {"SDR": 11.0}}},
            },
        })
        self.assertEqual(catalogue.models[0].filename, separation.DEFAULT_MODEL)


class SeparatorEnvironmentTests(unittest.TestCase):
    """Every audio-separator invocation needs FFmpeg reachable by name."""

    def runtime(self, root: pathlib.Path) -> provisioning.Runtime:
        ffmpeg = root / provisioning._executable_name("ffmpeg")
        ffmpeg.write_bytes(b"binary")
        (root / "models").mkdir(exist_ok=True)
        return provisioning.Runtime(
            environment=root, models=root / "models",
            separator=root / "audio-separator", ffmpeg=ffmpeg,
        )

    def test_listing_models_carries_the_prepared_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            runtime = self.runtime(root)
            completed = unittest.mock.Mock(returncode=0, stdout="{}", stderr="")
            with unittest.mock.patch("subprocess.run", return_value=completed) as run:
                separation.load_catalogue(runtime, root / "cache.json", refresh=True)
            environment = run.call_args.kwargs["env"]
            self.assertTrue(environment["PATH"].startswith(str(root)))
            self.assertEqual(environment["AUDIO_SEPARATOR_MODEL_DIR"], str(runtime.models))

    def test_a_download_carries_the_environment_and_is_checked_afterwards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            runtime = self.runtime(root)
            model = separation.Model(
                architecture="MDXC", name="Roformer", filename="model.ckpt",
                stems=("Vocals",), vocal_sdr=12.6,
                download_files=("model.ckpt", "config.yaml"),
            )
            (runtime.models / "model.ckpt").write_bytes(b"weights")
            process = unittest.mock.Mock(stdout=iter(["downloading\n"]))
            process.wait.return_value = 0
            # One of the two files never arrived: reported, not assumed.
            with unittest.mock.patch("subprocess.Popen", return_value=process) as popen:
                with self.assertRaises(RuntimeError) as raised:
                    separation.download_model(runtime, model)
            self.assertIn("config.yaml", str(raised.exception))
            self.assertTrue(popen.call_args.kwargs["env"]["PATH"].startswith(str(root)))


class RuntimeStateTests(unittest.TestCase):
    def home(self, directory: str) -> unittest.mock._patch_dict:
        return unittest.mock.patch.dict(
            "os.environ", {"RX3_STEM_STUDIO_HOME": directory}
        )

    def ready_runtime(self, root: pathlib.Path) -> provisioning.Runtime:
        """A runtime whose separator is the managed one."""
        environment = root / "runtime"
        return provisioning.Runtime(
            environment=environment, models=root / "models",
            separator=provisioning._script(environment, provisioning.SEPARATOR_COMMAND),
            ffmpeg=root / "ffmpeg",
        )

    def test_a_separator_outside_the_environment_is_not_managed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.assertTrue(self.ready_runtime(root).managed)
            external = provisioning.Runtime(
                environment=root / "runtime", models=root / "models",
                separator=pathlib.Path("/usr/local/bin/audio-separator"),
                ffmpeg=root / "ffmpeg",
            )
            self.assertTrue(external.ready)
            self.assertFalse(external.managed)
            with self.home(directory):
                (root / provisioning.STATE_NAME).write_text(
                    '{"accelerator": "cpu"}', encoding="utf-8"
                )
                # Nothing to rebuild: the copy in use is not the managed one.
                self.assertFalse(provisioning.needs_reinstall("cuda", external))

    def test_the_installed_accelerator_round_trips_and_a_damaged_state_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / provisioning.STATE_NAME
            with self.home(directory):
                self.assertIsNone(provisioning.installed_accelerator())
                state.write_text('{"accelerator": "cuda"}', encoding="utf-8")
                self.assertEqual(provisioning.installed_accelerator(), "cuda")
                for damaged in ("not json", '{"accelerator": "quantum"}'):
                    state.write_text(damaged, encoding="utf-8")
                    self.assertIsNone(provisioning.installed_accelerator())

    def test_reinstallation_is_needed_only_when_the_accelerator_differs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            runtime = self.ready_runtime(root)
            with self.home(directory):
                # No state at all: a runtime from an earlier version of the
                # application is not a mismatch.
                self.assertFalse(provisioning.needs_reinstall("cuda", runtime))
                (root / provisioning.STATE_NAME).write_text(
                    '{"accelerator": "cpu"}', encoding="utf-8"
                )
                self.assertFalse(provisioning.needs_reinstall("cpu", runtime))
                self.assertTrue(provisioning.needs_reinstall("cuda", runtime))
                # Nothing installed yet: there is nothing to reinstall.
                absent = provisioning.Runtime(
                    environment=root, models=root, separator=None, ffmpeg=None
                )
                self.assertFalse(provisioning.needs_reinstall("cuda", absent))

    def test_uninstall_removes_the_environment_and_keeps_the_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for name in ("runtime/lib", "bin", "models"):
                (root / name).mkdir(parents=True)
            (root / "models/model.ckpt").write_bytes(b"x")
            (root / provisioning.STATE_NAME).write_text('{"accelerator": "cpu"}', encoding="utf-8")
            with self.home(directory):
                provisioning.uninstall()
                self.assertIsNone(provisioning.installed_accelerator())
            self.assertFalse((root / "runtime").exists())
            self.assertFalse((root / "bin").exists())
            self.assertTrue((root / "models/model.ckpt").is_file())

    def test_ffmpeg_is_exposed_under_its_plain_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            bundled = root / "ffmpeg-macos-aarch64-v7.1"
            bundled.write_bytes(b"binary")
            runtime = provisioning.Runtime(
                environment=root, models=root, separator=root / "separator", ffmpeg=bundled,
            )
            with self.home(directory):
                exposed = runtime.ffmpeg_directory()
                self.assertIsNotNone(exposed)
                alias = exposed / provisioning._executable_name("ffmpeg")
                self.assertTrue(alias.exists())
                self.assertEqual(alias.read_bytes(), b"binary")
                self.assertEqual(runtime.ffmpeg_directory(), exposed)

    def test_an_already_named_ffmpeg_is_used_where_it_is_and_leads_the_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            real = root / provisioning._executable_name("ffmpeg")
            real.write_bytes(b"binary")
            runtime = provisioning.Runtime(
                environment=root, models=root / "models",
                separator=root / "separator", ffmpeg=real,
            )
            self.assertEqual(runtime.ffmpeg_directory(), root)
            values = runtime.subprocess_environment()
            self.assertTrue(values["PATH"].startswith(str(root)))
            self.assertEqual(values["AUDIO_SEPARATOR_MODEL_DIR"], str(root / "models"))


FILTER_LISTING = """Filters:
  T.. aformat           A->A       Convert the input audio to one of the specified formats.
  ... apad              A->A       Pad audio with silence.
  ..C aresample         A->A       Resample audio data.
  T.. astats            A->A       Show time domain statistics about audio frames.
  ... atrim             A->A       Pick one continuous section from the input.
  TS. volume            A->A       Change input volume.
"""


class FfmpegCapabilityTests(unittest.TestCase):
    """A build without one of the filters the pipeline uses fails partway
    through a job, so it has to be rejected before one is started."""

    def probe(self, binary, stdout, returncode=0):
        binary.write_text(stdout)  # distinct content keeps the probe cache honest
        result = subprocess.CompletedProcess([], returncode, stdout, "")
        with unittest.mock.patch.object(provisioning.subprocess, "run", return_value=result):
            return binary, provisioning.missing_filters(binary)

    def test_the_probe_reports_exactly_what_a_build_is_missing(self):
        without_apad = "\n".join(
            line for line in FILTER_LISTING.splitlines() if " apad " not in line
        )
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.assertEqual(self.probe(root / "complete", FILTER_LISTING)[1], ())
            self.assertEqual(self.probe(root / "partial", without_apad)[1], ("apad",))
            # A binary that cannot even list its filters is not trusted.
            self.assertEqual(
                self.probe(root / "mute", "", returncode=1)[1],
                provisioning.REQUIRED_FILTERS,
            )

    def test_an_incomplete_copy_falls_through_to_the_next(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            first, second = root / "system", root / "bundled"
            for path in (first, second):
                path.write_text("x")
            absent = {first: ("apad",), second: ()}
            with unittest.mock.patch.object(
                provisioning, "missing_filters", side_effect=lambda path: absent[path]
            ):
                chosen, rejected = provisioning._first_complete_ffmpeg([None, first, second])
            self.assertEqual(chosen, second)
            self.assertEqual(rejected, ((first, ("apad",)),))

    def test_the_gap_is_explained_rather_than_silent(self):
        runtime = provisioning.Runtime(
            environment=pathlib.Path("/x"), models=pathlib.Path("/x"),
            separator=pathlib.Path("/x/separator"), ffmpeg=pathlib.Path("/x/ffmpeg"),
            ffmpeg_incomplete=((pathlib.Path("/usr/bin/ffmpeg"), ("apad",)),),
        )
        self.assertIn("apad", runtime.summary)
        self.assertIn("ffmpeg", runtime.summary)

    def test_an_explicit_override_is_honoured_and_its_gap_only_reported(self):
        """The override is the documented escape hatch; a probe this project
        invented must not overrule the operator's own choice."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            chosen = root / "ffmpeg"
            chosen.write_text("x")
            with unittest.mock.patch.object(
                provisioning, "missing_filters", return_value=("apad",)
            ), unittest.mock.patch.dict("os.environ", {
                "RX3_FFMPEG": str(chosen), "RX3_SEPARATOR": str(chosen),
            }):
                runtime = provisioning.detect(root)
            self.assertEqual(runtime.ffmpeg, chosen)
            self.assertTrue(runtime.ready)
            self.assertIn("apad", runtime.summary)


class CudaWheelTests(unittest.TestCase):
    """PyPI ships a CPU-only PyTorch for Windows, and CUDA 13 dropped the
    architectures before Turing, so the index cannot be left to chance."""

    def resolve(self, capability):
        with unittest.mock.patch.object(
            provisioning, "_nvidia_compute_capability", return_value=capability
        ):
            return provisioning.resolve_acceleration("cuda")

    def test_the_index_follows_the_architecture_of_the_card(self):
        # A Blackwell card, and an unreadable capability, take the current
        # index; anything older than Turing keeps the legacy one.
        expected = {
            (12, 0): provisioning.CUDA_WHEEL_INDEX,
            (7, 5): provisioning.CUDA_WHEEL_INDEX,
            (6, 1): provisioning.LEGACY_CUDA_WHEEL_INDEX,
            None: provisioning.CUDA_WHEEL_INDEX,
        }
        for capability, index in expected.items():
            self.assertEqual(self.resolve(capability).torch_index, index)


class AccelerationTests(unittest.TestCase):
    def test_every_platform_resolves_to_a_known_profile(self):
        keys = [key for key, _ in provisioning.available_accelerations()]
        self.assertEqual(keys[0], provisioning.AUTOMATIC)
        self.assertIn("cpu", keys)

        resolved = provisioning.resolve_acceleration(provisioning.AUTOMATIC)
        self.assertIn(resolved.key, provisioning.ACCELERATIONS)
        self.assertIn(resolved.extra, ("cpu", "gpu", "dml"))
        # An accelerator stored by a later version falls back to detection.
        self.assertEqual(
            provisioning.resolve_acceleration("from-the-future").key, resolved.key
        )

    def test_directml_is_the_only_profile_needing_a_separation_flag(self):
        for key, acceleration in provisioning.ACCELERATIONS.items():
            expected = ("--use_directml",) if key == "directml" else ()
            self.assertEqual(acceleration.separation_flags, expected)

    def test_install_steps_pin_the_wheel_index_of_the_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = pathlib.Path(directory)
            for key in ("cuda", "rocm", "directml", "cpu"):
                steps = list(provisioning.install_packages(environment, provisioning.ACCELERATIONS[key]))
                joined = " ".join(part for _, command in steps for part in command)
                self.assertIn(provisioning.ACCELERATIONS[key].requirement, joined)
                self.assertIn(provisioning.LIBROSA_PIN, joined)
                index = provisioning.ACCELERATIONS[key].torch_index
                if index:
                    self.assertIn(index, joined)


class EngineTests(unittest.TestCase):
    def test_detect_resolves_overrides_before_the_managed_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            separator = root / "audio-separator"
            ffmpeg = root / "ffmpeg"
            for path in (separator, ffmpeg):
                path.write_text("#!/bin/sh\n", encoding="utf-8")
            with unittest.mock.patch.dict("os.environ", {
                "RX3_SEPARATOR": str(separator), "RX3_FFMPEG": str(ffmpeg),
            }):
                runtime = provisioning.detect()
            self.assertTrue(runtime.ready)
            self.assertEqual(runtime.separator, separator)
            self.assertIn("ready", runtime.summary)

    def test_summary_names_every_missing_component(self):
        runtime = provisioning.Runtime(
            environment=pathlib.Path("/nonexistent"),
            models=pathlib.Path("/nonexistent"),
            separator=None,
            ffmpeg=None,
        )
        self.assertFalse(runtime.ready)
        self.assertIn("audio-separator and FFmpeg", runtime.summary)

    def test_a_vanished_ffmpeg_leaves_the_path_untouched(self):
        """A dangling alias would shadow a working FFmpeg further down PATH."""
        with tempfile.TemporaryDirectory() as directory:
            runtime = provisioning.Runtime(
                environment=pathlib.Path(directory),
                models=pathlib.Path(directory) / "models",
                separator=pathlib.Path(directory) / "audio-separator",
                ffmpeg=pathlib.Path(directory) / "ffmpeg-macos-aarch64-v7.1",
            )
            with unittest.mock.patch.dict(
                "os.environ", {"RX3_STEM_STUDIO_HOME": directory}
            ):
                self.assertIsNone(runtime.ffmpeg_directory())
                values = runtime.subprocess_environment()
            self.assertEqual(values["PATH"], os.environ.get("PATH", ""))
            self.assertFalse((pathlib.Path(directory) / "bin").exists())


class TrackPositionTests(unittest.TestCase):
    """`completed` counts finished work; `position` says which track is running.

    Showing the first beside the name of the track being processed is what made
    the progress line read one behind reality.
    """

    def playlist(self, root: pathlib.Path, count: int):
        tracks = []
        for index in range(count):
            audio = root / f"Artist - Track {index}.aiff"
            audio.write_bytes(b"fixture")
            tracks.append((str(index + 1), f"Track {index}", "Artist", audio))
        return parse_collection(write_export(root, tracks))

    def test_position_leads_completed_and_both_reach_the_total(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            collection = self.playlist(root, 3)
            output = root / "export"
            stems = output / "RX3_STEMS"
            stems.mkdir(parents=True)
            for index in range(3):
                (stems / f"Artist - Track {index}.rx3stem").write_bytes(b"x" * 128)

            seen: list[tuple[str, int, int]] = []
            state = StemJob(
                provisioning.detect(), collection, collection.playlists[0], output,
                observer=lambda state: seen.append(
                    (state.current, state.position, state.completed)
                ),
            ).run()

            # Every update that names a track names it at its own position, and
            # never reports it as already counted.
            named = [entry for entry in seen if entry[0]]
            self.assertTrue(named)
            for current, position, completed in named:
                self.assertEqual(current, f"Artist — Track {position - 1}")
                self.assertLess(completed, position + 1)
            self.assertEqual(min(position for _, position, _ in named), 1)

            self.assertEqual(state.state, "done")
            self.assertEqual((state.position, state.completed, state.total), (3, 3, 3))


class EstimateTests(unittest.TestCase):
    def test_the_first_measurement_replaces_the_seeded_guess(self):
        estimator = estimate.Estimator("MDXC", "cpu")
        self.assertFalse(estimator.measured)
        seeded = estimator.rate
        estimator.observe(audio_seconds=200, elapsed=100)
        self.assertTrue(estimator.measured)
        self.assertAlmostEqual(estimator.rate, 0.5)
        self.assertNotAlmostEqual(estimator.rate, seeded)

    def test_later_measurements_are_blended_and_converge(self):
        estimator = estimate.Estimator("MDX", "cpu")
        estimator.observe(audio_seconds=100, elapsed=100)   # rate 1.0
        estimator.observe(audio_seconds=100, elapsed=200)   # rate 2.0
        self.assertGreater(estimator.rate, 1.0)
        self.assertLess(estimator.rate, 2.0)

        # An existing sidecar costs no time and says nothing about speed, so it
        # must not reach the blend at all.
        blended = estimator.rate
        estimator.observe(audio_seconds=300, elapsed=0.001)
        self.assertAlmostEqual(estimator.rate, blended)

        converging = estimate.Estimator("Demucs", "cpu")
        for _ in range(20):
            converging.observe(audio_seconds=100, elapsed=250)
        self.assertAlmostEqual(converging.rate, 2.5, places=3)
        self.assertIsNone(converging.remaining(0))

    def test_measured_rates_survive_to_the_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / estimate.THROUGHPUT_NAME
            estimator = estimate.estimator_for(path, "MDXC", "mps")
            self.assertFalse(estimator.measured)
            estimator.observe(audio_seconds=100, elapsed=42)
            estimate.remember(path, estimator)

            restored = estimate.estimator_for(path, "MDXC", "mps")
            self.assertTrue(restored.measured)
            self.assertAlmostEqual(restored.rate, 0.42)
            # Another pairing is a different machine configuration entirely.
            self.assertFalse(estimate.estimator_for(path, "MDXC", "cpu").measured)

    def test_the_two_presets_are_timed_apart_on_the_same_model(self):
        """They name the same model and differ only in passes over the audio,
        so one measured rate would be wrong for the other by that factor -
        and the blend would drag it back and forth as the operator alternated."""
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / estimate.THROUGHPUT_NAME
            quality = estimate.estimator_for(path, "MDXC", "mps", separation.QUALITY_MODE)
            quality.observe(audio_seconds=100, elapsed=17)
            estimate.remember(path, quality)

            normal = estimate.estimator_for(
                path, "MDXC", "mps", separation.NORMAL_MODE
            )
            self.assertFalse(normal.measured)
            self.assertTrue(
                estimate.estimator_for(
                    path, "MDXC", "mps", separation.QUALITY_MODE
                ).measured
            )

    def test_an_unmeasured_estimator_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / estimate.THROUGHPUT_NAME
            estimate.remember(path, estimate.Estimator("MDX", "cpu"))
            self.assertFalse(path.exists())

    def test_damaged_calibration_is_ignored_rather_than_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / estimate.THROUGHPUT_NAME
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(estimate.load_rates(path), {})
            self.assertFalse(estimate.estimator_for(path, "MDX", "cpu").measured)

    def test_durations_are_phrased_at_the_precision_they_support(self):
        self.assertEqual(estimate.format_duration(None), "unknown")
        self.assertEqual(estimate.format_duration(12), "under a minute")
        self.assertEqual(estimate.format_duration(59), "under a minute")
        self.assertEqual(estimate.format_duration(90), "about 2 min")
        self.assertEqual(estimate.format_duration(2040), "about 34 min")
        self.assertEqual(estimate.format_duration(3600), "about 1 h")
        self.assertEqual(estimate.format_duration(4800), "about 1 h 20 min")

    def test_a_forecast_names_the_playlist_and_flags_a_rough_estimate(self):
        tracks = [unittest.mock.Mock(duration=300) for _ in range(4)]
        rough = estimate.forecast(tracks, estimate.Estimator("MDX", "cpu"))
        self.assertEqual(rough.tracks, 4)
        self.assertEqual(rough.audio_seconds, 1200)
        self.assertFalse(rough.measured)
        self.assertIn("4 tracks", rough.summary)
        self.assertIn("20 min of audio", rough.summary)
        self.assertIn("(rough)", rough.summary)

        estimator = estimate.Estimator("MDX", "cpu")
        estimator.observe(audio_seconds=100, elapsed=100)
        measured = estimate.forecast(tracks, estimator)
        self.assertTrue(measured.measured)
        self.assertEqual(measured.seconds, 1200)
        self.assertIn("about 20 min", measured.summary)
        self.assertNotIn("(rough)", measured.summary)


class QualityPresetTests(unittest.TestCase):
    def catalogue(self, *entries: tuple[str, str, float]) -> separation.Catalogue:
        return separation.Catalogue(models=tuple(
            separation.Model(
                architecture=architecture, name=filename, filename=filename,
                stems=("Vocals", "Instrumental"), vocal_sdr=sdr,
                download_files=(filename,),
            )
            for filename, architecture, sdr in entries
        ))

    def variants(self):
        """Every (preset, variant, accelerates_torch) a machine can resolve to."""
        for preset in separation.PRESETS:
            for accelerates_torch in (True, False):
                yield (preset, preset.resolve(accelerates_torch=accelerates_torch),
                       accelerates_torch)

    def test_a_preset_takes_its_first_candidate_the_catalogue_offers(self):
        for preset, variant, accelerates_torch in self.variants():
            catalogue = self.catalogue(
                (variant.candidates[1], variant.architecture, 9.0),
                (variant.candidates[0], variant.architecture, 8.0),
            )
            resolved = separation.apply_preset(
                separation.Settings(), preset, catalogue,
                accelerates_torch=accelerates_torch,
            )
            # The order of the candidate list wins over the catalogue's score:
            # these are the models this pipeline has been measured against.
            self.assertEqual(resolved.model, variant.candidates[0])
            self.assertEqual(resolved.mode, preset.key)

    def test_a_withdrawn_candidate_falls_back_to_the_best_of_its_architecture(self):
        preset = separation.preset(separation.QUICK_MODE)
        variant = preset.resolve(accelerates_torch=False)
        catalogue = self.catalogue(
            ("renamed_upstream.onnx", variant.architecture, 12.4),
            ("weaker.onnx", variant.architecture, 9.0),
            ("another_architecture.ckpt", "MDXC", 13.0),
        )
        resolved = separation.apply_preset(
            separation.Settings(), preset, catalogue, accelerates_torch=False
        )
        # The best of the preset's own architecture, not the best overall: the
        # tuning and the timings only hold for that architecture, and on this
        # build the other one would not reach the GPU at all.
        self.assertEqual(resolved.model, "renamed_upstream.onnx")

    def test_an_empty_catalogue_still_resolves_to_something_runnable(self):
        """The state before the runtime is installed, so before any model list."""
        for preset, variant, accelerates_torch in self.variants():
            resolved = separation.apply_preset(
                separation.Settings(), preset, separation.Catalogue(),
                accelerates_torch=accelerates_torch,
            )
            self.assertEqual(resolved.model, variant.candidates[0])
            self.assertEqual(resolved.mode, preset.key)

    def test_a_preset_only_passes_arguments_of_its_own_architecture(self):
        for preset, variant, accelerates_torch in self.variants():
            catalogue = self.catalogue(
                (variant.candidates[0], variant.architecture, 10.0)
            )
            resolved = separation.apply_preset(
                separation.Settings(), preset, catalogue,
                accelerates_torch=accelerates_torch,
            )
            arguments = " ".join(resolved.arguments(variant.architecture))
            for other, options in separation.ARCHITECTURE_OPTIONS.items():
                if other == variant.architecture:
                    continue
                for option in options:
                    self.assertNotIn(option.flag, arguments)

    def test_the_ladder_trades_passes_first_and_the_model_only_at_the_bottom(self):
        """Three names have to mean three distinct things on every build.
        Trading the model costs a download and gives up SDR, so the ladder only
        does it once, at the bottom: High quality and Normal are one model at
        two steps, and moving between them is free in both senses. Below the
        roformer every architecture lands within a quarter of the same cost, so
        there is no second trade to make."""
        for accelerates_torch in (True, False):
            resolved = [
                preset.resolve(accelerates_torch=accelerates_torch)
                for preset in separation.PRESETS
            ]
            configurations = {
                (variant.architecture, variant.candidates, tuple(sorted(variant.values.items())))
                for variant in resolved
            }
            self.assertEqual(len(configurations), len(separation.PRESETS))

            quality, normal = (
                separation.preset(key).resolve(accelerates_torch=accelerates_torch)
                for key in (separation.QUALITY_MODE, separation.NORMAL_MODE)
            )
            self.assertEqual(quality.architecture, normal.architecture)
            self.assertEqual(quality.candidates, normal.candidates)
            self.assertNotEqual(quality.values, normal.values)

        # Where the roformer runs, only the quickest preset gives it up, and it
        # gives it up for a waveform model rather than the band-limited ONNX
        # fallback: SDR is traded, the top of the spectrum is not.
        for key in (separation.QUALITY_MODE, separation.NORMAL_MODE):
            self.assertEqual(
                separation.preset(key).resolve(accelerates_torch=True).candidates,
                separation.ROFORMER_CANDIDATES,
            )
        quick = separation.preset(separation.QUICK_MODE).resolve(accelerates_torch=True)
        self.assertNotEqual(quick.candidates, separation.ROFORMER_CANDIDATES)
        self.assertEqual(quick.architecture, "Demucs")

    def test_a_build_that_accelerates_torch_asks_for_the_better_model(self):
        """A roformer is a Torch checkpoint and an MDX-Net is an ONNX graph, so
        which architecture reaches the GPU is not the same on every platform.
        Where PyTorch is accelerated the roformer is both the better and the
        quicker answer; where it is not, only the ONNX model runs on the GPU at
        all, and 2.4 dB of vocal SDR is given up to get there."""
        for preset in separation.PRESETS:
            self.assertNotEqual(
                preset.resolve(accelerates_torch=True).architecture, "MDX"
            )
            self.assertEqual(preset.resolve(accelerates_torch=False).architecture, "MDX")
        accelerates_torch = {
            key: acceleration.accelerates_torch
            for key, acceleration in provisioning.ACCELERATIONS.items()
        }
        # DirectML accelerates ONNX Runtime alone and its PyTorch backend is
        # pinned to a release far behind what a roformer needs; a CPU build
        # accelerates neither, and ONNX Runtime is the quicker of the two
        # there. Everything else runs PyTorch on the GPU.
        self.assertEqual({key for key, value in accelerates_torch.items() if not value},
                         {"directml", "cpu"})

    def test_each_variant_says_what_it_costs_on_the_build_that_runs_it(self):
        """One preset is not one offer: on a build that runs no roformer, every
        preset is the same lighter model at a different overlap rather than the
        ladder of models the other build gets, and saying so is the only way
        the interface does not promise one quality everywhere."""
        summaries = {
            variant.summary
            for preset in separation.PRESETS
            for variant in (preset.torch, preset.onnx)
        }
        self.assertEqual(len(summaries), 2 * len(separation.PRESETS))
        for summary in summaries:
            self.assertTrue(summary and summary[0].isupper())

    # `vocals_mel_band_roformer` chunks at `stft_hop_length * (dim_t - 1)`, or
    # 441 * 1100 = 485100 samples = 11.0 s at 44.1 kHz.
    ROFORMER_CHUNK_SECONDS = 11

    def test_the_overlaps_step_the_right_way_on_each_architecture(self):
        """`mdxc_overlap` on a roformer is a step in seconds, not an amount of
        overlap: raising it advances the prediction window further, so the
        result is stitched from fewer passes. `mdx_overlap` is a real fraction
        and reads the other way round. Taking either for the other inverts
        every preset it appears in.

        The roformer step is clamped to the chunk, so any value at or above the
        chunk length in seconds separates in one pass with no overlap at all.
        Measured on a 90 s excerpt, that leaves a discontinuity every 11.0 s
        reaching 25x the surrounding sample-to-sample difference, against 0.7x
        away from a boundary - a click, and the deck subtracts the stem from the
        mix, so it lands in the instrumental too. One step below, 9% of the
        chunk still overlaps and it costs nothing: 0.399 s/s against 0.406."""
        mdxc, mdx = (
            next(item for item in separation.ARCHITECTURE_OPTIONS[architecture]
                 if item.name == name)
            for architecture, name in (("MDXC", "mdxc_overlap"), ("MDX", "mdx_overlap"))
        )
        # Normal is quicker than High quality, which on the roformer means a
        # higher value and on the MDX fallback a lower one.
        self.assertGreater(separation.NORMAL_OVERLAP, mdxc.default)
        self.assertLess(separation.NORMAL_OVERLAP, self.ROFORMER_CHUNK_SECONDS)
        self.assertGreater(separation.MDX_QUALITY_OVERLAP, mdx.default)
        self.assertLess(separation.MDX_QUICK_OVERLAP, mdx.default)
        self.assertNotIn("Higher is better", mdxc.help)

        # The build that can only run MDX still gets three distinct offers,
        # ordered the way their names are.
        overlaps = [
            preset.onnx.values.get("mdx_overlap", mdx.default)
            for preset in separation.PRESETS
        ]
        self.assertEqual(overlaps, sorted(overlaps, reverse=True))

    def test_no_preset_overrides_a_model_segment_size(self):
        """Every candidate runs at the segment size its own weights were
        trained for. Naming another one used to be how the fast preset reached
        the Torch runtime on Apple Silicon; the architecture split does that
        now, so nothing has to run at a context the model never saw."""
        for preset in separation.PRESETS:
            for variant in (preset.torch, preset.onnx):
                self.assertNotIn("mdx_segment_size", variant.values)
                self.assertNotIn("mdxc_segment_size", variant.values)
                self.assertNotIn("mdxc_override_model_segment_size", variant.values)

    def test_editing_the_configuration_by_hand_demotes_the_preset_to_custom(self):
        settings = separation.apply_preset(
            separation.Settings(), separation.preset(separation.QUALITY_MODE),
            separation.Catalogue(),
        )
        self.assertEqual(settings.mode, separation.QUALITY_MODE)
        option = separation.normalization_option()
        self.assertEqual(settings.with_value(option, 0.5).mode, separation.CUSTOM_MODE)
        self.assertEqual(
            settings.with_model("something_else.ckpt").mode, separation.CUSTOM_MODE
        )
        # Reapplying the dialog unchanged must not relabel the preset, and
        # acceleration is a property of the machine, not of the trade-off.
        self.assertEqual(settings.with_value(option, settings.value(option)), settings)
        self.assertEqual(settings.with_accelerator("cpu").mode, settings.mode)

    def test_the_mode_survives_a_round_trip_through_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / separation.SETTINGS_NAME
            for mode in (separation.QUALITY_MODE, separation.NORMAL_MODE,
                         separation.QUICK_MODE, separation.CUSTOM_MODE):
                settings = separation.Settings(mode=mode)
                separation.save_settings(path, settings)
                self.assertEqual(separation.load_settings(path).mode, mode)

            # Settings written before presets existed describe an unknown
            # configuration; calling it a preset would misreport what it holds.
            path.write_text(
                '{"model": "some_model.ckpt", "accelerator": "cpu", "values": {}}',
                encoding="utf-8",
            )
            self.assertEqual(separation.load_settings(path).mode, separation.CUSTOM_MODE)


class ThemeTests(unittest.TestCase):
    """The palette has to come from what Tk paints, not from a fixed guess."""

    def module(self):
        application = pathlib.Path(__file__).parents[1] / "apps/rx3-toolbox"
        if str(application) not in sys.path:
            sys.path.insert(0, str(application))
        import theme

        return theme

    _root = None
    _unavailable = "not probed"

    @classmethod
    def setUpClass(cls):
        # One Tk interpreter for the whole class. Creating and destroying a
        # root per test crashes some macOS Tk builds outright, taking the rest
        # of the suite with it, so each test gets a Toplevel on a shared root.
        #
        # The probe runs out of process for the same reason: when Aqua cannot
        # be initialised, Tk aborts rather than raising, and a headless run has
        # to be skipped rather than killed.
        probe = subprocess.run(
            [sys.executable, "-c", "import tkinter as tk; tk.Tk().destroy()"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if probe.returncode:
            detail = (probe.stderr or probe.stdout).strip().splitlines()
            cls._unavailable = detail[-1] if detail else f"exit status {probe.returncode}"
            return
        tkinter = __import__("tkinter")
        try:
            cls._root = tkinter.Tk()
            cls._root.withdraw()
        except tkinter.TclError as error:  # No display, as on a headless runner.
            cls._unavailable = str(error)

    @classmethod
    def tearDownClass(cls):
        if cls._root is not None:
            cls._root.destroy()
            cls._root = None

    def root(self):
        """A window of this test's own, on the shared interpreter."""
        if self._root is None:
            raise unittest.SkipTest(f"Tk is unavailable: {self._unavailable}")
        return __import__("tkinter").Toplevel(self._root)

    def test_the_window_themes_and_reflows_without_looping(self):
        """One window, exercising every live behaviour of the theme module.

        Kept as a single test because each one costs a mapped Tk window: the
        palette comes from what Tk paints, marked labels follow the width they
        are given, and neither the reflow nor the scrollbar may feed its own
        event back into itself.
        """
        theme = self.module()
        window = self.root()
        try:
            from tkinter import ttk

            style = ttk.Style(window)
            style.configure("TFrame", background="#ffffff")
            self.assertFalse(theme.is_dark(window))
            style.configure("TFrame", background="#1e1e1e")
            self.assertTrue(theme.is_dark(window))

            palette = theme.apply(window)
            self.assertEqual(style.lookup("Muted.TLabel", "foreground"), palette.muted)
            self.assertEqual(style.lookup("Warning.TLabel", "foreground"), palette.warning)

            window.geometry("600x400")
            label = theme.wrapping(ttk.Label(window, text="word " * 200), inset=40)
            label.pack(fill="x")
            scroller = theme.ScrollFrame(window)
            scroller.pack(fill="both", expand=True)
            ttk.Label(scroller.body, text="short").pack()
            theme.follow_width(window)
            window.update_idletasks()
            window.update()

            reflowed = label.cget("wraplength")
            self.assertGreater(reflowed, theme.MINIMUM_WRAP)
            self.assertFalse(scroller._bar_shown)
            roomy = scroller._canvas.winfo_width()

            # Every widget carries its toplevel in its bind tags, so a Toplevel
            # bound for <Configure> is handed each descendant's too. Reflowing
            # to an inner widget's width resizes it, which reports it again.
            # Filling the scroller must likewise not narrow its own viewport,
            # or the rewrapped text changes height and hides the bar again.
            for index in range(40):
                ttk.Label(scroller.body, text=f"row {index}").pack()
            window.update_idletasks()
            window.update()

            self.assertEqual(label.cget("wraplength"), reflowed)
            self.assertTrue(scroller._bar_shown)
            self.assertAlmostEqual(
                scroller._canvas.winfo_width(),
                roomy,
                delta=1,
            )
        finally:
            window.destroy()

    def test_the_two_appearances_never_share_a_colour(self):
        theme = self.module()
        for key in ("muted", "warning", "text_background", "text_foreground"):
            self.assertNotEqual(theme.LIGHT[key], theme.DARK[key])


if __name__ == "__main__":
    unittest.main()
