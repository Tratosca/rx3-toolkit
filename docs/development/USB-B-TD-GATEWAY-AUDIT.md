# RX3 USB-B TouchDesigner gateway candidate (2026-10-07)

This candidate follows the physically verified metadata checkpoint tag
`rx3-usbb-metadata-bench-2026-10-07`. Its bounded read and TD-format output
have now had a single-track physical bench check; endurance and subjective
audio quality remain unverified.
The existing `librx3_core.so` is byte-identical to that checkpoint. The new
deck code is an isolated `metadata-server` process; the new semantic gateway,
sample decoder, OSC publisher and HTTP API run on the computer.
The follow-up audited image installed on SOUND_PRO has SHA-256
`1723f3b140c925fe37a50360f03f701583343cb8aaf8faef931c205d42af0c26`.
The installer backed up the previous USB-root image and manifest in the
ignored host cache. The installed image hash was verified after writing.

## Physical bench check, 2026-10-07

With firmware 1.19 and one analyzed track playing from SOUND_PRO, the USB-B
helper opened TCP 50131. The rolling listener received continuing Now Playing
and position packets. A direct `STAT` and 4 KiB `RANGE` of that track's
47,075,968-byte FLAC succeeded; its reported size stayed consistent. The
fresh deck-served PDB contained 238 tracks. Its hash differed from the
pre-gig scan, so the first sample attempt stopped before reading audio; the
playing track's title, artist, audio path and analysis path still matched,
and the fresh export hash was stable across two reads three seconds apart.
Using that fresh identity, the host decoded a one-second excerpt at source
time 30 seconds into four quarter-second windows in 10.64 seconds. The helper
enforces its 8 MiB session cap, but exact bytes transferred were not measured
in this physical run. No drop in telemetry was observed afterward; the
rolling capture still recorded hundreds of Now Playing and position packets
per ten-second window.

The current captured packets and deck-served analysis produced a connected
bridge snapshot with valid title, beat phase and phrase. The existing NXS2 TD
OSC assembler accepted the output and exposed 68 deck fields. Fader and live
audio correctly remained invalid. This validates the packet schema and
single-track data path, **not** an actual running TouchDesigner network or a
full DJ set. The rolling recorder did not capture a separate startup status
packet in this insertion, although it did capture the preflight report and
the helper/telemetry functioned. A second one-second excerpt request, made
while the operator listened, returned HTTP 503 from the host decoder. Direct
`STAT` and 4 KiB `RANGE` still worked afterward, and the rolling telemetry
continued. The likely cause is the helper's remaining 8 MiB audio allowance
being too small for another FFmpeg seek, but this has not been measured or
confirmed. The operator reported **no audible dropout and no screen freeze**
during that request. Treat repeated excerpt sampling as unverified until a
subsequent bench run measures requested range bytes and distinguishes budget
exhaustion from other decode errors.

## TouchDesigner data

Start the existing `prodjlink_bridge.py --deck-metadata` on TCP 50130, then
run:

```sh
python3 scripts/td_gateway.py --deck-source 169.254.159.144 \
  --bridge-port 50130 --http-port 50132 --osc-port 4470
```

The address is the USB-B link-local IP observed in the bench run, not a fixed
RX3 address. The gateway emits the CDJ2000NXS2 `/vj/deck0/*` and
`/vj/deck1/*` OSC schema, with the same coherent multipart frame headers.
The existing NXS2 `Assembler` accepted a generated RX3 frame in a host test.
`GET /state`, `/assets`, `/assets/<track-id>`, and `/samples/<track-id>` on
localhost:50132 expose the full current snapshots and track assets. `GET
/health` reports bridge age. Rekordbox key is parsed from the mounted PDB key
table; a 238-track export yielded 238 keys and plausible sample rates.

`HEAD /audio/<track-id>` and a **single bounded** Range `GET` offer source
file bytes to a local decoder. `POST /samples/<track-id>` with JSON such as
`{"start_s":30,"duration_s":4}` decodes up to five seconds with FFmpeg and
stores quarter-second RMS, peak, coarse low/mid/high, onset and centroid
features. At most three excerpts per track are allowed by the gateway, and
the helper caps all audio traffic at 8 MiB per run. An excerpt contributes
`audio/valid=1` only while playback is inside one of its measured windows.
It is explicitly labelled `sampled_source_file_pre_fader`; it is **not**
live deck audio or a mixer meter. A host integration test successfully decoded
a four-second excerpt near 30 seconds in a generated 45-second FLAC via the
actual bounded range protocol, transferring fewer bytes than the full file.

The CDJ2000NXS2 workflows can receive title, artist, key, original/adjusted
BPM, beat phase, grid/phrase, PWV5 motion, transport and on-air state.
Continuous fader, crossfader, EQ, master/sync, loop bounds and live PCM/levels
remain unavailable and are sent with invalid flags or nulls. The preview
weight is manually selected; it does not estimate audibility. Source slot
identity is still unverified, so use one music USB for this bench candidate.
The RX3 source-frame-to-seconds conversion is still provisional for tracks at
sample rates other than 44.1 kHz.

## On-deck persistent-write audit

The only changed ARM source, `mod/lib/metadata_server.c`, opens the USB root
and each requested path read-only with `O_NOFOLLOW` on every component.
`STAT` and `RANGE` accept only `Contents/` audio extensions. The helper has
no file create, truncate, rename, mount, `mtd`, `ubi`, or flash syscall. Its
`WRITE`/`SEND` calls target the accepted TCP socket, not a disk file. A file
is limited to 512 MiB, a range to 256 KiB, and a helper run to 8 MiB total
audio. Access is limited to USB-B link-local peers, one connection at a time.
An invalid path, symlink, traversal, exhausted budget, or I/O failure returns
an error without touching the player process. Host tests cover these cases.
The follow-up audit fixed partial-send accounting: the helper now charges the
entire accepted range **before** transmitting, so disconnect/retry cycles
cannot recover budget. The host also serializes explicit excerpt decoding to
avoid multiple simultaneous sample jobs against the music USB.

The package source audit found exactly 19 expected files and no unexpected
ARM imports. The selected modules remain `core`, `now-playing`, and
`position-diagnostic`; the already-tested performance core is unchanged.
The existing startup path checks RAM-backed mounts and non-symlink target
paths before modifying `/root/pdj/rbp` (RAM), uses `/tmp` for staging, and
does not select a module that writes deck settings. It does restart the player
and patches the **RAM** copy of its executable, so a startup failure could
interrupt playback or require a normal reboot. This is a functional risk,
not evidence of persistent internal-storage modification.
The resident core's log path defaults to `/tmp`, but it previously allowed an
inherited `RX3_LOG_FILE` override. Startup now unsets that variable before
launching the player, removing a possible redirection to a persistent path.
The compiled helper is a static ARM EABI5 executable with no undefined
imports. The startup shell parses cleanly; 53 focused startup/staging/safety
tests and 11 audio-path/gateway tests pass after these changes. The broader
suite is not a clean signal on this host because its port-binding tests
collide with the user's rolling capture process, and unrelated optional test
dependencies are absent.

The installer writes `autoexec.bin` and `rx3-mod-manifest.json` at the **USB
stick root**, backing up any prior files in the host cache. Startup also
writes status text under that stick's `RX3_RUNTIME` directory. These writes
persist on the removable stick, **not** in the RX3 internal firmware or
settings. No path in the changed helper or selected modules writes the deck's
internal flash. This is a source/package audit, not proof against unforeseen
hardware or firmware behavior. Keep the prior known-good USB image available
and test this candidate at the bench before relying on it.
