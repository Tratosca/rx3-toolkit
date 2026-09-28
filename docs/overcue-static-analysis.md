<!-- SPDX-License-Identifier: MPL-2.0 -->
# OverCue reverse interoperability and resampling cost

Analysis date: 2026-09-28. This investigation inspects OverCue Desktop 2.1.9
Apple Silicon statically. It does not modify or execute its recognition code.
The CPU experiment executes our reader on the host, not on an RX3.

## Identified consumer

Later prototype results, including the native PCM comparison, are recorded in `docs/overcue-prototype.md`. Historical statements about the earlier writer below describe the implementation at the time of the initial analysis.

Official installer SHA-256:
`ef4928d241d017adda79d763539adc02ba7a0aeb24a1a999083da221fd43e019`.

`Contents/MacOS/overcue-desktop` (26786816 bytes), SHA-256:
`ff949741aabe49e3071ff1cdf05e4dd71ccfad258c5725d0b586d76b34e622a5`.

The distributed Mach-O retains Rust function symbols. `llvm-objdump` and
`nm` expose the relevant functions without patching the program. Addresses
below are preferred virtual addresses in this particular binary.

## Why valid PGZ files still show Not processed

`overcue_core::bundle::is_prepared` starts at `0x1005e0310`.
Its successful path requires more than the public format validator:

- Locate an indexed entry for the requested track; check track/path and
  optional current separation identity. The identity comparison includes a
  last-slash-component comparison at `0x1005e0478..0x1005e0520`.
- If indexed `source_sha256` exists, hash the original source and compare it:
  lookup at `0x1005e0578`, hash call at `0x1005e072c`.
- Require the three-part state (`0x1005e07a8..0x1005e07b8`).
- Require the **exact** string `full-mix-ceiling/2` in `loudness_policy`:
  key lookup at `0x1005e07d0`, type/length checks at `0x1005e086c`, and literal
  byte comparisons at `0x1005e0888..0x1005e08c0`. A missing or different policy
  returns false, even when the audio and its hashes are valid.
- Require the seven `stems-sidecar-ROLE.s16le.pgz` files to exist:
  role table `0x101177470`, call at `0x1005e0930`, filename construction and
  `Path::is_file` in the closure at `0x1005db8f4`.

The role table contains vocal, instrumental, drums, harmonics, vocals-drums,
vocals-harmonics and full-mix. There is no waveform-file or advisory-manifest
read on this function's successful path. Missing waveforms were a hypothesis
in the previous prototype report; they are not the cause established here.
This does not prove that no other playback/display path needs them.

`overcue_core::library::load` examines the indexed separation prefix at
`0x1005eee90..0x1005eeecc`. A literal `manual/` prefix branches to
`0x1005eef8c`, which supplies an empty expected separation identity to
`is_prepared`. The normal path supplies the current engine identity.
`overcue_desktop_lib::run_generation` has the analogous special case at
`0x1002d12c4..0x1002d12e8`. External imported stems therefore have an existing
category; they do not need to pretend to originate from OverCue's model.

Our writer currently emits `rx3-toolkit/prepared-stems/1` and
`rx3-toolkit/common-peak-ceiling/1`. In particular, the latter provably fails
this consumer's literal policy check. Adding a manifest or OneLibrary mapping
cannot remove that rejection. The public format validator ignores these
application-policy requirements, explaining the earlier apparent discrepancy.

## Correct route for the reverse export

Use the external-import category (a distinct `manual/rx3-toolkit/...` identity,
retaining the actual model/package provenance in the manifest), and implement
and verify the full-mix ceiling behavior before declaring its policy marker.
This is a candidate compatibility route identified statically, not a newly
validated Desktop or CDJ-3000 export.

Changing the policy label alone would make an unsupported claim about the
PCM. OverCue's `loudness::measure_padded` at `0x1005ef684` constructs an EBU R128
meter and calls window, momentary and short-term loudness routines.
`loudness::gains` at `0x1005f0480` compares each of six selections against the
full mix, bounds gains downwards, checks corresponding measured windows and
recomputes gated integrated loudness. The inspected path includes a -70 LUFS
floor, a 0.1 LU integrated margin and a 32-step search when required. It is
not equivalent to our current common peak normalization.

An implementation needs numerical fixtures covering silence, opposing stem
phases, quiet passages, transitions and tracks shorter than the measurement
windows. Compare the output gains and selected-role levels against genuine
OverCue exports. Recompute PCM hashes, table hashes and the bundle identity
after applying gains. Then test Desktop recognition and preview, before
claiming reciprocal CDJ playback. The exact complete loudness algorithm has
not been ported in this analysis.

## Current runtime CPU work

The reader converts only the selected complete role per deck, not seven
roles simultaneously. At normal playback speed, 44100 output frames/second,
two channels and 192 taps give:

