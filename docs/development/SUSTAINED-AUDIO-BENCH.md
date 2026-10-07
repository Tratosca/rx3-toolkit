# RX3 USB-B sustained audio read bench

This is a bench-only follow-up to the small read documented in
`USB-B-TD-GATEWAY-AUDIT.md`. It measures throughput while the operator listens
to playback. It is not a performance build or a beat-detection workflow.

The normal image limits audio reads to 8 MiB per run. This specifically marked
bench image raises the cumulative limit to 128 MiB and reduces the audio send
wait to 0.6 ms per 4 KiB. That gives a nominal application ceiling of about
6.8 MB/s before overhead, around the requested 50 Mb/s target. Metadata keeps
its 4 ms per 4 KiB pacing. The helper still handles one connection at a time
and reads no more than 256 KiB per request. The USB-B network interface's
100 Mb/s link rate is not a measured sustainable audio-file rate.

The host runner reads the latest Now Playing and position packets from the
rolling SQLite capture. Phase one selects the lowest-numbered deck that is
playing when the command starts. Phase two requires that same song to be
playing and another distinct song on the other deck. It interleaves 64 KiB
requests from the two tracks, throttling the host in four roughly equal byte
segments at 8, 16, 32, and 50 Mb/s. The runner stops before the next request if
telemetry is stale, either selected song changes or stops, the source changes,
or the mounted rekordbox export changes, or packet cadence exceeds 500 ms.
It also rejects a plan that comes within 4 MiB of the
128 MiB cumulative deck budget, leaving room for previous small probes. Files
are streamed directly to ignored host
storage, with per-track SHA-256; the repeated first track must match phase one.

With the audited bench image installed and both telemetry feeds recording:

```sh
python3 scripts/sustained_audio_bench.py --phase one \
  --out local/captures/sustained-audio-YYYY-MM-DD
```

Listen for dropouts and check the phase-one JSON and rolling telemetry. Only
if playback remains normal, keep the first track loaded, play a different
track on the second deck, and run:

```sh
python3 scripts/sustained_audio_bench.py --phase both \
  --out local/captures/sustained-audio-YYYY-MM-DD
```

Run each phase once in a fresh output directory. Both phases read entire
currently playing source files; they do not alter the deck's internal storage
or settings. This does not establish that full-song reads are needed for the
eventual adapter. It measures headroom for a future few-second excerpt plan.
The bench still runs the previously tested RAM startup patch, so a startup
failure could interrupt playback and require a reboot. Remove the bench image
from the music USB after testing; the normal 8 MiB limit is the default.

## First physical result, 2026-10-07

The audited image SHA-256 was
`e0866fbaaa5a4ddf0d88138d4c431b84f7f28a96b1aa6ba08c65a1545ad39005`.
The existing player hook was unchanged. The image was installed on SOUND_PRO
with a host backup and read-back verification. A first host attempt timed out
before audio transfer; a direct PDB request then succeeded. The next attempt
stopped after 256 KiB because the monitor checked SQLite before the rolling
listener's one-second commit. That monitor timing bug was fixed without
changing the on-deck image.

Phase one then read the currently playing Deck 1 track (47,075,968 bytes) in
28.94 seconds. Now Playing delivered 1,387 packets with a maximum 41.9 ms
gap; position diagnostics delivered 566 packets with a maximum 54.6 ms gap.
Actual rates by target segment were 8.0, 15.1, 17.5, and 17.0 Mb/s for 8,
16, 32, and 50 Mb/s targets. The plateau shows the current request path did
not approach 50 Mb/s. It does not identify the limiting component. The
operator was not listening closely during phase one; its telemetry was normal.

## Two-song physical result

Deck 1 continued playing the 47,075,968-byte track. The first Deck 2 choice
would have exceeded the session allowance, so the runner rejected it before
audio transfer. The operator loaded a distinct 31,865,785-byte track instead.
The two-song phase read 30,081,024 bytes before the deck-served PDB changed.
The runner stopped, while Now Playing and position packets continued with
maximum gaps of 41.7 and 57.3 ms. The operator heard no dropout or saw no
freeze during that portion.

For a guarded resume, the host read the new PDB twice and found it stable.
Both selected track IDs retained the same file paths and sizes. The host
verified the start and end of each saved partial file against fresh deck
ranges, then read only the remaining bytes. The final Deck 1 SHA-256 matched
the phase-one full-file hash. Both complete files totalled 78,941,753 bytes;
the interrupted and resumed portions took 48.7 seconds together. In the
resumed portion, measured segment rates were 14.6, 17.9, and 17.1 Mb/s for
16, 32, and 50 Mb/s targets. Its Now Playing and position maximum gaps were
41.7 and 65.4 ms. The operator reported no dropout or freeze during either
portion. The documented audio requests total less than the 128 MiB helper
allowance, including the earlier 256 KiB monitor false stop and four 64 KiB
resume identity checks.

This is evidence that these two files could be read concurrently with
playback in one bench run, at observed rates below 18 Mb/s. It is not a
guarantee of performance at 50 Mb/s or with different USB media, songs, or
firmware. The export changed in content while the relevant file identities
remained stable; future sampling should verify track-specific identity rather
than blindly accepting or permanently blocking all PDB changes.

After testing, SOUND_PRO was restored from the installer backup to its prior
8 MiB image. The read-back SHA-256 matched the previously verified
`1723f3b140c925fe37a50360f03f701583343cb8aaf8faef931c205d42af0c26`.
The stick was safely ejected from the computer.
