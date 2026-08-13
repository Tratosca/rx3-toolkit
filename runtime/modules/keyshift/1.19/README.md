# Per-deck key shift, firmware 1.19

Shifts each deck by up to twelve semitones from the `KEY` tab. Volatile: the
code is preloaded by the [performance core](../../core/1.19/README.md) and
nothing is written to NAND.

The XDJ-RX3 has no key shift, and the absence is real rather than hidden — a
reachability census over rbp's 17,745 functions found no dormant subsystem. So
this module provides one.

## Two engines, chosen by direction

Firmware 1.19 does contain a complete granular pitch shifter: the Beat FX
`Pitch` effect, `mixerengine::BeatEffectPitch`. It is excellent in one direction
and poor in the other, and this module's own shifter is the mirror image, so
each direction gets the engine that wins it.

Share of output energy left on the note, 440 Hz tone:

| semitones | −12 | −7 | −5 | +5 | +7 | +12 |
|---|---|---|---|---|---|---|
| rbp's `BeatEffectPitch` | — | 99.9% | 99.9% | 52.7% | **15.8%** | 84.6% |
| this module's shifter | 43.6% | 69.4% | 99.7% | 99.0% | **97.3%** | 93.8% |

The asymmetry is structural. Raising pitch has to repeat material — 0.414 s of
source per second of output at +6 semitones — and that is where grain splices
show. Lowering pitch skips material instead, which is far more forgiving.

Both are driven at the exact equal-tempered ratio, and the result is within
±0.7 cents across the range.

## Where the pitch stage sits, and where it must not

On `dsp::TimeStretchScratch::operate` and, while Master Tempo is on, on
`dsp::TimeStretchFGPR::operate`. Those are the deck's playback blocks, in order,
64 to 512 frames at a time. The two are mutually exclusive, which is why hooking
only the first made the shift vanish under Master Tempo rather than sound wrong.

It deliberately does **not** sit on `common::PcmReader::getStreamAt`. That is a
random-access read of the ring buffer, shared with `playengine::Player`'s BPM and
waveform analysis scan: measured on hardware, only 13.6% of its calls continue
where the previous one stopped, two thirds re-read an overlapping position and a
fifth move backwards. A shifter with a sequential grain cursor cannot live there,
and the audible result was a stutter.

Stem mixing, by contrast, is addressed by position and so is indifferent to that
access pattern, which is why it stays in `getStreamAt`.

## Driving rbp's engine

Through `mixerengine::BeatEffect::adjustParameter`, the base-class entry the
stock mixer uses. Two parameters matter:

- **level/depth**, fixed at `0.5`. That is the exact unity point of the effect's
  percentage curve, where its shift speed equals `percent / 100` and the mix is
  fully wet. The constructor leaves it at zero, which is total bypass: the effect
  runs and never moves a sample. This was the reason key shift appeared dead.
- **percentage**, carrying the semitone. `-50 .. +100` covers precisely
  `-12 .. +12`. Percentages are integers in this firmware, so each semitone uses
  the closest one; worst case is −9 semitones, 13 cents flat.

`initialize()` sizes its working buffers from the frame count at `+0x10` alone,
so that field must cover the largest block the hook can pass, not the audio
device's block size.

## This module's shifter

`rx3_pitch_shift.h`, self-contained: no libc, no libm, no allocation. Two read
heads walk a history ring at the pitch ratio, half a grain apart, each windowed
by a Hann envelope; reads are cubic-interpolated. Every design value in it was
measured, and the file records what each alternative cost.

The three findings worth repeating:

- **splices are aligned by correlation.** Without it, crossfading segments whose
  phases disagree forces a phase slew, and a phase slew is a frequency error: the
  whole shift came out at 97.9% of what was asked, 36 cents flat at −12.
- **the grain depends on direction**, 512 frames up and 2048 down. Against an
  impulse train of eight hits at +7 semitones, a 2048-frame grain returns
  sixteen — every hit doubled — and 512 returns nine.
- **the crossfade stays amplitude-complementary.** The power-complementary sine
  removes about a decibel of pumping on sustained noise and costs four spurious
  onsets, which is the worse trade.

Two artefacts remain and are inherent to time-domain shifting: about 2 dB of
level ripple above the input's own on broadband material, and occasional
transient doubling when raising pitch. Removing them needs a phase vocoder.
Cost is not the obstacle — the current stage measures 4 µs against a 1451 µs
block budget, with correlation bursts at 314 µs.

## Measuring it

Both engines are measured off the device, and the two harnesses print the same
columns so they can be read side by side:

```sh
.venv-re/bin/python tools/rx3_firmware/emulate_pitch.py <rbp> --quality
.venv-re/bin/python tools/rx3_firmware/measure_shifter.py
```

The first runs rbp's real ARM code under Unicorn; the second compiles this
module's shifter for the host.

## Files

- `manifest.json`: declares the feature's only module dependency, `core`.
- `module.sh`: exports `RX3_KEYSHIFT` so the core switches the feature on.
- `rx3_keyshift_decl.h`, `rx3_keyshift.h`: private state and DSP.
- `rx3_keyshift_feature.h`, `rx3_keyshift_panel.h`: implementations of the
  core lifecycle and UI contracts.
- `rx3_pitch_shift.h`: the shifter, shared with the host harness.
- `test_regressions.py`: guards, each one a measured fact.

Its per-deck pitch objects, pending state and shifter history are private. Deck
identity crosses the core boundary as an index; no Key Shift state lives in the
Stems context.
