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

from tools.rx3_stems import provisioning, separation, sidecar
from tools.rx3_stems import job as job_module
from tools.rx3_stems.job import JobState, StemJob, failure_detail
from tools.rx3_stems.rekordbox import file_url_to_path, parse_collection, safe_stem


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

    def test_windows_drive_letter_locations_lose_the_url_leading_slash(self):
        # Rekordbox on Windows writes this exact form.
        resolved = file_url_to_path("file://localhost/C:/Music/Artist%20-%20Track.aiff")
        self.assertEqual(pathlib.PurePath(resolved).parts[0].rstrip("\\/"), "C:")
        self.assertEqual(pathlib.PurePath(resolved).name, "Artist - Track.aiff")

    def test_posix_locations_keep_their_leading_slash(self):
        resolved = file_url_to_path("file://localhost/Users/dj/Music/Track.aiff")
        self.assertEqual(pathlib.PurePath(resolved).parts[1], "Users")

    def test_rejects_a_remote_location(self):
        with self.assertRaises(ValueError):
            file_url_to_path("https://example.invalid/Track.aiff")

    def test_safe_stem_strips_separators_and_control_characters(self):
        self.assertEqual(safe_stem("A/B:C\x01 "), "A_B_C")
        self.assertEqual(safe_stem("   "), "track")


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

    def test_refuses_two_distinct_sources_with_the_same_basename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            sources = []
            for folder in ("one", "two"):
                source = root / folder / "Same Name.aiff"
                source.parent.mkdir()
                source.write_bytes(b"fixture")
                sources.append(source)
            xml = write_export(root, [
                ("1", "One", "A", sources[0]),
                ("2", "Two", "B", sources[1]),
            ])
            collection = parse_collection(xml)
            output = root / "export"
            (output / "RX3_STEMS").mkdir(parents=True)
            (output / "RX3_STEMS/Same Name.rx3stem").write_bytes(b"x" * 128)

            state = StemJob(self.runtime(), collection, collection.playlists[0], output).run()
            self.assertEqual(state.state, "done")
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

    def test_an_accelerated_run_says_nothing(self):
        job = self.job("cuda")
        job._note_inference_device("CUDA is available in Torch, setting Torch device to CUDA")
        self.assertEqual(job.state.notices, ())

    def test_a_cpu_run_is_not_a_fallback(self):
        job = self.job("cpu")
        job._note_inference_device(f"{job_module.CPU_FALLBACK}, running in CPU mode")
        self.assertEqual(job.state.notices, ())


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

    def test_flags_are_emitted_without_a_value(self):
        denoise = next(o for o in separation.ARCHITECTURE_OPTIONS["MDX"] if o.kind == "flag")
        settings = separation.Settings().with_value(denoise, True)
        self.assertIn(denoise.flag, settings.arguments("MDX"))

    def test_out_of_range_values_are_refused(self):
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

    def test_a_missing_settings_file_yields_the_defaults(self):
        loaded = separation.load_settings(pathlib.Path("/nonexistent/separation.json"))
        self.assertEqual(loaded, separation.Settings())


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

    def test_downloading_a_model_carries_the_prepared_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            runtime = self.runtime(root)
            model = separation.Model(
                architecture="VR", name="HP-UVR", filename="1_HP-UVR.pth",
                stems=("Vocals",), vocal_sdr=7.9, download_files=("1_HP-UVR.pth",),
            )
            (runtime.models / "1_HP-UVR.pth").write_bytes(b"weights")
            process = unittest.mock.Mock(stdout=iter(["downloading\n"]))
            process.wait.return_value = 0
            with unittest.mock.patch("subprocess.Popen", return_value=process) as popen:
                separation.download_model(runtime, model)
            environment = popen.call_args.kwargs["env"]
            self.assertTrue(environment["PATH"].startswith(str(root)))

    def test_an_incomplete_download_is_reported_rather_than_assumed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            runtime = self.runtime(root)
            model = separation.Model(
                architecture="MDXC", name="Roformer", filename="model.ckpt",
                stems=("Vocals",), vocal_sdr=12.6,
                download_files=("model.ckpt", "config.yaml"),
            )
            (runtime.models / "model.ckpt").write_bytes(b"weights")
            process = unittest.mock.Mock(stdout=iter([]))
            process.wait.return_value = 0
            with unittest.mock.patch("subprocess.Popen", return_value=process):
                with self.assertRaises(RuntimeError) as raised:
                    separation.download_model(runtime, model)
            self.assertIn("config.yaml", str(raised.exception))


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

    def test_the_installed_accelerator_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.home(directory):
                self.assertIsNone(provisioning.installed_accelerator())
                (pathlib.Path(directory) / provisioning.STATE_NAME).write_text(
                    '{"accelerator": "cuda"}', encoding="utf-8"
                )
                self.assertEqual(provisioning.installed_accelerator(), "cuda")

    def test_an_unreadable_or_unknown_state_reads_as_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory) / provisioning.STATE_NAME
            with self.home(directory):
                state.write_text("not json", encoding="utf-8")
                self.assertIsNone(provisioning.installed_accelerator())
                state.write_text('{"accelerator": "quantum"}', encoding="utf-8")
                self.assertIsNone(provisioning.installed_accelerator())

    def test_reinstallation_is_needed_only_when_the_accelerator_differs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            runtime = self.ready_runtime(root)
            with self.home(directory):
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

    def test_a_runtime_from_an_earlier_version_reports_no_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with self.home(directory):
                self.assertFalse(provisioning.needs_reinstall("cuda", self.ready_runtime(root)))

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

    def test_an_already_named_ffmpeg_is_used_where_it_is(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            real = root / provisioning._executable_name("ffmpeg")
            real.write_bytes(b"binary")
            runtime = provisioning.Runtime(
                environment=root, models=root, separator=root / "separator", ffmpeg=real,
            )
            self.assertEqual(runtime.ffmpeg_directory(), root)

    def test_the_subprocess_environment_puts_ffmpeg_first_on_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            real = root / provisioning._executable_name("ffmpeg")
            real.write_bytes(b"binary")
            runtime = provisioning.Runtime(
                environment=root, models=root / "models",
                separator=root / "separator", ffmpeg=real,
            )
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

    def probe(self, root, stdout, returncode=0):
        binary = root / "ffmpeg"
        binary.write_text(stdout)  # distinct content keeps the probe cache honest
        result = subprocess.CompletedProcess([], returncode, stdout, "")
        with unittest.mock.patch.object(provisioning.subprocess, "run", return_value=result):
            return binary, provisioning.missing_filters(binary)

    def test_a_complete_build_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            _, absent = self.probe(pathlib.Path(directory), FILTER_LISTING)
            self.assertEqual(absent, ())

    def test_a_build_without_apad_is_reported(self):
        listing = "\n".join(
            line for line in FILTER_LISTING.splitlines() if " apad " not in line
        )
        with tempfile.TemporaryDirectory() as directory:
            _, absent = self.probe(pathlib.Path(directory), listing)
            self.assertEqual(absent, ("apad",))

    def test_a_binary_that_cannot_list_its_filters_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            _, absent = self.probe(pathlib.Path(directory), "", returncode=1)
            self.assertEqual(absent, provisioning.REQUIRED_FILTERS)

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

    def test_a_blackwell_card_gets_an_index_that_carries_its_architecture(self):
        self.assertEqual(self.resolve((12, 0)).torch_index, provisioning.CUDA_WHEEL_INDEX)

    def test_a_card_older_than_turing_keeps_the_legacy_index(self):
        self.assertEqual(
            self.resolve((6, 1)).torch_index, provisioning.LEGACY_CUDA_WHEEL_INDEX
        )

    def test_an_unreadable_capability_takes_the_current_index(self):
        self.assertEqual(self.resolve(None).torch_index, provisioning.CUDA_WHEEL_INDEX)

    def test_cuda_never_leaves_the_wheel_index_to_pypi(self):
        for capability in ((12, 0), (7, 5), (6, 1), None):
            self.assertIsNotNone(self.resolve(capability).torch_index)


class AccelerationTests(unittest.TestCase):
    def test_every_platform_offers_automatic_and_cpu(self):
        keys = [key for key, _ in provisioning.available_accelerations()]
        self.assertEqual(keys[0], provisioning.AUTOMATIC)
        self.assertIn("cpu", keys)

    def test_automatic_resolves_to_a_known_profile(self):
        resolved = provisioning.resolve_acceleration(provisioning.AUTOMATIC)
        self.assertIn(resolved.key, provisioning.ACCELERATIONS)
        self.assertIn(resolved.extra, ("cpu", "gpu", "dml"))

    def test_an_unknown_stored_accelerator_falls_back_to_detection(self):
        self.assertEqual(
            provisioning.resolve_acceleration("from-the-future").key,
            provisioning.resolve_acceleration(provisioning.AUTOMATIC).key,
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


if __name__ == "__main__":
    unittest.main()
