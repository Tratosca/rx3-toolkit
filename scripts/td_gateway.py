#!/usr/bin/env python3
"""RX3 semantic stream to the NXS2 TouchDesigner OSC bus and a local asset API.

This host-only process reads the existing localhost JSON bridge. It never sends
commands to the deck. Large grid/phrase/waveform assets stay in localhost HTTP;
small, validity-labelled control values use bounded OSC frames.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import re
import socket
import struct
import subprocess
import threading
import time
from urllib.parse import urlsplit

from audio_excerpt import decode_url
from remote_metadata import MAX_AUDIO_RANGE, RemoteCatalog
from prodjlink_bridge import load_catalog


def _number(value, default=0.0):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else default


def td_values(snapshot: dict, selected_deck: int) -> dict:
    """Map one canonical RX3 deck to the existing /vj/deckN TD addresses."""
    deck = snapshot["deck_index"]
    prefix = f"/vj/deck{deck}/"
    track = snapshot["track"]
    transport = snapshot["transport"]
    timing = snapshot["timing"]
    phrase = snapshot["phrase"]
    mixer = snapshot["mixer"]
    audio = snapshot["audio"]
    waveform = snapshot.get("waveform") or {}
    active = bool(snapshot["connected"] and transport.get("playing") and timing["valid"])
    preview = int(active and snapshot["player_number"] == selected_deck)
    phase_valid = bool(timing["valid"] and timing.get("beat_phase") is not None)
    grid_valid = bool(track.get("analysis_key") and timing.get("beat_number") is not None)
    phrase_valid = bool(phrase.get("valid"))
    seconds_to_boundary = (phrase.get("beats_to_boundary") * 60 / timing["effective_bpm"]
                           if phrase_valid and timing.get("effective_bpm") else None)
    fields = {
        "analysis/ready": int(grid_valid),
        "analysis/origin": phrase.get("source") or "unavailable",
        "analysis/reason": phrase.get("reason") or "",
        "analysis/fallback_required": int(not grid_valid),
        "track/bpm": _number(track.get("original_bpm")),
        "connected": int(bool(snapshot["connected"])),
        "playing": int(bool(transport.get("playing"))),
        "player": snapshot["player_number"],
        "track_generation": track.get("load_generation") or 0,
        "title": track.get("title") or "",
        "artist": track.get("artist") or "",
        "key": track.get("key") or "",
        "track_key": track.get("track_key") or "",
        "analysis_key": track.get("analysis_key") or "",
        "position_ms": _number(timing.get("position_ms")),
        "position/valid": int(bool(timing["valid"])),
        "bpm": _number(timing.get("effective_bpm")),
        "pitch_ratio": _number(timing.get("pitch_ratio")),
        "beat": _number(timing.get("fractional_beat")),
        "beat_phase": _number(timing.get("beat_phase")),
        "phase/valid": int(phase_valid),
        "beatinbar": timing.get("beat_in_bar") or 0,
        "bar": timing.get("bar_number") or 0,
        "master": int(bool(timing.get("is_master"))),
        "master/valid": int(timing.get("is_master") is not None),
        "sync": int(bool(timing.get("sync_enabled"))),
        "sync/valid": int(timing.get("sync_enabled") is not None),
        "timing/valid": int(bool(timing["valid"])),
        "timing/age_ms": _number(timing.get("age_ms")),
        "timing/discontinuity_id": timing.get("discontinuity_id") or 0,
        "phrase/valid": int(phrase_valid),
        "phrase/index": phrase.get("current_index") or 0,
        "section": phrase.get("section") or "",
        "next_section": phrase.get("next_section") or "",
        "phrase_pos": _number(phrase.get("progress_01")),
        "beats_to_next": _number(phrase.get("beats_to_boundary")),
        "seconds_to_next": _number(seconds_to_boundary),
        "phrase/in_fill": int(bool(phrase.get("in_fill"))),
        "phrase/source": phrase.get("source") or "unavailable",
        "phrase/revision": phrase.get("asset_id") or "",
        "preview/weight": preview,
        "preview/source": "manual_visual_selection",
        "transport/state": transport.get("state") or "unknown",
        "transport/direction": transport.get("direction") or "unknown",
        "loop": int(bool(transport.get("loop_active"))),
        "loop/valid": int(transport.get("loop_active") is not None),
        "on_air": int(bool(mixer.get("on_air"))),
        "on_air/valid": int(bool(mixer.get("on_air_valid"))),
        "fader": _number(mixer.get("fader_01")),
        "fader/valid": int(mixer.get("fader_01") is not None),
        "audibility/weight": 0,
        "audibility/valid": 0,
        "audio/valid": int(bool(audio.get("valid"))),
        "audio/source": audio.get("source") or "unavailable",
        "audio/rms_dbfs": _number(audio.get("rms_dbfs"), -120.0),
        "audio/peak_dbfs": _number(audio.get("peak_dbfs"), -120.0),
        "audio/low": _number(audio.get("low")),
        "audio/mid": _number(audio.get("mid")),
        "audio/high": _number(audio.get("high")),
        "audio/onset": _number(audio.get("onset")),
        "audio/centroid": _number(audio.get("centroid_hz")),
        "waveform/valid": int(bool(waveform.get("valid"))),
        "waveform/intensity": _number(waveform.get("intensity")),
        "waveform/activity": _number(waveform.get("activity")),
        "waveform/accent": _number(waveform.get("accent")),
        "waveform/contrast": _number(waveform.get("contrast")),
        "waveform/source": waveform.get("source") or "unavailable",
        "source": "rx3_usb_b",
    }
    return {prefix + name: value for name, value in fields.items()}


def _osc_string(value):
    # Long titles remain intact in the HTTP asset; a single OSC scalar must
    # fit the TD receiver's UDP budget even with a malformed export string.
    data = str(value).encode("utf-8")[:256]
    data = data.decode("utf-8", "ignore").encode("utf-8") + b"\0"
    return data + b"\0" * (-len(data) % 4)


def osc_bundle(values):
    messages = []
    for address, value in values.items():
        kind = "s" if isinstance(value, str) else "i" if isinstance(value, int) else "f"
        payload = (_osc_string(value) if kind == "s" else struct.pack(">" + kind, value))
        message = _osc_string(address) + _osc_string("," + kind) + payload
        messages.append(struct.pack(">I", len(message)) + message)
    return b"#bundle\0" + struct.pack(">Q", 1) + b"".join(messages)


def osc_frames(snapshot, selected_deck: int, sequence: int, max_bytes=1350):
    header = {"/vj/replay/time": float(snapshot["received_monotonic_ms"] / 1000),
              "/vj/replay/sequence": sequence,
              "/vj/replay/session": snapshot["session_id"]}
    groups, current = [], {}
    overhead = {"/vj/frame/part": 0, "/vj/frame/parts": 99}
    for address, value in td_values(snapshot, selected_deck).items():
        if len(osc_bundle({**header, **overhead, **current, address: value})) > max_bytes and current:
            groups.append(current); current = {}
        if len(osc_bundle({**header, **overhead, address: value})) > max_bytes:
            raise ValueError("OSC field exceeds packet budget")
        current[address] = value
    if current:
        groups.append(current)
    if len(groups) > 32:
        raise ValueError("OSC frame exceeds receiver part budget")
    return [osc_bundle({**header, "/vj/frame/part": i,
                        "/vj/frame/parts": len(groups), **part})
            for i, part in enumerate(groups)]


class Gateway:
    def __init__(self, catalog, selected_deck: int, osc_host: str, osc_port: int):
        self.catalog = catalog
        self.selected_deck = selected_deck
        self.osc_target = (osc_host, osc_port)
        self.osc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.lock = threading.Lock()
        self.decks = {}
        self.samples = {}
        self.sequence = 0
        self.last_update = 0.0

    def publish(self, snapshot, *, upstream=True):
        track_id = snapshot.get("track", {}).get("rekordbox_id")
        if track_id is not None and hasattr(self.catalog, "request"):
            self.catalog.request(track_id)
        with self.lock:
            if (upstream and snapshot.get("track", {}).get("valid") and
                    snapshot.get("timing", {}).get("valid")):
                source_s = snapshot["timing"].get("position_ms")
                source_s = source_s / 1000 if source_s is not None else None
                if source_s is not None:
                    for excerpt in self.samples.get(str(track_id), []):
                        for window in excerpt["windows"]:
                            if window["start_s"] <= source_s < window["end_s"]:
                                snapshot = json.loads(json.dumps(snapshot))
                                snapshot["audio"].update(window)
                                snapshot["audio"].update(
                                    valid=True, source="sampled_source_file_pre_fader",
                                    tap_location="source_file", live_audio=False,
                                    observed_at_ms=None, reason=None)
                                break
                        if snapshot["audio"].get("valid"):
                            break
            self.sequence += 1
            self.decks[snapshot["deck_index"]] = snapshot
            if upstream:
                self.last_update = time.monotonic()
            sequence = self.sequence
        for packet in osc_frames(snapshot, self.selected_deck, sequence):
            self.osc.sendto(packet, self.osc_target)

    def stale(self):
        with self.lock:
            snapshots = list(self.decks.values())
        for snapshot in snapshots:
            stale = json.loads(json.dumps(snapshot))
            stale["connected"] = False
            stale["transport"]["playing"] = False
            stale["timing"]["valid"] = False
            stale["phrase"]["valid"] = False
            stale["audio"]["valid"] = False
            stale["waveform"]["valid"] = False
            self.publish(stale, upstream=False)

    def close(self):
        self.osc.close()
        if hasattr(self.catalog, "close"):
            self.catalog.close()


def handler_for(gateway: Gateway):
    class Handler(BaseHTTPRequestHandler):
        def audio_response(self, track_id: int, *, head=False):
            if not hasattr(gateway.catalog, "audio_stat"):
                self.send_error(404, "remote audio ranges unavailable"); return
            try:
                size = gateway.catalog.audio_stat(track_id)
            except (OSError, ValueError, KeyError):
                self.send_error(503, "audio source unavailable"); return
            if head:
                self.send_response(200)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(size))
                self.end_headers()
                return
            matched = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
            if not matched:
                self.send_error(416, "a single bounded byte range is required"); return
            offset = int(matched.group(1))
            last = int(matched.group(2)) if matched.group(2) else size - 1
            if offset >= size or last < offset:
                self.send_error(416, "range outside audio file"); return
            count = min(last - offset + 1, MAX_AUDIO_RANGE)
            try:
                data, confirmed_size = gateway.catalog.audio_range(track_id, offset, count)
            except (OSError, ValueError, KeyError):
                self.send_error(503, "deck audio range unavailable or budget exhausted")
                return
            if confirmed_size != size:
                self.send_error(503, "audio file changed during range read"); return
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {offset}-{offset + count - 1}/{size}")
            self.send_header("Content-Length", str(count))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_HEAD(self):
            path = urlsplit(self.path).path
            if path.startswith("/audio/") and path[7:].isdigit():
                self.audio_response(int(path[7:]), head=True)
            else:
                self.send_error(404)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith("/audio/") and path[7:].isdigit():
                self.audio_response(int(path[7:])); return
            if path == "/health":
                with gateway.lock:
                    body = {"schema": "rx3-td-gateway/1", "sequence": gateway.sequence,
                            "bridge_age_s": (time.monotonic() - gateway.last_update
                                             if gateway.last_update else None)}
            elif path == "/state":
                with gateway.lock:
                    body = {"schema": "rx3-td-gateway/1", "sequence": gateway.sequence,
                            "decks": [gateway.decks.get(i) for i in (0, 1)]}
            elif path == "/assets":
                body = {"schema": "rx3-assets/1",
                        "media_generation": gateway.catalog.manifest["export_pdb_sha256"],
                        "track_ids": sorted(map(int, gateway.catalog.tracks))}
            elif path.startswith("/assets/") and path[8:].isdigit():
                track_id = path[8:]
                item = gateway.catalog.tracks.get(track_id)
                if item is None:
                    self.send_error(404); return
                if item.get("asset") is None and hasattr(gateway.catalog, "request"):
                    gateway.catalog.request(int(track_id))
                body = {"schema": "rx3-track-asset/1", "track_id": int(track_id),
                        "media_generation": gateway.catalog.manifest["export_pdb_sha256"],
                        "metadata": item["metadata"], "analysis": item.get("asset"),
                        "analysis_error": item.get("analysis_error")}
            elif path.startswith("/samples/") and path[9:].isdigit():
                with gateway.lock:
                    body = {"schema": "rx3-source-samples/1", "track_id": int(path[9:]),
                            "samples": list(gateway.samples.get(path[9:], []))}
            else:
                self.send_error(404); return
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            path = urlsplit(self.path).path
            if not path.startswith("/samples/") or not path[9:].isdigit():
                self.send_error(404); return
            if not hasattr(gateway.catalog, "audio_range"):
                self.send_error(404, "deck audio ranges unavailable"); return
            track_id = path[9:]
            item = gateway.catalog.tracks.get(track_id)
            if item is None:
                self.send_error(404); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 128:
                    raise ValueError("request body exceeds limit")
                request = json.loads(self.rfile.read(length))
                start = float(request["start_s"])
                duration = float(request["duration_s"])
                track_duration = item["metadata"].get("duration_s") or 0
                if (not math.isfinite(start) or not math.isfinite(duration) or
                        not 0 <= start < track_duration or
                        not 0 < duration <= 5 or start + duration > track_duration):
                    raise ValueError("sample must fit the track and five-second limit")
                with gateway.lock:
                    if len(gateway.samples.get(track_id, [])) >= 3:
                        raise ValueError("three-excerpt track limit reached")
                url = f"http://127.0.0.1:{self.server.server_port}/audio/{track_id}"
                result = decode_url(url, start, duration)
            except (ValueError, KeyError, TypeError):
                self.send_error(400, "invalid or over-budget sample request"); return
            except (OSError, subprocess.TimeoutExpired):
                self.send_error(503, "audio excerpt unavailable"); return
            with gateway.lock:
                gateway.samples.setdefault(track_id, []).append(result)
            data = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-host", default="127.0.0.1")
    parser.add_argument("--bridge-port", type=int, default=50130)
    parser.add_argument("--deck-source", help="RX3 USB-B IP for live assets")
    parser.add_argument("--catalog", help="pre-gig cache if deck metadata is unavailable")
    parser.add_argument("--http-port", type=int, default=50132)
    parser.add_argument("--osc-host", default="127.0.0.1")
    parser.add_argument("--osc-port", type=int, default=4470)
    parser.add_argument("--preview-deck", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    if bool(args.deck_source) == bool(args.catalog):
        parser.error("select exactly one of --deck-source or --catalog")
    catalog = (RemoteCatalog(args.deck_source) if args.deck_source else
               type("LocalCatalog", (), {})())
    if args.catalog:
        from pathlib import Path
        catalog.manifest, catalog.tracks = load_catalog(Path(args.catalog))
    gateway = Gateway(catalog, args.preview_deck, args.osc_host, args.osc_port)
    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), handler_for(gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(json.dumps({"http": f"http://127.0.0.1:{args.http_port}",
                      "osc": f"{args.osc_host}:{args.osc_port}",
                      "bridge": f"{args.bridge_host}:{args.bridge_port}"}), flush=True)
    try:
        while True:
            try:
                with socket.create_connection((args.bridge_host, args.bridge_port), timeout=3) as sock:
                    sock.settimeout(5)
                    for line in sock.makefile("r", encoding="utf-8"):
                        gateway.publish(json.loads(line))
            except (OSError, ValueError, json.JSONDecodeError):
                gateway.stale()
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        gateway.stale()
        server.shutdown(); server.server_close()
        gateway.close()


if __name__ == "__main__":
    main()