| Work | One deck | Two decks |
| --- | ---: | ---: |
| Multiply-accumulate pairs per second | 16,934,400 | 33,868,800 |
| Floating operations, multiply and add counted separately | 33,868,800 | 67,737,600 |
| Repeated signed-integer to float conversions per second | 16,934,400 | 33,868,800 |
| Expanded 96 kHz PCM byte rate, before boundary rereads | 384,000 B/s | 768,000 B/s |

The tested ARM core SHA-256 is
`72b85e722dca96da82c16a172637824d0ac3298238e9abfcac9150bb9b1eede3`.
Its inner filter loop at `0x351e4..0x35218` is **scalar VFP**, with 14 ARM/VFP
instructions per tap, including two `vcvt.f32.s32` and two `vmla.f32`.
That is about 118.54 million inner-loop instructions per second per deck;
it excludes frame setup, paging, zlib, SHA-256, copies and synchronization.
Instruction count is not cycle count or a CPU percentage. The build's NEON
flag does not make this particular loop vectorized.

A 4096-frame output block represents 92.88 ms of playback. For two concurrent
decks, the shared worker must prepare both blocks within that interval on
average, with enough margin for seeks, cache misses and the firmware's other
work. Faster playback increases the rate at which new source blocks are needed.
Random seeks and toggles can cause extra work beyond sequential playback.

## Measured host benchmark

Machine: Apple M1 Pro, 10 logical CPUs, 16 GiB RAM. Native Apple clang `-O2`;
same reader source with timing instrumentation around the existing filter,
page fetch/decode and SHA checks. Three sequential runs of 300 audio seconds,
full-mix role from real OverCue bundle `32ad10d965c3e9af`, 4096-frame blocks.
CPU time uses `CLOCK_PROCESS_CPUTIME_ID`; the worker thread is not launched.

| Stage | Median CPU seconds per 300 audio seconds | Equivalent fraction of one host core at 1x |
| --- | ---: | ---: |
| Resampling arithmetic | 1.959385 | 0.653% |
| zlib inflate | 0.269178 | 0.090% |
| Expanded-page SHA-256 | 0.590131 | 0.197% |
| Entire conversion/read path | 2.848630 | 0.950% |

The total includes other work; stages are independently timed and not an
exact additive accounting. Each run decoded 921 pages, including boundary
rereads. Source identity/table opening costs another median 0.315329 CPU
seconds once per load. Filter initialization costs approximately 0.0004 s.
Whole-process elapsed times were 3.25-3.32 s, including opening and scheduling.
The files were on local storage with warm OS caches, not a physical RX3 USB.

These are host measurements, not RX3 percentages. Cortex-A9 execution,
scalar VFP scheduling, clock frequency, memory hierarchy, USB latency and
concurrent firmware load differ. QEMU TCG timings cannot calibrate them.
No honest RX3 CPU percentage is available without a measurement on that unit.

## Recommendation

Keep the 96 kHz interchange bank. Before hardware acceptance, measure worker
thread CPU time, block preparation percentiles and misses under two-deck
playback, seeks and tempo changes on the RX3. Optimize the filter with explicit
NEON and convert the input block to float once, rather than repeating casts
for every tap. Preserve the current scalar version as a numerical reference.
Do not reduce the tap count without passband/alias rejection measurements.

If the measured hardware margin is inadequate, add an optional 44.1 kHz RX3
cache prepared by the Toolkit; the shared 96 kHz bank remains intact for
OverCue. This moves conversion to preparation at the cost of extra USB space.

## Reproduction and local evidence

Owner-local artifacts are under `local/research/overcue-static-20260928/`:
`make-bench.py`, generated `bench.c`, native `bench`, `cpu-m1-pro.json`,
`rx3-core-arm.asm`, and `index-fields.asm`. The full OverCue disassembly and
focused `is-prepared.asm`, `prepared-files.asm`, `loudness-gains.asm` and
`loudness-measure.asm` are under the preceding
`local/research/overcue-prototype-20260928/` directory. They remain local.

From the Toolbox checkout:

```sh
python3 local/research/overcue-static-20260928/make-bench.py
cc -DRX3_OVERCUE_HOST -O2 -Wall -Wextra -Werror \
  local/research/overcue-static-20260928/bench.c -lz -lm -pthread \
  -o local/research/overcue-static-20260928/bench
local/research/overcue-static-20260928/bench \
  ../rx3-emulator/build/media/overcue-desktop-usb \
  '/Contents/John Mood/UnknownAlbum/John Mood - DO IT.aiff' 300
```


## Follow-up implementation

The later [prototype adaptation](overcue-prototype.md#adaptation-reciprocal-recognition-and-neon)
implements manual provenance, measured downward loudness ceilings and RGB
preview files. Desktop recognition and active stem preview controls were
observed on a shared-index fixture. The earlier blockers above describe the
pre-adaptation exporter; they are retained as the static-analysis baseline.
The implementation differs numerically from Desktop and remains opt-in.
