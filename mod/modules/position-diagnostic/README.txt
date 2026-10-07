Playback position diagnostic — experimental, firmware 1.19 only

Explicit module selection: position-diagnostic (requires core + now-playing).
Disabled by default. Do not select other performance modules for the first test.
Position telemetry has one-track hardware validation. Live audio is a new
bench-only candidate and has not yet passed an on-deck run.

What changes on the deck
Uses the existing shared TimeStretch audio observer and PcmReader::load identity
hook. Core now installs the identity hook for an audio-only client before its
UI-free early return. No extra UI hooks are enabled. Existing executable and
instruction guards remain. The prepare hook additionally requires the exact
upstream-recorded firmware 1.19 player hash. An early read-only path/mount guard
now refuses layouts that cannot establish volatile write destinations. A failed identity install stops the modules and
runs the existing cleanup path. With only Now Playing selected, this diagnostic
is not started and the new identity hook is not requested.

The callback publishes position scalars under a one-attempt atomic gate and
copies a bounded, decimated mono PCM block to fixed memory for host analysis.
Contention or a full queue drops the block. No callback I/O, allocation, clock
lookup or wait. A worker sends position at <=20 Hz on UDP 50124 and PCM16LE
at 22,050 samples/s on UDP 50127 to the USB link-local broadcast; nothing
listens for commands. Existing Now Playing UDP 50123 is unchanged. No firmware,
bootloader, settings or audio writes added.

Wire data
JSON type=position-diagnostic, version=1, sequence=uint32, units=unverified.
Two deck entries numbered 1/2:
- readerGeneration: increments on the existing reader's will-load notification.
- sample: null until observed in this generation; otherwise generation,
  observation (uint32 counter), rawPosition (signed 32-bit), frames (uint32).
Repeated observations are exported again; the host tracks their age. They do
not prove current playback or audibility. Values wrap at their integer width.
No pointers, titles or track IDs leave through this position message. The
separate RX3A binary packets on 50127 include deck, reader generation, source
frame, packet sequence, drop count and up to 512 mono samples. The host must
join them with Now Playing and reject a mismatched generation.

Reader generation is not a rekordbox ID or source-media ID. It is deliberately
not joined with the independent Now Playing feed. The existing core load hook
publishes reader identity without interpreting the native load return code;
we have not verified its failure semantics. Unload may leave a last observation
until reload, so consumers must not use this stream alone as loaded/play state.
Late/in-flight callbacks, reused reader pointers, audible latency, render-ahead,
position units and pitch/master-tempo behavior require physical validation.
No exact source position/phrase mapping should be enabled based on this probe.

Recovery / limitations
Preserve the existing USB package before replacing it. Use a stopped-player,
cold-start test and a clean stock restart afterward. No live library unloading.
Upstream audio-stage release uses a drain without a timeout and retains a hook
if restoration fails. This diagnostic does not strengthen that inherited
teardown or prove recovery from arbitrary crashes. Volatile privileged hooks
still can crash or interrupt playback; this is not a no-risk certification.

See testing/rx3-1.19/POSITION-TEST.txt for the controlled test procedure and
scripts/position_diagnostic.py for position. See
docs/development/RX3-LIVE-AUDIO-USB-B-AUDIT.md and
scripts/receive_live_audio.py for the receive-only audio bench.
