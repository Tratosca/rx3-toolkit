#!/usr/bin/env python3
"""RX3 USB-B packets to Pro DJ Link semantic-contract JSON lines over TCP.

The bridge listens to the already-tested Now Playing and position UDP streams.
It never sends commands to the deck. Only the configured, scanned single USB
export can be resolved to metadata; the RX3 packets do not identify a media
slot, so a second mounted music USB makes this association unproven.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import json
from pathlib import Path
import selectors
import socket
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from position_diagnostic import validate as validate_position  # noqa: E402
from telemetry_diagnostic import validate as validate_now_playing  # noqa: E402


FAST_STALE_S = 0.5
TRACK_STALE_S = 3.0
SOURCE_FRAMES_PER_SECOND = 44100.0  # physical test: 44.1-kHz track, RX3 1.19


def load_catalog(path: Path) -> tuple[dict, dict]:
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest.get("schema") != "rx3-pre-gig/1":
        raise ValueError("unsupported pre-gig catalog")
    tracks = json.loads((path / "tracks.json").read_text())
    for track_id, track in tracks.items():
        rel = track.get("analysis")
        if rel:
            asset = (path / rel).resolve()
            if not asset.is_relative_to(path.resolve()) or not asset.is_file():
                raise ValueError("analysis asset escapes catalog")
            track["asset"] = json.loads(asset.read_text())
            if str(track["asset"].get("track_id")) != track_id:
                raise ValueError("analysis asset belongs to another track")
            if track["asset"].get("export_pdb_sha256") != manifest["export_pdb_sha256"]:
                raise ValueError("analysis asset belongs to another export")
    return manifest, tracks


def asset_key(asset: dict) -> str:
    """Invalidate a cached analysis when either grid or phrase file changes."""
    return f"{asset.get('dat_sha256')}:{asset.get('ext_sha256') or '-'}"


def musical_position(asset: dict, position_ms: float) -> tuple[dict, dict]:
    """Use the actual exported beat times, including variable-tempo grids."""
    grid = asset.get("grid") or []
    timing = {"beat_number": None, "beat_phase": None,
              "fractional_beat": None, "beat_in_bar": None}
    phrase = {"valid": False, "source": "local_analysis", "reason": "no_phrase_at_position",
              "current_index": None, "section": None, "next_section": None,
              "progress_01": None, "beats_to_boundary": None,
              "asset_id": asset_key(asset)}
    if not grid:
        phrase["reason"] = "missing_grid"
        return timing, phrase
    times = [entry["time_ms"] for entry in grid]
    index = bisect_right(times, position_ms) - 1
    if index < 0 or index >= len(grid):
        phrase["reason"] = "outside_grid"
        return timing, phrase
    current = grid[index]
    if index + 1 < len(grid):
        span = times[index + 1] - times[index]
        phase = (position_ms - times[index]) / span if span > 0 else None
    else:
        # There is no measured following beat from which to derive phase.
        phase = None
    beat = float(current["beat"]) + phase if phase is not None else None
    timing.update(beat_number=current["beat"], beat_phase=phase,
                  fractional_beat=beat,
                  beat_in_bar=current["count_in_bar"])
    entries = asset.get("phrases") or []
    if asset.get("phrase_status") != "ready":
        phrase["reason"] = asset.get("phrase_status", "missing_phrases")
        return timing, phrase
    if beat is None:
        phrase["reason"] = "beat_phase_unavailable"
        return timing, phrase
    starts = [entry["beat"] for entry in entries]
    phrase_index = bisect_right(starts, beat) - 1
    if phrase_index < 0:
        phrase["reason"] = "before_first_phrase"
        return timing, phrase
    current_phrase = entries[phrase_index]
    end = current_phrase["end_beat"]
    if not current_phrase["beat"] <= beat < end:
        phrase["reason"] = "after_phrase_boundary"
        return timing, phrase
    remaining = end - beat
    phrase.update(valid=True, reason=None,
                  current_index=current_phrase["index"],
                  section=current_phrase["label"],
                  next_section=(entries[phrase_index + 1]["label"]
                                if phrase_index + 1 < len(entries) else None),
                  progress_01=(beat-current_phrase["beat"]) /
                              (end-current_phrase["beat"]),
                  beats_to_boundary=remaining)
    return timing, phrase


class BridgeState:
    def __init__(self, manifest: dict, tracks: dict, firmware: str,
                 remote_metadata: bool = False):
        self.manifest = manifest
        self.tracks = tracks
        self.firmware = firmware
        self.remote_metadata = remote_metadata
        self.session_id = str(uuid.uuid4())
        self.sequence = 0
        self.peer = None
        self.waveform_cache = {}
        self.decks = {number: {"now": None, "now_at": None, "position": None,
                               "position_at": None, "track_id": None,
                               "load_generation": 0, "reader_generation": None,
                               "required_new_reader": None,
                               "last_raw_position": None, "discontinuity_id": 0}
                      for number in (1, 2)}

    def ingest(self, kind: str, data: bytes, peer: str, now: float) -> bool:
        if self.peer is not None and peer != self.peer:
            return False
        decoded = validate_now_playing(data) if kind == "now-playing" else validate_position(data)
        if decoded is None:
            return False
        self.peer = peer
        for packet in decoded["decks"]:
            state = self.decks[packet["deck"]]
            if kind == "now-playing":
                track_id = packet["trackId"] if packet["loaded"] else None
                if track_id != state["track_id"]:
                    state["load_generation"] += 1
                    state["discontinuity_id"] += 1
                    state["required_new_reader"] = (state["reader_generation"]
                                                    if state["reader_generation"] is not None
                                                    else state["required_new_reader"])
                    state["reader_generation"] = None
                    state["last_raw_position"] = None
                    state["track_id"] = track_id
                state["now"], state["now_at"] = packet, now
            else:
                generation = packet["readerGeneration"]
                sample = packet["sample"]
                if (state["reader_generation"] is not None and
                        generation != state["reader_generation"]):
                    state["load_generation"] += 1  # same-track reload or new reader
                    state["discontinuity_id"] += 1
                    state["reader_generation"] = None
                    state["last_raw_position"] = None
                if (sample and state["track_id"] is not None and
                        (state["required_new_reader"] is None or
                         generation != state["required_new_reader"])):
                    previous = state["last_raw_position"]
                    if (previous is not None and
                            (sample["rawPosition"]-previous < -10000 or
                             sample["rawPosition"]-previous > 44100)):
                        state["discontinuity_id"] += 1
                    state["last_raw_position"] = sample["rawPosition"]
                    state["reader_generation"] = generation
                    state["required_new_reader"] = None
                state["position"], state["position_at"] = packet, now
        return True

    def snapshot(self, deck: int, now: float) -> dict:
        state = self.decks[deck]
        raw = state["now"]
        observed = state["now_at"]
        position = state["position"]
        pos_at = state["position_at"]
        now_fresh = raw is not None and now-observed <= TRACK_STALE_S
        pos_fresh = position is not None and now-pos_at <= FAST_STALE_S
        track_id = state["track_id"] if now_fresh else None
        catalog = self.tracks.get(str(track_id)) if track_id is not None else None
        asset = catalog.get("asset") if catalog else None
        metadata = catalog.get("metadata", {}) if catalog else {}
        sample = position["sample"] if position else None
        associated = (now_fresh and pos_fresh and sample is not None and
                      state["reader_generation"] == sample["generation"] and
                      track_id is not None)
        position_ms = (sample["rawPosition"] * 1000.0 / SOURCE_FRAMES_PER_SECOND
                       if associated and sample["rawPosition"] >= 0 else None)
        timing_valid = position_ms is not None
        musical = {"beat_number": None, "beat_phase": None,
                   "fractional_beat": None, "beat_in_bar": None}
        phrase = {"valid": False, "source": "local_analysis", "reason": "no_matching_analysis",
                  "current_index": None, "section": None, "next_section": None,
                  "progress_01": None, "beats_to_boundary": None, "asset_id": None}
        if timing_valid and asset:
            musical, phrase = musical_position(asset, position_ms)
            if self.remote_metadata:
                phrase["source"] = "deck_usb_rekordbox_analysis"
        elif catalog and catalog.get("analysis_error"):
            phrase["reason"] = "analysis_fetch_failed"
        elif not timing_valid:
            phrase["reason"] = "position_unavailable"
        original_bpm = (asset["grid"][0]["bpm_x100"] / 100
                        if asset and asset.get("grid") else None)
        waveform = {"valid": False, "source": "rekordbox_pwv5",
                    "observed_at_ms": int(pos_at*1000) if pos_at else None,
                    "reason": "waveform_or_position_unavailable", "style": None,
                    "intensity": None, "activity": None, "accent": None,
                    "contrast": None, "rgb_display": None, "bands": None}
        if timing_valid and asset and asset.get("waveform"):
            key = asset_key(asset)
            if key not in self.waveform_cache:
                from waveform_motion import WaveformMotion
                try:
                    self.waveform_cache[key] = WaveformMotion(asset["waveform"])
                except (ValueError, KeyError, TypeError):
                    self.waveform_cache[key] = None
            decoded = self.waveform_cache[key]
            if decoded is not None:
                waveform.update(decoded.at(position_ms))
        effective_bpm = raw["bpmX100"] / 100 if now_fresh and raw["bpmX100"] > 0 else None
        self.sequence += 1
        source = self.manifest["export_pdb_sha256"]
        return {
            "schema_version": "1.0", "session_id": self.session_id,
            "sequence": self.sequence, "received_monotonic_ms": int(now * 1000),
            "device_id": f"rx3-usb-b:{self.peer or 'unseen'}", "player_number": deck,
            "deck_index": deck-1, "model": "XDJ-RX3", "firmware": self.firmware,
            "connected": bool(now_fresh and pos_fresh),
            "capabilities": {"position": "rx3_reader_frames_44k1_provisional",
                             "track_identity": ("deck_usb_export_unverified_slot"
                                                if self.remote_metadata else
                                                "configured_single_export"),
                             "media_slot_verified": False,
                             "phrase": (("deck_usb_rekordbox_pssi" if self.remote_metadata
                                         else "cached_rekordbox_pssi") if asset else "unavailable")},
            "track": {"valid": bool(now_fresh and track_id is not None and catalog),
                      "source": ("deck_usb_export_pdb" if self.remote_metadata
                                 else "local_export_pdb"), "observed_at_ms":
                      int(observed * 1000) if observed else None,
                      "reason": None if catalog and now_fresh else "unmatched_or_stale_track",
                      "load_generation": state["load_generation"],
                      "source_player": None, "source_slot": None,
                      "rekordbox_id": track_id, "media_generation": source,
                      "track_key": f"{source}:{track_id}" if catalog and now_fresh else None,
                      "analysis_key": asset_key(asset) if asset else None,
                      "title": metadata.get("title"), "artist": metadata.get("artist"),
                      "key": metadata.get("key"), "duration_ms": metadata.get("duration_s", 0)*1000 or None,
                      "original_bpm": original_bpm},
            "transport": {"valid": bool(now_fresh), "source": "rx3_now_playing",
                          "observed_at_ms": int(observed * 1000) if observed else None,
                          "reason": None if now_fresh else "stale_now_playing",
                          "state": ({2: "playing", 3: "playing", 4: "paused"}
                                    .get(raw["playModeRaw"], "unknown") if now_fresh else "unknown"),
                          "playing": (raw["playModeRaw"] in (2, 3)
                                      if now_fresh and raw["playModeRaw"] in (2, 3, 4) else None),
                          "direction": "unknown", "loop_active":
                          True if now_fresh and raw["playModeRaw"] == 3 else None,
                          "loop_start_ms": None, "loop_end_ms": None},
            "timing": {"valid": timing_valid, "source": "rx3_usb_b_position",
                       "observed_at_ms": int(pos_at * 1000) if pos_at else None,
                       "reason": None if timing_valid else "stale_or_unassociated_position",
                       "position_ms": position_ms,
                       "position_method": "rx3_source_frame_44k1_provisional",
                       "effective_bpm": effective_bpm,
                       "pitch_ratio": (effective_bpm/original_bpm if effective_bpm and original_bpm else None),
                       **musical, "bar_number": None, "is_master": None,
                       "sync_enabled": None,
                       "discontinuity_id": state["discontinuity_id"]},
            "phrase": {**phrase, "observed_at_ms": int(pos_at*1000) if pos_at else None},
            "mixer": {"valid": False, "source": "rx3_now_playing",
                      "observed_at_ms": int(observed*1000) if observed else None,
                      "reason": "continuous_mixer_state_unavailable",
                      "on_air": raw["onAir"] if now_fresh else None,
                      "on_air_valid": bool(now_fresh), "fader_01": None,
                      "crossfader_01": None, "eq_low": None, "eq_mid": None,
                      "eq_high": None},
            "audio": {"valid": False, "source": None, "observed_at_ms": None,
                      "reason": "live_audio_levels_unavailable",
                      "rms_dbfs": None, "peak_dbfs": None},
            "waveform": waveform,
            "rx3_raw": {"play_mode": raw["playModeRaw"] if now_fresh else None,
                        "tempo": raw["tempoRaw"] if now_fresh else None,
                        "reader_generation": position["readerGeneration"] if position else None},
        }


def serve(catalog: Path | None, firmware: str, host: str, port: int,
          now_port: int = 50123, position_port: int = 50124,
          source: str | None = None, deck_metadata: bool = False,
          metadata_port: int = 50131) -> None:
    remote = None
    if deck_metadata:
        if not source:
            raise ValueError("--deck-metadata requires exact --source IP")
        from remote_metadata import RemoteCatalog
        remote = RemoteCatalog(source, metadata_port)
        manifest, tracks = remote.manifest, remote.tracks
    else:
        if catalog is None:
            raise ValueError("--catalog or --deck-metadata is required")
        manifest, tracks = load_catalog(catalog)
    state = BridgeState(manifest, tracks, firmware, remote_metadata=deck_metadata)
    clients: set[socket.socket] = set()
    with selectors.DefaultSelector() as selector, socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port)); server.listen(); server.setblocking(False)
        selector.register(server, selectors.EVENT_READ, "server")
        for udp_port, kind in ((now_port, "now-playing"),
                               (position_port, "position-diagnostic")):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("", udp_port)); sock.setblocking(False)
            selector.register(sock, selectors.EVENT_READ, kind)
        print(json.dumps({"listening": f"tcp://{host}:{port}",
                          "rx3_udp": [now_port, position_port],
                          "catalog_tracks": len(tracks)}), flush=True)
        last_emit = 0.0
        try:
            while True:
                for key, _ in selector.select(0.05):
                    kind = key.data
                    if kind == "server":
                        client, _ = server.accept(); client.setblocking(False)
                        clients.add(client)
                        continue
                    data, addr = key.fileobj.recvfrom(4097)
                    if (addr[0] != source if source else
                            not addr[0].startswith("169.254.")):
                        continue
                    accepted = state.ingest(kind, data, addr[0], time.monotonic())
                    if accepted and remote and kind == "now-playing":
                        for deck_state in state.decks.values():
                            remote.request(deck_state["track_id"])
                now = time.monotonic()
                if now-last_emit < 0.05:
                    continue
                last_emit = now
                for deck in (1, 2):
                    line = (json.dumps(state.snapshot(deck, now), separators=(",", ":"),
                                       ensure_ascii=False) + "\n").encode("utf-8")
                    for client in list(clients):
                        try:
                            if client.send(line) != len(line):
                                raise BlockingIOError("slow client")
                        except (OSError, BlockingIOError):
                            clients.remove(client); client.close()
        finally:
            for client in clients:
                client.close()
            if remote:
                remote.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--catalog", type=Path)
    source_group.add_argument("--deck-metadata", action="store_true",
                              help="Fetch the mounted USB's PDB/ANLZ over RX3 USB-B")
    parser.add_argument("--firmware", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50130)
    parser.add_argument("--now-port", type=int, default=50123)
    parser.add_argument("--position-port", type=int, default=50124)
    parser.add_argument("--source", help="Exact RX3 USB IPv4; default accepts link-local")
    parser.add_argument("--metadata-port", type=int, default=50131)
    args = parser.parse_args()
    try:
        serve(args.catalog, args.firmware, args.host, args.port,
              args.now_port, args.position_port, args.source,
              args.deck_metadata, args.metadata_port)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"RX3 bridge: {exc}\n")


if __name__ == "__main__":
    main()
