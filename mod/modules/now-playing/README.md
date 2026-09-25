<!-- SPDX-License-Identifier: MPL-2.0 -->
# Now playing

Sends what each deck is playing to the computer plugged into the rear USB-B port: the title, the track id, the BPM, the tempo and whether the channel is on air. Use it for a stream overlay, a VJ screen or a set list, while the RX3 plays standalone, with no rekordbox and no PRO DJ LINK.

Off by default. Tick it on the Modules screen, build, and on the computer run:

    python3 scripts/now_playing.py

Each line it prints is the state of both decks. Allow inbound UDP 50123 through the computer's firewall.

## What it sends

One JSON datagram to UDP port 50123, on the directed broadcast of the link-local network the USB-B port brings up (169.254.255.255). It goes out when something changes on a deck, and every two seconds anyway, so a listener started mid-set catches up at once. Each datagram carries both decks whole:

    {"type":"now-playing","version":1,"sequence":42,"reason":"change",
     "decks":[{"deck":1,"loaded":true,"onAir":true,"trackId":1234,
               "bpmX100":12800,"tempoRaw":0,"playModeRaw":3,"title":"..."},
              {"deck":2,"loaded":false, ...}]}

`reason` is `start`, `change` or `heartbeat`. `scripts/now_playing.py` adds `bpm` in beats per minute.

## What is not established yet

- Nothing here has run on hardware. The event hooks and accessors are checked against the 1.19 player binary, not yet observed on a deck.
- `tempoRaw` and `playModeRaw` are sent as the player stores them. Which values mean playing, paused or cued, and the unit of the tempo, wait for a capture on a deck.
- The artist, the album and the key are not sent: where the standalone player keeps them has not been found.
- `trackId` is the id the player loaded the track with, not yet shown to be stable across exports.
- The datagrams are not authenticated. Anything on the USB link can read them, and anything on it could send look-alikes to a listener.

## If it gets in the way

Create `/tmp/rx3-now-playing.off` on the player and the module stays out from the next insertion until the next power cycle.

## Credits

The event hooks, the accessors and the protocol design come from evanpurkhiser's USB telemetry prototype (#32). The UDP transport over the USB link comes from jacksight's Now Playing export (#20).
