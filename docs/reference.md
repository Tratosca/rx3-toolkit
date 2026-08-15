# Reference

Commands, formats, addresses and platform findings. Written for a contributor.
Nothing here is needed to use the applications.

## Commands

Nothing in this repository is pip-installable. There is no packaging metadata
and no console script. Every entry point is invoked as a path.

### Make targets

| Target | Effect |
|---|---|
| `make help` | Print the target list. The default goal. |
| `make hook` | Cross-compile the ARM performance core and assert the resulting ELF. |
| `make autoexec KEY=<path>` | Build `autoexec.bin`. `KEY` is required and must exist. |
| `make app` | Run XDJ-RX3 Toolkit from source. |
| `make emulate` | Run `rbp` with a visible, clickable virtual framebuffer. |
| `make emulate-system` | Probe the genuine RX3 U-Boot and kernel on QEMU i.MX6Q. |
| `make emulate-system-fast` | Boot the genuine kernel through `init`, `apl_start` and `rbp`. |
| `make test` | Run the runtime regression guards, then the unit tests. |
| `make preflight` | Inspect every publishable tracked or untracked file. |
| `make clean` | Remove `build/` and nothing else. |

Variables: `PYTHON` defaults to `python3`, `BUILD_DIR` to `build`, `FIRMWARE` to
`1.19`, `MODULES` to empty, which means the manifest defaults. `CC` defaults to
`clang` unless the environment sets it.

```sh
make autoexec KEY=/absolute/path/to/aes256.key FIRMWARE=1.19
```

```sh
make autoexec KEY=/absolute/path/to/aes256.key FIRMWARE=1.19 \
  MODULES="beatjump-32bars beatjump-no-quantize decoder-sleep"
```

### Runtime build CLI

```sh
python3 tools/rx3_runtime/cli.py list --firmware 1.19
```

```sh
python3 tools/rx3_runtime/cli.py build --firmware 1.19 \
  --patch beatjump-32bars --patch stems \
  --key /path/to/aes256.key --output build
```

`--firmware` defaults to `1.19`. `--patch` repeats, and when it is omitted every
module whose manifest sets `default: true` is selected. `--key` and `--output`
are required. `--prebuilt-hook` accepts an already-compiled ARM component
instead of invoking Clang.

Both panes of the desktop application call the same engines. Module discovery, ARM
compilation, ISO creation, encryption and verification are not duplicated in
either GUI.

### Firmware image codec

```sh
python3 tools/rx3_firmware/firmware_image.py verify XDJRX3.UPD
```

```sh
python3 tools/rx3_firmware/firmware_image.py decrypt \
  XDJRX3.UPD firmware.iso --key /path/to/aes256.key
```

```sh
python3 tools/rx3_firmware/firmware_image.py encrypt \
  firmware.iso XDJRX3-modified.UPD --key /path/to/aes256.key --version 1.19
```

```sh
python3 tools/rx3_firmware/firmware_image.py verify-autoexec \
  build/autoexec.bin --key /path/to/aes256.key
```

`decrypt-autoexec IN OUT --key K` and `autoexec DIR OUT --key K` complete the
set. `--key` is required everywhere except `verify`, where it is optional.

Firmware reconstruction exists for offline analysis. The default build uses the
USB autoexec path and does not flash NAND.

### Sidecar encoder

```sh
python3 tools/rx3_stems/make_sidecar.py vocals.wav "Artist - Title.rx3stem" \
  --match-full "Artist - Title.mp3" --separator-normalization 1.0
```

`--format` accepts `s16`, the default, or `f32`. `--match-full` validates trim
and padding against the full 44.1 kHz track. `--separator-normalization` takes
the peak the separator scaled the mix to before inference and requires
`--match-full`. `--ffmpeg` defaults to `ffmpeg`.

### Offline Beat Jump patchers

Both operate on a host copy of `rbp`. Neither includes nor retrieves it. Apply
in this order when both are needed:

