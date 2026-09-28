# SPDX-License-Identifier: MPL-2.0
"""Additional compatibility files cannot replace the native RX3 output."""
import dataclasses
import os
from pathlib import Path
import tempfile
import sys
import shutil
import hashlib
import unittest
from unittest.mock import Mock, patch

from app.localization import LocalizedError
from app.stems import overcue_option, rekordbox
from app.stems.overcue_exact import NativePreparation, bundled_coefficients, COEFFICIENT_SHA256


class OvercueOptionTests(unittest.TestCase):
    def test_estimate_counts_unique_tracks_and_marks_unknown_duration(self):
        track = rekordbox.Track('1', 'Track', '', 30, Path('/track.wav'), True)
        self.assertEqual(overcue_option.estimate([track, track]), {'bytes': 75_000_000, 'unknown': 0})
        unknown = dataclasses.replace(track, track_id='2', location=Path('/unknown.wav'), duration=0)
        self.assertEqual(overcue_option.estimate([track, unknown]), {'bytes': 75_000_000, 'unknown': 1})

    def test_missing_helper_cannot_silently_use_approximate_export(self):
        with patch.dict(os.environ, {'RX3_OVERCUE_HELPER':'/nonexistent/rx3-overcue-audio'}, clear=True):
            self.assertFalse(overcue_option.status()['ready'])
            with self.assertRaises(LocalizedError): overcue_option.native()

    def test_bundled_table_needs_no_local_profile_setting(self):
        with patch.dict(os.environ, {'RX3_OVERCUE_HELPER':sys.executable}, clear=True):
            prepared = overcue_option.native()
        raw = prepared.coefficients.read_bytes()
        self.assertEqual(len(raw), 320 * 59 * 4)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), COEFFICIENT_SHA256)

    def test_frozen_table_is_resolved_and_corruption_is_refused(self):
        reference = bundled_coefficients()
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory)/'stems/overcue-44100-96000.f32'
            table.parent.mkdir()
            shutil.copyfile(reference, table)
            with patch.object(sys, '_MEIPASS', directory, create=True):
                self.assertEqual(NativePreparation(sys.executable).coefficients, table.resolve())
                raw = bytearray(table.read_bytes()); raw[100] ^= 1; table.write_bytes(raw)
                with self.assertRaises(ValueError): NativePreparation(sys.executable)
                table.unlink()
                with self.assertRaises(FileNotFoundError): NativePreparation(sys.executable)

    def test_destination_library_id_wins_over_xml_id_and_external_tracks_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'track.wav'; source.touch()
            track = rekordbox.Track('99', 'Track', '', 30, source, True)
            local = dataclasses.replace(track, track_id='17')
            library = rekordbox.Collection(root/'export.pdb', 1, (rekordbox.Playlist('1','List','List',(local,)),))
            with patch.object(overcue_option,'native',return_value=Mock()), \
                 patch.object(rekordbox,'has_export',return_value=True), \
                 patch.object(rekordbox,'parse_drive',return_value=library):
                export = overcue_option.Export(root, [track])
                self.assertEqual(export.entries[source], ('/track.wav', '17'))
                for other in (dataclasses.replace(track,location=root.parent/'outside.wav'),
                              dataclasses.replace(track,location=root/'missing.wav')):
                    with self.assertRaises(LocalizedError): overcue_option.Export(root,[other])


if __name__ == '__main__':
    unittest.main()
