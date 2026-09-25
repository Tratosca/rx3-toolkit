#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Print what an RX3 running the now-playing module says each deck is playing.

Plug the computer into the deck's rear USB-B port and run this. Every datagram
the deck sends carries both decks whole, so the output is one JSON line per
state, ready to pipe into an overlay, a VJ tool or a set-list logger:

    python3 scripts/now_playing.py
    python3 scripts/now_playing.py --changes-only | your-overlay

The firewall has to let inbound UDP 50123 through. No dependency beyond the
standard library.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys

PORT = 50123
VERSION = 1


def decode(datagram: bytes) -> dict | None:
    """The state a datagram carries, or None for anything that is not one."""
    try:
        message = json.loads(datagram.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(message, dict) or message.get("type") != "now-playing":
        return None
    if message.get("version") != VERSION:
        return None
    decks = message.get("decks")
    if not isinstance(decks, list) or len(decks) != 2:
        return None
    for deck in decks:
        # Hundredths are what the player stores. None rather than 0.00 when
        # nothing is loaded, so a consumer cannot mistake it for a tempo.
        raw = deck.get("bpmX100") or 0
        deck["bpm"] = raw / 100 if deck.get("loaded") and raw else None
    return message


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--changes-only", action="store_true",
                        help="drop heartbeats that repeat the previous state")
    arguments = parser.parse_args(argv)

    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("", arguments.port))
    previous = None
    while True:
        datagram, sender = listener.recvfrom(4096)
        message = decode(datagram)
        if message is None:
            continue
        if arguments.changes_only and message["decks"] == previous:
            continue
        previous = message["decks"]
        message["from"] = sender[0]
        print(json.dumps(message, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(0)
