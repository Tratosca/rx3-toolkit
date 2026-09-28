# OverCue conversion on the physical RX3

Measured on 2026-09-28. No sound output, player injection, firmware update or
reboot was performed. `scripts/overcue_bench.c` directly includes the prototype
reader and measures file reads, page inflation, integrity checks and the
192-tap NEON 96 kHz to 44.1 kHz conversion together.

## Environment and method

- RX3: Linux 3.0.101, four ARMv7 processors, about 1 GiB RAM.
- Sampled CPU frequency: 996000 kHz, interactive governor.
- ARM GCC 12.2, softfp ABI, native glibc 2.13 and zlib 1.2.3 libraries.
- Input on the device USB volume, isolated benchmark directory. No rootfs writes.
- Thirty-second stereo music fixture with nonzero vocals and drums, repeated.
  Source SHA-256: `8ae3027c6c7ffac8f245166a3752b957d3ddf27ae614f9dee73430c0500f03df`.
- Toolkit-produced bundle: `58443c6784a6d038`, seven 96 kHz roles.
- One deck converts full mix; two decks convert full mix and drums with separate
  reader states. Both execute serially in one thread at real-time cadence.
- Blocks contain up to 4096 frames: a full block has 92.880 ms of audio.
- Tests follow bank validation and earlier reads: this is not a cold USB test.
- Thermal sensor `anatoptz` sampled approximately once per second; its old
  vendor ABI returns degrees Celsius directly. Benchmark stops at 75 C.
  Reported driver hot/critical thresholds are 90/100 C.

## Results

| Measurement | One deck | Two decks |
|---|---:|---:|
| Elapsed test | 60 s | 300 s |
| Conversion CPU time | 6.900233 s | 65.156296 s |
| Conversion CPU, one-core basis | 11.50% | 21.72% |
| Conversion CPU, four-core capacity equivalent | 2.88% | 5.43% |
| Entire benchmark process CPU | 7.048929 s | 66.369364 s |
| Per-deck block p95 wall time | 27.486 ms | 27.014 ms |
| Per-deck block p99 wall time | 30.532 ms | 28.546 ms |
| Maximum complete batch wall time | 42.141 ms | 81.975 ms |
| Batches exceeding their own audio duration | 0 | 0 |
| Sampled temperature range | 54-56 C | 55-57 C |
| Start/end temperature | 55/55 C | 56/56 C |

Initial filter construction costs about 26 ms CPU. Opening and validating the
bank costs 0.342 s CPU / 0.475 s wall time for one reader, and 0.675 s CPU /
0.951 s wall time for two. These are separate from steady-state conversion.
The initial idle observation was 54 C; a post-test read was 55 C. No sampled
frequency reduction or thermal stop occurred. Temperature was not measured at
the enclosure surface; ambient temperature was not recorded.

Thirty seconds of physical full-mix output were also transferred back and
compared to the same C implementation on the Mac. Maximum absolute float
difference was 1.7881393432617188e-7 (0.005859375 of a signed-16-bit LSB), with
RMS error 1.5336124815868708e-8. This checks numerical agreement across ARM32
and ARM64, not bit identity after changing sample rate.

## Interpretation and limits

Conversion cost is compatible with continuing the background-cache prototype.
The largest two-deck batch still leaves only about 10.9 ms against a full
92.9 ms batch budget: average CPU headroom alone cannot prove glitch-free audio.
The benchmark does not exercise the asynchronous consumer, cache misses,
scratching, seeks, role transitions, effects, independent tracks or concurrent
USB traffic. A five-minute run is not a passive-enclosure thermal soak test.
No electrical power consumption was measured.

This benchmark is not a physical playback validation. The production hook was
not loaded, and its compiler/build differs from this standalone executable.
Before playback, notify the operator; then validate the complete audio path
and perform a longer thermal run under representative load.

## Reproduction and evidence

Host build (requires zlib headers and a prepared bank):

```sh
cc -O2 scripts/overcue_bench.c -o /tmp/overcue-bench -lz -lm -pthread
/tmp/overcue-bench BANK_ROOT /Contents/fixture.wav 60 1 1 6
/tmp/overcue-bench BANK_ROOT /Contents/fixture.wav 300 2 1 6
```

The optional last argument writes interleaved stereo float32 PCM to a new file;
it never opens a sound device. ARM builds must target the device's ABI, loader
and library versions, not the modern toolchain's default runtime.

Owner-local evidence is under `local/research/overcue-physical-20260928/`:
`one-deck.jsonl`, `two-decks.jsonl`, `device-pcm-validation.json`, build inputs
and the executable. Executable SHA-256:
`d3c8f0e2d031ff17c109a7ab80a3fe56a7dc242bd882c90cca9f609aa9ad1b5d`.
Proprietary libraries and audio are not distributed. The reference coefficient
table was subsequently added to the experimental desktop export resources.

The fresh Desktop oracle comparison with nonzero drums remains unvalidated:
manual stem timing checks passed, but Desktop refused packaging because the
reused rekordbox analysis waveform describes the previous, longer track.
A matching analysis/export fixture is required before claiming seven-role
PCM identity for this input. This does not affect the measured RX3 conversion.
