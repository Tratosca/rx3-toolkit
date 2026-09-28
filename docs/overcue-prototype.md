<!-- SPDX-License-Identifier: MPL-2.0 -->
# OverCue shared USB prototype

## Desktop output policy

The preparation screen keeps RX3 packages in all cases. Its optional OverCue checkbox adds `CDJMODS` files on the computer after the RX3 package has been saved. Leaving it unchecked produces only RX3 files and does not remove any OverCue files already on the drive. The checkbox never enables the experimental RX3 reader below: normal playback uses `.rx3stem` with no 96 kHz conversion.

Additional storage is estimated for the selected playlist at 2.5 MB per second (decimal MB), rounded up to whole MB. This rounds the measured 74,935,926 bytes for the thirty-second nonzero-drums fixture to 75 MB. It excludes native packages and source music; it describes the full extra selection, not the bytes remaining to copy when an export already exists. Unknown track durations produce an unknown estimate, not a falsely complete total. Actual size depends on compression; free-space checks use uncompressed sizes with page overhead, separately from the estimate.

The desktop job automatically locates the native helper in the local build or packaged application and uses the bundled, hash-verified reference table. `RX3_OVERCUE_HELPER` and `RX3_OVERCUE_COEFFICIENTS` remain optional overrides. Build the helper with `make overcue-audio` before packaging to include it; a missing helper or invalid table makes the checkbox unavailable, with no silent fallback to approximate preparation. Only WAV, AIFF and FLAC sources are accepted for now. The destination must contain a matching rekordbox export: IDs come from its `export.pdb`, never from an unrelated XML library. CDJ-3000 compatibility and nonzero-drums PCM identity remain pending the acceptance described below.

Existing native stems are reused, including when compatibility is added later. If OverCue export fails or is cancelled, saved RX3 packages and their manifest remain usable. A failed extra export is reported separately; immutable bundle publication still writes the index last. Cancellation owns the native helper and FFmpeg processes. The desktop option does not deploy firmware or start audio playback.

The complete desktop job was exercised on a disposable local USB copy with the thirty-second nonzero-drums fixture. It returned one existing RX3 result, added 74,935,971 bytes under `CDJMODS`, and left the native package SHA-256 unchanged. Separation was guarded against being called. All seven output PCM streams and gain parameters match the earlier standalone Toolkit export. This checks job integration, not a new Desktop oracle or CDJ playback. Owner-local evidence is in `local/research/overcue-option-20260928/result.json` and `pcm-comparison.json`.

## Earlier reader experiment

This is an opt-in experiment, not a hardware-supported release. Its scope is
stems data interoperability: one `CDJMODS` bank for OverCue on CDJ-3000 and the
RX3 Toolkit reader. No OverCue firmware is installed on the RX3.