```sh
python3 -m tools.rx3_patcher.beatjump_32bars rbp -o rbp.32bars
python3 -m tools.rx3_patcher.beatjump_no_quantize rbp.32bars -o rbp.patched
```

Inspect or revert each separately:

```sh
python3 -m tools.rx3_patcher.beatjump_32bars rbp.32bars --check
python3 -m tools.rx3_patcher.beatjump_no_quantize rbp.patched \
  --revert -o rbp.32bars
python3 -m tools.rx3_patcher.beatjump_32bars rbp.32bars \
  --revert -o rbp.restored
```

`-o` defaults to the input name with `.patched` appended. Both refuse unexpected
words, and applying then reverting in reverse order restores the input byte for
byte.

### Release plumbing

```sh
python3 scripts/package_release.py "dist/XDJ-RX3 Toolkit" out.zip --include LICENSE
```

```sh
python3 scripts/smoke_desktop_app.py "dist/XDJ-RX3 Toolkit"
```

```sh
python3 scripts/check_macos_bundle.py "dist/XDJ-RX3 Toolkit.app"
```

```sh
./scripts/preflight.sh
```

`smoke_desktop_app.py` runs the packaged binary with `--self-test` under a
120-second timeout. `check_macos_bundle.py` shells out to `otool` and `nm`, so it
runs on macOS only. `preflight.sh` takes no arguments and rejects disallowed
extensions, files over 2097152 bytes, and matches against its secret patterns.

Both applications accept `--self-test` and nothing else. Any other argument is
ignored.

### On-device

```sh
/mnt/iso/modules/decoder-sleep/apply.sh 100000 /tmp/decoder-sleep.log
```

The interval defaults to `100000` nanoseconds and the log to
`/tmp/rx3-decoder-sleep.log`. The script needs `/bin/bash`, requires a positive
integer interval, waits up to 20 seconds for UDP port 20000, and applies the
setting per deck. Failure is logged and does not stop the main runtime.

## Environment variables

| Variable | Read by | Effect |
|---|---|---|
| `RX3_SEPARATOR` | Stem Studio | Path to an `audio-separator` to use instead of `PATH` or the managed environment |
| `RX3_FFMPEG` | Stem Studio | Path to an `ffmpeg`. Used as given; a missing filter is reported, not worked around |
| `RX3_STEM_STUDIO_HOME` | Stem Studio | Overrides the managed runtime and model cache location |
| `RX3_PREBUILT_HOOK` | `mod_generator.spec` | Path to the compiled ARM component. Required when running PyInstaller; there is no fallback |
| `RX3_STEMS_DIR` | on-device stems module | Overrides the sidecar directory the hook looks in |
| `DECODER_SLEEP_NS` | on-device decoder module | Overrides the polling interval, default `100000` |
| `CC` | build engine | Compiler used for the ARM component, default `clang` |

## Build prerequisites

| Component | Version | Notes |
|---|---|---|
| Python | `3.12` in CI | No `requires-python` and no runtime guard exist. `[TODO: verify]` the actual floor |
| `cryptography` | `50.0.0` | Pinned in `requirements.txt` |
| `pycdlib` | `1.14.0` | Pinned. Imported lazily, with an `mkisofs` subprocess fallback |
| `pyinstaller` | `6.21.0` | Pinned in `requirements-release.txt` |
| Clang, LLD | any recent | Required to compile the ARM component from source |
| FFmpeg | any complete build | Must carry `aformat`, `apad`, `aresample`, `astats`, `atrim`, `volume` |

The separation runtime for Stem Studio needs a Python interpreter between 3.10
and 3.13 on the host to seed its environment. That range is enforced in code.

Cross-compile flags:

```text
--target=arm-linux-gnueabi -march=armv7-a -marm -mfloat-abi=softfp -mfpu=neon
-fPIC -fno-stack-protector -O2 -Wall -Wextra -Werror
-fuse-ld=lld -shared -nostdlib -Wl,--hash-style=sysv -Wl,--build-id=none
```

CI runs the source job on `ubuntu-latest`, and both application jobs on
`ubuntu-24.04`, `windows-2025`, `macos-latest` and `macos-15-intel`.

