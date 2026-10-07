#!/usr/bin/env python3
"""Prepare a rekordbox USB for an RX3 gig without copying any music.

``scan`` reads the mounted stick and writes a host-side catalog. ``install`` is
an explicit, separate operation that backs up and verifies an audited RX3
telemetry package. Neither command updates rekordbox analysis or audio files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import sys
import tempfile
from datetime import datetime, timezone


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from app.stems import pdb  # noqa: E402


PSSI_MASK = bytes([0xCB, 0xE1, 0xEE, 0xFA, 0xE5, 0xEE, 0xAD, 0xEE, 0xE9,
                   0xD2, 0xE9, 0xEB, 0xE1, 0xE9, 0xF3, 0xE8, 0xE9, 0xF4, 0xE1])


def load_tracks(source: Path) -> dict[int, dict]:
    if source.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("export.pdb is too large")
    tables = pdb.read_tables(source.read_bytes())
    artists = {}
    for row in pdb.iter_rows(tables, pdb.TABLE_ARTISTS):
        try:
            artist_id, name = pdb.parse_artist(row)
            artists[artist_id] = name
        except ValueError:
            continue
    keys = {}
    for row in pdb.iter_rows(tables, pdb.TABLE_KEYS):
        try:
            key_id, name = pdb.parse_key(row)
            keys[key_id] = name
        except ValueError:
            continue
    tracks = {}
    for row in pdb.iter_rows(tables, pdb.TABLE_TRACKS):
        try:
            track = pdb.parse_track(row)
        except ValueError:
            continue
        if track.track_id in tracks:
            raise ValueError(f"duplicate rekordbox track ID {track.track_id}")
        tracks[track.track_id] = {
            "id": track.track_id, "title": track.title,
            "artist": artists.get(track.artist_id, ""),
            "duration_s": track.duration,
            "file_path": track.file_path,
            "anlz_path": track.analysis_path,
            "key": keys.get(track.key_id),
            "sample_rate_hz": track.sample_rate_hz or None,
            "file_size_bytes": track.file_size_bytes or None,
        }
    return tracks


def phrase_label(mood: int, kind: int, k1: int, k2: int) -> str:
    if mood == 1:
        if kind == 1:
            return "Intro 1" if k1 == 1 else "Intro 2"
        if kind == 2:
            return {(0, 0): "Up 1", (0, 1): "Up 2", (1, 0): "Up 3"}.get((k1, k2), "Up")
        if kind == 3:
            return "Down"
        if kind == 5:
            return "Chorus 1" if k1 == 1 else "Chorus 2"
        if kind == 6:
            return "Outro 1" if k1 == 1 else "Outro 2"
    if mood == 2:
        return {1: "Intro", 2: "Verse 1", 3: "Verse 2", 4: "Verse 3",
                5: "Verse 4", 6: "Verse 5", 7: "Verse 6", 8: "Bridge",
                9: "Chorus", 10: "Outro"}.get(kind, f"kind{kind}")
    if mood == 3:
        return {1: "Intro", 2: "Verse 1", 3: "Verse 1", 4: "Verse 1",
                5: "Verse 2", 6: "Verse 2", 7: "Verse 2", 8: "Bridge",
                9: "Chorus", 10: "Outro"}.get(kind, f"kind{kind}")
    return f"kind{kind}"


def parse_pssi(tag: bytes) -> dict:
    count = int.from_bytes(tag[0x10:0x12], "big")
    if not 0 < count <= 200 or len(tag) != 0x20 + 0x18 * count:
        raise ValueError("truncated or unsupported PSSI entries")
    body = bytearray(tag)
    key = lambda i: (PSSI_MASK[i % len(PSSI_MASK)] + count) & 0xff
    plain_mood = int.from_bytes(body[0x12:0x14], "big")
    masked_mood = ((body[0x12] ^ key(0)) << 8) | (body[0x13] ^ key(1))
    if plain_mood not in (1, 2, 3) and masked_mood in (1, 2, 3):
        for i, offset in enumerate(range(0x12, len(body))):
            body[offset] ^= key(i)
        masked = True
    elif plain_mood in (1, 2, 3):
        masked = False
    else:
        raise ValueError("PSSI mood is unknown")
    mood = int.from_bytes(body[0x12:0x14], "big")
    end_beat = int.from_bytes(body[0x1a:0x1c], "big")
    phrases = []
    for i in range(count):
        offset = 0x20 + i * 0x18
        entry = body[offset:offset + 0x18]
        index, beat, kind = struct.unpack_from(">HHH", entry)
        fill = int.from_bytes(entry[0x16:0x18], "big") if entry[0x15] else None
        phrases.append({"index": index, "beat": beat, "kind": kind,
                        "label": phrase_label(mood, kind, entry[0x07], entry[0x09]),
                        "fill_at": fill})
    return {"mood": {1: "High", 2: "Mid", 3: "Low"}[mood],
            "mood_id": mood, "end_beat": end_beat, "encrypted": masked,
            "phrases": phrases}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def usb_file(root: Path, record_path: str) -> Path:
    """Confine an export.pdb path to a regular file inside the mounted USB."""
    if not isinstance(record_path, str) or not record_path.startswith("/"):
        raise ValueError("analysis path is not USB-absolute")
    rel = PurePosixPath(record_path)
    if ".." in rel.parts or not str(rel).startswith("/PIONEER/USBANLZ/"):
        raise ValueError("analysis path leaves USBANLZ")
    path = root.joinpath(*rel.parts[1:])
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("analysis path escapes mounted USB")
    return path


def bounded_read(path: Path, limit: int = 32 * 1024 * 1024) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > limit:
        raise ValueError(f"analysis file exceeds {limit} bytes")
    return path.read_bytes()


def sections(data: bytes) -> list[tuple[bytes, bytes]]:
    """Reject a truncated PMAI container instead of accepting partial tags."""
    if len(data) < 28 or data[:4] != b"PMAI":
        raise ValueError("not a PMAI analysis file")
    start = int.from_bytes(data[4:8], "big")
    declared = int.from_bytes(data[8:12], "big")
    if start < 28 or start > len(data) or declared != len(data):
        raise ValueError("invalid PMAI file length")
    out = []
    pos = start
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError("truncated analysis section")
        length = int.from_bytes(data[pos + 8:pos + 12], "big")
        if length < 12 or pos + length > len(data):
            raise ValueError("invalid analysis section length")
        out.append((data[pos:pos + 4], data[pos:pos + length]))
        pos += length
    return out


def decode_analysis(dat: bytes, ext: bytes | None) -> dict:
    dat_tags = sections(dat)
    ext_tags = sections(ext) if ext is not None else []
    grids = [tag for name, tag in dat_tags if name == b"PQTZ"]
    if len(grids) != 1:
        raise ValueError("expected exactly one PQTZ beat grid")
    grid = grids[0]
    if len(grid) < 24 or len(grid) != 24 + 8 * int.from_bytes(grid[20:24], "big"):
        raise ValueError("truncated or oversized PQTZ grid")
    beats = list(struct.iter_unpack(">HHI", grid[24:]))
    if not beats or len(beats) != int.from_bytes(grid[20:24], "big"):
        raise ValueError("beat grid could not be decoded")
    times = [b[2] for b in beats]
    if (times != sorted(set(times)) or
            any(b[0] not in (1, 2, 3, 4) or b[1] <= 0 for b in beats)):
        raise ValueError("beat grid has invalid timing or meter")
    result = {"grid": [{"beat": i, "time_ms": b[2],
                         "count_in_bar": b[0], "bpm_x100": b[1]}
                        for i, b in enumerate(beats, 1)],
              "phrases": None, "phrase_status": "missing_pssi",
              "waveform_tags": sorted({name.decode("ascii", "replace") for name, _ in
                                       dat_tags + ext_tags if name.startswith(b"PWV")})}
    detailed = [tag for name, tag in dat_tags + ext_tags if name == b"PWV5"]
    if len(detailed) == 1:
        tag = detailed[0]
        count = int.from_bytes(tag[16:20], "big") if len(tag) >= 24 else 0
        if (len(tag) >= 24 and int.from_bytes(tag[4:8], "big") == 24 and
                int.from_bytes(tag[12:16], "big") == 2 and
                int.from_bytes(tag[20:24], "big") in (150 << 16, 0x00960305) and
                0 < count <= 540000 and len(tag) == 24 + count * 2):
            result["waveform"] = {"style": "PWV5", "rate_hz": 150,
                                  "encoding": "hex", "data_hex": tag[24:].hex()}
    phrase_tags = [tag for name, tag in ext_tags if name == b"PSSI"]
    if not phrase_tags:
        return result
    try:
        if len(phrase_tags) != 1:
            raise ValueError("multiple PSSI tags")
        tag = phrase_tags[0]
        parsed = parse_pssi(tag)
        phrases = parsed["phrases"]
        starts = [p["beat"] for p in phrases]
        end_beat = parsed["end_beat"]
        if (starts != sorted(set(starts)) or starts[0] < 1 or
                end_beat <= starts[-1] or end_beat > len(beats) + 16 or
                any(p["index"] < 1 for p in phrases)):
            raise ValueError("PSSI boundaries do not fit beat grid")
        for i, phrase in enumerate(phrases):
            end = starts[i + 1] if i + 1 < len(starts) else end_beat
            fill = phrase["fill_at"]
            if fill is not None and not phrase["beat"] <= fill < end:
                raise ValueError("PSSI fill falls outside phrase")
            phrase["end_beat"] = end
        result.update(phrases=phrases, phrase_status="ready", mood=parsed["mood"],
                      mood_id=parsed["mood_id"], end_beat=end_beat,
                      masked=parsed["encrypted"])
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        result.update(phrase_status="invalid_pssi", phrase_error=str(exc)[:200])
    return result


def scan(root: Path, output: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("USB path is not a directory")
    pdb = root / "PIONEER" / "rekordbox" / "export.pdb"
    if not pdb.is_file() or pdb.is_symlink():
        raise FileNotFoundError(f"classic rekordbox export not found: {pdb}")
    if output.resolve().is_relative_to(root):
        raise ValueError("host cache must be outside the USB")
    if output.exists():
        raise FileExistsError(f"choose a fresh cache directory: {output}")
    tracks = load_tracks(pdb)
    if not tracks:
        raise ValueError("export.pdb contains no tracks")
    output.mkdir(mode=0o700, parents=True)
    (output / "analysis").mkdir(mode=0o700)
    catalog = {}
    summary = {"schema": "rx3-pre-gig/1", "scanned_at": datetime.now(timezone.utc).isoformat(),
               "source_label": root.name, "export_pdb_sha256": sha256(pdb),
               "track_count": len(tracks), "ready": 0, "missing_analysis": 0,
               "missing_phrases": 0, "invalid_phrases": 0, "invalid_analysis": 0,
               "note": "Host cache only; no music copied or USB files changed."}
    for track_id, meta in sorted(tracks.items()):
        item = {"metadata": meta, "status": "missing_analysis", "analysis": None,
                "error": None}
        try:
            dat_path = usb_file(root, meta["anlz_path"])
            dat = bounded_read(dat_path)
            ext_path = dat_path.with_suffix(".EXT")
            ext = bounded_read(ext_path) if ext_path.exists() else None
            decoded = decode_analysis(dat, ext)
            asset_name = f"{track_id}.json"
            asset = {"schema": "rx3-analysis/1", "track_id": track_id,
                     "export_pdb_sha256": summary["export_pdb_sha256"],
                     "dat_sha256": hashlib.sha256(dat).hexdigest(),
                     "ext_sha256": hashlib.sha256(ext).hexdigest() if ext else None,
                     "analysis_path": meta["anlz_path"], **decoded}
            (output / "analysis" / asset_name).write_text(
                json.dumps(asset, ensure_ascii=False, separators=(",", ":")) + "\n")
            item.update(status=decoded["phrase_status"], analysis=f"analysis/{asset_name}",
                        beat_count=len(decoded["grid"]),
                        phrase_count=len(decoded["phrases"] or []))
        except FileNotFoundError:
            item["status"] = "missing_analysis"
        except (ValueError, OSError, KeyError, IndexError) as exc:
            item.update(status="invalid_analysis", error=str(exc)[:200])
        summary[{"ready": "ready", "missing_pssi": "missing_phrases",
                 "invalid_pssi": "invalid_phrases",
                 "missing_analysis": "missing_analysis",
                 "invalid_analysis": "invalid_analysis"}[item["status"]]] += 1
        catalog[str(track_id)] = item
    (output / "tracks.json").write_text(json.dumps(catalog, ensure_ascii=False,
                                                   indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _atomic_write(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".rx3-prepare-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
        if path.read_bytes() != data:
            raise OSError(f"write verification failed: {path}")
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(root: Path, cache: Path, package: Path, firmware: str,
            allow_bench_audio: bool = False) -> dict:
    """Install only two root-level telemetry files, with a recoverable backup."""
    root = root.resolve(strict=True)
    cache = cache.resolve(strict=True)
    if not (root / "PIONEER" / "rekordbox" / "export.pdb").is_file():
        raise ValueError("destination is not a classic rekordbox USB")
    if cache.is_relative_to(root):
        raise ValueError("backup/cache must remain off the USB")
    scan_manifest = json.loads((cache / "manifest.json").read_text())
    if sha256(root / "PIONEER" / "rekordbox" / "export.pdb") != scan_manifest["export_pdb_sha256"]:
        raise ValueError("USB export changed since scan; scan again")
    catalog = json.loads((cache / "tracks.json").read_text())
    for track_id, item in catalog.items():
        if not item.get("analysis"):
            continue
        asset_file = (cache / item["analysis"]).resolve()
        if not asset_file.is_relative_to(cache) or not asset_file.is_file():
            raise ValueError("cached analysis path is invalid")
        asset = json.loads(asset_file.read_text())
        if asset.get("track_id") != int(track_id):
            raise ValueError("cached analysis track ID mismatch")
        dat_path = usb_file(root, asset["analysis_path"])
        ext_path = dat_path.with_suffix(".EXT")
        if (sha256(dat_path) != asset["dat_sha256"] or
                (sha256(ext_path) if ext_path.is_file() else None) != asset["ext_sha256"]):
            raise ValueError("USB analysis changed since scan; scan again")
    candidate = package / "autoexec.bin"
    candidate_manifest = package / "rx3-mod-manifest.json"
    audit_path = package / "package-audit.json"
    details = json.loads(candidate_manifest.read_text())
    audit = json.loads(audit_path.read_text())
    is_bench = (details.get("benchOnly") or details.get("benchAudioBudgetBytes") or
                details.get("benchAudioPaceNs"))
    if is_bench and not allow_bench_audio:
        raise ValueError("bench-only audio image requires explicit --bench-audio")
    if is_bench and not (
            details.get("benchOnly") is True and
            details.get("benchAudioBudgetBytes") ==
            audit.get("bench_audio_budget_bytes") == 128 * 1024 * 1024 and
            details.get("benchAudioPaceNs") == audit.get("bench_audio_pace_ns") == 600_000):
        raise ValueError("bench audio budget does not match the image audit")
    image = bounded_read(candidate, limit=8 * 1024 * 1024)
    if (details.get("firmware") != firmware or audit.get("firmware") != firmware or
            details.get("modules") != ["core", "now-playing", "position-diagnostic"] or
            audit.get("modules") != details["modules"] or
            audit.get("result") !=
            "exact source and independently built hook match; not hardware certification" or
            audit.get("unexpected_imports") != [] or
            details.get("bytes") != len(image) or
            details.get("sha256") != hashlib.sha256(image).hexdigest() or
            audit.get("package_sha256") != details["sha256"]):
        raise ValueError("telemetry package does not match its audit/firmware")
    targets = {"autoexec.bin": image,
               "rx3-mod-manifest.json": candidate_manifest.read_bytes()}
    backup = cache / "usb-root-backup"
    if backup.exists():
        raise FileExistsError("this cache already has a USB root backup")
    backup.mkdir(mode=0o700)
    original = {}
    for name in targets:
        path = root / name
        if path.is_symlink():
            raise ValueError("refusing symlinked root target")
        original[name] = path.read_bytes() if path.exists() else None
        if original[name] is not None:
            (backup / name).write_bytes(original[name])
    backup_manifest = {name: {"existed": data is not None,
                              "sha256": hashlib.sha256(data).hexdigest() if data else None}
                       for name, data in original.items()}
    (backup / "manifest.json").write_text(json.dumps(backup_manifest, indent=2) + "\n")
    try:
        for name, data in targets.items():
            _atomic_write(root / name, data)
        os.sync()
        if sha256(root / "PIONEER" / "rekordbox" / "export.pdb") != scan_manifest["export_pdb_sha256"]:
            raise OSError("Rekordbox export changed during installation")
    except BaseException:
        for name in reversed(targets):
            if original[name] is None:
                (root / name).unlink(missing_ok=True)
            else:
                _atomic_write(root / name, original[name])
        raise
    result = {"package_sha256": details["sha256"], "firmware": firmware,
              "installed_files": list(targets), "backup": str(backup),
              "write_scope": "USB root autoexec.bin and rx3-mod-manifest.json"}
    (cache / "installation.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan", help="read USB analysis into a fresh host cache")
    scan_p.add_argument("usb", type=Path)
    scan_p.add_argument("--out", type=Path, required=True)
    install_p = sub.add_parser("install", help="back up USB root and install audited telemetry")
    install_p.add_argument("usb", type=Path)
    install_p.add_argument("--cache", type=Path, required=True)
    install_p.add_argument("--package", type=Path, required=True)
    install_p.add_argument("--firmware", required=True, help="RX3 firmware displayed on the unit")
    install_p.add_argument("--bench-audio", action="store_true",
                           help="explicitly allow the audited 128 MiB bench-only audio image")
    args = parser.parse_args()
    try:
        result = (scan(args.usb, args.out) if args.command == "scan" else
                  install(args.usb, args.cache, args.package, args.firmware,
                          args.bench_audio))
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"pre-gig: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
