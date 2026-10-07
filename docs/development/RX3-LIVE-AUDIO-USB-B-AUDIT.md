# RX3 live audio over USB-B: candidate and safety audit

2026-10-07. This is a **bench candidate for firmware 1.19**, not a performance
release or a claim of zero permanent-damage risk. The user requested a live
audio feed for host-side TD analysis. The first test image SHA-256 is
`546f1eb87f4e3ed9ac9e8105522e732e67710977c82211868f9500c1c791e3ac`.
The corrected duplicate-filter candidate is
`90140036bb43cc5177f14839db4953f534c33981fa9210a98cde14519c448350`.
Both select `core`, `now-playing`, and `position-diagnostic` only. The previous
known-running image (`1723f3b140c925fe37a50360f03f701583343cb8aaf8faef931c205d42af0c26`)
is backed up under ignored `local/gigs/rx3-live-audio-2026-10-07/usb-root-backup`.

## Scope and risk controls

The position module already owns the one existing TimeStretch deck-stream
observer. This change adds no hook, player symbol, master-bus tap, flash write,
firmware update, settings write, or endpoint that accepts commands from the
host. The module copies at most 512 mono samples per callback from an even-frame
decimation of the post-tempo deck stream into one of 32 fixed slots per deck.
Buffers total about 67 KiB. A busy producer, full ring, or oversized native
block drops audio instead of waiting. The callback does no allocation, socket
I/O, lock acquisition, or unbounded retry. It never changes the player's PCM.

A separate worker sends PCM16LE at 22,050 samples/s over UDP 50127 on the
existing USB-B link, with deck, reader generation, source frame, sequence and
drop count. Each datagram is at most 1,056 bytes. The send is nonblocking; a
stalled or absent host cannot stall the audio callback. Position telemetry
remains at 20 Hz on 50124. No master/fader/EQ signal is claimed: these are
per-deck post-tempo samples before the mixer, not the audible final mix.

The inherited privileged startup still stages the player image in RAM and
restarts `rbp`, then installs guarded hooks. An unknown firmware hash is refused
before that mutation. The source audit found no direct path to firmware,
bootloader, flash or persistent settings. Residual uncertainty remains in the
closed-source player ABI, callback timing, USB-B stability, and startup/recovery
behavior. A freeze or dropout calls for stopping the test and restarting with
the mod USB absent; that stock-return procedure is not hard-brick recovery.

## Verification before on-deck test

- Strict ARM build succeeded; no unexpected imported symbols.
- Independent ARM hook rebuild matched the packaged hook byte-for-byte.
- Decrypted package audit matched all 19 expected files and their source/build
  bytes; no unexpected imports or runtime files.
- Focused audio, position, bridge, TD gateway and symbol tests: 25 passed.
  Extracted ARM module imports: four passed with the configured LLVM toolchain.
- Host UDP loopback decoded a generated packet into a WAV and index.
- The full repository suite ran 496 tests but did not pass in this environment:
  old tests collided with the already-running diagnostic UDP ports, some used
  `/usr/bin/clang` rather than configured LLVM, and Pillow was absent. These
  failures are not evidence of a working audio stream or an audio regression.
- Fresh SOUND_PRO scan found 238 tracks; 236 valid phrase maps. Installer
  verified the current PDB and analysis hashes, backed up the two root files,
  replaced only `autoexec.bin` and `rx3-mod-manifest.json`, and read back exact
  package bytes. The PDB hash stayed unchanged. SOUND_PRO was safely ejected.

## First physical capture and correction

The first image ran with Deck 1 playing. A 30-second host capture received
6,127 packets with no wire sequence gaps; packet `dropped` remained at 61,672
throughout the capture. Now Playing delivered 1,517 packets (max 31.9 ms gap)
and position diagnostics delivered 594 (max 58 ms gap). The captured source
positions revealed **two interleaved, overlapping render sequences** roughly
2,159 source frames apart. A naive concatenation produced 61 seconds of PCM
in 30 seconds of wall time, so it cannot honestly feed beat/onset detection.

The correction keeps one forward source-position progression and accepts a
large rewind for cue/loop. Replaying the exact recorded block positions through
the filter retains 30.04 seconds of PCM in 30 seconds of wall time. It drops
3,526 overlapping packets without calling them transport or queue loss. This
also lowers expected USB-B traffic. The corrected ARM image passes the source
audit and 29 focused tests. **It still needs its own physical run.**

## Physical acceptance still required

Insert SOUND_PRO in the RX3, boot the selected runtime, and play a track while
the host records UDP 50127 with `scripts/receive_live_audio.py`. Check both
deck WAV/index files, sequence gaps, reported ring drops, Now Playing and
position cadence, and audible playback. Then test pause, cue, track load and
two-deck playback; a short passing run does not establish gig readiness.

The receiver is a bounded bench recorder, not yet the TD feature analyzer. It
does not send commands to the RX3. Audio features should be computed on the Mac
after packet receipt; packet generation and track identity must be matched to
the existing semantic stream before driving visuals.