## Hardware and vendor platform

| Component | Observed value |
|---|---|
| SoC | Freescale/NXP i.MX 6Quad |
| CPU | ARMv7-A, 32-bit little-endian, NEON/VFPv3 |
| ABI | ARM EABI5, softfp |
| Bootloader | U-Boot 2009.08, `mx6q_sabresd` derivative |
| Kernel | Linux 3.0.101-imx |
| Userland | LTIB, BusyBox, glibc 2.13, SysV init |
| Graphics | DirectFB over fbdev |
| Main application | `/root/pdj/rbp`, dynamically linked, not stripped |

The hook is compiled as an ARMv7 EABI5 shared object in ARM mode with
softfp/NEON settings and linked with `-nostdlib`. libc and pthread symbols are
resolved by the host process when it is loaded through `LD_PRELOAD`.

### Flash layout

| Partition | Size | Observed purpose |
|---|---:|---|
| `boot` | 3 MiB | U-Boot |
| `bb1` | 1 MiB | auxiliary boot block |
| `env` | 1 MiB | U-Boot environment |
| `kernel_a` | 10 MiB | primary kernel |
| `kernel_b` | 10 MiB | secondary kernel |
| `rootfs` | 30 MiB | CramFS system image, exposed as `mtd5` |
| `settings` | 10 MiB | writable UBIFS settings |
| `pdj` | 8 MiB | application archive, exposed as `mtd7` |
| `bb2` | 5 MiB | auxiliary area |
| `core` | 30 MiB | writable UBIFS data |
| `gui` | 40 MiB | GUI resources |
| `quickboot` | 102 MiB | quick-boot data |

At runtime the effective root filesystem is a 60 MiB `tmpfs` assembled from the
system and application images. `/proc/mounts` may hold more than one entry for
`/`; the last matching entry is the effective mount, and the one the
orchestrator checks.

### On the root password

The runtime does not need one. During filesystem analysis the stock
`/etc/shadow` entry was identified as legacy DES `crypt(3)` and cracked in
roughly three minutes, since that format has no adaptive work factor and
considers only the first eight password characters. Neither the hash nor the
plaintext is published. Only the optional Telnet module, disabled by default,
relies on the stock login account.

### Supported player binaries

`mod/1.19/compatibility.sh` registers four accepted `rbp` SHA-1 values. An
unlisted hash aborts the run with `STOP: unsupported rbp SHA-1` before anything
is modified. They correspond to firmware `1.19`, which has no sub-revisions.

## Firmware image format

An `XDJRX3.UPD` update container:

```text
[encrypted body, multiple of 512 bytes]
[7-byte model + 5-byte version field]
[CRC32 of the encrypted body, little-endian]
```

The encrypted body is an ISO 9660 filesystem named `UsbAuto`. The 16-byte
trailer holds a model identifier and a CRC32. The analyzed verification path
implements no asymmetric signature and no MAC.

The official initramfs encrypts through Linux cryptoloop, `losetup -e aes -p 0`:

| Parameter | Value |
|---|---|
| Cipher | AES-256-CBC |
| Unit | independent 512-byte sectors |
| IV | sector index as 32-bit little-endian, then 12 zero bytes |
| Key input | first line of the supplied key file |
| Effective key | first 31 bytes followed by one NUL byte |

The 31-byte behaviour follows the historical `xstrncpy(dst, src, 32)` call,
which copies at most `n - 1` bytes and terminates the destination. Using the
first 32 input bytes directly produces a different key.

The ISO 9660 primary volume descriptor starts at ISO sector 16. Since the crypto
unit is 512 bytes and an ISO sector is 2048, the `CD001` signature lands in
crypto sector 64.

Unlike an update image, `autoexec.bin` is an encrypted raw ISO with no model
trailer and no CRC. Rock Ridge extensions are required so `autoexec.sh` keeps
its executable bit, and the image size must stay aligned to 512 bytes.

## Beat Jump ±32 and direct execution

