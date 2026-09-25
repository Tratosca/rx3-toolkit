# SPDX-License-Identifier: MPL-2.0
import dataclasses
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from app.rx3_stems import cache, job, provisioning, rekordbox, safety, separation, stem


class CacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        for patcher in (patch.dict(os.environ, {"RX3_STEM_STUDIO_HOME": str(self.root / "data")}),
                        patch.object(safety, "library_busy", return_value=False),
                        patch.object(cache, "mounted_roots", return_value=())):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.source = self.root / "track.wav"
        self.source.write_bytes(b"one source")
        self.runtime = provisioning.detect()

    def make_job(self, drive, settings=None):
        track = rekordbox.Track("1", "Track", "Artist", 1, self.source, True)
        playlist = rekordbox.Playlist("1", "List", "List", (track,))
        collection = rekordbox.Collection(self.root / "library.xml", 1, (playlist,))
        return job.StemJob(self.runtime, collection, playlist, self.root / drive, settings=settings)

    def encode(self, source, target, **kwargs):
        target.write_bytes(stem.HEADER.pack(stem.MAGIC, 44100, 2, 2, 64, 16, b"\0" * 32) + b"\1\0" * 32)
        return stem.StemResult(target, 16, 16 / 44100, 64, gain=1.1, delay=37)

    def prepare(self, drive="first", settings=None):
        current = self.make_job(drive, settings)
        with patch.object(current, "_separate", return_value={"vocals": self.source}) as separate, \
             patch.object(job, "write_stem", side_effect=self.encode):
            state = current.run()
        self.assertEqual(state.state, "done", state.fatal)
        self.assertEqual(state.errors, ())
        return state, separate.call_count

    def test_second_drive_and_renamed_source_reuse_final_audio(self):
        first, calls = self.prepare()
        self.assertEqual(calls, 1)
        self.source = self.source.rename(self.root / "renamed.wav")
        second, calls = self.prepare("second")
        self.assertEqual(calls, 0)
        self.assertEqual(second.results[0].status, "reused")
        self.assertEqual(second.results[0].delay, 37)
        self.assertEqual(second.results[0].gain, 1.1)
        self.assertEqual((first.output / first.results[0].stem).read_bytes(),
                         (second.output / second.results[0].stem).read_bytes())

    def test_changed_content_with_same_size_and_name_regenerates(self):
        self.prepare()
        before = self.source.stat()
        self.source.write_bytes(b"two source")
        os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
        result, calls = self.prepare()
        self.assertEqual(calls, 1)
        self.assertEqual(result.results[0].source_sha256, safety.digest(self.source))
        self.assertTrue(any(getattr(n, "key", "") == "stems.regenerating" for n in result.notices))

    def test_settings_change_never_reuses_audio(self):
        self.prepare()
        state, calls = self.prepare(settings=dataclasses.replace(separation.Settings(), model="different-model"))
        self.assertEqual(calls, 1)
        self.assertEqual(state.results[0].status, "created")

    def test_old_manifest_is_read_without_inventing_a_source_hash(self):
        drive = self.root / "first"
        output = drive / "RX3_STEMS"
        output.mkdir(parents=True)
        target = output / "track.rx3stem"
        self.encode(None, target)
        old = {"format": 1, "tracks": [{"stem": target.name, "trackId": "1"}]}
        (drive / safety.MANIFEST_NAME).write_text(json.dumps(old))
        state, calls = self.prepare()
        self.assertEqual(calls, 0)
        self.assertIsNone(state.results[0].source_sha256)
        self.assertEqual(json.loads(state.manifest.read_text())["format"], 2)
        self.assertEqual(json.loads((drive / safety.MANIFEST_NAME).read_text()), old)

    def test_other_mounted_drive_is_used_after_cache_clear(self):
        self.prepare()
        cache.configure(clear=True)
        with patch.object(cache, "mounted_roots", return_value=(self.root / "first",)):
            state, calls = self.prepare("second")
        self.assertEqual(calls, 0)
        self.assertEqual(state.results[0].status, "reused")

    def test_corrupt_cached_audio_is_not_used(self):
        self.prepare()
        cached = next(cache.root().glob("*/*.rx3stem"))
        content = cached.read_bytes()
        cached.write_bytes(content[:-1] + b"\x7f")
        _, calls = self.prepare("second")
        self.assertEqual(calls, 1)

    def test_cache_limit_evicts_oldest_and_clear_removes_entries(self):
        self.prepare()
        oldest = cache.directories()[0]
        os.utime(oldest, ns=(1, 1))
        self.source.write_bytes(b"another source")
        self.prepare("second")
        newest = next(p for p in cache.directories() if p != oldest)
        cache.configure(cache.size(newest))
        self.assertFalse(oldest.exists())
        self.assertTrue(newest.exists())
        cache.configure(clear=True)
        self.assertFalse(cache.directories())

    def test_bass_preparation_includes_the_drums_prerequisite(self):
        current = self.make_job("first")
        with_bass = job.StemJob(self.runtime, current.collection, current.playlist,
                               current.output_root, roles=("bass",))
        self.assertEqual(with_bass.roles, ("vocals", "drums", "bass"))

    def test_manifest_paths_cannot_escape_the_stems_directory(self):
        state, _ = self.prepare()
        entry = state.results[0].as_manifest_entry()
        entry["stems"][0]["file"] = "../track.wav"
        self.assertIsNone(cache.verified_files(state.output, entry, ("vocals",)))
