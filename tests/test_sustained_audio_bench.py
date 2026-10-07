"""Safety gates for selecting and pacing live-deck audio bench reads."""
import json
from pathlib import Path
import sqlite3
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sustained_audio_bench import live_state, playing_tracks, ranges, RANGE_BYTES


class SustainedAudioBenchTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, wall_ns INTEGER, "
                        "event TEXT, source TEXT, payload TEXT)")

    def tearDown(self):
        self.db.close()

    def emit(self, event, source="169.254.1.2", age_ns=0, tracks=(31, 42)):
        packet = {"raw": {"decks": [
            {"deck": 1, "loaded": True, "playModeRaw": 2, "trackId": tracks[0]},
            {"deck": 2, "loaded": True, "playModeRaw": 2, "trackId": tracks[1]},
        ]}}
        self.db.execute("INSERT INTO events(wall_ns,event,source,payload) VALUES (?,?,?,?)",
                        (time.time_ns()-age_ns, event, source, json.dumps(packet)))

    def test_current_tracks_come_from_packets(self):
        self.emit("now-playing", tracks=(77, 88))
        self.emit("position-diagnostic", tracks=(77, 88))
        source, decks = live_state(self.db)
        self.assertEqual(source, "169.254.1.2")
        self.assertEqual(playing_tracks(decks), {1: 77, 2: 88})

    def test_stale_or_mixed_source_stops_before_a_read(self):
        self.emit("now-playing", age_ns=3_000_000_000)
        self.emit("position-diagnostic")
        with self.assertRaisesRegex(RuntimeError, "stale"):
            live_state(self.db)
        self.db.execute("DELETE FROM events")
        self.emit("now-playing")
        self.emit("position-diagnostic", source="169.254.1.3")
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            live_state(self.db)

    def test_two_songs_are_interleaved_in_bounded_ranges(self):
        result = list(ranges({31: RANGE_BYTES + 1, 42: RANGE_BYTES + 2}))
        self.assertEqual(result, [(31, 0, RANGE_BYTES), (42, 0, RANGE_BYTES),
                                  (31, RANGE_BYTES, 1), (42, RANGE_BYTES, 2)])


if __name__ == "__main__":
    unittest.main()