The contract is the public [OverCue format](https://github.com/OverCue-gg/overcue-stems-format/tree/1eddcb70093326146ac776e232dc7c827785d79f),
revision `1eddcb70093326146ac776e232dc7c827785d79f`. Keep the seven stereo
PCM16 roles at 96000 Hz on USB. Replacing them with 44100 Hz files would break
that contract. The RX3 worker verifies and decompresses pages, then resamples
into a bounded RAM cache at 44100 Hz (147/320, 192-tap polyphase filter).
The callback only reads cached frames; it does no filesystem or zlib work.

## Reader and controls

`mod/modules/stems/overcue/` implements the index, page reader, SHA-256,
resampling and two-deck cache. Exact source paths select entries; numerical
IDs from different libraries are not treated as interchangeable. Optional
source hashes, authenticated page tables and each consumed page are checked.
Paths cannot escape the bank through dot components or symbolic links.

INST/VOCAL/DRUMS choose the seven prepared roles. All off is silence. Gain
sliders are disabled for this prototype. A missing cache block leaves the
native buffer intact, so a seek or uncached selection can briefly restore the
original mix. Selection recovery uses a 256-frame interpolation from the last
sample, not a complete dual-role crossfade. These behaviors need refinement
before performance use. This opt-in mode takes precedence over legacy stems;
an unmatched track plays natively. It currently targets USB1.

Build separately, so ordinary and experimental objects cannot be confused:

```sh
make hook OVERCUE=1 BUILD_DIR=build/overcue-prototype \
  PYTHON=.venv/bin/python CC=/opt/homebrew/opt/llvm/bin/clang
```

In the sibling emulator repository:

```sh
python3 -m tools.rx3_machine.cli --profile stems --overcue-prototype \
  --media 2048 --media-source /path/to/copied/library --no-autoexec --hold \
  --output outputs/rx3-machine/overcue-test
```

The runner supplies `RX3_OVERCUE_ROOT=/media/usb1/sda1` and copies `CDJMODS`.
It never imports a source USB's autoexec. The prototype is not enabled in the
normal Toolkit installer or application UI.

## Toolkit export

The CLI reuses an existing current VOCAL+DRUMS package; it does not separate
the track again. Original, vocals and drums reconstruct the seven selections,
with a common true-peak headroom gain and downward per-selection loudness
trims, before PCM16 encoding and paging.
The original track and its library database are preserved. Bundles are written
before atomic index replacement, and existing unrelated index entries survive.
The writer lock serializes this CLI only, not OverCue Desktop: do not run both
writers on the same bank concurrently.

```sh
.venv/bin/python -m app.stems.overcue --drive /path/to/copied/library \
  --track '/Contents/Artist/Album/Track.aiff' --track-id 2 \
  --package /path/to/Track.rx3stem
```

The source hash and decoded timeline must match. Initial export accepts only
WAV, AIFF and FLAC. RGB preview waveforms are generated from the final role
PCM. Lossy encoder delay, full OverCue analysis export and
OneLibrary entry creation are not implemented. Existing OneLibrary entries
for the same path are updated. Thus format conformance alone is not a claim
of complete OverCue Desktop or CDJ-3000 integration.

## Evidence, 2026-09-28

- Eight host tests compile the same C reader and check all masks, stereo,
  page crossings, arbitrary seeks, ultrasonic rejection, corrupt data,
  Unicode, path rejection, two asynchronous decks and Toolkit export math.
- The official `verify_usb.py` accepts all seven synthetic roles, bundle
  `07c1590fcae4379a`.
- ARM firmware run `overcue-prototype-20260928-r2`: current core activated,
  readable 1280x800 framebuffer, live stem buttons and USB bank loaded;
  machine report passed. Core SHA-256:
  `6c3e0d05cf63c6b752209db8b9f75a4324d674e47c0e013bb0d6bbf5137357e3`.
- Captured master audio contains precisely the selected 1/2/3 kHz fixture
  tones for all seven masks; unselected tone amplitude is at least 55 dB below
  selected tone amplitude in these captures. All-off capture is exactly zero.
  Firmware samples in this capture use signed 24-bit values in the low bits
  of 32-bit words; sign extension is necessary before spectral analysis.
- Current repository checks: 351 Toolkit tests (two skipped), 72 emulator
  tests (one skipped), ordinary and opt-in ARM builds, publication preflight.
  The initial baseline had three unrelated failures; other working-tree
  changes occurred during this session. No claim that this prototype fixed
  those failures.

Owner-local evidence lives in `local/research/overcue-prototype-20260928/`
and the sibling emulator's `outputs/rx3-machine/overcue-prototype-20260928-r2/`.
The later real-bank run below includes generation-race hardening, bundle
identity verification and reduced logging compared with the captured r2 core.

## Real OverCue Desktop export

OverCue Desktop 2.1.9 (Apple Silicon) was downloaded from the official release;
installer SHA-256 `ef4928d241d017adda79d763539adc02ba7a0aeb24a1a999083da221fd43e019`
matches the published checksum. A disposable FAT32 image contains a copy of
the owner's library. Desktop generated and packaged DO IT with its own local
engine and displayed `On USB`. No CDJ firmware installer was generated.

Bundle `32ad10d965c3e9af` has 34165479 frames at 96 kHz and zero reported
latency padding. All seven roles pass the official validator and the same C
reader. The unmodified `CDJMODS` copy was booted in the RX3 firmware emulator
(`outputs/rx3-machine/overcue-desktop-20260928/`). Its report passes; core SHA-256
is `72b85e722dca96da82c16a172637824d0ac3298238e9abfcac9150bb9b1eede3`.
Deck 1 controls alter captured audio and all-off produces exactly zero. Both
decks load the bank and log successful cached rendering. The master-ring
capture did not establish deck 2 audibility: both-deck audio routing remains
an explicit unverified item. Startup/selection cache misses occurred, consistent
with the documented native fallback; this is not glitch-free playback proof.

The reverse export reused the existing Toolkit package, without separation,
and produced bundle `e132aa1cceaee984`. The official validator accepts all seven
roles. However, Desktop 2.1.9 still displays `Not processed` and disables stem
preview for it. Supplying the exact OneLibrary ID from the matching official
export, a complete descriptive manifest, and truthful Toolkit provenance did
not resolve that result. The subsequent [static analysis](overcue-static-analysis.md)
identified an additional exact `full-mix-ceiling/2` policy check and separation
identity handling in Desktop. Its recognition function does not require
waveform files; the earlier waveform hypothesis is not supported by that path.
Do not equate format-validator success with reciprocal application
or CDJ-3000 support. Those diagnostic metadata edits exist only in the
`toolkit-overcue-test.img` fixture; the writer still creates no new OneLibrary
mapping automatically.

The synthetic fixture retains library names and old analysis waveforms as
navigation placeholders. Its audio is test tones, not those named recordings;
it does not validate waveform accuracy. TCG with a divided transport clock
cannot prove RX3 CPU deadlines. Physical RX3 playback, pitch/key/loops/scratch,
USB removal, real-time cache behavior, and reciprocal CDJ-3000 playback remain
unverified. The real export establishes OverCue-to-RX3 emulator ingestion;
reciprocal Desktop/CDJ validation and physical RX3 measurements remain open.

## Adaptation: reciprocal recognition and NEON

The writer identifies reused stems as `manual/rx3-toolkit/prepared-stems/1`.
It measures all seven floating-point 96 kHz selections with FFmpeg EBU R128
at 100 ms intervals, then limits each selection against full mix using
momentary, short-term and gated integrated loudness, plus true peak. Gains
never increase a selection. Negative trims include the 0.1 dB margin observed
in Desktop 2.1.9; integration recomputes the absolute and relative gates after
attenuation. Common headroom and the seven gains are recorded in the manifest.
The complete export uses `full-mix-ceiling/2`; generic precomputed fixture
publication retains `precomputed/1` and cannot claim that processing.

This is an independent implementation of the ceiling policy, not byte-identical
reproduction of Desktop. FFmpeg measurements have rounded metadata; peak and
loudness bounds include conservative rounding margins. The common peak target
is 0.95. The resampler and PCM quantization also differ from Desktop. Digital
silence can yield NaN from FFmpeg's rolling energy subtraction: the adapter
accepts this only after reading and verifying the entire window is zero.
Nonfinite PCM and undefined measurements on nonsilent windows reject export.

The reader converts input PCM16 to float once per block and explicitly uses
four-lane NEON for the unchanged 192-tap filter. Define `RX3_OVERCUE_SCALAR`
to build the scalar reference. ARM disassembly confirms `vld2.32` and vector
`vmla.f32`; host tests compare the kernels with an absolute tolerance of 1e-6.
The extra input staging memory is 36 KiB per deck.

`rx3_overcue_stats()` supplies a nonblocking cumulative per-deck snapshot:
worker CPU and monotonic elapsed microseconds, measured blocks, maximum block
times, clock failures, cache hits/misses and published blocks. Each block holds
4096 frames at 44.1 kHz (92.88 ms). Measurements include page reads, integrity
checks, decompression and conversion; bank opening is outside these timings.
Every 256 published blocks, the worker logs maximum block times and cache
counters. No timing or logging is added to the audio callback. `clock_gettime`
is exported by the firmware's librt, already a dependency of rbp.

A three-run M1 Pro benchmark over 300 seconds of the same official OverCue bank
measured median SRC CPU time of 0.533 s (NEON) versus 1.825 s (scalar), and total
reader CPU time of 1.452 s versus 2.730 s. That is about 3.4 times faster for SRC
and 47 percent less total CPU, on this host only. These numbers are not RX3 CPU
percentages. Owner-local measurements: `local/research/overcue-static-20260928/`.

The reciprocal fixture now appears `On USB` in Desktop 2.1.9 without another
separation. Its Device Library and OneLibrary databases were hash-identical to
the official reference bank; the existing OneLibrary correspondence was reused
by exact source path and hash. New OneLibrary mapping discovery remains outside
this prototype. The seven roles of bundle `e7c4dc4ced764e30` pass the official
validator. The writer additionally creates six minimal PMAI/PWV5 RGB detail
files from the final PCM, keeping every original Rekordbox analysis untouched.
These files are for preview; full CDJ analysis parity is not claimed.

For comparison, Desktop manually imported the same Toolkit vocal and drum PCM
plus the reconstructed harmonics. Its timing checks passed, and it published
bundle `31b7b11aa0e95924` on a disposable 4 GiB image. Per-selection gain
agreement: four unity gains match exactly, instrumental and harmonics differ
by -0.00223 dB, vocals-harmonics receives an additional -0.102 dB here. The
common headroom also differs (0.717794 here versus 0.754839 in Desktop), as
expected from our 0.95 peak target and measurement/resampler differences.
This is evidence of a conservative compatible policy, not numerical identity.

After adding the six RGB files, Desktop displayed the waveforms and enabled
all three selection buttons. Vocal-only USB preview was started, its time
position advanced and the two other selectors remained off. This establishes
Desktop recognition and preview UI operation; CDJ-3000 playback is untested.

The NEON firmware run `overcue-neon-20260928` activated the current core and
rendered both loaded decks from the official OverCue bank. Captured deck 1
full mix and vocal are nonzero; all-off is exactly zero. Selection changes and
CUE/restart produced cache misses, then resumed cache hits. Both decks' worker
logs and a live framebuffer were checked. Master routing for deck 2 and
physical tempo/loop/scratch deadlines remain unverified. TCG block timings
must not be interpreted as physical RX3 utilization.

Final focused checks: 17 tests pass (reader, loudness, preview chunk validation
and documentation hygiene). The complete Toolkit suite passed 356 tests with
two skips before the preview addition; the affected export tests were rerun
after it. Publication preflight passes for 364 candidate files. No hardware
session, deployment or publication was performed.

## Autonomous native PCM prototype

The optional native helper now replaces the approximate FFmpeg resampling, loudness measurement and quantization steps. Separation and reconstruction of the input roles still use the existing Toolkit package. The helper runs offline on the preparation computer; this change does not add work to the RX3 audio callback. Build and coefficient provisioning requirements are in `native/overcue-audio/README.md`.

```
make overcue-audio
python -m app.stems.overcue --drive COPY_OF_USB \
  --track '/Contents/path/to/track.aiff' --track-id 2 --package TRACK.rx3stem \
  --native-helper build/overcue-audio/release/rx3-overcue-audio \
  --coefficients LOCAL_PROFILE.f32
python -m scripts.overcue_compare REFERENCE_BUNDLE TOOLKIT_BUNDLE
```

The coefficient profile is bundled and verified by SHA-256; `--coefficients` is an optional override when a native helper is selected. No OverCue process, executable or installation is used during this export. The native path remains opt-in in the CLI; its default exporter retains the earlier approximate implementation. The desktop compatibility checkbox always uses the native path.

On 2026-09-28, the native export from the current VOCAL/DRUMS package reproduced the manual Desktop 2.1.9 reference bundle `31b7b11aa0e95924`. All seven expanded PCM SHA-256 values match. The comparison validated every compressed page and complete PCM hash independently, and found zero differing samples in all roles. Each role contains 34165479 stereo frames (136661916 PCM bytes). Common headroom rounds to `0.75483936` in float32; instrumental and harmonics gains round to `0.9881239`, with unity gains for the other five roles. Those values were computed by the Toolkit, not supplied from the reference manifest. The resulting content-derived bundle identifier is identical.

This reference has silent drums: it originated from the emulator's visual pad fixture, whose drums file was zero-filled, not from a real drum separation. It consequently covers fewer independent signals than seven arbitrary selections. Cancellation with three nonzero components, short signals and other source rates still need independent Desktop fixtures. Native structural tests cover phase ordering, floor frame counts, signed quantization, partial measurement windows and nonfinite rejection. Numerical agreement on this macOS fixture is not evidence of identical results on Windows or Linux. A subsequent nonzero-drums bank was converted on the physical RX3; see [conversion measurements](overcue-rx3-benchmark.md) for results and the remaining Desktop-reference limitation.

The 1:1 result above concerns PCM, timeline and gain parameters. Compressed PGZ bytes/page tables and preview analysis files differ; creation timestamps and writer provenance also differ by design. The comparator reports PGZ and preview equality separately, and does not label those files identical. Its status 0 means verified audio identity, 1 means differences, and 2 means an invalid or unreadable bundle. It never plays audio. No physical RX3 audio playback or CDJ test has been performed for this native preparation path.

Validation for this change: 27 focused tests pass with the native helper built, publication preflight passes for 372 candidate files, and `git diff --check` is clean. The complete suite was not rerun for this offline prototype addition. No audio playback was started during the native comparison work.