Guarded 32-bit words cover five related effects:

| Group | Change |
|---|---|
| A | jump values from ±8.0 to ±32.0 |
| B | availability guard from 8 to 32 beats |
| C | LED availability threshold from 16 to 64 half-beats |
| D | pad images from the available `8` assets to the available `32` assets |
| E | quantized branch replaced by an ARM NOP, selecting the direct path |

Groups A to D belong to `beatjump-32bars`; group E is `beatjump-no-quantize`.
Each module states its offsets twice: in `module.sh` for the device, and in
`tools/rx3_patcher/` for offline use. `tests/test_module_consistency.py` fails
if the two ever disagree.

`32.0` cannot be encoded by the VFP immediate used at the target site. The patch
loads the IEEE-754 value through `r5`, moves it to `s16`, and converts the
negative-path magnitude calculation to single precision with `vabs`. Every
affected jump magnitude is exactly representable in single precision.

No directional `32` pad image exists in the shipped GUI data, so the patch reuses
the non-directional `32` image from the Beat Loop page. The jog display is
untouched: its four-bit display codes are interpreted by separate jog controller
firmware, which provides no `32` glyph.

## Decoder polling

Not a binary patch. After `rbp` starts, the module sends the following to its
loopback debug console on UDP port 20000:

```text
bufsleep 0 100000
bufsleep 1 100000
```

That calls `playengine::Player::setDecoderSleep` for each deck, changing the
decoder-thread sleep interval from the stock 1 ms to 0.1 ms. The setting is
volatile and alters neither NAND nor the `rbp` executable. It costs CPU, and it
does not guarantee any fixed reduction in end-to-end audio latency. See the
[module documentation](../mod/modules/decoder-sleep/1.19/README.md).

## Stems internals

### Hooked functions

Guarded ARM trampolines at these firmware 1.19 addresses:

| Address | Function | Purpose |
|---:|---|---|
| `0x0003d1e0` | `common::PcmReader::getStreamAt` | replace or subtract vocal PCM |
| `0x00038ff0` | `common::PcmReader::load` | associate an `.rx3stem` with a deck |
| `0x003060e8` | `ui::PlayerInnards::onKey_Pad` | handle pads 7 and 8 |
| `0x002fcc04` | Slip Loop LED update | render independent component state |

Each site has an eight-byte prologue guard. Three prologues are copied directly
into a trampoline because their stolen instructions are not PC-relative. The LED
prologue begins with a PC-relative `ldr`, so its trampoline loads a copy of the
original literal before replaying the following instruction.

### Track association and loading

The first field of the target `StTrackInfo` object is an inline NUL-terminated
path, not a `juce::String`. The hook derives the basename directly and looks for
`RX3_STEMS/<basename>.rx3stem`.

Sidecars load asynchronously into anonymous RAM. The deck stays on the stock
audio path until loading completes, after which the USB file is closed, so
removing the drive after a completed load cannot invalidate an active mapping.
Allocation is rejected when the payload would exceed 60% of the estimated
immediately available or reclaimable memory.

The basename the hook sees is the one on the drive. Rekordbox truncates a
filename to the first 44 characters of its stem when it exports a track, leaving
the library file untouched, so Stem Studio derives the sidecar name from the
library file through the same truncation (`export_stem`,
`tools/rx3_stems/rekordbox.py`). Trailing spaces survive the cut on both sides
and are not trimmed.

Two tracks with the same basename cannot be told apart reliably through the
observed load interface, so Stem Studio rejects such collisions instead of
picking an arbitrary sidecar. Truncation is applied before that comparison,
because two names that only differ past character 44 collide on the drive.

### Audio domain and gain

`PcmReader` operates at 44,100 frames per second, corroborated by the
constructor constants, the cue-store path, the buffer sizes, and the sample-rate
converter instantiated by `ReaderImpl::loadFile`. Sources at other rates are
converted before reaching the hooked buffer.

Vocal stems and the full mix must come from the same decode path, because the
instrumental is computed as full mix minus vocal. Phase, delay, gain or
resampling differences leave residual vocals.

