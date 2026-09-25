# SPDX-License-Identifier: MPL-2.0
"""A failed preparation must not publish a damaged file to a drive."""
import dataclasses
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from app.localization import LocalizedError, wire
from app.rx3_stems import safety, job, provisioning, rekordbox, stem


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = pathlib.Path(self.workspace.name)
        self.output = self.root / "RX3_STEMS"
        self.output.mkdir()
        self.source = self.root / "track.wav"
        self.source.write_bytes(b"source")
        track = rekordbox.Track("1", "Track", "Artist", 60, self.source, True)
        playlist = rekordbox.Playlist("1", "List", "List", (track, dataclasses.replace(track, track_id="2")))
        collection = rekordbox.Collection(self.root / "library.xml", 2, (playlist,))
        self.job = job.StemJob(provisioning.detect(), collection, playlist, self.root)
        closed = patch.object(safety, "require_library_closed")
        closed.start()
        self.addCleanup(closed.stop)

    def encode(self, source, target, **kwargs):
        target.write_bytes(b"encoded" * 100)
        return stem.StemResult(target, 175, 175 / 44100, 700)

    def test_full_drive_stops_before_any_separation(self):
        with patch.object(safety.shutil, "disk_usage", return_value=type("Usage", (), {"free": 1})()), \
             patch.object(self.job, "_separate") as separate:
            state = self.job.run()
        self.assertEqual(state.state, "failed")
        self.assertEqual(len(state.errors), 1)
        self.assertEqual(wire(state.fatal)["key"], "stems.space")
        separate.assert_not_called()
        self.assertEqual(state.as_dict()["errors"][0]["track"], "Artist — Track")

    def test_corrupt_readback_keeps_old_file_and_removes_partial(self):
        local = self.root / "local"
        local.write_bytes(b"new")
        target = self.output / "track.rx3stem"
        target.write_bytes(b"old")
        digest = safety.digest
        with patch.object(safety, "digest", side_effect=lambda path: "corrupt" if path.suffix == ".partial" else digest(path)):
            with self.assertRaises(LocalizedError):
                safety.publish(local, target)
        self.assertEqual(target.read_bytes(), b"old")
        self.assertFalse(list(self.output.glob("*.partial")))

    def test_metadata_cleanup_stays_in_our_directory_and_names(self):
        owned = ("._track.rx3stem", "._track.rx3drums", "._track.rx3bass", "._" + safety.MANIFEST_NAME)
        for name in (*owned, "._notes.txt", "notes.txt"):
            (self.output / name).write_bytes(b"user")
        outside = self.root / "._track.rx3stem"
        outside.write_bytes(b"outside")
        safety.clean_metadata(self.output)
        self.assertTrue(outside.exists())
        for name in owned:
            self.assertFalse((self.output / name).exists())
        self.assertEqual((self.output / "._notes.txt").read_bytes(), b"user")
        self.assertEqual((self.output / "notes.txt").read_bytes(), b"user")

    def test_changed_source_never_reaches_the_drive(self):
        self.job.playlist = dataclasses.replace(self.job.playlist, tracks=self.job.playlist.tracks[:1])
        def separate(*args):
            self.source.write_bytes(b"changed")
            return {"vocals": self.source}
        with patch.object(self.job, "_separate", side_effect=separate), patch.object(job, "write_stem", side_effect=self.encode):
            state = self.job.run()
        self.assertEqual(len(state.errors), 1)
        self.assertEqual(wire(state.errors[0].error)["key"], "stems.sourceChanged")
        self.assertFalse((self.output / "track.rx3stem").exists())
        self.assertFalse(list(self.output.glob("*.partial")))

    def test_symlinks_never_redirect_a_write(self):
        target = self.output / "track.rx3stem"
        target.symlink_to(self.source)
        with self.assertRaises(LocalizedError):
            safety.publish(self.source, target)
        self.assertEqual(self.source.read_bytes(), b"source")
        target.unlink()
        self.output.rmdir()
        self.output.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.job.run().state, "failed")
        self.assertEqual(self.source.read_bytes(), b"source")

    def test_manifest_is_published_inside_stems_only(self):
        with patch.object(self.job, "_separate", return_value={"vocals": self.source}), \
             patch.object(job, "write_stem", side_effect=self.encode):
            state = self.job.run()
        self.assertEqual(state.errors, ())
        self.assertEqual(state.manifest, self.output / safety.MANIFEST_NAME)
        self.assertFalse((self.root / safety.MANIFEST_NAME).exists())

    def test_process_query_and_library_refusal(self):
        with patch.object(safety.sys, "platform", "darwin"), patch.object(safety.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(safety.library_busy())
            run.return_value.returncode = 1
            self.assertFalse(safety.library_busy())
            run.return_value.returncode = 2
            with self.assertRaises(LocalizedError):
                safety.library_busy()
        with patch.object(safety.sys, "platform", "win32"), patch.object(safety.subprocess, "run") as run:
            run.return_value.stdout = '"rekordbox.exe","123"\n'
            self.assertTrue(safety.library_busy())
        with patch.object(safety, "require_library_closed", side_effect=LocalizedError("stems.libraryBusy")), \
             patch.object(rekordbox.ET, "parse") as parse:
            with self.assertRaises(LocalizedError):
                rekordbox.parse_collection(self.root / "missing.xml")
            parse.assert_not_called()
            self.assertEqual(self.job.run().state, "failed")
