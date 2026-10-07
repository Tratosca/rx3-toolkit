#!/usr/bin/env python3
"""Bench-only, paced RX3 USB-B file reads: one playing song, then both.

Run --phase one first. Inspect playback and its JSON report before running
--phase both. Each phase selects currently playing tracks from live telemetry;
the second includes the first track and interleaves the other deck's song.
Files and reports stay in the ignored host output directory. No deck command
or write is sent, and this script never increases the deck helper's rate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from remote_metadata import MAX_AUDIO_RANGE, RemoteCatalog

BENCH_BUDGET = 128 * 1024 * 1024
BENCH_RESERVE = 4 * 1024 * 1024
STALE_NS = 2_000_000_000
PLAYING = (2, 3)
RATE_STAGES_MBPS = (8, 16, 32, 50)
RANGE_BYTES = 64 * 1024


def live_state(db: sqlite3.Connection, source: str | None = None) -> tuple[str, dict]:
    rows = db.execute("SELECT wall_ns,event,source,payload FROM events "
                      "ORDER BY id DESC LIMIT 100").fetchall()
    latest = {}
    for wall_ns, event, peer, payload in rows:
        if event in ("now-playing", "position-diagnostic") and event not in latest:
            latest[event] = (wall_ns, peer, payload)
    if set(latest) != {"now-playing", "position-diagnostic"}:
        raise RuntimeError("both live telemetry feeds are required")
    now = time.time_ns()
    if any(now - entry[0] > STALE_NS or entry[0] > now + STALE_NS
           for entry in latest.values()):
        raise RuntimeError("deck telemetry is stale; stopped before next range")
    peers = {entry[1] for entry in latest.values()}
    if len(peers) != 1 or (source is not None and source not in peers):
        raise RuntimeError("telemetry source changed")
    peer = next(iter(peers))
    packet = json.loads(latest["now-playing"][2])["raw"]
    decks = {int(deck["deck"]): deck for deck in packet["decks"]}
    return peer, decks


def playing_tracks(decks: dict) -> dict[int, int]:
    return {deck: int(row["trackId"]) for deck, row in decks.items()
            if row.get("loaded") and row.get("playModeRaw") in PLAYING and
            isinstance(row.get("trackId"), int) and row["trackId"] > 0}


def gaps(db: sqlite3.Connection, start_ns: int) -> dict:
    result = {}
    for event in ("now-playing", "position-diagnostic"):
        rows = db.execute("SELECT wall_ns FROM events WHERE wall_ns >= ? AND "
                          "event = ? ORDER BY wall_ns", (start_ns, event)).fetchall()
        values = [row[0] for row in rows]
        result[event] = {"packets": len(values),
                         "max_gap_ms": (round(max((b-a for a, b in zip(values, values[1:])),
                                               default=0) / 1e6, 1))}
    return result


def ranges(sizes: dict[int, int], start_offsets: dict[int, int] | None = None):
    offsets = dict(start_offsets) if start_offsets is not None else {
        track_id: 0 for track_id in sizes}
    while any(offsets[track_id] < size for track_id, size in sizes.items()):
        for track_id, size in sizes.items():
            offset = offsets[track_id]
            if offset >= size:
                continue
            count = min(MAX_AUDIO_RANGE, RANGE_BYTES, size - offset)
            yield track_id, offset, count
            offsets[track_id] += count


def run(phase: str, db_path: Path, output: Path, resume: bool = False) -> dict:
    if resume and phase != "both":
        raise ValueError("only the interrupted two-song phase can resume")
    output = output.resolve()
    if str(output).startswith("/Volumes/"):
        raise ValueError("bench output must stay on the computer, not a USB drive")
    output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=2)
    catalog = None
    try:
        source, decks = live_state(db)
        active = playing_tracks(decks)
        if not active:
            raise RuntimeError("no playing track was observed")
        plan_path = output / "phase-one.json"
        previous = json.loads(plan_path.read_text()) if phase == "both" else None
        report_path = output / f"phase-{phase}.json"
        interrupted = json.loads(report_path.read_text()) if resume else None
        if interrupted and (interrupted.get("status") != "stopped" or
                            "export changed" not in interrupted.get("error", "")):
            raise RuntimeError("only an export-identity stop can resume automatically")
        if phase == "both":
            if not previous or previous.get("status") != "complete":
                raise RuntimeError("complete phase one before testing both songs")
            first_deck = previous["first_deck"]
            first_id = previous["first_track_id"]
            if active.get(first_deck) != first_id:
                raise RuntimeError("the first song changed; start a new bench run")
            others = {deck: track for deck, track in active.items()
                      if deck != first_deck and track != first_id}
            if len(others) != 1:
                raise RuntimeError("both phases need two distinct playing songs")
            tracks = {first_id: first_deck, next(iter(others.values())): next(iter(others))}
        else:
            first_deck = min(active)
            first_id = active[first_deck]
            tracks = {first_id: first_deck}

        catalog = RemoteCatalog(source)
        generation = catalog.manifest["export_pdb_sha256"]
        if previous and (previous["source"] != source or
                         (previous["media_generation"] != generation and not interrupted)):
            raise RuntimeError("source/export changed since phase one")
        sizes = {track_id: catalog.audio_stat(track_id) for track_id in tracks}
        total = sum(sizes.values()) + (previous["bytes"] if previous else 0)
        if total + BENCH_RESERVE > BENCH_BUDGET:
            raise RuntimeError(f"planned {total} bytes plus 4 MiB reserve exceeds "
                               "128 MiB bench budget")
        if not sizes or any(size <= 0 for size in sizes.values()):
            raise RuntimeError("a selected song has no readable audio file")
        paths = {track_id: catalog.tracks[str(track_id)]["metadata"]["file_path"]
                 for track_id in tracks}
        if previous and paths[first_id] != previous["paths"][str(first_id)]:
            raise RuntimeError("first song audio path changed")
        if interrupted and (interrupted["source"] != source or
                            interrupted["first_track_id"] != first_id or
                            interrupted["deck_tracks"] !=
                            {str(deck): track for track, deck in tracks.items()} or
                            interrupted["paths"] != {str(k): v for k, v in paths.items()} or
                            interrupted["sizes"] != {str(k): v for k, v in sizes.items()}):
            raise RuntimeError("playing track identity, path, or size changed")
        if interrupted:
            time.sleep(2)
            catalog.verify_export(max_age_s=0)

        start_ns = time.time_ns()
        start = time.monotonic()
        bytes_done = interrupted["bytes"] if interrupted else 0
        planned_bytes = sum(sizes.values())
        stage_index = min(3, bytes_done * 4 // planned_bytes)
        stage_bytes = 0
        stage_start = time.monotonic()
        stages = []
        next_cadence_check = stage_start + 2.0
        handles = {}
        digests = {track_id: hashlib.sha256() for track_id in tracks}
        offsets = {track_id: 0 for track_id in tracks}
        if interrupted:
            for track_id in tracks:
                part = output / f"phase-{phase}-track-{track_id}.part"
                with part.open("rb") as stream:
                    while block := stream.read(1024 * 1024):
                        digests[track_id].update(block)
                offsets[track_id] = part.stat().st_size
                if offsets[track_id] > sizes[track_id] or offsets[track_id] == 0 or (
                        digests[track_id].hexdigest() !=
                        interrupted["sha256"][str(track_id)]):
                    raise RuntimeError("host partial-file length or hash changed")
            if sum(offsets.values()) != bytes_done:
                raise RuntimeError("host partial-file byte count changed")
            for track_id, offset in offsets.items():
                part = output / f"phase-{phase}-track-{track_id}.part"
                for check_offset in (0, max(0, offset - RANGE_BYTES)):
                    count = min(RANGE_BYTES, offset - check_offset)
                    deck_data, actual_size = catalog.audio_range(track_id, check_offset, count)
                    with part.open("rb") as stream:
                        stream.seek(check_offset)
                        host_data = stream.read(count)
                    if actual_size != sizes[track_id] or deck_data != host_data:
                        raise RuntimeError("deck source differs from saved partial audio")
        report = {"schema": "rx3-sustained-audio-bench/1", "phase": phase,
                  "status": "running", "source": source, "media_generation": generation,
                  "first_deck": first_deck, "first_track_id": first_id,
                  "deck_tracks": {str(deck): track for track, deck in tracks.items()},
                  "paths": {str(k): v for k, v in paths.items()},
                  "sizes": {str(k): v for k, v in sizes.items()},
                  "planned_cumulative_bytes": total, "bytes": bytes_done}
        if interrupted:
            (output / "phase-both-interrupted.json").write_text(
                json.dumps(interrupted, indent=2) + "\n")
            report["resumed_from_bytes"] = bytes_done
            report["prior_media_generation"] = interrupted["media_generation"]
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        try:
            for track_id in tracks:
                part = output / f"phase-{phase}-track-{track_id}.part"
                handles[track_id] = part.open("ab" if interrupted else "xb")
            next_progress = (bytes_done // (8 * 1024 * 1024) + 1) * 8 * 1024 * 1024
            for track_id, offset, count in ranges(sizes, offsets):
                intended_stage = min(3, bytes_done * 4 // planned_bytes)
                if intended_stage != stage_index:
                    stages.append({"target_Mb_s": RATE_STAGES_MBPS[stage_index],
                                   "bytes": stage_bytes,
                                   "elapsed_s": round(time.monotonic()-stage_start, 3)})
                    stage_index = intended_stage
                    stage_start = time.monotonic()
                    stage_bytes = 0
                peer, current = live_state(db, source)
                if peer != source or any(playing_tracks(current).get(deck) != track
                                         for track, deck in tracks.items()):
                    raise RuntimeError("a playing track changed or stopped")
                data, size = catalog.audio_range(track_id, offset, count)
                if size != sizes[track_id] or len(data) != count:
                    raise RuntimeError("audio size or range changed")
                handles[track_id].write(data)
                digests[track_id].update(data)
                bytes_done += count
                stage_bytes += count
                target_elapsed = stage_bytes * 8 / (RATE_STAGES_MBPS[stage_index] * 1_000_000)
                remaining = target_elapsed - (time.monotonic()-stage_start)
                if remaining > 0:
                    time.sleep(remaining)
                if time.monotonic() >= next_cadence_check:
                    # The rolling writer commits once per second. Give a full
                    # commit interval before judging cadence from SQLite.
                    recent = gaps(db, time.time_ns()-2_000_000_000)
                    if any(item["packets"] < 5 or item["max_gap_ms"] > 500
                           for item in recent.values()):
                        raise RuntimeError("telemetry cadence degraded during audio read")
                    next_cadence_check = time.monotonic() + 2.0
                if bytes_done >= next_progress:
                    elapsed_total = (interrupted["elapsed_s"] if interrupted else 0) + \
                                    time.monotonic() - start
                    print(f"{phase}: {bytes_done / 1048576:.1f} MiB, "
                          f"{bytes_done / max(elapsed_total, .001) / 1048576:.2f} MiB/s",
                          flush=True)
                    next_progress += 8 * 1024 * 1024
            for track_id, handle in handles.items():
                handle.flush();os.fsync(handle.fileno());handle.close()
                (output / f"phase-{phase}-track-{track_id}.part").replace(
                    output / f"phase-{phase}-track-{track_id}.audio")
            if previous and digests[first_id].hexdigest() != previous["sha256"][str(first_id)]:
                raise RuntimeError("repeat read of the first song differs")
            stages.append({"target_Mb_s": RATE_STAGES_MBPS[stage_index],
                           "bytes": stage_bytes,
                           "elapsed_s": round(time.monotonic()-stage_start, 3)})
            report["rate_stages"] = stages
            report["status"] = "complete"
        except BaseException as exc:
            report["status"] = "stopped"
            report["error"] = f"{type(exc).__name__}: {exc}"[:240]
            raise
        finally:
            for handle in handles.values():
                if not handle.closed:
                    handle.close()
            report.update(bytes=bytes_done,
                          elapsed_s=round((interrupted["elapsed_s"] if interrupted else 0) +
                                          time.monotonic() - start, 2),
                          throughput_MiB_s=round(bytes_done /
                                                  max((interrupted["elapsed_s"] if interrupted else 0) +
                                                      time.monotonic()-start, .001) /
                                                  1048576, 3),
                          sha256={str(k): digest.hexdigest()
                                  for k, digest in digests.items()},
                          telemetry=gaps(db, start_ns))
            report_path.write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        if catalog is not None:
            catalog.close()
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("one", "both"), required=True)
    parser.add_argument("--resume", action="store_true",
                        help="resume a two-song run stopped by an export metadata change")
    parser.add_argument("--database", type=Path,
                        default=Path("local/captures/rx3-rolling.sqlite3"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.phase, args.database, args.out, args.resume)
    except (ValueError, RuntimeError, OSError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f"sustained audio bench stopped: {exc}\n")
    print(json.dumps({key: result[key] for key in
                      ("phase", "status", "bytes", "elapsed_s", "throughput_MiB_s",
                       "telemetry")}, indent=2))


if __name__ == "__main__":
    main()