Delay is the one the container introduces. An mp3 or AAC file declares the
samples its encoder prepended, and FFmpeg drops them: position zero of a default
FFmpeg decode is not position zero of `PcmReader`, which starts at the first
sample the deck's own decoder emits, padding included. A 1,105-sample delay,
which is what LAME declares, puts the stem 25 ms ahead of the mix and leaves the
vocal essentially untouched in the instrumental while the isolated vocal still
sounds correct. The sidecar encoder therefore decodes the source twice, once
with `-flags2 +skip_manual` and once without, locates the trimmed decode inside
the untrimmed one to measure the padding exactly, and pushes the separator's
stem back by that many frames before padding and trimming it to the untrimmed
length (`tools/rx3_stems/sidecar.py`). Sources declaring no padding, which is
every WAV, AIFF and FLAC, are unaffected. When the offset cannot be measured —
a silent decode leaves no unique pattern to locate — the stem stays on the
separator's grid and the run reports it.

Gain is the one a separator breaks silently. The MDX and MDXC architectures
scale the mix to the normalization threshold before inference and write the stem
in that scaled domain, so a threshold below 1.0 multiplies the vocal by
`threshold / peak` and leaves `1 - threshold / peak` of it in the instrumental.
That is roughly -20 dB of leftover vocal at the separator's own default of 0.9.

Stem Studio therefore pins normalization to 1.0, which is the highest value
`audio-separator` accepts and also the highest that is safe: its writer converts
with `(stem * 32767).astype(np.int16)`, which wraps rather than clips above full
scale. The Demucs architecture never scaled the mix, which is why stems made
before the move to `audio-separator` do not show this.

At 1.0 no stage touches a source that decodes at or below full scale, which
covers integer PCM at 44.1 kHz outright. Lossy codecs reconstructing
inter-sample peaks, and resampling from 48 or 96 kHz, can still land above it;
the leftover would be `1 - 1/peak`, around -19 dB at one decibel of overshoot.

The sidecar encoder closes that case by measuring instead of assuming. The pass
that decodes the full track for its frame count also runs `astats`, and the stem
is multiplied back by `peak / threshold`. Since FFmpeg negotiates a filter chain
backwards from its output format, the measurement has to be forced into float
ahead of the `s16le` conversion, or it reads values already clamped to full scale
and reports no overshoot at all.

Only stems from architectures that scale the mix, MDX and MDXC, are corrected.
Demucs and VR leave the mix alone and rescale a stem only when it peaks above the
threshold by itself, which at 1.0 means a vocal above full scale that an `s16`
sidecar could not carry regardless. Correction restores the vocal to its true
level, so what clips is only what genuinely exceeded full scale in the source.
The manifest records `gainCorrection` and `clippedSamples` per track.

Levels here are peak sample values relative to digital full scale, not loudness.
No EBU R128 or ITU-R BS.1770 measurement is performed anywhere in the pipeline.

When the stock reader returns an all-zero region during a seek or a buffer
underrun, the hook leaves it untouched: subtracting the vocal from a zero-filled
buffer would emit an inverted vocal signal. A 256-frame linear transition covers
each change between the four states.

### Pad and LED behaviour

Stem controls are active only when Slip Loop mode is selected, no Shift modifier
is active, the current deck has a valid corresponding sidecar, and the event
targets pad 7 or 8. Otherwise events are delegated unchanged to the stock
handler.

The LED list contains entries for both decks, so filtering by LED id alone would
alter the other deck's visual state. The hook also checks the channel stored at
offset `+4` in each 44-byte `uif::Led` entry.

While a sidecar is being read, both pads blink, then hold their colour once the
payload is resident and the toggles take effect. The blink uses the firmware's
own `uif::Led::State` 2 with a 500 ms period rather than a toggle driven from
the hook, so its cadence does not depend on how often the LED refresh calls
back. That period is a half-period: `SubMiconTx::setFullColorLed` lights the LED
while `floor((now - started_at) / period)` is even, so 500 ms is one second on,
one second off.

