#!/usr/bin/env python3
"""Receive bounded RX3 USB-B PCM diagnostic packets (UDP 50127).

This is a bench recorder, not an audio output device. It never sends to the
deck. Each deck gets a WAV and a JSONL index; gaps are recorded, not concealed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import struct
import time
import wave


PORT = 50127
HEADER = struct.Struct("<4sBBHIIIiIHH")
RATE = 22050
MAX_SAMPLES = 512


def parse_packet(data: bytes) -> dict:
    if len(data) < 32:
        raise ValueError("short audio header")
    magic, version, deck, reserved, rate, sequence, generation, position, dropped, count, tail = HEADER.unpack_from(data)
    if (magic != b"RX3A" or version != 1 or deck not in (1, 2) or reserved or tail or
            rate != RATE or not 0 < count <= MAX_SAMPLES or len(data) != 32 + 2 * count):
        raise ValueError("invalid audio packet")
    return {"deck": deck, "rate": rate, "sequence": sequence,
            "generation": generation, "source_position": position,
            "dropped": dropped, "samples": count, "pcm": data[32:]}


def record(out: Path, duration: float, bind: str = "0.0.0.0", port: int = PORT) -> dict:
    if not 0 < duration <= 300:
        raise ValueError("duration must be in (0, 300] seconds")
    out.mkdir(parents=True, exist_ok=False)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind, port))
    sock.settimeout(0.25)
    wavs, indices = {}, {}
    stats = {deck: {"packets": 0, "samples": 0, "sequence_gaps": 0,
                    "reported_drops": 0, "generation": None} for deck in (1, 2)}
    previous = {}
    end = time.monotonic() + duration
    try:
        while time.monotonic() < end:
            try:
                data, peer = sock.recvfrom(1500)
            except socket.timeout:
                continue
            try:
                packet = parse_packet(data)
            except ValueError:
                continue
            deck = packet["deck"]
            if deck not in wavs:
                wavs[deck] = wave.open(str(out / f"deck{deck}.wav"), "wb")
                wavs[deck].setparams((1, 2, RATE, 0, "NONE", "not compressed"))
                indices[deck] = (out / f"deck{deck}.jsonl").open("w")
            row = {key: value for key, value in packet.items() if key != "pcm"}
            row["received_unix_ms"] = int(time.time() * 1000)
            row["peer"] = peer[0]
            indices[deck].write(json.dumps(row, separators=(",", ":")) + "\n")
            wavs[deck].writeframesraw(packet["pcm"])
            stat = stats[deck]
            if deck in previous:
                stat["sequence_gaps"] += max(0, packet["sequence"] - previous[deck] - 1)
            previous[deck] = packet["sequence"]
            stat["packets"] += 1
            stat["samples"] += packet["samples"]
            stat["reported_drops"] = packet["dropped"]
            stat["generation"] = packet["generation"]
    finally:
        sock.close()
        for file in wavs.values():
            file.close()
        for file in indices.values():
            file.close()
    (out / "summary.json").write_text(json.dumps(stats, indent=2) + "\n")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    print(json.dumps(record(args.out, args.seconds), indent=2))


if __name__ == "__main__":
    main()
