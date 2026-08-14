# Vocal and instrumental controls, firmware 1.19

Splits a track into vocal and instrumental from a prepared sidecar. Volatile:
the code is preloaded by the [performance core](../../core/1.19/README.md) and
nothing is written to NAND.

Slip Loop pads 7 and 8 are independent instrumental and vocal toggles, and the
`STEMS` tab exposes the same two toggles per deck on screen. Both pads blink at
one second on, one second off while a sidecar is being read, in step with the
on-screen toggles, and hold their colour once the payload is resident. Without a
matching sidecar, audio and pads follow the stock path.

## How it works

A basename-matched sidecar is associated in `PcmReader::load` and applied in
`PcmReader::getStreamAt`. The instrumental is the full mix minus the vocal, so
both signals must come from the same decode path to keep phase, delay and gain
aligned.

The mix stays in `getStreamAt` on purpose. That function is a random-access read
of the ring buffer — shared with the BPM and waveform analysis scan, and mostly
out of order — but the mix is addressed by absolute frame position, so re-reads
and jumps cost it nothing. [Key shift](../../keyshift/1.19/README.md) carries a
sequential cursor and therefore cannot sit there.

Stems are copied into anonymous RAM before publication to the audio thread and
then made read-only, so removing the drive after a completed load leaves no
active file mapping, and an accidental write from the audio thread fails
loudly instead of corrupting samples. `int16` and `float32` payloads are
supported. `PcmReader` works at 44,100 frames per second regardless of the source
file's rate, so the sidecar frame index stays in one time domain.

## USB layout

```text
autoexec.bin
RX3_STEMS/
  Artist - Title.rx3stem
```

The sidecar basename must match the audio basename exactly.

## Files

- `manifest.json`: declares the feature's only module dependency, `core`.
- `module.sh`: exports `RX3_STEMS_DIR` so the core switches the feature on.
- `rx3_stems_decl.h`: private sidecar format and per-deck state.
- `rx3_stems_feature.h`, `rx3_stems_panel.h`: implementations of the core
  lifecycle, hook-group and UI contracts.
- `test_regressions.py`: guards for hardware-confirmed behaviour.

The core installs this feature's stream, pad and LED hook group only when the
module is enabled. A guard failure removes that group without removing Key
Shift or its DSP state.