The waveform is not modified. Its internal three-band representation is not the
PCM buffer processed by `getStreamAt`.

### Sidecar format

A 64-byte little-endian header followed by interleaved stereo vocal PCM:

| Offset | Size | Field |
|---:|---:|---|
| `0x00` | 8 | magic `RX3STM1\0` |
| `0x08` | 4 | sample rate, `44100` |
| `0x0c` | 4 | channel count, `2` |
| `0x10` | 4 | sample format: `1` float32, `2` int16 |
| `0x14` | 4 | header size, `64` |
| `0x18` | 8 | frame count |
| `0x20` | 32 | reserved, zero-filled |
| `0x40` | variable | interleaved stereo vocal PCM |

The generator defaults to int16 to halve resident memory relative to float32.
The frame count is aligned to the full track decoded at 44.1 kHz, not derived
only from the separator output duration.

### Stem Studio internals

The application holds no separation code. `tools/rx3_stems/` carries the export
parser, the runtime resolver, the model catalogue, the job pipeline and the
container encoder, and the Tkinter interface only drives them.

| Path | Contents |
|---|---|
| `tools/rx3_stems/rekordbox.py` | Rekordbox XML export parser |
| `tools/rx3_stems/provisioning.py` | runtime detection, acceleration profiles, environment provisioning |
| `tools/rx3_stems/separation.py` | model catalogue, tunable options, stored settings |
| `tools/rx3_stems/job.py` | separation and sidecar generation pipeline |
| `tools/rx3_stems/sidecar.py` | `.rx3stem` encoder |
| `tools/rx3_stems/make_sidecar.py` | encoder command-line front end |

audio-separator and FFmpeg are invoked as subprocesses, so no separation
dependency is linked into the release archive. Which accelerator an environment
was built for is recorded beside it, since a CPU-only PyTorch cannot be
accelerated afterwards.

## Module manifests

Each runtime feature lives under a firmware version directory and provides a
`manifest.json`. The GUI, the CLI and the release packager all discover the same
manifest rather than maintaining separate feature lists.

| Field | Meaning |
|---|---|
| `id` | Stable lowercase module identifier. |
| `firmware` | Exact compatible firmware revision; it must match the directory. |
| `runtime_directory` | Single safe directory name written into the ISO. |
| `namespace` | Unique POSIX-shell prefix for every lifecycle callback. |
| `default` | Selected by default when the module is user-selectable. |
| `selectable` | `false` for an internal service such as `core`; direct selection is rejected. Defaults to `true`. |
| `order` | Stable load order; dependencies must have a lower order. |
| `requires` | Transitive module dependencies. |
| `conflicts` | Modules that cannot appear in the same runtime. |
| `files` | Source-to-runtime file mappings and executable bits. |
| `build_files` | Module-owned headers or other compile-time-only sources. |
| `arm_hook` | Optional ARM source and ELF target owned by this module. |

The build resolves dependencies, rejects cycles/conflicts and writes the exact
device load order to `modules/index`. Thus `--patch keyshift` packages `core`
and `keyshift`, while `--patch decoder-sleep` remains standalone. `BuildResult`
reports this effective selection.

### Example

```json
{
  "id": "decoder-sleep",
  "name": "Faster decoder polling",
  "description": "Check decoded audio more frequently after seeks and large jumps.",
  "firmware": "1.19",
  "default": true,
  "order": 30,
  "runtime_directory": "decoder-sleep",
  "namespace": "decoder_sleep",
  "requires": [],
  "conflicts": [],
  "files": [
    {"source": "module.sh", "target": "module.sh", "executable": false},
    {"source": "apply.sh", "target": "apply.sh", "executable": true}
  ]
}
```

The internal `core` module adds an `arm_hook` object naming its composition root
and the shared object it compiles to. Feature headers stay in their owning
module's `build_files`. The directory name must equal the `firmware` field, and
ids, runtime directories and shell namespaces must be unique for that firmware.
