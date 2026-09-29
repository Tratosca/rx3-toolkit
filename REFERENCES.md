<!-- SPDX-License-Identifier: MPL-2.0 -->
# XDJ-RX3 Toolkit — engineering reference

This is the maintained entry point for the project's technical contracts, verified observations and detailed records. The [README](README.md) is the DJ guide; [CONTRIBUTING.md](CONTRIBUTING.md) gives the contributor workflow. This reference describes the **development tree**, not necessarily the [latest published release](https://github.com/Tratosca/rx3-toolkit/releases).

## Table of contents

The current overview comes first. The engineering findings from `docs/` follow, including dated and superseded investigations. The hardware acceptance booklet and its operational assets are maintained separately under `docs/acceptance/0.6.0/`.

### Start here

- [How to read this reference](#how-to-read-this-reference)
- [Names on the RX3](#names-on-the-rx3)
- [Evidence and current limits](#evidence-and-current-limits)
- [Detailed documents](#detailed-documents)
- [Cross-cutting contracts](#cross-cutting-contracts)

### Engineering

- [1. The machine](#1-the-machine)
- [2. How a mod runs without flashing anything](#2-how-a-mod-runs-without-flashing-anything)
- [3. Changing a binary you did not write](#3-changing-a-binary-you-did-not-write)
- [4. The display](#4-the-display)
- [5. Front-panel input](#5-front-panel-input)
- [6. Stems](#6-stems)
- [7. Key shift](#7-key-shift)
- [8. Faster decoder polling](#8-faster-decoder-polling)
- [9. Building and running](#9-building-and-running)
- [Appendix A: front-panel codes](#appendix-a-front-panel-codes)

### Complete documents from `docs/`

#### Player, USB and acceptance

- [RX3 0.6.0 hardware acceptance booklet](docs/acceptance/0.6.0/ACCEPTANCE.md)
- [If the RX3 or prepared drive misbehaves](#doc-troubleshooting)
- [Published source package and first-use key](#doc-extract-initramfs)
- [RX3 hardware findings, 29 September](#doc-hardware-feedback-20260929)
- [QEMU findings, 29 September](#doc-emulator-feedback-20260929)
- [RX3 startup incident](#doc-rx3-startup-incident)

#### Touchscreen, pads and BROWSE

- [KEY, STEMS and SAMPLES touchscreen positions](#doc-performance-tab-matrix)
- [Performance control artwork](#doc-pad-visual-design)
- [Deck-title eye controls](#doc-title-visibility)
- [BROWSE scrolling](#doc-browse-scroll-performance)
- [KEY SYNC follow-up](#doc-key-sync-follow-up)
- [Key Shift, Key Sync and MASTER](#doc-transposition)
- [DJ experience audit (dated proposals)](#doc-ux-audit-dj)

#### Stems, audio and waveforms

- [Current .rx3stem package](#doc-stem-package)
- [Migration from v0.5.2 stems](#doc-stems-migration)
- [Blue, RGB and 3Band waveforms](#doc-waveform-formats)
- [In-memory waveform trials](#doc-waveform-in-memory-tests)
- [Waveform timing on Antisocial](#doc-waveform-performance-antisocial)
- [Sample banks stored on the computer](#doc-samples-local-projects)
- [OverCue static findings](#doc-overcue-static-analysis)
- [OverCue USB prototype](#doc-overcue-prototype)
- [OverCue conversion timing on RX3](#doc-overcue-rx3-benchmark)

#### Runtime, build and project history

- [Shared runtime services and ownership](#doc-runtime-framework)
- [USB reinsertion and RX3 restart](#doc-runtime-reinsertion-plan)
- [Recovering a released module](#doc-recovering-a-module)
- [macOS app signing and distribution](#doc-macos-distribution)
- [Desktop application restructuring decision](#doc-adr-0001-restructure-in-place)
- [Superseded stems design (history only)](#doc-history-legacy-stems)

## How to read this reference

| Need | Start here |
| --- | --- |
| What runs on the RX3, and how to return to stock | [Machine](#1-the-machine), [USB runtime](#2-how-a-mod-runs-without-flashing-anything), [troubleshooting](#doc-troubleshooting) |
| Module layout, lifecycle and shared services | [Modules](#modules), [orchestrator](#the-orchestrator), [runtime framework](#doc-runtime-framework), [reinsertion contract](#doc-runtime-reinsertion-plan) |
| Screen, pads and input | [Display](#4-the-display), [front-panel input](#5-front-panel-input), [panel codes](#appendix-a-front-panel-codes) |
| Stems, waveforms and pitch | [Stems](#6-stems), [Key Shift](#7-key-shift), [stem package](#doc-stem-package), [transposition](#doc-transposition) |
| Build and validate | [Building and running](#9-building-and-running), [acceptance campaign](docs/acceptance/0.6.0/ACCEPTANCE.md#doc-acceptance-0-6-0-readme) |
| What is established and what still needs a device test | [Evidence and current limits](#evidence-and-current-limits) |

**Evidence levels.** A source inspection establishes what a particular checked binary or source revision contains. A host test validates that tested code path. Emulator output shows behavior in that emulator. Only a recorded physical RX3 run establishes device behavior, and it does not automatically cover audio, a second deck or a full set. Dated investigations below retain their own scope and hashes. Treat any older result as historical when current code or newer device evidence differs.

## Names on the RX3

Start with what the DJ can point to. **The touchscreen** is the central display. **Deck 1 and Deck 2** are the two player sides. Each deck has eight physical **performance pads** below its controls; the buttons beside or above the screen and the on-screen touch areas are different inputs.

| What the DJ sees or presses | Meaning in this reference | Code term, when needed |
| --- | --- | --- |
| **ZOOM** and **GRID** on the touchscreen | Native touch areas in the upper strip of the performance screen. When selected, **KEY** or **STEMS** uses this same strip. | tab strip, panel selection |
| **STATUS** and **BEAT FX** on the touchscreen | Native destinations in the lower touch row. The optional **SAMPLES** view occupies the STATUS side; BEAT FX remains available. | panel, row, render target |
| **KEY**, **STEMS**, **SAMPLES** on the touchscreen | Toolkit views for pitch, prepared stems and sample bank controls. A *panel* in source code means one of these touch views and its controls, not a separate physical board inside the RX3. | `rx3_pad_row`, `services->panels`, panel registry |
| **HOT CUE**, **BEAT LOOP**, **SLIP LOOP**, **BEAT JUMP** and pads **1–8** | Physical performance modes and pads. The selected mode decides what a pad press does. | pad input, mode selector |
| **BROWSE**, rotary selector, **LOAD 1 / LOAD 2**, **MENU (UTILITY)**, **SHIFT**, **SHORTCUT** | Physical controls used by navigation, loading and mod shortcuts. | input events, key codes |

The **panel registry** is simply the code that knows which of the KEY, STEMS and SAMPLES touchscreen views are available and opens the selected one. It is not a DJ-facing control. When a section discusses touch geometry, read it against the named screen areas above; when it discusses a physical pad, the mode and deck must be stated.

## Evidence and current limits

As of 29 September 2026, the development tree supports firmware 1.19 and 1.20 by manifest and guarded binary checks. The v0.5.2 material tracked in this repository predates these development changes. The current source includes Stems, Key Shift and Key Sync, Samples, Browse extensions, display modules and the shared runtime services. These are implementation facts, **not a claim that the combined selection passed physical acceptance**. The [module manifests](mod/modules), [README](README.md#what-you-get) and [0.6.0 acceptance matrix](docs/acceptance/0.6.0/ACCEPTANCE.md#doc-acceptance-0-6-0-readme) define the selectable set and test plan.

| Area | Latest recorded boundary | Detailed record |
| --- | --- | --- |
| RX3 startup and display | The 29 September physical trials found missing or unresponsive title-eye controls, faulty return from KEY/STEMS, delayed tabs and slow BROWSE. Candidate fixes need another physical run. | [Hardware feedback](#doc-hardware-feedback-20260929), [title visibility](#doc-title-visibility), [startup incident](#doc-rx3-startup-incident) |
| Emulator | Interactive rendering and navigation were exercised, but an exception and BROWSE latency kept the candidate from release acceptance. | [Emulator feedback](#doc-emulator-feedback-20260929), [BROWSE investigation](#doc-browse-scroll-performance) |
| Audio and stems | Package structure and several host paths are tested; mixing, transitions, resource headroom and both decks still require the full hardware campaign. | [Stem package](#doc-stem-package), [waveform formats](#doc-waveform-formats), [acceptance cases](docs/acceptance/0.6.0/ACCEPTANCE.md#doc-acceptance-0-6-0-cas-de-test) |
| OverCue interoperability | Static inspection, host prototypes and a bounded physical RX3 conversion benchmark have different proof levels. The benchmark did not play audio or establish CDJ-3000 interoperability. | [Static analysis](#doc-overcue-static-analysis), [prototype](#doc-overcue-prototype), [RX3 benchmark](#doc-overcue-rx3-benchmark) |

## Detailed documents

The sections below are the stable overview. Exact procedures, binary layouts, measurements and dated evidence follow in full later in this file; the links here lead to those integrated sections.

| Topic | Documents and their role |
| --- | --- |
| Operating and recovery | [Troubleshooting](#doc-troubleshooting) (symptoms and recovery), [root filesystem and key source](#doc-extract-initramfs) (manual procedure), [macOS distribution](#doc-macos-distribution) (packaging), [module recovery](#doc-recovering-a-module) (provenance and address gates) |
| Runtime contracts | [Shared framework](#doc-runtime-framework) (service ownership and API versions), [reinsertion](#doc-runtime-reinsertion-plan) (restart decision), [performance tabs](#doc-performance-tab-matrix) (visible panels), [ADR 0001](#doc-adr-0001-restructure-in-place) (desktop restructuring decision) |
| Audio data and preparation | [Stem package](#doc-stem-package) (binary contract), [migration](#doc-stems-migration) (v0.5.2 files), [waveform formats](#doc-waveform-formats) (Blue/RGB/3Band), [transposition](#doc-transposition) (harmonic rules), [local sample projects](#doc-samples-local-projects) (host storage) |
| Audio investigations | [In-memory waveform tests](#doc-waveform-in-memory-tests), [waveform performance](#doc-waveform-performance-antisocial), [OverCue static analysis](#doc-overcue-static-analysis), [OverCue prototype](#doc-overcue-prototype), [physical RX3 benchmark](#doc-overcue-rx3-benchmark), [superseded stems design](#doc-history-legacy-stems) |
| Display and interaction | [Pad visual design](#doc-pad-visual-design), [Key Sync follow-up](#doc-key-sync-follow-up), [title visibility](#doc-title-visibility), [BROWSE scrolling](#doc-browse-scroll-performance). The [DJ UX audit](#doc-ux-audit-dj) is a dated audit with proposals; check current UI before treating a proposal as pending. |
| Validation and incidents | [0.6.0 acceptance campaign](docs/acceptance/0.6.0/ACCEPTANCE.md#doc-acceptance-0-6-0-readme) and its cases, [hardware feedback](#doc-hardware-feedback-20260929), [emulator feedback](#doc-emulator-feedback-20260929), [startup incident](#doc-rx3-startup-incident) |

The [changelog](CHANGELOG.md) is chronological history, not an authority for the current state. [AUDIT.md](AUDIT.md) and [CLEANUP.md](CLEANUP.md) record earlier repository decisions. Local evidence and vendor binaries live outside Git under `local/`; the private `local/INDEX.md` describes that workspace when present. Do not copy private keys, firmware or commercial audio into public documentation.

## Cross-cutting contracts

### Runtime, restart and ownership

- A module declares its files, dependencies and load order in its manifest. The internal core provides shared hooks and services; a feature owns its state and registers through a public service contract. The current service inventory, API versions and remaining legacy coupling are maintained in [runtime-framework.md](#doc-runtime-framework).
- Reinsert an unchanged image without restarting `rbp` only when the running PID, executable mapping, loaded core and startup resources still match. Changed modules, core or startup resources require a guarded restart. Unknown process state or patch words stop the operation before writes. Host coverage does not yet establish this behavior on a physical RX3; see the [reinsertion plan](#doc-runtime-reinsertion-plan).
- A successful build or readiness marker proves installation reached that point. A renderer response, an audible output and sustained playback are separate checks. The [acceptance campaign](docs/acceptance/0.6.0/ACCEPTANCE.md#doc-acceptance-0-6-0-readme) records them separately.

### DJ controls and deck state

- On the RX3 touchscreen, **KEY** replaces the **ZOOM/GRID** strip when Key Shift is selected; **STEMS** uses that strip when Stems is selected. If both are selected, each gets a touch area in the strip. **SAMPLES** appears in the lower **STATUS** area when its module is selected. **BEAT FX** remains available. The code's *panel registry* opens these views; Key Sync and Key Match add no separate touch view. The [eight combinations](#doc-performance-tab-matrix) specify the exact layout and touch behavior. Emulator coverage is recorded there; physical acceptance is pending.
- Key Shift is a manual deck control. Key Sync requires Key Shift and Key Match, uses an explicit local MASTER and refuses unknown or stale reference data. A device identifier is a source, not a deck number. The [transposition contract](#doc-transposition) gives the native observations, fallback rules and test limits.
- Hiding a title is per deck and should leave the underlying track metadata unchanged. The second physical trial displayed both eye icons, but touch did not toggle them. The corrected touch path and the remaining device cases are in [title-visibility.md](#doc-title-visibility).

### Stem and waveform data

- Current preparation writes one `RX3_STEMS/<track>.rx3stem` package, framed as `RX3PKG2`, with verified PCM, waveforms and a manifest. The original track remains necessary for the full mix and residual instruments. The 512 MiB package limit participates in the shared two-deck memory budget. Readers retain older package support; the [package contract](#doc-stem-package) is authoritative for bytes and rejection rules.
- New packages carry Blue, RGB and 3Band waveforms for audible stem combinations on a 150 Hz grid. When an older package lacks the selected format, the mod keeps the native waveform while stems audio remains usable. The [format contract](#doc-waveform-formats) and [migration guide](#doc-stems-migration) describe regeneration without repeating separation when source checks pass.
- The in-memory waveform benchmark and the OverCue conversion measurements are bounded experiments on named inputs. They are recorded in [waveform tests](#doc-waveform-in-memory-tests), [performance measurements](#doc-waveform-performance-antisocial) and the [OverCue benchmark](#doc-overcue-rx3-benchmark), not general speed or playback guarantees.

### Release and document maintenance

- [macOS distribution](#doc-macos-distribution) describes signing, notarization and platform-specific validation. A locally built `.app`, self-test or submitted notarization request is not a published release. Windows and Linux need their own packaged-app checks.
- Preserve an integrated section when it holds an executable procedure, an exact binary format, a dated measurement or evidence that cannot be inferred from current source. Update the summary and table of contents when its conclusion changes. Keep superseded trials dated and labelled; do not silently convert an emulator or source finding into a hardware claim.

---

## 1. The machine

The player is an embedded ARM appliance. Nothing exotic, just a bit old.

| | |
| --- | --- |
| **SoC** | Freescale/NXP i.MX 6Quad |
| **CPU** | ARMv7-A, 32-bit little-endian, with NEON |
| **ABI** | ARM EABI5, soft-float with FPU registers (`softfp`) |
| **Bootloader** | U-Boot 2009.08 |
| **Kernel** | Linux 3.0.101 |
| **Userland** | BusyBox, glibc 2.13, SysV init |
| **Graphics** | DirectFB drawing straight to a framebuffer device |
| **Application** | a single large C++ binary, dynamically linked and not stripped |

Everything you see on the screen (browser, waveforms, effects, settings) is that one process. It is not stripped, which is the single fact that makes any of this work: symbol names survive, so the binary can be read rather than guessed at.

### Storage layout

Internal flash is partitioned into fixed regions:

| Partition | Size | Holds |
| --- | ---: | --- |
| boot | 3 MiB | the bootloader |
| env | 1 MiB | bootloader environment |
| kernel A / B | 10 MiB each | two kernel slots |
| rootfs | 30 MiB | compressed read-only system image |
| settings | 10 MiB | writable settings |
| pdj | 8 MiB | the application archive |
| core | 30 MiB | writable data |
| gui | 40 MiB | display resources |
| quickboot | 102 MiB | fast-start data |

At runtime the effective root is a 60 MiB `tmpfs` assembled from the system and application images. Because more than one filesystem can be mounted at `/`, the *last* matching entry in the mount table is the live one: anything inspecting mounts has to read it that way or it will report the wrong filesystem.

---

## 2. How a mod runs without flashing anything

The player has a maintenance path: on boot it looks for a specific encrypted image on a USB volume and, if present, runs a script from inside it. That is the entire mechanism. We write to the stick, never to the player.

The consequence worth internalising: **power off, remove stick, power on, and the player is stock again.** There is nothing to uninstall because nothing was installed. It also means a mistake cannot brick anything, **as long as it does not write to the system persistent partitions**, which this project will focus on not doing. The worst case is a player that fails to start the modified application and falls back, or a crash during a gig.

### The autoexec image

The image is an ISO 9660 filesystem carrying a startup script and the runtime it launches, encrypted sector by sector so the player will accept it.

| | |
| --- | --- |
| Cipher | AES-256-CBC |
| Unit | independent 512-byte sectors |
| Initialisation vector | the sector index as a 32-bit little-endian integer, then 12 zero bytes |
| Key input | the first line of a key file you supply |
| Effective key | the first 31 bytes of that line, followed by one zero byte |

That 31-byte quirk is not a design choice, it is a bug preserved for compatibility: the original code copies the key with a bounded string copy that reserves a byte for a terminator. Using the first 32 bytes directly produces a different key and an image the player rejects.

Two practical consequences. Rock Ridge extensions must be enabled or the startup script loses its executable bit. And the image size must stay a multiple of 512 bytes, because the encryption unit is a sector.

The key is yours to supply. It is not in this repository and never will be.

### The hook

Features are implemented as a shared library injected into the application with `LD_PRELOAD`. It is compiled as an ARMv7 shared object, linked `-nostdlib`; libc and pthread symbols resolve against the host process at load time.

One build flag is load-bearing and worth knowing about before it bites you. At `-O2`, Clang rewrites `memcmp(a, b, n) == 0` into a call to `bcmp`, which this player's libc does not export. The hook then fails to load with an undefined symbol, silently, and every run falls back to stock behaviour with nothing in any log to say why. The rewrite happens after the front end, so no warning fires. `-fno-builtin-memcmp -fno-builtin-bcmp` prevents it, and a test pins the resulting symbol set so it cannot come back.

### Modules

Each feature is one directory under `mod/modules/`, described by a `manifest.json` that lists the firmware versions it is built against. The desktop application, the command line and the release packager all read the same manifests rather than keeping their own lists.

| Field | Meaning |
| --- | --- |
| `id` | stable identifier |
| `firmwares` | the firmware versions this module is built against, as a list |
| `runtime_directory` | one directory name written into the image |
| `namespace` | shell prefix for every lifecycle callback, so modules cannot collide |
| `default` | selected unless the user says otherwise |
| `selectable` | `false` for internal services, which cannot be picked directly |
| `order` | load order; dependencies must sort earlier |
| `requires` / `conflicts` | module relationships |
| `files` | source-controlled or generated files to copy into the image, and what must be executable |
| `build_files` | headers this module owns at compile time |
| `arm_hook` | the ARM source and target this module compiles, if any |

A file with `"artifact": true` is read from
`build/artifacts/<firmware>/<module>/` instead of the module source directory.
Generated artifacts stay out of Git; their feature-specific recipes use the
shared builder under `tools/rx3_kernel`.

The build resolves dependencies, rejects cycles and conflicts, and writes the resolved load order into the image. Asking for one feature therefore pulls in the internal core it depends on, without the caller having to know. `make new-module ID=<id>` writes a directory that already satisfies the whole of the above, described in [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-module).

### The orchestrator

Insertion runs entirely through the manufacturer's own path. Nothing in this project installs a hook into the boot sequence:

```text
player powered on
USB insertion
  the vendor's udev rule fires
  the vendor's decrypt script runs
    decrypts the image with the key and mounts it
    runs the startup script inside, as root
```

From there, one shared orchestrator does the work for every module: discovery, validation, guarded writes, restarting the application, rollback and logging. A module contributes exactly two things: an adapter and its payload. Adding or removing a module requires no change to the orchestrator. That is what the manifest indirection is for.

**Before it modifies anything, it verifies all of the following, and refuses the entire run if any one fails:**

1. the effective root mount really is a RAM filesystem;
2. the application's directory is not a separate mount;
3. the application's checksum is one it explicitly supports;
4. every location it intends to change currently holds either its stock value or the value it would write;
5. the application is stopped before its backing file is touched;
6. every write is read back and compared;
7. the replacement process survives eight seconds, otherwise the original bytes and preload state are restored and the application is started again.

Point 5 is not a nicety. Writing an executable's backing file while its pages are mapped can kill the process with `SIGBUS`, and the failure looks nothing like a patching bug.

Point 7 is what makes the whole approach safe to experiment with: the worst realistic outcome is a few seconds of stock interface, not a device that needs recovering.

Re-inserting a drive into an already-patched session is cheap by design. The orchestrator restarts the application only for a location still holding its stock value, or a module whose runtime part is not already live. Everything else is recognised as done and skipped, so the interface neither freezes nor rescans.

The performance core still writes its diagnostic log to a path chosen for compatibility with existing tooling, reachable only with the diagnostic shell module enabled.

---

## 3. Changing a binary you did not write

Some features cannot be done from a preloaded library and need the application's own machine code changed. The rule for all of them is the same, and it is the most important idea in this codebase:

> Read the location first. If it does not hold exactly the bytes we expect, **stop**. Never write, never guess, never "try anyway".

A binary that does not match is a different binary. It might be a firmware revision we have not studied, or a corrupted copy. Either way the safe response is to refuse, and every patch path (on the device, offline, and under emulation) implements that same guard and reads the value back after writing.

Each patch is stated twice: once for the device and once for the offline tool. A test fails the build if the two ever disagree, because two copies of a constant that drift apart is how you end up writing the right bytes to the wrong place.

### A worked example: longer beat jumps

The jump feature moves playback by a number of beats. Extending its maximum touches five separate things, which is typical. A user-visible number is rarely stored in one place:

| | What changes |
| --- | --- |
| A | the jump distances themselves |
| B | the guard that decides whether a jump is allowed (jumps pads will be off when what's left is shorter in the jump direction) |
| C | the threshold that lights the corresponding indicator |
| D | which images the pads display |
| E | a branch that made repeated presses wait for the beat grid |

The interesting part is A. The new value cannot be encoded as an immediate by the floating-point instruction at that site, so the patch loads the constant through a general register, moves it into the FPU, and converts the negative-path magnitude calculation to single precision. Every jump distance involved is exactly representable in single precision, which is what makes that conversion safe rather than merely convenient.

D is a compromise worth admitting: the shipped display resources contain no image with an arrow for 32 beats jump, so the patch reuses a non-directional image from another page. The jog display is untouched. It is driven by a separate controller with its own glyph set, which has nothing suitable.

---

## 4. The display

This section records the original firmware investigation and rendering approach. For current panel ownership, touch behavior and module boundaries, use the [runtime framework](#doc-runtime-framework), [performance tab matrix](#doc-performance-tab-matrix) and [latest hardware findings](#doc-hardware-feedback-20260929). Historical geometry or refresh experiments below are not a substitute for a fresh device check.

### Extending the image table

The application draws from a table of several thousand fixed-size image records. Every draw call resolves an image by index through one lookup function, and that function rejects any index at or past the table's declared count. To show our own artwork we need entries that do not exist.

The obvious approach, hooking the lookup function, was tried and rejected. That function runs continuously from the rendering path, so patching it while the process is live opens a window where the code is half-written. The result crashed shortly after activation. (The fallback worked correctly and restored the stock application, which is the only reason that experiment was cheap.)

What works instead touches nothing hot:

1. Before the application starts, one guarded instruction is rewritten so the declared table size is larger.
2. At startup the hook allocates a second, larger table.
3. Every original record is copied across, with its pixel offsets adjusted so it still points at the original artwork.
4. Our own records occupy the new entries past the end.
5. Only when the whole table is ready is the global pointer swapped, in one atomic write.

The original artwork and indices are never modified. A model of the relocation verifies every copied record as well as the new ones.

**The mistake this replaced is instructive.** An earlier attempt reused a block of indices that looked unused. They were not: they were the colour swatches for the source selector, and the display literally read "Aqua", "Blue", "Default". Because drawing surfaces are decoded and cached, overwriting the pixels late could never be made deterministic. Two apparently unrelated bugs turned out to be one collision: leaks into the source screen, and colour names appearing in performance mode.

### The bitmap font

The player's fonts are flat arrays of fixed-size cells, one per glyph, in codepoint order. No header, no offset table, no metrics.

| | Main Latin font |
| --- | --- |
| Row stride | 7 bytes |
| Cell size | 14 x 27 pixels |
| Bytes per cell | 189 |
| Glyphs | 422, covering Latin, Greek and Cyrillic |
| Index | codepoint - 32, so index 0 is the space character |

Pixels are 4 bits each, two per byte, leftmost pixel in the high nibble. The value is coverage from 0 to 15, plain anti-aliasing with no palette. That is where the sixteen grey levels visible throughout the interface come from.

```python
STRIDE, HEIGHT, WIDTH = 7, 27, 14
CELL = STRIDE * HEIGHT

def coverage(data, codepoint):
    """Return HEIGHT rows of WIDTH coverage values, each 0..15."""
    base = (codepoint - 0x20) * CELL
    rows = []
    for row in range(HEIGHT):
        line = []
        for x in range(WIDTH):
            index = base + row * STRIDE + x // 2
            byte = data[index] if index < len(data) else 0
            line.append(byte >> 4 if x % 2 == 0 else byte & 0x0F)
        rows.append(line)
    return rows
```

The file is 42 bytes shorter than 422 cells would be: the final glyph's trailing blank rows are simply not stored, so a reader must zero-fill the tail. A sibling font uses the same scheme with a different stride, which tells you this is a house format with one fixed size per file rather than a one-off.

**What the file does not contain is advance widths.** Glyphs sit left-aligned in their cell with the remainder blank, so proportional spacing has to come from somewhere else, in this case a metrics function reached through a table populated at runtime. Since that table is filled in dynamically, its contents cannot be recovered by reading the binary; you would have to observe it running. Deriving the advance from the ink extent plus a fixed side bearing is a usable approximation, but visibly tight on pairs like `Y -` and `+1`.

### Matching the typeface

The face is Helvetica Neue LT W1G. That is identified rather than guessed, from two independent artefacts that agree: the desktop library software declares that family in its own interface graphics, and "W1G" is the vendor's World 1 Glyph set (Latin, Greek and Cyrillic), which is exactly the repertoire of the font file. The face is licensed and not redistributable, so our label builder approximates it with a system cut instead of bundling it.

The approximation is fitted, not eyeballed. Fourteen captions in the shipped artwork segment cleanly into individual letters along blank columns, giving ground truth for nineteen capitals. Cap height is a consistent 16 pixels with round letters overshooting to 17, itself confirmation that these are real font renderings rather than hand-drawn artwork. Sweeping weight against size over that ground truth and scoring mean per-pixel error picks Regular at 22 points, clearly ahead of the neighbours.

An earlier fit chose Light at 24. It had been scored on whole-word bounding boxes, which is a weak signal: weight and size trade off against each other and still match a box. Per-glyph pixel error does not have that failure mode.

### Reusing the host's typeface at run time, and why it does not work

Nothing in the drawing code sets a font. A control wears whichever face the model it was cloned from was drawn in, so the theory was that picking the right model *is* the typography, and there were two candidates:

- **A pad label**, captured on its way into the text renderer before a live panel replaces that same draw, upgraded once to one carrying a fill since that is a real button rather than a caption.
- **A header glyph**, twice the size, as a fallback.

The first of those does not exist. The pad subtree issues no text draw at all: twelve subtrees draw text and `0x17`/`0x18` are not among them, because those stock labels are images. So the capture never fires, the fallback is what every control was lettered in, and it is twice the size the row wants. Two measurements settled it, the second being that four different donor glyphs all rendered at 19 pixels: nothing about a clone selects a face.

The row is therefore lettered from artwork of our own, one image per character, composed at draw time -- see the pad row's own section below. A cloned text model is still what a filled rectangle is cut from, because it carries the renderer and window attachment; it just no longer pretends to carry a typeface.

The row itself is painted from the pane backdrop, which opens once per pass over the row rather than once per intercepted call. Draws elsewhere in that subtree are the stock furniture the panel stands in for and are dropped; draws *outside* it belong to the vendor and reach the renderer untouched. Keying that test on the deck's window instead of the widget subtree is what used to swallow unrelated labels elsewhere on screen.

### The palette question, and the way round it

The stock colours are known, measured off the shipped artwork: a two-pixel frame, a selected fill with black glyphs, an inactive state with grey glyphs. What was never established is the encoding the *glyph's* colour field wants.

The text renderer decodes that field three different ways, choosing by the pixel format of the window it is drawing into, which it reads from the window rather than from the glyph. One branch takes the low byte alone, one the whole word, one unpacks a packed 24-bit value into 5/6/5. Measured against the real layers: one interpretation painted magenta lettering on green, another painted green, and sweeping all 256 low-byte values moved the green channel alone without ever lifting red or blue off zero.

The question is now avoided rather than answered, and that is the better outcome. Lettering is artwork, so the ink colour is a property of the image and no field has to be encoded to set it. What the row still writes is a *fill*, and the background field of a text draw does land: `0xff9000` was written into it and rendered for as long as the stems strip existed. So a control is a filled rectangle in a known colour with artwork drawn over it, and the colour comes out of the artwork file rather than out of a constant, so the fill and the ink it sits behind are one measurement.

The pressed state the touch layer tracks now has something to paint itself with, which it did not before: the artwork carries a set of glyphs per ground, and a press selects one.

### The pad row

The strip where KEY and STEMS draw their controls is one region, y 521..560 on screen and y 21..59 in the pad window's own coordinates, spanning x 19..613 within each deck's half. Deck one is widget subtree `0x17` and deck two `0x18`, and each is its own 640 wide window: a box is placed in the coordinates of the window it is drawn into, while a touch arrives in screen coordinates. Getting those two confused is the standing trap here.

A feature does not draw the row. It declares what its controls are -- a button, a toggle, a stepper, a slider -- with a weight each, and the core solves the row into rectangles, paints them and hit-tests them from that one set. The solver is `rx3_pad_layout.h`, deliberately free of player types, globals and libc so that it compiles on a computer and can be run against the preview's copy of it. Everything else about a control is a callback: what it says, whether it is lit, what it does.

There are two ways a touch can reach the row and only one is used. The player's six Beat FX touch objects report press and release for a rectangle each, which is convenient and caps the row at three controls per deck, because there are six of them and two decks. The other is the coordinate solver, which reports every event of a gesture once a press has been claimed. The row uses the second, so it can carry as many controls as it likes, track a drag, and tell a release inside a control from one that slid off it first. The six objects are parked off screen while a custom panel is up and handed back untouched on the way out, which is what keeps a native action from firing in the gaps between controls -- the one place the row declines a touch and lets it through.

Repainting is a request, not a paint. Anything may set `performance_refresh_pending`; the renderer's own thread drains it and holds a one second window at 100 ms intervals, because a single repaint loses a race the player starts on its own. Painting from the input path instead is a stall, and the row does not do it.

Lettering is artwork. `build_labels.py` renders one image per character on each ground, and the deck composes a string from that atlas at draw time. Whole captions were tried and cannot spell what the row says: the KEY centre carries a key and a move, `*3A +2`, which is twenty-four tonalities times twenty-five transpositions. The cells are colour-keyed on the pixels the ink never touched, so an anti-aliased edge -- a blend of ink and the ground it was drawn on -- survives, and a letter whose ink overflows its advance is not erased by the letter after it.

### On-screen messages

`EMERGENCY LOOP` is not special. It is one entry in a table of on-screen notices the player raises for itself, alongside `PC FULL`, `OVERCURRENT`, `DATABASE UNFOUND`, `QUANTIZE LIMITED` and dozens more. The mechanism is `ui::CautionManager`, and the binary is not stripped, so all of it is readable.

The entry point takes the text, which is what makes it usable from here:

    ui::Caution::set(bool show, uif::UiObject::Channel deck, unsigned short const *text) const

The player builds 72 `ui::Caution` objects in one static initialiser, each 32 bytes, and keeps a pointer to each in a table. A caution carries a service code as its first field, encoded as the code reads: `A008` is `0xa008`, `B051` is `0xb051`. Its placement is fixed at construction, in four shapes -- `CautionOnTop`, `CautionOnInfo`, `CautionOnBrowse`, and the plain base -- and the info-bar ones carry a life in milliseconds, 500 to 3000.

**Twenty of the seventy-two are constructed and then never referenced anywhere else in the binary**, so the player never raises them. Counting the literal pools alone is not enough to establish that: four more are reached through `movw`/`movt` pairs, and `B046` and `B059` look unused until those are counted too. The mod borrows `B051`, an info-bar notice with a three second life and no other reader.

Borrowing rather than building is deliberate. Constructing a caution means modelling a C++ object with bitfields and multiple inheritance, and a wrong field is a frozen player. That is not hypothetical here: a build predating this repository had caution workers of its own, and the only record of them is the line that disabled them, in `tools/rx3_runtime/patch_r38_ui.py`, kept in the tag `snapshot/before-cleanup` -- "invoking that path froze rbp". The cause was never written down.

### The player's language

One byte, `gUtilityLanguageNo`, and it counts from one. The Utility row that renders the setting reads it and subtracts one before indexing, which is the off-by-one to respect: a table that counts from zero and a byte that counts from one differ by exactly one language.

Eighteen, in this order:

| 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|
| ENGLISH | FRANCAIS | DEUTSCH | ITALIANO | NEDERLANDS | ESPANOL |

| 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|
| Russian | Korean | Chinese simplified | Chinese traditional | Japanese | PORTUGUES |

| 13 | 14 | 15 | 16 | 17 | 18 |
|---|---|---|---|---|---|
| SVENSKA | CESTINA | MAGYAR | DANSK | Greek | TURKCE |

The names are the player's own, read from the choices array the Utility row points at. Two arrays in the binary begin with a pointer to `ENGLISH`; the second is a coincidence in unrelated data, and the strings after it are noise. The one to read is the array the row itself uses.

Note what the shipped font covers. The main face is Latin, Greek and Cyrillic; Korean, Japanese and both Chinese sets come from a separate font. The player renders its own notices in all eighteen, so this path should reach both faces, but a message in a CJK language has not been seen on a deck.

The mod's own notices live in `mod/modules/core/rx3_messages.h`, one line per language in this order, written as UTF-16 literals so they stay readable. A language left out falls back to English, which is what the selection does with a short table.

### Two sizes of one face

One more thing that costs an afternoon if you miss it: **there are two sizes of the same face in play.** The font file is a condensed cut, roughly half the width and slightly taller, used for live text like track titles. The captions beside the effect controls are pre-rendered artwork in the normal width. A label meant to sit in that row must match the artwork, not the font file.

---

## 5. Front-panel input

Every physical control reports a 16-bit code. The complete list was recovered **statically**: one function maps each code to a human-readable name for diagnostics, so decompiling it and resolving the string pointers yields the whole table without pressing a single button.

The decompiler folds some branches into range comparisons rather than equalities, so six codes were re-read from their guard conditions rather than inferred. As an independent check, the extraction reproduced the two pad codes that had already been established much earlier by a completely different route.

This replaced a far worse plan. Mapping the panel by capturing traffic on the internal bus needs one press per control, a person standing at the machine, and a synchronisation window that is easy to miss. Two attempts failed on exactly that. Reading the table is one offline pass with no hardware involved.

Bus capture keeps one use: it alone tells you *which bit of which frame* carries a control. But you do not need that to *inject* input. The handlers take an input object whose layout is known: a 16-bit code, a channel selecting which deck, and a press/release flag. Synthesising one is enough.

The complete code table lives in [Appendix A](#appendix-a-front-panel-codes).

---

## 6. Stems

The computer separates the selected parts before a set. The RX3 reads a prepared package and mixes its PCM with the original track; it does not run a separator. The current preparation path emits VOCAL and DRUMS when available, with INST reconstructed from the original mix. The supported package and role rules are in [stem-package.md](#doc-stem-package); older `RX3STM1` sidecars remain a reader compatibility path, not the format to produce for new tracks.

### Playback and controls

The runtime loads and verifies a package before publishing its roles to the deck. A malformed package is refused as a unit. Each deck keeps its own selection; both decks share a memory budget. On the current intended Slip Loop layout, pads 5, 6 and 7 address INST, VOCAL and DRUMS, while pad 8 remains native. The STEMS touch panel can toggle or adjust the available roles. The [module guide](mod/modules/stems/README.md) records user behavior; the [panel contract](#doc-runtime-framework--panels-buttons-and-sliders-api-version-3) records ownership and gesture rules. Integrated playback, transitions and the complete two-deck memory budget still need physical acceptance.

### Package and waveforms

`RX3PKG2` frames 44.1 kHz stereo PCM, embedded waveforms and a manifest. The source track remains necessary for the full mix. The package has a 512 MiB size cap and verifies its entries before use. The current detailed waveform member uses `RX3WAV3` for Blue, RGB and PWV7/3Band at 150 columns per second for each audible selection. A missing or incompatible waveform falls back to native display; it does not invalidate valid audio. Exact layouts, old version handling and rejection conditions belong to [stem-package.md](#doc-stem-package) and [waveform-formats.md](#doc-waveform-formats).

### Preparation, reuse and proof

The host preparation path checks source identity and processing provenance before reusing PCM or completing a package. A successful preparation publishes a verified package atomically, preserving a prior valid package on failure. [Migration](#doc-stems-migration) covers compatible v0.5.2 material, while [waveform tests](#doc-waveform-in-memory-tests) give a measured local example. Imported stems need explicit alignment and listening checks; a matching file name or source hash alone does not certify audio quality.

The older separate-file reader, model selection notes, pad behavior and benchmark details are preserved in [the historical stems design](#doc-history-legacy-stems). They are not the current format or a current hardware result.

---

## 7. Key shift

The engine measurements below describe the earlier implementation and their named test signals. Current deck metadata, Key Sync rules and unresolved hardware cases are in [transposition.md](#doc-transposition) and [the Key Shift module guide](mod/modules/keyshift/README.md).

The player has no key shift, and that absence is real rather than hidden: a reachability census over all 17,745 functions in the binary found no dormant subsystem waiting to be switched on. So this is built rather than unlocked.

### Two engines, picked by direction

The firmware *does* contain a complete granular pitch shifter, the `Pitch` beat effect. It is excellent in one direction and poor in the other. Our own shifter is the mirror image. So each direction gets whichever engine wins it.

Share of output energy still on the intended note, measured on a 440 Hz tone:

| Semitones | -12 | -7 | -5 | +5 | +7 | +12 |
| --- | --- | --- | --- | --- | --- | --- |
| The firmware's shifter | - | 99.9% | 99.9% | 52.7% | **15.8%** | 84.6% |
| Ours | 43.6% | 69.4% | 99.7% | 99.0% | **97.3%** | 93.8% |

The asymmetry is structural, not a bug in either. Raising pitch has to *repeat* material, 0.414 s of source per second of output at +6 semitones, and that is where grain splices become audible. Lowering pitch skips material instead, which is far more forgiving. Both engines are driven at the exact equal-tempered ratio, and the result lands within ±0.7 cents across the range.

### Where the pitch stage sits, and where it must not

It hooks the deck's playback blocks, 64 to 512 frames at a time, and both of them, because the second replaces the first while Master Tempo is on. Hooking only the first made the shift *vanish* under Master Tempo rather than sound wrong, which is a much harder bug to read.

It deliberately does **not** sit on the buffer read that stems use. That read is random-access, shared with the analysis scan, and measured on hardware only 13.6% of its calls continue where the previous one stopped: two thirds re-read an overlapping position and a fifth move backwards. A shifter carrying a sequential grain cursor cannot live there, and the audible result was a stutter.

Stem mixing is indifferent to that access pattern because it is addressed by absolute frame position, which is exactly why the two features hook different places. This is the clearest example in the codebase of *where* a hook goes being determined by measurement rather than convenience.

### Driving the firmware's engine

Two parameters matter, and one of them cost a long debugging session:

- **Depth**, fixed at the exact unity point of the effect's percentage curve, where its shift speed equals the requested percentage and the mix is fully wet. The constructor leaves it at zero, which is total bypass: the effect runs and never moves a sample. That is why key shift first appeared completely dead.
- **Percentage**, carrying the semitone. The usable range covers exactly -12 to +12. Percentages are integers here, so each semitone takes the closest one; the worst case is -9 semitones, 13 cents flat.

The engine also sizes its working buffers from a frame count set at initialisation, so that field has to cover the largest block the hook can pass, not the audio device's block size.

### Our shifter

Self-contained: no libc, no libm, no allocation. Two read heads walk a history ring at the pitch ratio, half a grain apart, each windowed and cubically interpolated. Every design value in it was measured, and three findings are worth repeating because each one looks like a detail and is not:

- **Splices are aligned by correlation.** Without it, crossfading segments whose phases disagree forces a phase slew, and a phase slew *is* a frequency error. The whole shift came out at 97.9% of what was asked, 36 cents flat at -12.
- **Grain size depends on direction**, 512 frames up against 2048 down. Against an impulse train of eight hits at +7 semitones, a 2048-frame grain returns sixteen, every hit doubled, where 512 returns nine.
- **The crossfade stays amplitude-complementary.** The power-complementary alternative removes about a decibel of pumping on sustained noise and costs four spurious onsets, which is the worse trade.

Two artefacts remain, both inherent to time-domain shifting: roughly 2 dB of level ripple above the input's own on broadband material, and occasional transient doubling when raising pitch. Removing them needs a phase vocoder, and cost is not the obstacle: the current stage measures 4 µs against a 1451 µs block budget, with correlation bursts at 314 µs.

### Measuring both

Off the device, with both harnesses printing the same columns so the two can be read side by side. The first runs the firmware's real ARM code under emulation; the second compiles our shifter for the host. Neither is in this repository. Both are kept with the emulator, which is not published, along with the rest of the scripts that model the player rather than build for it.

```sh
emulate_pitch.py <application> --quality
measure_shifter.py
```

---

## 8. Faster decoder polling

Not a patch at all. After startup, a module sends two commands to the application's own debug console on a loopback UDP port, changing the decoder thread's sleep interval from 1 ms to 0.1 ms per deck.

The setting is volatile, alters neither flash nor the executable, and disappears on power off. It costs CPU and guarantees no particular reduction in end-to-end latency. It reduces one specific source of it. Failure is logged and does not stop the runtime.

---

## 9. Building and running

Nothing here is installable through a package manager. There is no packaging metadata and no console script; every entry point is invoked as a path.

### Make targets

| Target | Effect |
| --- | --- |
| `make help` | print the target list (the default) |
| `make hook` | cross-compile the ARM hook and assert the resulting binary |
| `make overcue-audio` | build the optional native audio helper for experimental OverCue export |
| `make autoexec KEY=<path>` | build the runtime image; `KEY` is required and must exist |
| `make app` | run the desktop application from source |
| `make new-module ID=<id> CATEGORY=<category> [NAME=<name>] [CORE=1]` | scaffold a module with a manifest, shell contract and README |
| `make test` | run the unit tests |
| `make preflight` | inspect every publishable file |
| `make clean` | remove the build directory and nothing else |

`PYTHON` defaults to `python3`, `BUILD_DIR` to `build`, `FIRMWARE` to `1.19`, `CC` to `clang` unless the environment sets it. `FIRMWARE` is the version an operator reads in the deck's menu, and it selects which modules go on the drive: each module's manifest lists the versions it is built against. `MODULES` empty means "the manifest defaults".

### The desktop application

The current application uses one webview window. Its navigation covers USB, Tutorial, Modules, Samples, Logo, Stems, Install the mod and Settings; some are sections within the same screen rather than separate windows. The UI contract is the checked source below, not a screen count from an older release.

| File | Contents |
| --- | --- |
| `app/ui/shell.py` | window and `--self-test` entry point |
| `app/ui/bridge.py` | methods exposed to the webview |
| `app/ui/web/index.html` | interface markup |
| `app/ui/web/app.css` | layout and appearance |
| `app/ui/web/app.js`, `components.js` | navigation, shared components and jobs |
| `app/ui/web/samples.js`, `logo.js`, `stems.js` | feature screens |
| `app/ui/web/i18n.js`, `app/localization/en.json`, `fr.json` | translation plumbing and visible copy |

**No screen holds engine logic.** They call `bridge.Bridge`, which calls `app/services/`, which drives `app/runtime/` and `app/stems/`. That is why the command line and the packager produce identical results without duplicating anything, and why a test can hold the whole surface with no window.

Two rules are easy to break and the result is invisible to whoever broke it.

**Arguments cross the bridge positionally.** The window packs what JavaScript passed into a list and calls the method with it, so a method taking `**kwargs` can never be reached with any of them set: it silently runs at its defaults. Anything richer than a scalar is one dict parameter, reduced to the keys it knows before a service sees it.

Appearance values and contrast rules belong in `app/ui/web/app.css`; the [UI design audit](app/ui/web/design-audit/README.md) records the measured checks for its tested revision. Re-run those checks after a visual change rather than assuming an older measurement still holds.

Progress is polled through `job_status()`, not pushed. The bridge and services define job ownership and cancellation; consult their current code before changing concurrent work.

```sh
make app                          # or: python3 app/ui/shell.py
```

### Command-line tools

Build a runtime with specific modules:

```sh
python3 -m app.runtime.cli build --firmware 1.19 \
  --patch beatjump-32bars --patch stems \
  --key /path/to/keyfile --output build
```

`--patch` repeats; omitting it selects every module whose manifest sets `default`. `--prebuilt-hook` accepts an already-compiled hook instead of invoking the compiler.

Build and inspect a runtime image:

```sh
python3 app/firmware/firmware_image.py autoexec \
  build/runtime build/autoexec.bin --key /path/to/keyfile
python3 app/firmware/firmware_image.py verify-autoexec \
  build/autoexec.bin --key /path/to/keyfile
```

The Stems screen and import paths use the shared services in `app/stems/`. A script can call `write_stem` in `app/stems/stem.py`; use the package API for complete `.rx3stem` publication.

### Environment variables

| Variable | Read by | Effect |
| --- | --- | --- |
| `RX3_SEPARATOR` | Stems preparation | path to a separator binary, instead of searching |
| `RX3_FFMPEG` | Stems preparation | path to FFmpeg; used as given, a missing filter is reported rather than worked around |
| `RX3_STEM_STUDIO_HOME` | Stems preparation | overrides the managed runtime and model cache location |
| `RX3_PREBUILT_HOOK` | packaging | path to the compiled hook; required when packaging, with no fallback |
| `RX3_KEY` | `make autoexec` and the application | path of the key file, outside the repository; `KEY=` on the make command line wins |
| `RX3_KEYSHIFT`, `RX3_STEMWAVE`, `RX3_THEME`, `RX3_LOGO`, `RX3_SEARCH_LATIN`, `RX3_SAMPLES_DIR`, `RX3_SAMPLES_CONFIG`, `RX3_LOG_FILE` | the hook, exported by each module's `module.sh` | switches that feature on, or names its directory or file; the names are typed by hand on both sides, so a rename touches both |
| `RX3_TAB_DELAY_MS`, `RX3_RENDER_PROBE` | the hook, when set by hand | diagnostics: delays the tab draw, or logs what the renderer is asked to paint |
| `RX3_STEMS_DIR` | on-device stems module | overrides the stem directory |
| `DECODER_SLEEP_NS` | on-device decoder module | overrides the polling interval |
| `CC` | build | compiler for the ARM hook |

### Prerequisites

| Component | Version | Notes |
| --- | --- | --- |
| Python | 3.12 in CI | no floor is declared or enforced |
| `cryptography`, `pycdlib` | pinned | `pycdlib` is imported lazily, with an external fallback |
| Clang and LLD | any recent | needed to compile the hook |
| FFmpeg | any complete build | must carry the `aformat`, `apad`, `aresample`, `astats`, `atrim` and `volume` filters |

Stem separation additionally needs a host Python between 3.10 and 3.13 to seed its own environment; that range is enforced in code. The separator and FFmpeg run as subprocesses, so no separation dependency is linked into the release archive. Which accelerator an environment was built for is recorded beside it, because a CPU-only build cannot be accelerated after the fact.

Cross-compilation flags:

```text
--target=arm-linux-gnueabi -march=armv7-a -marm -mfloat-abi=softfp -mfpu=neon
-fPIC -fno-stack-protector -fno-builtin-memcmp -fno-builtin-bcmp
-O2 -Wall -Wextra -Werror
-fuse-ld=lld -shared -nostdlib -Wl,--hash-style=sysv -Wl,--build-id=none
```

### Supported binaries

Five application checksums are accepted. Two are established here: firmware 1.19 stock and firmware 1.20 stock, each hashed from the player binary in that update. The other three were registered before this record was kept and their builds are not identified. An unlisted checksum aborts before anything is modified. This is the same refuse-rather-than-guess rule as every patch site.

### On the root password

The runtime does not need one. During filesystem analysis, on 10 August 2026, the stock password hash was found to use a legacy algorithm with no adaptive work factor that considers only the first eight characters, and it fell in about three minutes. Neither the hash nor the plaintext is published. Only the optional remote-shell module, disabled by default, uses the stock account at all.

The finding has not been reported to the manufacturer, and no report is planned. It is recorded here so that the state of it is not left to inference: what is written above is the whole of what this project has done with it.

### Build directory policy

`build/` is ignored by Git and generated by Make, Cargo, preview tools and packaging checks. `make clean` removes it. The working `build/librx3_core.so` and optional `build/overcue-audio/release/rx3-overcue-audio` can be rebuilt with `make hook` and `make overcue-audio`; neither is source or hardware evidence. Dated engineering findings belong in this reference; the acceptance plan and session records belong under `docs/acceptance/`. Keep private binaries and raw captures in `local/`.

---

## Appendix A: front-panel codes

Recovered statically as described in [section 5](#5-front-panel-input). Codes are 16-bit values carried in the input object; the channel selects the deck.

### Pad mode selectors

| Code | Control |
| --- | --- |
| `0x4113` | Hot Cue |
| `0x4114` | Beat Loop |
| `0x4115` | Slip Loop |
| `0x4116` | Beat Jump |

### Performance pads

Pads 1 to 8 occupy consecutive codes from `0x4117` to `0x411e`. These are physical input codes, independent of which current module owns a pad in a selected mode. The current Stems mapping is described in [section 6](#playback-and-controls).

### Browse controls

These travel a different path from the pads: a table pumped by the interface cycle rather than the deck's own handlers, which is why they respond even when the deck is not started.

| Index | Control |
| --- | --- |
| 4 | Source |
| 5 | Browse |
| 6 | Tag List |
| 7 | Playlist |
| 8 | Search |
| 10 | Menu / Utility (a long press, held up to three seconds) |
| 11 | Rotary encoder push |
| 12, 13 | Load, deck 1 and deck 2 |
| 17 | Back |

Menu is worth calling out: the handler measures how long the key is held, so tapping it is a *different gesture*, not a faster one.

<!-- BEGIN INTEGRATED DOCS -->
## Complete documents migrated from `docs/`

Each section below incorporates a former engineering document. French source material is rendered in English, and headings and internal links have been adjusted for this file. Source markers and hashes identify the pre-consolidation originals, not the edited text below. Historical findings retain their original date and evidence level. The hardware acceptance booklet is maintained separately in [ACCEPTANCE.md](docs/acceptance/0.6.0/ACCEPTANCE.md).

<a id="doc-adr-0001-restructure-in-place"></a>
### ADR-0001: Restructure the desktop application in place behind a verified application boundary

<!-- source: docs/adr/0001-restructure-in-place.md | sha256: 2ed191479a474817bdb5d938f6fc1864c13ae8244be30d8f6b1f16cbdc1e64f8 -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

**Status:** Proposed, amended after independent review; not approved for implementation
**Date:** 2026-09-27
**Deciders:** François Brille
**Scope:** Desktop application, its public operations, workers and packaging. No redesign of the C runtime and no change to on-drive formats.

<a id="doc-adr-0001-restructure-in-place--context"></a>
##### Context

The desktop application is about 12,500 Python lines under `app/`, including a 1,169-line bridge exposing 57 public operations. It uses pywebview, Python services and engines, separately provisioned inference dependencies, and PyInstaller. At review time HEAD was `256596cbdb8b2fb59a1a52c342fa9de51918c4a8`, but extensive staged, unstaged and untracked changes mean HEAD alone does not identify the reviewed code. Capture the working-tree baseline before implementation.

The bridge contains application policy, engine calls, serialization and task scheduling. Four cancellation exception classes coexist. The stems import graph contains cycles across audition, importing, package, waveform and cache. The page loads nine global scripts. These are structural problems; changing the implementation language or the window shell does not resolve them by itself.

Existing tests remain useful but are not a complete behavioral oracle. At review time the suite ran 329 tests with one failure and two skips. The failure is `test_ui_setting_events_and_persistence`, in `tests/key_sync_settings.cjs`, reading `hidden` from an undefined element. The source self-test passes with 57 operations. Neither result validates the packaged UI, all supported operating systems, inference accelerators or playback on the RX3. The stems tests pin implementation internals with more than 50 `patch.object` calls (54 in `test_stems*.py` alone), which is a review signal, not a reason to delete them.

The existing exclusive task slot is valuable but narrower than first claimed. It is local to a Bridge instance. `mod_remove` (bridge.py:505), `samples_activate` (bridge.py:723) and `samples_remove` (bridge.py:728) reach mutating services while that slot is occupied, `drive_report` writes a probe file on the drive (services/drive.py:79), and `runtime/cli.py` invokes the build engine directly. Preserving `_claim` alone does not establish exclusion across all writers or application processes.

The desktop produces data consumed by the deck even when the C sources are unchanged. File structure, PCM properties, manifests, waveform interpretation and settings compatibility remain acceptance requirements. Local fixtures, real exports, packaged desktop workflows and hardware playback establish different parts of that evidence.

<a id="doc-adr-0001-restructure-in-place--decision"></a>
##### Decision

Retain Python, pywebview and PyInstaller for this restructuring. Introduce a typed, explicit application boundary and migrate one feature at a time. Keep existing behavior unless a defect and its intended correction are explicitly recorded. Reconsider the shell in a separate ADR only after a representative prototype demonstrates a useful improvement.

Do not combine code relocation with automatic relocation of installed data. First centralize path resolution while retaining existing physical locations. A physical data migration requires its own recovery and compatibility design.

The intended layout is:

```text
contract/              standard request/result schemas and operation metadata
app/
  platform/            paths, packaged resources, cancellation, owned processes,
                       tool discovery, diagnostic logging and process locks
  jobs/                exclusive task runner, identity, state and progress
  services/            application use cases and shared GUI/CLI entry points
  stems/               engines and formats, with an acyclic dependency graph
  samples/ ...         other engines and formats
  localization/        Message, LocalizedError and catalogs
  ui/
    shell.py           window creation and lifecycle binding
    host.py            native dialogs and file-manager actions, if extraction helps
    bridge.py          explicit dispatch, request validation and one serialization point
    web/               modular source, one folder per screen, shared client
```

`platform` names OS-facing facilities explicitly and distinguishes them from the embedded `mod/modules/core`. It must not become a catch-all business layer. No dependency injection container, CQRS or generic plugin system is introduced. Explicit arguments or small protocols at filesystem, process and inference boundaries are allowed where they make behavior testable.

<a id="doc-adr-0001-restructure-in-place--application-boundary-and-contracts"></a>
###### Application boundary and contracts

- Use an explicit operation registry. Adding a public Python helper must not expose a new operation automatically. Separate application operations from host actions such as file selection and Reveal.
- Keep one authoritative contract definition. Prefer standard JSON Schema for transport requests and results, validated through an established Python validator and used to generate JS type declarations and a typed client. Validate this choice on two representative operations before applying it to all 57; do not build a custom schema language or general code generator.
- Pass one named request object through pywebview rather than long positional argument lists. Temporary adapters preserve existing callers while each feature migrates; remove them when its callers and tests have migrated.
- Define nullability, defaults, numeric bounds, allowed enum values, unknown-field behavior and stable error codes. Structural validation does not replace filesystem checks or application invariants in services. CLI callers must enforce the same invariants.
- Use a consistent success/error envelope. Keep `Message` and `LocalizedError` machine-readable until the existing localization serialization boundary. Unexpected errors return a neutral localized message and a diagnostic identifier; sanitized stack traces remain in local logs, never in the page.
- Results are typed per operation, including task results discriminated by operation. A common envelope must not flatten build results, sample exports and per-track stems outcomes into an untyped dictionary.
- Generate and actually check the frontend client types, for example with checked JavaScript and `tsc --noEmit`. Type declaration generation alone proves nothing about callers. CI verifies generated files are current and checks representative serialized responses against the schemas.
- Fixtures, defaults and UI mocks derive from, or are checked against, the same contract definitions, so a drifting mock fails in CI instead of hiding a mismatch.
- Backend validation stays authoritative. The UI may use the same constraints for immediate feedback; removing all frontend validation is not a goal.

<a id="doc-adr-0001-restructure-in-place--tasks-exclusion-and-cancellation"></a>
###### Tasks, exclusion and cancellation

- Preserve one exclusive long-running task at a time. This restructuring introduces no queue, resume framework or concurrent preparation feature.
- Centralize all operations that can conflict with publication, including synchronous removal and activation. Admission and mutation must share a guard; checking an idle flag before a separate write is insufficient. Classify operations by actual side effects, since even `drive_report` writes a probe file.
- Add a shared interprocess exclusion mechanism for mutating GUI and CLI entry points, or explicitly enforce a single writer process. Internal service composition must not reacquire the guard recursively. Document the scope and its limits concerning external programs.
- Extract the generic cancellation primitive and owned-process control from `stems` to a neutral package. `jobs` must not depend on the stems engine. One cancellation exception and token do not imply that every operation owns subprocesses.
- Give each task a stable identity. Scope status, cancellation and progress updates to that identity so a delayed update cannot modify the next task.
- Specify transitions from running to cancelling and a terminal state. Cancellation is a request, not evidence of termination. Release the task slot only after workers, process trees and file handles are cleaned up, including on launch failure and window closure.
- Define progress as a localized stage, a fraction in `[0, 1]` or `null`, and typed detail. Distinguish per-stage from overall progress. Convert existing percentage callbacks through explicit adapters and permit returning to indeterminate progress.
- Preserve commit boundaries. Do not insert cancellation checkpoints into a publication sequence where interruption would make its reported outcome false. Per-track results must identify already committed outputs and remaining failures after cancellation or partial success.
- Scheduling threads belong to the task runner. Service use cases stay callable synchronously for tests and CLI execution; engine-managed worker pools and preview-server lifecycles remain explicitly owned resources.

<a id="doc-adr-0001-restructure-in-place--stems-dependency-structure-and-tests"></a>
###### Stems dependency structure and tests

Separate low-level format readers and writers and shared audio primitives from orchestration. Readers must not import publication workflows, waveform generation or audition orchestration. Move multi-engine workflows into application services or clearly identified orchestration modules. Preserve the persistent inference worker, its framed protocol, model reuse and disposal after failure.

Add behavioral characterization before moving each responsibility. Keep the precise low-level tests for PCM, binary formats, hashes, cache provenance, timing, frame counts and publication failures. Replace implementation-coupled mocks only when equivalent observable behavior is covered. Do not rewrite the implementation and its expected test output together merely to restore a green suite, because that can erase regressions from the assertions.

Use deterministic byte comparisons where output is deterministic; normalize documented volatile metadata before comparisons elsewhere. Real inference comparisons need recorded model hashes, package versions, accelerator and appropriate numerical tolerances. Successful mocked service calls are not proof of inference or audio parity.

<a id="doc-adr-0001-restructure-in-place--paths-and-installed-data"></a>
###### Paths and installed data

Centralize path and resource discovery without changing storage on the first pass. Preserve explicit environment overrides, external runtime precedence, existing model caches, sample project asset references and saved webview preferences. Keep different lifecycles for configuration, persistent user data, caches, logs and managed runtimes, even if they share a product namespace.

Do not treat renaming an existing virtual environment as a directory migration. Installed scripts can contain absolute interpreter paths, and Python documents virtual environments as generally non-portable. Reuse the old environment in place, or rebuild it at its final destination and validate it before switching the recorded location. Retain reusable models and the previous working environment until success. See the [Python venv documentation](https://docs.python.org/3/library/venv.html#how-venvs-work).

If consolidation is later justified, make it versioned, idempotent and recoverable after interruption. Define conflict precedence, free-space checks, verification before switching, rollback compatibility and treatment of absolute paths inside sample projects. Do not silently delete old data or trigger a multi-gigabyte download just to simplify the directory tree. Update user-facing folder-removal instructions if their scope changes.

<a id="doc-adr-0001-restructure-in-place--frontend-and-packaging"></a>
###### Frontend and packaging

Convert one screen at a time using a shared transport client and explicit imports. Preserve localization behavior, settings persistence, preview audio and UI outcomes. Native dialogs remain shell concerns; they do not become business services simply to make the bridge smaller.

The current shell loads a `file://` URL (shell.py:125), and native ES module loading has origin and CORS constraints there, so choose and validate the asset transport before converting all scripts. A small reproducible build that bundles modular source into local static assets is a reasonable initial option because it preserves the current origin and the saved browser state. A local HTTP asset server is another option, but requires explicit persistence and access-scope decisions. Neither option requires a frontend framework. See [JavaScript module loading constraints](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules) and the [pywebview API](https://pywebview.flowrl.com/api/).

Update packaging as part of this change: the PyInstaller spec copies only files directly under `web/` (packaging/toolkit.spec:50), so screen subdirectories would be silently omitted. Package generated schemas, client assets, worker scripts and transitive frontend resources deliberately, excluding audit tooling. Extend the self-test to verify the declared asset set and run a real packaged-webview startup test, because scanning HTML `src` and `href` attributes does not execute JS or discover its transitive imports.

<a id="doc-adr-0001-restructure-in-place--options-considered"></a>
##### Options considered

| Option | Assessment | Decision |
|---|---|---|
| Python restructuring with current shell | Preserves working engines and permits incremental verification. Medium risk overall; publication, task control and data migration deserve separate gates. | Chosen |
| Full Rust rewrite | Reimplements orchestration and requires a proven strategy for the current models and inference runtimes. Structure could improve, but language choice provides no automatic parity. | Rejected for current scope |
| Tauri with Python sidecar now | Adds process lifecycle, IPC, crash handling and per-platform packaging while the existing structural problems remain. | Deferred |
| Electron | Provides a bundled browser runtime, which can improve rendering consistency, but adds distribution and maintenance costs while retaining Python inference needs. | No demonstrated requirement |

Earlier drafts promised a static 10 MB binary, instant startup and about a week of porting work. Those figures were not measured and are removed. Tauri uses system webviews and a process architecture, a Python sidecar may itself be packaged with PyInstaller, and signed Windows applications can still encounter reputation warnings. See [Tauri sidecars](https://v2.tauri.app/develop/sidecar/), the [process model](https://v2.tauri.app/concept/process-model/) and [Windows signing](https://v2.tauri.app/distribute/sign/windows/).

A shell change is assessed on measured startup time, installed application size separately from models and runtimes, memory use, installation success, update reliability, native integration and maintenance cost. Python-to-Rust performance gains require profiling of actual bottlenecks; compiled inference does not imply every Python processing stage has negligible cost.

<a id="doc-adr-0001-restructure-in-place--implementation-sequence-and-acceptance-gates"></a>
##### Implementation sequence and acceptance gates

These are dependent milestones with small reversible changes inside each one, not independent bulk edits. Every behavior change is identified separately from structural movement.

| Milestone | Work | Required evidence before continuing |
|---|---|---|
| 0. Baseline | Identify the working-tree snapshot; resolve or explicitly isolate the existing UI-test failure; inventory operations, writers, data roots, outputs and runtime versions. | Reproducible baseline, relevant behavioral fixtures, documented remaining validation gaps. |
| 1. Boundary pilot | Specify request, error, progress and result envelopes; migrate module selection and one long-running build use case through the service boundary with temporary adapters. | Existing callers remain compatible; valid and invalid requests and serialized responses are checked; JS callers are type-checked. |
| 2. Execution control | Extract generic cancellation and process ownership and the task runner; apply admission control to all conflicting mutations and GUI and CLI writers. | Concurrent launch, synchronous mutation, second-process exclusion, early cancellation, launch failure, cleanup and close tests. |
| 3. Application API | Move remaining business rules from the bridge into services one feature at a time; relocate sample draft orchestration; migrate contracts and remove adapters by feature. | Operation parity, service-level behavior and no engine-to-service or engine-to-UI imports. Host operations are separately identified. |
| 4. Stems internals | Extract pure format and audio primitives, break cycles, split settings, catalogue and provisioning responsibilities and remove proven unused code. | Characterization exists before each move; format, PCM, cache, worker and interruption checks pass. Profile representative workloads. |
| 5. Platform policy | Centralize data, resource and tool resolution while preserving existing locations and runtime precedence. | Legacy installs, overrides, managed and external runtime detection and packaged resource discovery behave as specified. No physical migration in this milestone. |
| 6. Modular frontend | Migrate shared infrastructure and screens; choose module delivery; update asset packaging and replace source-position tests with behavior tests. | Packaged startup, settings persistence, six-screen workflows, preview audio and localization on the supported webview and OS matrix. |

Physical data consolidation and a shell replacement are separate optional follow-up decisions. Neither is required for this ADR to be complete. Any shell prototype must cover dialogs, worker startup and failure, cancellation, window closure, preview streaming, persisted settings and signed distribution on the target platforms.

<a id="doc-adr-0001-restructure-in-place--consequences"></a>
##### Consequences

- New operations have an explicit contract and reuse existing services and task infrastructure.
- The shell boundary becomes narrower and easier to replace, but transport contracts do not eliminate OS integration, distribution or lifecycle work.
- Test coverage grows at behavior boundaries while the precise low-level tests remain. A green suite is evidence within its exercised scope, not a hardware guarantee.
- Installed data remains usable throughout the code restructuring. Migration complexity is paid only if a separate benefit justifies it.
- No change to the player-facing files or their semantics is implicit in this restructuring. Any intended format or DSP change requires its own decision and acceptance evidence.

<a id="doc-adr-0001-restructure-in-place--action-items"></a>
##### Action items

1. [ ] Review and accept this amended decision and its milestone gates.
2. [ ] Record a reproducible baseline and investigate the current UI-test failure.
3. [ ] Inventory all mutating entry points and specify their admission policy.
4. [ ] Implement and validate the boundary pilot before selecting contract-generation tooling for the whole surface.
5. [ ] Complete milestones 2 through 6 in independently reviewable changes.
6. [ ] Record packaged desktop results separately from fixture and hardware results.
7. [ ] Open a separate data-migration or shell ADR only when evidence justifies it.

---

<a id="doc-browse-scroll-performance"></a>
### BROWSE: reduction of repeated readings during scroll

<!-- source: docs/browse-scroll-performance.md | sha256: 7f45022046dec6863141474b466b675a1769e1db658c899f0edfc46c7445a89a -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

<a id="doc-browse-scroll-performance--current-correction-native-local-metadata"></a>
##### Current correction: native local metadata

The 29 September emulator follow-up isolated the extra per-track request/response streams: ten expired rows added about 872 ms before their page could be displayed. Increasing the timeout only postponed the pause.

The core now observes `DBSMain_ListBufGetContents` and `DBSMain_ListBufRec2CommCmd`. On the database server task, it copies artist, duration, BPM and key for the records being returned from a local rekordbox USB database. The client only reads bounded snapshots; neither the renderer nor another thread calls into that database connection. A page generation prevents reuse of an earlier server snapshot, including when clearing storage would contend with a reader. Drive identity, database kind and the local/remote connection flag separate sources. Remote and unsupported records retain the native metadata fallback.

The existing 32-entry client cache retains source/row/settings invalidation and retries failed reads. Unchanged exported metadata no longer expires by wall clock. A fresh local snapshot can update a cached record even when its title is unchanged. Colours and harmonic compatibility are still recomputed rather than cached. Server snapshots add approximately 9 KiB; allocation remains bounded. The counters distinguish server preparation time from client processing time, so a shift of work is not reported as a free speedup.

`ConvertRKey2RStr` consumes its DBCCmd input string, even for numeric values. The new snapshot path formats BPM and duration without calling it or allocating a native string. Native stream formatting keeps its original ownership rules.

Tests cover copied values, two drives with the same track ID, snapshot replacement, unknown keys, numeric rounding, allocation ownership and idle/clock changes. See [emulator results](#doc-emulator-feedback-20260929) for measured evidence and hardware limits.

<a id="doc-browse-scroll-performance--earlier-diagnosis-superseded-cache-timeout"></a>
##### Earlier diagnosis (superseded cache timeout)

<a id="doc-browse-scroll-performance--retour-matriel-du-29-septembre"></a>
##### Material return of 29 September

The scroll remains slow on the RX3, according to François' first essay. The gain
therefore does not validate a perceptible improvement. A building
diagnostic add meters and timings described in
[the hardware report](#doc-hardware-feedback-20260929--browse-remains-unresolved).

<a id="doc-browse-scroll-performance--diagnostic-et-porte"></a>
##### Diagnosis and scope

The target symptom is slow displacement in the list, not scrolling
horizontal text long. 60 ms interval and two seconds break
remain unchanged.

The line hook reconstructed at most fourteen tracks per message. Before
patch, each track triggered a reading of its metadata for the
column added/preserved, even if it was present on the previous page.
Additional key could also be requested for Key Match or
Key column. The local disassembly of `dbcl GetNewKeyID` shows an allocation,
a request sending and a reply waiting: this is not a simple access to
A table in memory.

This additional cost is demonstrated in the code and in a host bank. **Its share in the
* Other possible costs
remain rendering, native requests, USB support and creation of surfaces
of text. No promise of image frequency arises from the number of queries.

<a id="doc-browse-scroll-performance--correctif"></a>
##### Correctif

`core/services/rx3 browse.c` keeps 32 tracks raw metadata in
34 304 fixed bytes. It does not create any additional thread or dynamic allowance
and does not move any database access to rendering.

- Reuse requires the same context, object and basic connection, index
source, depth, sorting, requested fields, track ID and native line content.
- Each successful reading expires after 30,000 ms, without renewal on a hit.
An unobserved change in metadata can therefore remain visible until
expiry and next native update; the cache does not force a
Refreshing the screen after 30 seconds.
- Changes in track key, invalidation of a deck, rejected pages
or off track list and the removal of a provider invalidate the generation.
Worker alone changes entries; other callbacks only uncrement
an atomic generation.
- Incomplete streams, formatting failures, unknown keys/lookup failures and
clock failures do not remain frozen in the cache.
- MASTER, compatibility rules and colors are recalculated with each message;
no green/yellow/orange/red classification is cached.
- Without any additional key or column, no metadata request
is added. A purely tonal column does not open the full flow of fields.

The same IDs of a new key must never inherit indefinitely
values of the previous one. Connection/source range and short expiration
reduce this risk; the case of native reuse of the same objects after removal
and reintegration must be checked on the reader. The first page, the pages without
recovery and expired values retain the cost of native reading.

<a id="doc-browse-scroll-performance--reproduction-hte"></a>
##### Reproduction hôte

`tests/test browse performance.py` compiles the real service C by replacing its
firmware calls by doubles that count access and provide data
separate by track ID. No mapping to a firmware address is created on the Mac.

Deterministic scenario: 100 successive windows of 14 tracks, advancing from a
track, with a simulated clock moving 8 ms per window. These 800 ms are one
**Simulation parameter**, not a scrolling or calculation measurement.

| Access added by the service | Before | After |
|---|---:|---:|
| Metadata requests | 1 400 | 113 |
| Key requests | 1 400 | 113 |
| All these applications | 2 800 | 226 |

91.9 per cent reduction in this scenario. After the first window, only the new
piece requires information. Slower navigation beyond expiration
produce more readings; This is voluntary to limit seniority.

The tests also cover: return to a track, restricted eviction, change of
source/context/connexion/depth/tri/fields, line content changed,
publication/key invalidation, change of time, counter wrap,
interrupted stream, formatting failure and key request alone. Browse tests
cover sorting, preservation of native filters and markers, and
l’ownership des hooks et des chaînes.

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_browse*.py'
make hook
make test PYTHON=.venv/bin/python
make preflight
```

<a id="doc-browse-scroll-performance--mesure-matrielle--mener"></a>
##### Physical action

Reuse BR-09 from the [acceptance cases](docs/acceptance/0.6.0/ACCEPTANCE.md#doc-acceptance-0-6-0-cas-de-test), with the
same firmware, export, support, sorting and settings on the buildings before/after.
Archive both hashs. No material gain is reported before this measure.

1. Pick up the stock drive, then the previous candidate, then the corrected candidate.
Check PID, core mapping and readiness for each build. Deployment
is not done during a mix in progress.
2. For everyone: Browse Columns alone (BPM), Key Match alone with MASTER known,
then both; Finish with the full profile and two reading decks.
3. Film the wheel and screen: 30 slow pins spaced more than a second,
30 steps at about 5 Hz, then a quick scroll of 100 positions and a return.
Repeat three times. Counting the gestures actually made, not only
those requested, and compare lines/IDs travelled.
4. Measuring time gestures → visible selection, total time, p50/p95 and worse gel;
simultaneously record audio and a CPU/light memory telemetry.
Separate cold first page, scrolling over and large jumps.
5. Check for correction of values and colors after change of MASTER,
Transposition, sorting, filter, category and USB drive, including same track IDs
between two exports. Confirm physical loading operation.
6. If no gain appears, do not blindly elongate the TTL: instrument the
native calls and rendering to measure the dominant cause before the continuation.

Status: local patch; hardware validation pending. Roadmap remains
« In progress ».

<a id="doc-browse-scroll-performance--deuxime-retour-matriel-du-29-septembre"></a>
##### Second material return of 29 September

Scrolling remains judged slow. The track of the candidate `e36fe0...` measures
6 list answers, 745 ms of added processing, 35 field readings,
22 new entries and 12 expirations, in a single cache context.
The average cost added is 21.3 ms per field reading. This quotient is
not an isolated measure of the time of each call, nor of the full screen latency.
There is no additional key request in this trace.

The initial delay of a second caused revisions at the normal rate of
the wheel. Next candidate increases absolute limit to 30 seconds keeping
Source, context, line and configuration invalidations. Compromise: one
metadata modification without invalidation event can remain in cache
up to this limit, then until the next list answer.
First readings remain synchronous; This change therefore does not demonstrate
resolution of all the slowness. The local test now covers the guts
spaced 1.2 seconds with 21 ms by missing reading, and not only one
Fast synthetic scanning. RX3 validation always required.

---

<a id="doc-emulator-feedback-20260929"></a>
### Recipe of the September 29 candidate in QEMU

<!-- source: docs/emulator-feedback-20260929.md | sha256: 22a8fdaa375c1e6741003301c1244fbd949ddb3efaddcf71210a5a17ea3c732d -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

**Verdict: candidate not validated for release.** Eye and changes
requested visuals work in the interactive session. An exception to
start with notification and a BROWSE at the end of the cache remain
observed. No result below is a physical validation.

<a id="doc-emulator-feedback-20260929--provenance-et-conditions"></a>
##### Source and conditions

- Prepared image for DJ FRANCOIS : SHA-256
  `d3f5b3a569e13e357f51b4966fb71d6cda31471638a6b38a5cdfb3c86436e9fe`.
- Core extracted from this image, without recompilation : SHA-256
  `67ab2510c4df1a6a646fc7a40924e9922526da0150e532d470f522c644f13670`.
- Firmware 1.19, SHA-256 from source rbp:
  `60bcbd8876116bf09f0d8f747f95d7c7d3081ebd39d6fe14d56005a22f7f3b09`.
- QEMU TCG machine track ARMv7, four vCPU, 1/4 transport clock,
framebuffer 1280 × 800, real touch events and emulated UPE encoder.
- Core assets extracted from the candidate, BROWSE settings and harmonics included
  from its files. KEY, STEMS, Stemwave, Key Match, BROWSE and title-eye services active.
This is not a recipe for all autoexec modules.
- Existing test library: 12 tracks, including a playlist of 10 tracks.
Two tracks actually loaded: DO IT and Antisocial (Extended MK Remix).
Source support is not modified: QEMU disk with disposable overlay.

The first test of the complete autoexec mounts its ISO, but does not provide
confirmation of activation before the end of the session. Its generic report
stock therefore does not validate **no** mod. The following tests load directly
the exact core and its assets. This complete installation remains unvalidated.

Traces of the core are redirected to the console for measurements. The
generic collector always searches for `/tmp/rx3-stems.log`: its indicator
`hook active` remains false in these instrumental tests. The original reports
are kept as is. The activation is checked separately by the message
`RX3 performance hook active`, marker `hook ready`, core print
and mod specific rendering/interactions.

<a id="doc-emulator-feedback-20260929--rsultats"></a>
##### Results

| Monitoring | Observed result |
| --- | --- |
| KEY/STEMS on startup | Present before any interaction with their area; Initial refresh marker present |
| Eye deck 1 | Support: eye closed/barred and title erased; Second support: restoration |
| Eye deck 2 | Same result; the two choices are independent, including the two titles hidden simultaneously |
| Eye quality | Smooth contours visible in framebuffer catches |
| Touch geometry | Journalized origins (106,584) and (746,584) consistent with native windows |
| KEY → BEAT FX | Good selected tab and stable status after transition |
| STEMS → BEAT FX | Good selected tab and stable status after transition |
| New BEAT FX support | No change in tabs or pad area |
| STATUS ↔ BEAT FX | Correct selection in catches |
| Old eye position in BROWSE | No change in daytime masking; the event remains in the browser |
| BROWSE en cache | Additional list answers without new field readings |
| BROWSE after expiration | At once again; Not accepted as complete correction |
| Start notification enabled | Two tests, two exceptions and stop rbp, code 134 |
| Notification disabled | Interactive session completed without this stop |

<a id="doc-emulator-feedback-20260929--stabilit-des-transitions"></a>
###### Stability of transitions

586 samples of tab/pad regions, spaced approximately 60 ms in practice.
Each action is observed for about 4.7 seconds. The last 1.5
seconds of each phase contain only one state of pixels for each
region. Only one tab change per transition, none supporting BEAT FX
Repeated. The passage STEMS → BEAT FX produces two successive states of the zone
pads during the re-drawing, then remains stable: no repeated deoscillation detected.
A phenomenon shorter than sampling cannot be excluded.

<a id="doc-emulator-feedback-20260929--browse--bnfice-du-cache-et-limite-persistante"></a>
###### BROWSE: benefit of cache and persistent limit

In the survey before/after the last movement:

- Answers 23 → 30; accumulated added time 2,976 → 2,981 ms.
- Field readings unchanged at 40: seven hot responses add 5 ms
total mod processing to this extent.
- The previous expiration triggered ten revisions: the reading counter
from 30 to 40, from 0 to 10.
- Encoder time → visible selection change after expiration: 1,162.9 ms.
- Seven movements in cache: 140.8 to 230.6 ms; median 201.1 ms.

These delays include firmware, virtual devices and rendering
under TCG. They are not transferable to RX3. The small library
does not cover the escape of the 32 entrance cache or a long journey of new
Titles. Eight tests conducted beyond the last line are excluded from
latency: selection was legitimately limited. The first point detector
selection met the pixels of the numbers; its times are ruled out at
profit of the detector per blue surface, recorded separately.

Switching from 1 to 30 seconds avoids frequent expirations, but delays
Instead of deleting synchronous readings. We still have to deal with this.
path to claim fluid scrolling.

<a id="doc-emulator-feedback-20260929--notification-de-dmarrage"></a>
###### Start notification

Both tests with activated notification stop after:

```
messages: startup notice queued
terminate called after throwing an instance of 'char const*'
Aborted
RX3M: rbp-exit=134
```

The same binary with `RX3 MESSAGES=0` allows all interactive controls.
This isolates the path activated by notifications in this bench; the exact site
which raises the exception has not been traced. No equivalent crash is demonstrated
on the RX3. The above visual validations are therefore explicitly
conditional on deactivation of notifications in the trial.

<a id="doc-emulator-feedback-20260929--preuves-locales"></a>
##### Local evidence

Sous `../rx3-emulator/outputs/rx3-machine/` :

- `feedback-20260929-candidate/`: autoexec installation test, not validated.
- `feedback-20260929-direct/` and `feedback-20260929-notice-repeat/`: two judgments
with notification enabled, reports and logs retained.
- `feedback-20260929-no-notice/` : session interactive, `feedback-verdict.json`,
`transitions.json`, `browse-scroll-validated.json`, measuring scripts,
  captures `boot.png`, `loaded2.png`, `hidden-both.png`, `both-restored.png`,
`key-to-beatfx.png`, `stems-to-beatfx.png` and intermediate catches.

No core or emulator code was changed during this recipe.
No new image was copied on DJ FRANCOIS. The QEMU sessions of this
were discontinued after collection.

---

<a id="doc-extract-initramfs"></a>
### Getting a root filesystem from the published GPL sources

<!-- source: docs/extract-initramfs.md | sha256: be5a9951f718b5ca516b658d98c0a0d9f13bde3718a8124adee05a9508afb38a -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

The app does this for you when it needs the key: see step 4 of the README. This page is the same path by hand, for anyone who prefers to run it themselves or wants the whole filesystem rather than the key alone.

The XDJ-RX3 source package is distributed as two ZIP files:

```text
A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

Each ZIP contains one part of a split `tar.bz2` archive. Reassemble the two parts, extract the tree, and the filesystem archive is already in it: for reading the filesystem, there is nothing to compile.

```text
ZIP files
   ↓
split .tar.bz2 parts
   ↓
reassembled .tar.bz2
   ↓
source tree
   ↓
initramfs.tar.gz          already in the tree — section 5
   ↓
root filesystem
```

Every step of that path is ordinary archive handling, so **macOS, Linux and Windows all do it natively**. `make_rootfs` produces the same archive from the sources instead; it is the one step that wants a Linux environment, it is section 6, and it is only for changing what goes into the filesystem.

---

<a id="doc-extract-initramfs--1-extract-the-two-zip-files"></a>
##### 1. Extract the two ZIP files

The ZIP files use **Deflate64**, so 7-Zip is recommended.

<a id="doc-extract-initramfs--macos"></a>
###### macOS

Install 7-Zip:

```bash
brew install sevenzip
```

Create a working directory and extract both files:

```bash
mkdir rx3-source
cd rx3-source

7zz x ../A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
7zz x ../57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

<a id="doc-extract-initramfs--linux"></a>
###### Linux

Install 7-Zip.

Debian / Ubuntu:

```bash
sudo apt update
sudo apt install 7zip
```

Fedora:

```bash
sudo dnf install 7zip
```

Then extract both files:

```bash
mkdir rx3-source
cd rx3-source

7zz x ../A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
7zz x ../57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

On some distributions, the executable may be named `7z` instead of `7zz`.

<a id="doc-extract-initramfs--windows"></a>
###### Windows

Install 7-Zip, then open PowerShell in the directory containing the ZIP files.

```powershell
mkdir rx3-source
cd rx3-source

& "C:\Program Files\7-Zip\7z.exe" x ..\A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
& "C:\Program Files\7-Zip\7z.exe" x ..\57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

After extraction, you should have:

```text
pioneerdj_xdj_rx3.tar.bz2.00
pioneerdj_xdj_rx3.tar.bz2.01
```

---

<a id="doc-extract-initramfs--2-reassemble-the-split-archive"></a>
##### 2. Reassemble the split archive

The two files are consecutive parts of the same `tar.bz2` archive.

<a id="doc-extract-initramfs--macos--linux"></a>
###### macOS / Linux

```bash
cat \
  pioneerdj_xdj_rx3.tar.bz2.00 \
  pioneerdj_xdj_rx3.tar.bz2.01 \
  > pioneerdj_xdj_rx3.tar.bz2
```

<a id="doc-extract-initramfs--windows-2"></a>
###### Windows

Using `cmd.exe`:

```cmd
copy /b pioneerdj_xdj_rx3.tar.bz2.00+pioneerdj_xdj_rx3.tar.bz2.01 pioneerdj_xdj_rx3.tar.bz2
```

---

<a id="doc-extract-initramfs--3-verify-the-reconstructed-archive"></a>
##### 3. Verify the reconstructed archive

This step is optional but recommended.

<a id="doc-extract-initramfs--macos--linux-2"></a>
###### macOS / Linux

```bash
bzip2 -tv pioneerdj_xdj_rx3.tar.bz2
```

Expected output:

```text
pioneerdj_xdj_rx3.tar.bz2: ok
```

<a id="doc-extract-initramfs--windows-3"></a>
###### Windows

Using 7-Zip:

```powershell
& "C:\Program Files\7-Zip\7z.exe" t pioneerdj_xdj_rx3.tar.bz2
```

Expected output:

```text
Everything is Ok
```

---

<a id="doc-extract-initramfs--4-extract-the-reconstructed-archive"></a>
##### 4. Extract the reconstructed archive

<a id="doc-extract-initramfs--macos--linux-3"></a>
###### macOS / Linux

```bash
mkdir source
tar -xjf pioneerdj_xdj_rx3.tar.bz2 -C source
cd source
```

<a id="doc-extract-initramfs--windows-4"></a>
###### Windows

Recent Windows versions include `tar`:

```powershell
mkdir source
tar -xjf pioneerdj_xdj_rx3.tar.bz2 -C source
cd source
```

Alternatively, use 7-Zip:

```powershell
& "C:\Program Files\7-Zip\7z.exe" x pioneerdj_xdj_rx3.tar.bz2
& "C:\Program Files\7-Zip\7z.exe" x pioneerdj_xdj_rx3.tar
```

At this point, the XDJ-RX3 source tree has been extracted.

---

<a id="doc-extract-initramfs--5-extract-the-filesystem"></a>
##### 5. Extract the filesystem

Find it first:

<a id="doc-extract-initramfs--macos--linux-4"></a>
###### macOS / Linux

```bash
find . -type f -name initramfs.tar.gz
```

<a id="doc-extract-initramfs--windows-5"></a>
###### Windows

```powershell
Get-ChildItem -Recurse -Filter initramfs.tar.gz
```

If the archive is there, unpack it and you're done:

```bash
mkdir ../initramfs
tar -xzf path/to/initramfs.tar.gz -C ../initramfs
```

The same `tar` command works in PowerShell. A root filesystem holds symlinks, device nodes and ownership that a desktop account cannot always recreate, so expect warnings on those entries; they are harmless here, because nothing in this path has to be bootable — it only has to be readable.

If the archive is not in your copy of the sources, build it: section 6.

> [!CAUTION]
> That archive is the manufacturer's own build, sitting alongside the sources published for the components covered by the GPL and the LGPL. Unpacking it on your own machine, for a device you own, is not the same act as passing it on. It stays on your disk: not in an issue, not in a pull request, not in a release, not in a repository. See [the legal position](LEGAL.md) and [SECURITY.md](SECURITY.md).

---

<a id="doc-extract-initramfs--6-if-step-5-didnt-work-rebuilding-the-filesystem-with-makerootfs"></a>
##### 6. If step 5. didn't work: rebuilding the filesystem with `make_rootfs`

You need this only if you intend to change what the filesystem contains, or if your copy of the sources does not carry the archive. It builds from the published sources, and it is the step that wants Linux.

<a id="doc-extract-initramfs--macos--linux-5"></a>
###### macOS / Linux

Change to the extracted directory, containing `make_rootfs`:

```bash
cd /path/to/directory/containing/make_rootfs
```

Make it executable if necessary:

```bash
chmod +x make_rootfs
```

Run it:

```bash
./make_rootfs
```

It then generates `initramfs.tar.gz`, which is unpacked as in section 5.

<a id="doc-extract-initramfs--windows-6"></a>
###### Windows

Use WSL2 for the `make_rootfs` step.

From WSL2, it is preferable to copy the source tree into the Linux filesystem instead of building directly under `/mnt/c`.

For example:

```bash
cp -a /mnt/c/path/to/source ~/rx3-source
cd ~/rx3-source
```

Locate `make_rootfs`:

```bash
find . -type f -name make_rootfs
```

Then:

```bash
cd /path/to/directory/containing/make_rootfs
chmod +x make_rootfs
./make_rootfs
```

---

<a id="doc-extract-initramfs--platform-support"></a>
##### Platform support

| Step | macOS | Linux | Windows |
|---|---:|---:|---:|
| Extract the ZIP files | Yes | Yes | Yes |
| Reassemble the split archive | Yes | Yes | Yes |
| Extract the `tar.bz2` | Yes | Yes | Yes |
| Unpack the `initramfs.tar.gz` in the tree | Yes | Yes | Yes |
| Rebuild it with `make_rootfs`, if you need to | Yes | Yes | Via WSL2 |

---

<a id="doc-extract-initramfs--full-process"></a>
##### Full process

```text
A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
57CB205B-D45A-4143-BC09-22D8400074C2.zip
        │
        │ 7-Zip
        ▼
pioneerdj_xdj_rx3.tar.bz2.00
pioneerdj_xdj_rx3.tar.bz2.01
        │
        │ concatenate
        ▼
pioneerdj_xdj_rx3.tar.bz2
        │
        │ tar -xjf
        ▼
XDJ-RX3 source tree
        │
        ├───────────────► initramfs.tar.gz, already in the tree
        │                          │
        │                          │
        └─── make_rootfs ──────────┤ rebuilds the same archive
             then ./ltib --deploy  │ from the sources
                                   │
                                   │ tar -xzf
                                   ▼
                            root filesystem
```

---

<a id="doc-hardware-feedback-20260929"></a>
### RX3 1.19 — hardware feedback, 29 September 2026

<!-- source: docs/hardware-feedback-20260929.md | sha256: 05148745e1856c2ca7a49abe589f69543fa27b8b4ee1b9541cc6068f75b1b31a -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

The first hardware trial failed three acceptance points: no title eye; returning
from KEY/STEMS displayed BEAT FX with STATUS highlighted and flashing panels;
BROWSE still scrolled slowly. None of these is accepted on hardware yet.

<a id="doc-hardware-feedback-20260929--evidence-recovered-from-dj-francois"></a>
##### Evidence recovered from DJ FRANCOIS

The installed core hash was
`7b8754ea7a6dd7d0d08809fe97957d40d3e6c079308aa39096bb73fe623ea30c`,
matching the tested local build. `mod.txt` confirms `asshole-mode` active. The
session warning that the core was inactive occurred earlier than the later
successful activation logged by the core; it does not explain the missing eye.
The logs also record the provisional STATUS/BEAT FX reconstruction sequence.

The returned USB drive is available on the Mac; the RX3 is not connected for live
measurement. Original logs, manifest and image are retained under ignored
`local/research/hardware-feedback-20260929/`.

<a id="doc-hardware-feedback-20260929--title-eye-correction"></a>
##### Title eye correction

The native `Lib_Obj_CTRL_COUNTER` table at `0x0052b0e8` has 87 properties.
Its indices are **61** (music icon), **62** (title), **64** (title group).
The original implementation incorrectly used the generated symbol suffixes
25, 24 and 22. Host mock objects repeated that mistake and therefore passed.

`DrawImage` and its image-ID offset `0x44` are correct; the investigated
`DrawImageMark` route is not the cause. A new independent local-firmware test
compares the implementation's IDs against the actual native property table.
The core logs `title eye attached: deck 1/2` when it first replaces each icon.

<a id="doc-hardware-feedback-20260929--beat-fx-correction-candidate"></a>
##### BEAT FX correction candidate

The previous transition deliberately requested STATUS for 60 ms before BEAT FX,
then refreshed only the pane backgrounds. This both exposed an intermediate
state and failed to request all of the native child widgets.

The candidate keeps BEAT FX selected, queues one complete native-layer refresh
from the UI path, and stops inferring selection from the previous frame's tab
image. Native type `0x11` is a layer; type `0x14` is a window and bounds the parent
walk. Native render inspection shows that refreshing the layer traverses its
children. This is a supported correction candidate, **not a verified hardware
result**. Host tests verify the target ancestor, absence of a temporary STATUS
write, cancellation and duplicate-event behaviour.

<a id="doc-hardware-feedback-20260929--browse-remains-unresolved"></a>
##### BROWSE remains unresolved

The earlier synthetic cache result did not translate into a visible hardware
improvement. The candidate adds cumulative counters, sampled by the watcher
at five-second intervals only when pages changed:

- `browse pages`: intercepted row responses processed by the mod.
- `browse native ms`: time inside the original row-response handler.
- `browse mod ms`: time added while processing its response.
- `browse cache hits/misses`: matching raw row identities versus new entries.
- `browse cache expiries/scopes`: metadata expiry and scope resets.
- `browse key/field queries`: actual extra native metadata requests.

These timings do not include the entire input-to-screen path or upstream work
before the row hook. Their purpose is to identify repeated synchronous reads
and decide what to profile next. No file write occurs inside the database
callback. No new cache lifetime or metadata-consistency tradeoff is hidden in
this diagnostic build.

<a id="doc-hardware-feedback-20260929--next-hardware-pass"></a>
##### Next hardware pass

The retest image retains the same module selection, logo and six supplied
configuration/artwork files from the installed image.

1. Boot, load one track per deck. Check both eyes, hide/restore independently,
   and load another track while hidden. Photograph the deck strip if absent.
2. Switch KEY → BEAT FX, STEMS → BEAT FX, then STATUS → BEAT FX. Check both
   panel contents and the highlighted tab, including repeated presses.
3. In one track list, scroll steadily down for 10 seconds, then up for 10 seconds.
   Stop moving for at least 5 seconds so the watcher can log its last counters.
4. Shut down normally and return the USB drive. Compare counter deltas and
   preserve `RX3_RUNTIME/mod.txt` before another run overwrites it.

This pass deliberately separates a display fix from the unresolved performance
investigation. A successful compile or host suite does not close these cases.

<a id="doc-hardware-feedback-20260929--second-trial-eye-visible-input-still-broken-tabs-delayed"></a>
##### Second trial: eye visible, input still broken; tabs delayed

The returned image hash is `e36fefe0f8365e949dce4bc031a2b5c33b1825db326800984281e981c13e25e0`.
The trace confirms both eyes attached, but contains no initial-tab-refresh marker.
François reports no eye toggle, jagged artwork, persistent BEAT FX/STATUS flashing,
slow BROWSE, and ZOOM/GRID until the first interaction. Original evidence is in
ignored `local/research/hardware-feedback-20260929-second/`.

The new candidate addresses four code paths:

- A header text repaint cleared the performance touch gate. Native display state
  now gates eye, tab and pad input instead. Eye hitboxes also include the ancestor window translation that
  local render coordinates omit. Eye artwork uses an antialiased bitmap
  rather than discrete rectangular strokes; its geometry and state changes are logged.
- The startup refresh required both mutually exclusive ZOOM/GRID images to have
  drawn, plus an unused text template. Either image is now sufficient; providers,
  replacement assets and native backing must still be ready.
- Pending custom-panel refreshes repeated for up to one second after a panel
  closed, repeatedly clearing full native layers. They are discarded outside
  a custom panel. BEAT FX is an idempotent destination; STATUS remains separate.
- Six BROWSE responses cost 745 ms of added work, with 35 field reads and 12
  expirations. The metadata cache now expires after 30 seconds, instead of one.
  First reads remain synchronous; a cache lifetime change is not hardware proof
  of smooth scrolling. See the performance report for the freshness tradeoff.

All four corrections require another physical RX3 check. Start with cold boot
without touching the tab zone, then eye toggles on each deck, KEY/STEMS → BEAT FX
and repeated BEAT FX taps, and finally slow/fast BROWSE scrolling in both directions.
Also tap the old eye position in BROWSE to check that it does not consume input.

Candidate image SHA-256: `d3f5b3a569e13e357f51b4966fb71d6cda31471638a6b38a5cdfb3c86436e9fe`.
Core SHA-256: `67ab2510c4df1a6a646fc7a40924e9922526da0150e532d470f522c644f13670`.
Packaging verification decrypts the generated image, checks the embedded core
against the ARM build, and compares all six supplied files and the 16-module
selection with the returned USB image. No hardware pass is implied.

Final local verification: 438 tests, 2 skipped; ARM build successful; publication
preflight successful (421 candidate files). Installed on DJ FRANCOIS with SHA-256
readback matching the candidate. Previous image and manifest were preserved as
`autoexec.bin.backup-20260929-feedback-second` and
`rx3-mod-manifest.backup-20260929-feedback-second.json`. Physical retest pending.

<a id="doc-hardware-feedback-20260929--emulator-follow-up"></a>
##### Emulator follow-up

The same candidate core was exercised in QEMU after deployment. See
[the emulator acceptance report](#doc-emulator-feedback-20260929). Independent eye
toggles, boot-time KEY/STEMS and stable tab transitions pass with startup notices
disabled. Two notice-enabled starts abort in this emulator configuration, and
BROWSE still stalls when synchronous metadata reads recur after cache expiry.
The candidate remains unaccepted; no additional USB deployment occurred.

---

<a id="doc-history-legacy-stems"></a>
### Historical stems design (superseded)

<!-- source: docs/history/legacy-stems.md | sha256: 59a4059b30d1a70567ae535b6640cddd5c5ae4afa5ffd6d80dc43aa91aa33d54 -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

This is the former section 6 of `REFERENCES.md`. It documents an earlier implementation with separate `RX3STM1` and `.rx3wave` files, older pad allocation, host pipeline and model observations. It is retained for provenance and regression research. **Do not use it to describe the current package or runtime.** The maintained contract is [REFERENCES.md](#6-stems) and the byte-level specification is [stem-package.md](#doc-stem-package). Commands, performance figures and model choices below were recorded for their original revision and require fresh verification before reuse.

<a id="doc-history-legacy-stems--6-stems"></a>
##### 6. Stems

The largest feature: replacing or removing the vocal from a track in real time, from a stem file prepared on a computer.

<a id="doc-history-legacy-stems--hooking-the-audio-path"></a>
###### Hooking the audio path

Four sites are hooked with guarded trampolines: the function that hands decoded audio to the mixer, the one that associates a file with a deck, the pad handler, and the indicator refresh.

Each site has an eight-byte prologue guard. Three of them can have their stolen instructions copied straight into the trampoline. The fourth begins with a PC-relative load, whose meaning depends on where it sits, so that trampoline loads a copy of the original constant before replaying the instruction after it. This is the standard hazard of prologue-stealing hooks and the reason each site is inspected individually rather than handled by one generic routine.

<a id="doc-history-legacy-stems--finding-the-right-stem"></a>
###### Finding the right stem

The hook derives a track's base name and looks for a matching stem in a fixed directory on the stick.

Two details make this harder than it sounds. The library software truncates a filename to the first 44 characters when it exports a track, leaving the original untouched. So the name on the stick is not the name in the library, and the preparation tool applies the same truncation when it names a stem. Trailing spaces survive that cut on both sides and are not trimmed.

Second, two different tracks can truncate to the same name. The load interface gives no reliable way to tell them apart, so the tool **refuses the collision** rather than picking one arbitrarily. Truncation is applied before that comparison, because two names that differ only past character 44 collide on the stick.

Stems load asynchronously into anonymous memory. The deck stays on the stock audio path until loading finishes, after which the file on the stick is closed, so pulling the drive after a completed load cannot invalidate a live mapping. Allocation is refused if resident stem audio across both decks and the pending roles would exceed 512 MiB, or if the next allocation would leave less than 300 MiB of estimated available memory. Available memory is re-read after every allocation; it already reflects resident audio, so that part is not subtracted twice. Not yet run on hardware.

<a id="doc-history-legacy-stems--getting-the-audio-right"></a>
###### Getting the audio right

This is where the real engineering is, and both problems are silent failures: everything appears to work and the result is subtly wrong.

The instrumental is computed as *full mix minus vocal*. That subtraction is only valid if both come from the same decode. Any difference in phase, delay, gain or sample rate leaves audible residual vocal.

**Delay** is introduced by the container. Compressed formats declare samples the encoder prepended, and decoders normally drop them, so position zero of a normal decode is not position zero of what the player's own decoder emits, padding included. A delay of about a thousand samples puts the stem 25 ms ahead of the mix, which leaves the vocal essentially untouched in the instrumental while the isolated vocal still sounds perfectly fine. You will not hear the bug in the thing you are listening to.

The encoder therefore decodes each source twice, with and without padding removal, locates the trimmed decode inside the untrimmed one to measure the padding exactly, and shifts the stem by that amount. Uncompressed sources declare no padding and are unaffected. When the offset cannot be measured, because a silent decode has no unique pattern to locate, the stem stays on the separator's grid and the run says so rather than guessing.

**Gain** is broken by the separator. Two of the common model architectures scale the mix to a normalisation threshold before inference and emit the stem in that scaled domain. A threshold below 1.0 therefore multiplies the vocal by some factor and leaves the remainder of it in the instrumental, roughly -20 dB of leftover vocal at the tool's own default of 0.9.

Pinning normalisation to 1.0 fixes the common case and is also the highest safe value, since the writer converts to 16-bit integers in a way that wraps rather than clips above full scale. But lossy codecs reconstructing inter-sample peaks, or resampling from a higher rate, can still land above 1.0.

So the encoder measures instead of assuming: the pass that decodes the full track also measures its true peak, and the stem is scaled back accordingly. One trap here. The measurement has to be forced into floating point *ahead of* the integer conversion, because filter chains are negotiated backwards from the output format. A measurement placed after the conversion reads values already clamped to full scale, and cheerfully reports no overshoot at all.

Only stems from architectures that scale the mix are corrected. The others leave it alone. Correction restores the vocal to its true level, so anything that clips is something that genuinely exceeded full scale in the source. The manifest records the correction applied and the number of clipped samples per track.

Levels throughout are peak sample values relative to full scale, not perceptual loudness. No loudness measurement is performed anywhere in this pipeline.

One last case: when the stock reader returns an all-zero region during a seek or a buffer underrun, the hook leaves it alone. Subtracting a vocal from silence would emit an inverted vocal. A 256-frame linear ramp covers each state change.

<a id="doc-history-legacy-stems--stems-file-format"></a>
###### Stems file format

To encure perfect phase cancellation when playing only the instrumental, the stems needs to be PCM, that's whay they're heavier than the original audio files.

A 64-byte little-endian header followed by interleaved stereo vocal audio:

| Offset | Size | Field |
| ---: | ---: | --- |
| `0x00` | 8 | magic, `RX3STM1\0` |
| `0x08` | 4 | sample rate, always 44100 |
| `0x0c` | 4 | channel count, always 2 |
| `0x10` | 4 | sample format: 1 = float32, 2 = int16 |
| `0x14` | 4 | header size, 64 |
| `0x18` | 8 | frame count |
| `0x20` | 32 | reserved, zero-filled |
| `0x40` | - | interleaved stereo audio |

The default is 16-bit to halve resident memory. The frame count is aligned to the full track as decoded at 44.1 kHz, not to the separator's output duration.

The player's audio path runs at 44,100 frames per second, corroborated by the constructor constants, the buffer sizes and the sample-rate converter it instantiates. Sources at other rates are converted before they reach the hooked buffer.

<a id="doc-history-legacy-stems--preparing-stems-on-the-host"></a>
###### Preparing stems on the host

Separation itself is not ours. The pipeline drives [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) and FFmpeg as subprocesses, so nothing separation-related is linked into the release archive. Those dependencies together are two orders of magnitude larger than the application.

Components are resolved in a fixed order, first hit wins: the `RX3_SEPARATOR` and `RX3_FFMPEG` overrides, then whatever is on `PATH`, then a managed environment installed under the user's data directory. Supplying your own is therefore equivalent to letting the application install one; a separator found on `PATH` is used as-is, reported as unmanaged, and never rebuilt or removed.

Three pins in that managed environment are deliberate and each has a reason:

- PyTorch comes from the CPU wheel index unless an accelerator is selected, because the default Linux and Windows wheels carry multi-gigabyte CUDA payloads a CPU pipeline never touches.
- `librosa` is held below 1.0, because audio-separator still imports `audioread` and calls `get_duration(filename=...)`, both removed there.
- The seeding interpreter is capped at 3.13, because audio-separator pins `beartype` below 0.19, which rejects the separator's own annotations on 3.14.

FFmpeg found on `PATH` is preferred over the bundled copy, but only once it is shown to carry every filter the pipeline uses. Builds configured without one of them exist, and the failure would otherwise land partway through a long job rather than at startup. An explicit override is exempt: that is the documented escape hatch, so a gap in it is reported rather than acted on.

The data directory keeps the name the earlier standalone application used, so a runtime installed by that version is still found rather than downloaded again. That name is load-bearing and should not be tidied up.

<a id="doc-history-legacy-stems--safe-publication"></a>
###### Safe publication

Preparation reserves the estimated s16 payload (duration times 44100 times four bytes per role, plus 64 bytes per header) and a fixed 16 MiB margin before separation. The margin covers integer-second library duration rounding, encoder padding, filesystem allocation and the manifest; it does not assume old files can be removed to make room. Unknown durations require an audio probe. A space refusal stops the batch.

Each file is staged exclusively under a `.partial` suffix, stripped of extended attributes, synced and read back for SHA-256 comparison with the local file before replacement. The directory is synced where supported. Matching AppleDouble metadata files are removed only inside RX3_STEMS; unrelated files are preserved. Symlink output directories and targets are refused. Source size, nanosecond mtime and a streamed full-file SHA-256 must still match before publication. These checks detect software-visible failures, not a USB controller that acknowledges writes it has not durably stored.

The manifest is published through the same path inside RX3_STEMS. The old root-level manifest is left untouched. Process detection blocks library reads and preparation while an export application is open; an unavailable process query fails closed. It cannot prevent an application being launched after the check.

<a id="doc-history-legacy-stems--reuse-and-provenance"></a>
###### Reuse and provenance

Manifest schema 2 records `source_sha256`, `source_bytes`, `processing`, the applied gain and delay, and a SHA-256 for each final stem. The processing signature includes the model filename, catalogue architecture when available, preset, effective command arguments, requested roles, s16 format and stem/encoder versions. Changing any of these invalidates reuse. Source hashes stream in 1 MiB blocks and report progress. A source hash proves file identity, not ownership or separation quality.

Readers accept schema 1 and check the old drive-root location when the new manifest is absent. Legacy entries retain null source identity until regenerated: hashing a current track cannot establish which source produced an older stem. Missing manifests keep the legacy existence-based behaviour with a visible warning. Known entries require matching source and processing, valid equal-length stem headers and matching audio hashes. A damaged known entry is regenerated. Each completed track is merged into the manifest so later failures do not erase earlier provenance.

The app data directory holds a 4 GiB default cache, configurable from zero (disabled) to 1024 GiB. Entries are keyed by source SHA-256 and processing signature and contain final encoded audio, not model output. Hits are copied to a local workspace while holding the cache lock; eviction therefore cannot interrupt a drive write. Directory modification time records last use for LRU eviction. Only verified entries are reused, first from this cache and then from mounted drives. Optional roles from an earlier preparation are removed before replacing vocals, so an interruption reduces available roles instead of combining different sources.

<a id="doc-history-legacy-stems--manual-imports"></a>
###### Manual imports

Manual import accepts lossless WAV, AIFF and FLAC with one or two channels. The audio probe checks the codec as well as the suffix, so compressed audio in a WAV container is refused. Conversion duplicates mono to stereo and resamples to 44100 Hz. The mix is decoded with UNTRIMMED, and imports shorter than it or longer by more than one second are refused before correlation.

Eight positions shared with the encoder-delay probes are examined where a complete window and a one-second search margin exist. At least four windows must be usable. A 64-frame amplitude envelope narrows the search; two passes over waveform samples refine it to individual frames. Every usable window must have correlation at least 0.55, and shifts must lie within one frame of their median. Silent or ambiguous material is refused rather than assigned an alignment. A constant offset up to one second can be corrected, with the milliseconds and removed head/end frames displayed. No surplus is trimmed unless its location agrees with that offset.

Gain is a heuristic: the median least-squares coefficient across probes must be within five percent of unity. This can reject a valid correlated component or miss a processed one; it is not certification. The full set's residual-energy ratio is reported, not required to approach zero, because voices, drums and bass do not include every other instrument. The application never applies the estimated gain. It encodes the corrected timeline with write_stem, records peak, corrections and checks with origin `imported`, then uses verified publication. Listen to the reconstructed instrumental before relying on an imported set.

Assignments persist per library and track in the app data directory. A file chooser is available on every supported webview; dropping a file also works where the backend supplies its native path. The shared job slot keeps import publication separate from other drive-writing jobs. Local synthetic measurements on a six-minute track, including decode, checks and final encoding: 1.03 s for one role and 4.61 s for three roles. These are measurements on the development machine, not estimates used by the interface.

<a id="doc-history-legacy-stems--host-audition"></a>
###### Host audition

Audition reads the drive's final s16 stems and decodes the source on the UNTRIMMED 44100 Hz grid. Optional roles are admitted only as a contiguous prefix beginning with vocals and with identical frame counts, as in the loader. The original mix, remaining instruments and every available role combination use one Python reconstruction module. Native tests compare every float32 output bit with the C mixer across interrupted ramps, silence and selection changes. The native reference disables fused arithmetic because the configured ARMv7 NEON target uses separate multiply and add operations.

The bridge returns at most 30 seconds of IEEE-float WAV, waveform peaks and the exact ramp state at each changed frame. Float output preserves peaks beyond unity until the playback device's own conversion. The browser requests a 44100 Hz audio context, retains position while preparing a changed selection, and carries the returned mixer state to the next request. Preparation may pause playback briefly; it is asynchronous and never blocks the interface thread. The excerpt cache holds at most four replies. The Imported view validates and encodes assigned files locally without publishing them; On the drive reads the existing files. Neither view emulates the player's time stretching, DAC or audio driver.

<a id="doc-history-legacy-stems--host-stem-waveforms"></a>
###### Host stem waveforms

Preparation reads the analysis path from string 14 of the output drive's track row, matches the exported audio by basename and SHA-256, and opens its DAT and EXT files read-only. It does not rely on track IDs being shared between libraries. Paths escaping the drive, files above 32 MiB, truncated or duplicate tags, malformed beat grids, unsupported detailed strides/cadences and conflicting column counts disable waveform preparation for that track. PQTZ beats are decoded as bar position, tempo times 100 and time in milliseconds; they are not used to infer a sample-accurate encoder offset. XML-only destinations without a matching exported analysis keep their audio stems without a waveform file.

The detailed axis is fixed by the template: PWV3 has one byte per column, PWV5 has two bytes per column, both at 150 columns per second. The richer format is selected when both are present. At 44100 Hz each column covers 294 audio frames, starting at frame zero of the UNTRIMMED grid. The stem frame count must give exactly the template count when rounded up to a complete terminal cell. Only that terminal cell may receive zeros, never an extra column or a shifted origin. A differing count is refused. This convention does not certify the original analyser's encoder-delay policy.

Columns are computed from the final s16 files, after publication, with an instrumental produced by the host mixer's settled mix-minus-vocal selection. They do not reuse or filter the mix's stored colours. Blue uses a quantized mono average, per-cell peaks, a 150 Hz low-pass peak ratio for colour and a squared, globally normalized height. RGB uses an amplitude-aware mono projection, second-order filters (low: 100 Hz low-pass; middle: 300 Hz high-pass followed by 3000 Hz low-pass; high: 1500 Hz high-pass), millisecond peak envelopes, 12 ms/1 ms symmetric maximum windows for low/middle, then 150 Hz cells and nonlinear colour mapping. Filter Q is 1/sqrt(2). Filtering uses double precision in the existing audio subprocess; envelope reduction and packing use the standard library. Heights are normalized per role, so comparing their displayed heights is not a loudness measurement. This is an independently implemented host analysis, not a claim of bit-identical output from the original analyser. PWV7 and preview replacement are not emitted. The lower-level calculator accepts an explicit PCM sample rate for native-rate reference checks; published stem PCM remains 44100 Hz. Five hash-pinned real PCM exports (WAV, AIFF and AIF, including 24-bit audio) matched the complete PWV5 payload byte for byte after correcting the middle-band cutoff. This observation does not certify other decoder outputs or codecs. Set RX3_WAVE_EXPORT_MANIFEST to an operator-owned JSON list of source/dat/ext paths and corresponding source_sha256/dat_sha256/ext_sha256 values, relative to the manifest, to run tests.test_waveform_exports. No music or exported analysis is distributed with the tests.

The optional file is `RX3_STEMS/<exported-basename>.rx3wave`. All container integers are little-endian. Header size is 128 bytes; a 64-byte entry for each role immediately follows it. Payloads follow the role table contiguously, in table order, without padding. The current player has no reader for this file, so its presence or absence cannot change rendering. Not yet run on hardware.

| Offset | Bytes | Header field |
| --- | --- | --- |
| `0x00` | 8 | magic `RX3WAV1\0` |
| `0x08` | 4 | version, 1 |
| `0x0c` | 4 | header size, 128 |
| `0x10` | 4 | audio rate, 44100 |
| `0x14` | 4 | columns per second, 150 |
| `0x18` | 4 | columns per role, 1 through 540000 |
| `0x1c` | 4 | column encoding: 1 = PWV3, 2 = PWV5 |
| `0x20` | 4 | role count, 2 through 4 |
| `0x24` | 4 | role-entry size, 64 |
| `0x28` | 32 | SHA-256 of the complete source audio file |
| `0x48` | 32 | SHA-256 of DAT length as u64 LE, DAT bytes, then EXT bytes |
| `0x68` | 8 | exact audio frame count, before terminal-cell padding |
| `0x70` | 16 | reserved, zero |

| Entry offset | Bytes | Role field |
| --- | --- | --- |
| `0x00` | 4 | role: 1 vocals, 2 instrumental, 3 drums, 4 bass |
| `0x04` | 4 | bytes per column, equal to header encoding |
| `0x08` | 8 | absolute payload offset |
| `0x10` | 8 | payload bytes, exactly count times stride |
| `0x18` | 32 | SHA-256 of the exact stereo float32 LE PCM submitted for this role |
| `0x38` | 8 | reserved, zero |

PWV3 payload bytes contain colour in bits 7..5 and height in bits 4..0. PWV5 preserves the template's big-endian 16-bit column encoding inside the little-endian container: red in bits 15..13, green in 12..10, blue in 9..7 and height in 6..2; bits 1..0 are zero. Keeping payload order explicit avoids confusing the file header with the analysis format. Vocals and instrumental are mandatory; drums precede bass. Unknown versions, sizes, role order, counts, trailing bytes and nonzero reserved fields are refused by the host reader.

An old waveform is removed before replacing audio roles, and whenever optional regeneration is unavailable. The source, final stems and analysis files are checked again after computation. Publication uses the same verified partial-file path as audio stems. Only matching metadata names inside RX3_STEMS are cleaned. Waveform work runs in the preparation worker; it is excluded from separation-speed observations. Temporary disk reservation is 96 bytes per padded audio frame plus the ordinary margin, covering decoded mix, role PCM and six double-precision filter streams. There is no waveform disk cache yet. A local six-minute synthetic track with four RGB roles took 75.37 seconds including decoding, reconstruction, filtering and hashing; its waveform file was 432384 bytes. This measured cost is separate from manual-import validation and is not used as an interface time estimate.

<a id="doc-history-legacy-stems--waveform-renderer-integration-review"></a>
###### Waveform renderer integration review

No runtime rendering change is part of host waveform preparation. The current renderer consumes 16-byte resident columns (three amplitude bytes, one reserved byte, three 32-bit colour fields), not compact analysis bytes. Flat is the simplest future target for an amplitude plus role colour. The Bands path needs the original compact-to-resident conversion and mode mapping. Blue also needs its palette-pointer semantics and separate 2736-byte overview conversion. Existing stock-renewal callbacks do not by themselves establish safe ownership of replacement buffers. Before integration, verify column origin, count pointers, zoom/seek behaviour, regeneration completion, buffer lifetime and track-change synchronization against the player binary and then on hardware.

For N columns and R stored roles, the compact payload costs N*R bytes for Blue or 2*N*R for RGB. Six minutes at 150 columns/s gives N=54000: four RGB roles occupy 432000 payload bytes plus 384 bytes of header/table. Expanding all four into 16-byte resident columns adds 3456000 bytes per deck; keeping only the selected role expanded costs 864000 bytes, with another buffer of that size if publication requires double buffering. At the current 540000-column cap, four expanded roles cost 34560000 bytes per deck. Include this memory in the existing resident-role budget and account for both decks.

Absent, incompatible, stale or allocation-failed files must retain the current display filter; returning to full mix must restore stock columns. Combined selections without a prepared waveform also retain the filter: peak envelopes and colours cannot in general be added, because the underlying audio can cancel. The second phase still requires explicit approval and hardware acceptance. Not yet run on hardware.

<a id="doc-history-legacy-stems--which-model-actually-runs"></a>
###### Which model actually runs

The best models available are roformers, which are PyTorch checkpoints. The ones that reach a GPU without PyTorch are MDX-Net, which are ONNX graphs. Neither runtime is accelerated everywhere, and the split differs per platform:

| Accelerator | PyTorch | ONNX Runtime | Best available | Fastest |
| --- | --- | --- | --- | --- |
| NVIDIA CUDA | GPU | GPU | roformer, 12.6 dB | Demucs, 9.9 dB |
| Apple Silicon | GPU | mostly **CPU** | roformer, 12.6 dB | Demucs, 9.9 dB |
| AMD ROCm | GPU | **CPU** | roformer, 12.6 dB | Demucs, 9.9 dB |
| DirectML | **CPU** | GPU | MDX-Net, 10.2 dB | MDX-Net, 10.2 dB |
| CPU only | CPU | CPU | MDX-Net, 10.2 dB | MDX-Net, 10.2 dB |

On the first three the roformer is both better *and* quicker, so there is nothing to trade. On the last two it is neither: DirectML's PyTorch backend is pinned far behind what a roformer needs, and a CPU-only build has nothing to offload to, where ONNX Runtime is the quicker of the two. Those machines give up 2.4 dB of vocal separation quality to run on the hardware they have.

MDX-Net is also band-limited, with its wall at 17.6 kHz: above that nothing is separated at all, so the air of a vocal stays in the instrumental the deck reconstructs. That is a different kind of loss from a lower score, and it is why the waveform-based Demucs is preferred for the fast path, because it gives up quality without giving up the top of the spectrum.

**Apple Silicon is the case worth explaining, because CoreML looks like it works.** It is offered, it is enabled, and it does take most of the model, but it cannot take the graph whole. On an MDX-Net model it claims 151 of 178 nodes and splits them into 28 partitions, so the run spends its time shuttling tensors back and forth with the CPU. That is why an ONNX model is not the answer there even though a provider is listed. An Intel Mac never reaches Metal at all: the separator gates that path on an ARM processor.

Because the accelerator determines the model, changing the accelerator can change which model a given quality setting resolves to.

A quality setting is therefore not one model. It is one or more *variants*, a list of candidate models plus the tuning each wants, and a setting always names exactly one configuration. Editing anything by hand switches the setting to Custom rather than leaving a preset's name on a configuration it no longer describes. Candidates are a list rather than a filename because the catalogue comes from upstream and can change; the first one actually offered is used, and if none survive, the best-scoring model of that architecture is.

A setting gets a second variant when the trade-off it names cannot be expressed the same way everywhere. Two flags record which inference runtime a given build actually gets GPU work out of, and the preset picks its variant from them.

**Those two flags are answers to measurements, not to capability queries**, and that distinction is the whole point. Neither is derivable from which extras were installed, since Metal and ROCm share those while behaving differently. Neither follows from what the ONNX runtime claims to support, as the Apple Silicon case above demonstrates: it reports CoreML, the separator enables it, and the work still lands on the CPU. If you change one of these flags, say what you measured and on what.

<a id="doc-history-legacy-stems--the-overlap-parameter-and-a-click"></a>
###### The overlap parameter, and a click

The knob between the two best quality settings is the separator's `mdxc_overlap`. Despite the name it is a *step* in seconds, not an amount of overlap: the chunk is 11.0 s, the window advances that many seconds each time, so a **lower** value means more passes and more inference.

The default of 8 gives 27% overlap. Stepping to 10 gives 9%, and measurably less work. Stepping to 11 would be free, and wrong. At the chunk length and above, the step is clamped to the chunk and the passes stop overlapping at all, which measured as a discontinuity every 11.0 s reaching 25x the surrounding sample-to-sample difference, against 0.7x away from a boundary.

That is a click. And because the deck reconstructs the instrumental by subtracting the stem, it lands in the instrumental too. The one second of overlap that removes it costs essentially nothing: 0.399 s of compute per second of audio at a step of 10, against 0.406 at 11.

<a id="doc-history-legacy-stems--estimating-time-honestly"></a>
###### Estimating time honestly

Speed depends on the model, the device and whatever else the machine is doing, so nothing in the interface quotes a fixed ratio. A first estimate comes from a table of typical rates per architecture and accelerator and is marked as rough. As soon as one track finishes, this machine's measured speed replaces it.

Measured rates are stored per architecture, accelerator **and** quality setting. The last part matters: the top two settings run the same model and differ only in how many passes they make over the audio, so one shared rate would be wrong for each of them in turn.

Nothing here should ever grow a hardcoded duration. The seed rates are keyed on the accelerator alone, precisely so that no measurement taken on one machine becomes a claim about every machine.

<a id="doc-history-legacy-stems--pads-and-indicators"></a>
###### Pads and indicators

Stem controls are active only when the right pad mode is selected, no modifier is held, the deck has a valid stem, and the event targets one of two specific pads. Anything else is passed to the stock handler untouched.

The indicator list holds entries for both decks, so filtering by indicator identity alone would disturb the other deck. The hook also checks the channel stored in each entry.

While a stem loads, both pads blink, then hold colour once the audio is resident. The blink uses the firmware's own timed state rather than a toggle driven from the hook, so its cadence does not depend on how often the refresh happens to call back. Note that the configured period is a *half*-period: the indicator is lit while the elapsed count is even, so 500 ms means one second on, one second off.

The waveform display is not modified. Its internal three-band representation is not the audio buffer we process.

---


---

<a id="doc-key-sync-follow-up"></a>
### KEY SYNC — harmonic evolution

<!-- source: docs/key-sync-follow-up.md | sha256: eba959bb7b35b777b2d3a6c3516f21b03a370371b7d027a807a840b171254543 -->


François's request: finish the coloured backgrounds of the controls first, then
extend KEY SYNC with a configurable harmonic mode in the Toolkit.

- Keep the current "Identical" mode.
- Add "Harmonic": same key, neighbours ±1 Camelot of the same mode,
relative major/minor (same number, other letter).
- Search for the smallest semitone shift within ±x.
- If already compatible, display "Compatible" without correction.
- Keep x = 1 by default and the actual transpositions of both decks.
- Do not include expressive/energy boost transitions in this mode.

Reference case accepted: against 8A, 9A is already compatible. 10A lowered
half-tone gives 3A, incompatible; Lowered by two gives 8A. With x = 1,
no correction; with x = 2, KEY SYNC proposes -2.

Implemented: both modes are available in the Toolkit, with persistence
local and integration into the generated module. Same mode remains the default.
The KEY MATCH state is informative and does not change the transposition. In case
equality of distance, an identical target is preferred, then positive direction.
The tests check the reference case and the minimumity on the 24 tones,
the transpositions of both decks and the absolute limits of ±12 half-tones.

---

<a id="doc-macos-distribution"></a>
### Sign and notarize the macOS app

<!-- source: docs/macos-distribution.md | sha256: f74edc494e990b72ad114a88381ca82be3af73d56b48a35364dff2c4c7b6b52c -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

Build separately on Apple Silicon and Intel. The certificate must be Developer ID Application, with its private key in the build machine's Keychain. Apple Development certificates do not sign an outside-App-Store distribution. No certificate, password or private key belongs in this repository.

Release bundles use `fr.francois-brille.rx3-toolkit` as their identifier; the display name remains XDJ-RX3 Toolkit.

From the repository root, using the build environment's Python:

```sh
make hook PYTHON=.venv/bin/python
RX3_PREBUILT_HOOK=build/librx3_core.so \
RX3_CODESIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)' \
  .venv/bin/python -m PyInstaller --noconfirm --clean packaging/toolkit.spec
.venv/bin/python scripts/check_macos_bundle.py 'dist/XDJ-RX3 Toolkit.app'
'dist/XDJ-RX3 Toolkit.app/Contents/MacOS/XDJ-RX3 Toolkit' --self-test
codesign --verify --deep --strict 'dist/XDJ-RX3 Toolkit.app'
```

PyInstaller signs the collected binaries with hardened runtime and an Apple timestamp when `RX3_CODESIGN_IDENTITY` is set. No hardened-runtime exception is enabled by default. Open the resulting application and exercise Modules, Samples, Logo, Stems and Settings before notarizing; the headless self-test does not execute the page's JavaScript.

Create a notarization profile interactively in your own terminal. Enter credentials only in Apple's prompts, not in scripts, command arguments or chat:

```sh
xcrun notarytool store-credentials RX3-Toolkit
```

After testing, submit the signed application to Apple:

```sh
.venv/bin/python scripts/notarize_macos.py 'dist/XDJ-RX3 Toolkit.app' \
  --profile RX3-Toolkit --output local/release/XDJ-RX3-Toolkit-macOS.zip
```

The script saves the submission result and Apple log beside the archive, requires an Accepted result, staples and validates the ticket, checks Gatekeeper, then archives the app and notices with `ditto`. A failed check produces no distribution archive. It neither tags nor publishes a release. Keep the signed app and submission ID when a request fails or is interrupted so its status can be queried without resubmitting.

<a id="doc-macos-distribution--separation-runtime-baseline"></a>
#### Separation runtime baseline

Managed installations request audio-separator 0.44.5, librosa 0.11.0 and imageio-ffmpeg 0.6.0. Apple Silicon also fixes PyTorch at 2.13.0 and ONNX Runtime at 1.28.0, the versions exercised by the signed app. Other platforms and accelerators still need their own validated pins; this is not a complete transitive lock. Capture their installed versions when validating each release platform. The PCM cache records actual inference package versions and model asset hashes, so changing an engine invalidates automatic separation reuse. Imported PCM retains its original provenance.

Before release, exercise a silent worker cancellation, window closure during work, interrupted installation, interrupted publication, a full destination and a missing destination. Already published packages must remain readable; the next run must reuse completed tracks and regenerate unfinished ones. Tests use temporary directories, never an operator's USB drive.

---

<a id="doc-overcue-prototype"></a>
### OverCue shared USB prototype

<!-- source: docs/overcue-prototype.md | sha256: 5419b3314639e1c81cf3f23f3c5dc2259b939edfe1c1fd68e76ca3f5450d9f6e -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

<a id="doc-overcue-prototype--desktop-output-policy"></a>
##### Desktop output policy

The preparation screen keeps RX3 packages in all cases. Its optional OverCue checkbox adds `CDJMODS` files on the computer after the RX3 package has been saved. Leaving it unchecked produces only RX3 files and does not remove any OverCue files already on the drive. The checkbox never enables the experimental RX3 reader below: normal playback uses `.rx3stem` with no 96 kHz conversion.

Additional storage is estimated for the selected playlist at 2.5 MB per second (decimal MB), rounded up to whole MB. This rounds the measured 74,935,926 bytes for the thirty-second nonzero-drums fixture to 75 MB. It excludes native packages and source music; it describes the full extra selection, not the bytes remaining to copy when an export already exists. Unknown track durations produce an unknown estimate, not a falsely complete total. Actual size depends on compression; free-space checks use uncompressed sizes with page overhead, separately from the estimate.

The desktop job automatically locates the native helper in the local build or packaged application and uses the bundled, hash-verified reference table. `RX3_OVERCUE_HELPER` and `RX3_OVERCUE_COEFFICIENTS` remain optional overrides. Build the helper with `make overcue-audio` before packaging to include it; a missing helper or invalid table makes the checkbox unavailable, with no silent fallback to approximate preparation. Only WAV, AIFF and FLAC sources are accepted for now. The destination must contain a matching rekordbox export: IDs come from its `export.pdb`, never from an unrelated XML library. CDJ-3000 compatibility and nonzero-drums PCM identity remain pending the acceptance described below.

Existing native stems are reused, including when compatibility is added later. If OverCue export fails or is cancelled, saved RX3 packages and their manifest remain usable. A failed extra export is reported separately; immutable bundle publication still writes the index last. Cancellation owns the native helper and FFmpeg processes. The desktop option does not deploy firmware or start audio playback.

The complete desktop job was exercised on a disposable local USB copy with the thirty-second nonzero-drums fixture. It returned one existing RX3 result, added 74,935,971 bytes under `CDJMODS`, and left the native package SHA-256 unchanged. Separation was guarded against being called. All seven output PCM streams and gain parameters match the earlier standalone Toolkit export. This checks job integration, not a new Desktop oracle or CDJ playback. Owner-local evidence is in `local/research/overcue-option-20260928/result.json` and `pcm-comparison.json`.

<a id="doc-overcue-prototype--earlier-reader-experiment"></a>
##### Earlier reader experiment

This is an opt-in experiment, not a hardware-supported release. Its scope is
stems data interoperability: one `CDJMODS` bank for OverCue on CDJ-3000 and the
RX3 Toolkit reader. No OverCue firmware is installed on the RX3.

The contract is the public [OverCue format](https://github.com/OverCue-gg/overcue-stems-format/tree/1eddcb70093326146ac776e232dc7c827785d79f),
revision `1eddcb70093326146ac776e232dc7c827785d79f`. Keep the seven stereo
PCM16 roles at 96000 Hz on USB. Replacing them with 44100 Hz files would break
that contract. The RX3 worker verifies and decompresses pages, then resamples
into a bounded RAM cache at 44100 Hz (147/320, 192-tap polyphase filter).
The callback only reads cached frames; it does no filesystem or zlib work.

<a id="doc-overcue-prototype--reader-and-controls"></a>
##### Reader and controls

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

<a id="doc-overcue-prototype--toolkit-export"></a>
##### Toolkit export

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

<a id="doc-overcue-prototype--evidence-2026-09-28"></a>
##### Evidence, 2026-09-28

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

<a id="doc-overcue-prototype--real-overcue-desktop-export"></a>
##### Real OverCue Desktop export

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
not resolve that result. The subsequent [static analysis](#doc-overcue-static-analysis)
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

<a id="doc-overcue-prototype--adaptation-reciprocal-recognition-and-neon"></a>
##### Adaptation: reciprocal recognition and NEON

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

<a id="doc-overcue-prototype--autonomous-native-pcm-prototype"></a>
##### Autonomous native PCM prototype

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

This reference has silent drums: it originated from the emulator's visual pad fixture, whose drums file was zero-filled, not from a real drum separation. It consequently covers fewer independent signals than seven arbitrary selections. Cancellation with three nonzero components, short signals and other source rates still need independent Desktop fixtures. Native structural tests cover phase ordering, floor frame counts, signed quantization, partial measurement windows and nonfinite rejection. Numerical agreement on this macOS fixture is not evidence of identical results on Windows or Linux. A subsequent nonzero-drums bank was converted on the physical RX3; see [conversion measurements](#doc-overcue-rx3-benchmark) for results and the remaining Desktop-reference limitation.

The 1:1 result above concerns PCM, timeline and gain parameters. Compressed PGZ bytes/page tables and preview analysis files differ; creation timestamps and writer provenance also differ by design. The comparator reports PGZ and preview equality separately, and does not label those files identical. Its status 0 means verified audio identity, 1 means differences, and 2 means an invalid or unreadable bundle. It never plays audio. No physical RX3 audio playback or CDJ test has been performed for this native preparation path.

Validation for this change: 27 focused tests pass with the native helper built, publication preflight passes for 372 candidate files, and `git diff --check` is clean. The complete suite was not rerun for this offline prototype addition. No audio playback was started during the native comparison work.

---

<a id="doc-overcue-rx3-benchmark"></a>
### OverCue conversion on the physical RX3

<!-- source: docs/overcue-rx3-benchmark.md | sha256: f897a33ed570fec4341f3e8a83f1aab1995b92f807e48351eb735a8262c3b50e -->


Measured on 2026-09-28. No sound output, player injection, firmware update or
reboot was performed. `scripts/overcue_bench.c` directly includes the prototype
reader and measures file reads, page inflation, integrity checks and the
192-tap NEON 96 kHz to 44.1 kHz conversion together.

<a id="doc-overcue-rx3-benchmark--environment-and-method"></a>
##### Environment and method

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

<a id="doc-overcue-rx3-benchmark--results"></a>
##### Results

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

<a id="doc-overcue-rx3-benchmark--interpretation-and-limits"></a>
##### Interpretation and limits

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

<a id="doc-overcue-rx3-benchmark--reproduction-and-evidence"></a>
##### Reproduction and evidence

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

---

<a id="doc-overcue-static-analysis"></a>
### OverCue reverse interoperability and resampling cost

<!-- source: docs/overcue-static-analysis.md | sha256: e4be1652317d459f44b65dacaede803064527db83f13550d0256a0946f09b896 -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

Analysis date: 2026-09-28. This investigation inspects OverCue Desktop 2.1.9
Apple Silicon statically. It does not modify or execute its recognition code.
The CPU experiment executes our reader on the host, not on an RX3.

<a id="doc-overcue-static-analysis--identified-consumer"></a>
##### Identified consumer

Later prototype results, including the native PCM comparison, are recorded in the [OverCue prototype](#doc-overcue-prototype). Historical statements about the earlier writer below describe the implementation at the time of the initial analysis.

Official installer SHA-256:
`ef4928d241d017adda79d763539adc02ba7a0aeb24a1a999083da221fd43e019`.

`Contents/MacOS/overcue-desktop` (26786816 bytes), SHA-256:
`ff949741aabe49e3071ff1cdf05e4dd71ccfad258c5725d0b586d76b34e622a5`.

The distributed Mach-O retains Rust function symbols. `llvm-objdump` and
`nm` expose the relevant functions without patching the program. Addresses
below are preferred virtual addresses in this particular binary.

<a id="doc-overcue-static-analysis--why-valid-pgz-files-still-show-not-processed"></a>
##### Why valid PGZ files still show Not processed

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

<a id="doc-overcue-static-analysis--correct-route-for-the-reverse-export"></a>
##### Correct route for the reverse export

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

<a id="doc-overcue-static-analysis--current-runtime-cpu-work"></a>
##### Current runtime CPU work

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

<a id="doc-overcue-static-analysis--measured-host-benchmark"></a>
##### Measured host benchmark

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

<a id="doc-overcue-static-analysis--recommendation"></a>
##### Recommendation

Keep the 96 kHz interchange bank. Before hardware acceptance, measure worker
thread CPU time, block preparation percentiles and misses under two-deck
playback, seeks and tempo changes on the RX3. Optimize the filter with explicit
NEON and convert the input block to float once, rather than repeating casts
for every tap. Preserve the current scalar version as a numerical reference.
Do not reduce the tap count without passband/alias rejection measurements.

If the measured hardware margin is inadequate, add an optional 44.1 kHz RX3
cache prepared by the Toolkit; the shared 96 kHz bank remains intact for
OverCue. This moves conversion to preparation at the cost of extra USB space.

<a id="doc-overcue-static-analysis--reproduction-and-local-evidence"></a>
##### Reproduction and local evidence

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


<a id="doc-overcue-static-analysis--follow-up-implementation"></a>
##### Follow-up implementation

The later [prototype adaptation](#doc-overcue-prototype--adaptation-reciprocal-recognition-and-neon)
implements manual provenance, measured downward loudness ceilings and RGB
preview files. Desktop recognition and active stem preview controls were
observed on a shared-index fixture. The earlier blockers above describe the
pre-adaptation exporter; they are retained as the static-analysis baseline.
The implementation differs numerically from Desktop and remains opt-in.

---

<a id="doc-pad-visual-design"></a>
### Performance controls — visual refinement

<!-- source: docs/pad-visual-design.md | sha256: 79b9d70a4fc046b8588dab6daa9e63b5861fe2def0002b29f7dc1be6319d8487 -->


Mode: Operate. Scope: the shared on-device renderer for STEMS, KEY and Samples.
Authority: RX3 1.19 native screen, shipped glyph atlases, the working pad gestures,
and the user's Rekordbox role colours. This is a refinement of that interface.

<a id="doc-pad-visual-design--common-treatment"></a>
##### Common treatment

- Keep the 39 px native touch band, layout solver, labels and atlas typeface.
- Neutral one-pixel frames; colour identifies a stem or selected state.
- Full-volume stem: a full semantic-colour face, readable name and a vivid inset status rail.
- Partial volume: the same frame, bright label, numeric percentage (number alone in narrow four-role cells), a six-pixel
  track and a six-pixel handle. The handle remains within the control at 0/100.
- A pressed control highlights its frame. Off removes the coloured face and status rail; its
  label stays readable so the control remains discoverable.
- KEY uses the same frames, caption contrast and status rail. Samples uses the
  same track/handle and retains its VOL readout/reset button.
- Inactive/status labels, loading blink, empty/error copy and all gestures keep
  their existing meanings. No decorative animation or new mode switch.

<a id="doc-pad-visual-design--theme-and-semantic-colour"></a>
##### Theme and semantic colour

Framework neutral tokens live next to the painter in `rx3_pad_widgets.h`.
Dark frame/track: `#41474d` / `#30363c`. Light: `#8c949c` / `#a5adb5`.
Handle: white in dark mode, `#202830` in light mode. Neutral backgrounds come from the active glyph atlas. Active/semantic cells use the unattenuated RGB565 semantic colour in both themes. The caption uses
white or dark keyed glyphs according to the face brightness; the alternate
ink is mapped into the selected atlas slot. Sliders use the same contrasting
ink colour for their fill and handle.

Role accents remain supplied by Stems: drums blue, vocal green, instrumental
red, optional bass yellow. Colours are not lifted, darkened or mixed with a neutral. They are not reused as loading or error colours.

<a id="doc-pad-visual-design--verification"></a>
##### Verification

Real ARM-emulator captures cover STEMS toggles, partial levels and off, KEY
and shifted KEY, and Samples, in dark/light themes. The unit suite checks the
unchanged touch/layout contracts and the ARM build checks firmware imports.
Emulator evidence does not establish physical-device behaviour.

<a id="doc-pad-visual-design--camelot-colours-on-key"></a>
##### Camelot colours on KEY

Only the current key fills its whole central cell with its Camelot colour.
The decrement/increment actions use neutral faces and the fixed labels −1/+1,
without target-key text or chevrons. Their small colour rails still preview the
adjacent key, and disappear at the absolute ±12 limits. Limits still clamp the
pitch; action labels remain stable. Unknown keys stay neutral.
Pallet source: https://mixedinkey.com/camelot-wheel/ (RGB565).

<a id="doc-pad-visual-design--harmonic-feedback--operate"></a>
##### Harmonic feedback — Operate

The right-hand slot communicates a relationship or offers one action. It stays
in the same position while both track keys are known, preserving the stepper's
hit targets through changes in compatibility.

- **COMPATIBLE**: neutral, readable text on the band's own background. No
  button frame, filled action face, status rail, hover or pressed treatment.
  The original keys retain their full Camelot colours. A different hue on each
  deck is normal: compatibility does not mean the keys are identical.
- **KEY SYNC ±n**: a neutral button with a two-pixel Camelot contour identifying
  the proposed key. Its signed shift says what a press will do. The contour
  grows to three pixels while held and darkens on the light theme for contrast.
- **PAS DE SYNC**: passive text when neither compatibility nor a correction
  within the selected mode/range is available. This makes absence of an action
  explicit without moving the manual controls.
- **IDENTIQUE**: passive confirmation in Identical mode when keys already match.
- If either key is unknown, the comparison slot is omitted.

The core's STATUS widget consumes the complete gesture without firing, including
state changes during a hold. A gesture beginning on a status cannot turn into
a sync on release. This is a real non-actionable element, not a disabled-looking
button with an active hit target. Status ink is white on dark and dark on light,
using the shipped glyph atlases. Colour remains reserved for key identity and
action; no green success code competes with the vocal stem convention.

---

<a id="doc-performance-tab-matrix"></a>
### Performance tab selection

<!-- source: docs/performance-tab-matrix.md | sha256: adb5b9c40c7febb82deaa9c88a0a234c396a5d076bc93092273a2ec6e1b121af -->


The on-device tab strip follows the modules that actually registered a panel, not a module list cached by the Toolkit. KEY is Key Shift's panel; Key Sync and Key Match do not add another tab. The eight selection combinations are:

| KEY | STEMS | SAMPLES | Upper strip | Lower left | Lower right |
|---|---|---|---|---|---|
| off | off | off | native ZOOM / GRID | native STATUS | native BEAT FX |
| off | off | on | native ZOOM / GRID | SAMPLES | native BEAT FX |
| on | off | off | KEY full width | native STATUS | native BEAT FX |
| on | off | on | KEY full width | SAMPLES | native BEAT FX |
| off | on | off | STEMS full width | native STATUS | native BEAT FX |
| off | on | on | STEMS full width | SAMPLES | native BEAT FX |
| on | on | off | KEY / STEMS | native STATUS | native BEAT FX |
| on | on | on | KEY / STEMS | SAMPLES | native BEAT FX |

With both modules present, the upper cells keep their original 90 x 50 pixel footprint. A single module extends its native-derived artwork across the 180 x 50 pixel strip, and the whole strip handles touch. The custom strip sits below QUANTIZE and shares a two-pixel inner border with STATUS / BEAT FX. Its touch area ends above the lower row. If either KEY or STEMS is active, both native ZOOM and GRID touch controls are replaced; the Toolkit says so beside the module choices. If neither is active, the core passes the native strip through unchanged.

Touching an active KEY, STEMS or SAMPLES tab again returns to the native status/pad display. With SAMPLES absent, STATUS is shown and explicitly handles touch even while a custom panel is open. BEAT FX remains separate and available. Physical pad-mode buttons still return to the native display. A panel registration that disappears while another panel is visible is recovered on the next tab touch; normal module removal stops the whole hook.

The image-choice and touch functions are covered by `tests/test_runtime_transitions.py`. The machine emulator has painted and responded in the isolated KEY, isolated STEMS, isolated SAMPLES and combined cases. The compact combined-tab capture uses core SHA-256 `19cb0bf4c68cdb74eb4ef7ff6b665fb13852b47feda3611e0fc6406bdeff57d7`. Physical RX3 behavior requires later hardware validation.

---

<a id="doc-recovering-a-module"></a>
### Porting a released runtime

<!-- source: docs/recovering-a-module.md | sha256: 53411c53835c0ba613d040c7fb52cda0d684bb2bccdd6f52d8341ebf478ef4d6 -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

The released runtime defines the behaviour to reproduce. Read each function and its surrounding state machine in Ghidra before writing it. A decompilation helps identify constants and branches; verify register use, pointer arithmetic and callback ordering in the disassembly.

The recovery target is the DJ's capabilities, not an identical internal architecture. Keep an existing implementation when it is more useful to the DJ and easier to maintain. In particular, native touch hooks replaced by the shared pad row are not missing features merely because their original function names disappeared. Compare the complete user action, resulting audio or display, fallback, and cleanup before deciding to port code.

Permission to use the reference is recorded in writing. The migration pull request must record the permission and the decision to defer attribution until merge in its Legal section. No supplied binary or unpacked resource is included in the repository. Local analysis material stays on the operator's machine.

<a id="doc-recovering-a-module--method"></a>
##### Method

Compare defined symbols and hook guards against the current core. Missing names identify work to inspect, but shared names do not prove shared behaviour. Compare known functions to calibrate the reading.

Trace each feature from configuration through hook installation, input, rendering or audio, and teardown. Shared hooks need an owner, and callbacks must finish before their data or trampoline is freed. An inner loop is not a complete feature.

Keep provisional addresses and disassembly evidence in local notes. [CONTRIBUTING.md](CONTRIBUTING.md#supporting-another-firmware-build) requires the firmware hash, guard bytes and a result on hardware before an address is documented as verified in [REFERENCES.md](REFERENCES.md).

<a id="doc-recovering-a-module--current-status"></a>
##### Current status

All migration changes remain uncommitted. The table distinguishes prior hardware observations from source work; compilation and native C tests do not establish device behaviour.

| Module | Source status | Hardware status |
| --- | --- | --- |
| [logo](mod/modules/logo) | Host conversion, container loading and dark/light image-table replacement. | The handover reports a byte-exact host conversion. The new light-table connection has no device run. |
| [Stems waveform](mod/modules/stems/WAVEFORM.md) | Refresh sequencing, three column render paths, Blue overview restoration and the four-role selection adapter. | The earlier hook fired on toggles. The new renderer and refresh request are untested on hardware. |
| [theme-white](mod/modules/theme-white) | Solid fills, lazy image conversion, shared-bitmap cache, light logo and optional tabs, Utility row, UI-thread switching and waveform palette. | Automated queued dark/light/dark/light transitions on 1.19 preserve the unloaded-deck background, header and eight hot-cue cells. Physical shortcut, Utility and loaded-track coverage remain pending. |
| [samples](mod/modules/samples) | Settings and WAV contract, resident bank loader, master mix, retriggering, shared pad routing, LEDs, volume strip and worker teardown. | No playback or pad validation. |
| [search-latin](mod/modules/search-latin) | Folding hook and configuration. | The handover reports installation. Search for an accented title using unaccented input remains untested. |
| [keyshift](mod/modules/keyshift) | Common time-stretch manager attachment, generated requests, transport resets, neutral on track load and Camelot labels. | The new attachment and key recognition need an audio and display comparison. |
| [stems](mod/modules/stems) | Playback hook, four-role selection, 256-frame fades, resident PCM16 loading, additional-file fallback, pad routing, LEDs and dynamic strip. | No comparison of the new audio path has been measured. |

Native tests cover waveform sequencing, settings and WAV rejection, the four-role mix, changes during fades, concurrent toggles, key recognition and labels, transport reset decisions, sample pad ownership, master mix order, slider capture across decks, memory reserve checks and failed hook restoration. ARM builds check the resulting imports. These checks do not validate device callback timing, audio continuity, display output or unloading.

The player hash, seven new or changed hook prologues and thirteen Utility words were checked against the supplied player image. The image lookup patch uses a file offset; the hook uses the corresponding virtual address. The regression suite pins that distinction. This is static evidence, not a hardware result.

Behavioural parity is not yet established. Diagnostic formatting, dark-image conversion and sustained performance refresh are present in the current source. The runtime coalesces worker redraw requests onto the render thread and repeats refreshes every 100 ms for a one-second window. This is an adaptation to assess against the visible result, not a missing function to copy back. Optional light tab files are accepted with a dark fallback; supplied artwork is not packaged.

<a id="doc-recovering-a-module--recovery-checkpoint-2026-09-25"></a>
##### Recovery checkpoint, 2026-09-25

The supplied runtime decrypts to the archived analysis image byte for byte. All 26 payload files match the analysis tree, and the core hash matches the Ghidra export. The refreshed inventory covers 103 function bodies, 286 data symbols, 29 reference guards and 23 undefined ELF imports. There are 77 same-name source candidates and 26 candidates under replacement names. These are navigation links, not 103 proofs of equivalent behaviour.

The current source passes 88 tests and the publication preflight. The address checker reports 37 matching hook or patch checks against the local 1.19 player. This does not check every pointer, callback contract or runtime transition.

The pure pixel functions were compared against execution of the reference ARM instructions under Unicorn. Every RGB565 input was tested for the dark transform and six light cases: ordinary image, each of the two special replacement image classes, with artwork both enabled and disabled. All 458752 comparisons matched. Only the unsigned integer division import was substituted with integer division on the host. This establishes the tested pixel calculations, not image classification, conversion allocation, display timing or the appearance of a complete screen. The script and hash-bound results remain under the ignored local analysis directory.

| DJ capability | Existing implementation to retain and inspect | Remaining acceptance |
| --- | --- | --- |
| Mute and combine vocal, instruments, drums and bass | Four-role stems, native pad routing, shared on-screen row and 256-frame transitions | Both decks, missing additional files, rapid loading, audible transitions and uninterrupted transport |
| Shift a deck's key and return to neutral | Per-deck shifter, Camelot labels and shared time-stretch attachment; the current interface also offers key matching | Real audio at positive and negative shifts, track changes and transport changes |
| Play samples and adjust their level | Resident bank, shared volume strip, master mix and pads; retain the added hold and loop modes and per-pad gain | Trigger, release, retrigger, loop exit, microphone talkover and bank replacement |
| Make waveforms follow stem selection | Flat, RGB/3 Band and Blue rendering with saved Blue overview | Selection changes, return to full mix, display-mode changes and track replacement |
| Use a light display | Image and fill transforms, Utility choice, shortcut, optional light artwork | Full screen with a loaded track, both switching routes, logo and tab assets |
| Search with accent folding | Bounded in-place query folding after the native shaping function | Actual indexed search results for accented titles, rather than just the folding buffer |
| Display custom artwork | Host image conversion and dark/light logo replacement | Placement, transparency, fallback and reload on the deck |
| Jump 32 beats and jump without quantization | Existing guarded byte patches | Both directions and the resulting transport position |

The subsequent device session confirmed the live 1.19 player hash and loaded only core, theme, Telnet and logging. SHIFT + SHORTCUT changed some panels, but left the central area dark and replaced the hot-cue cells with a checkerboard. Leaving and returning to the deck screen restored the complete light background and all eight cells. This establishes an incomplete refresh during the shortcut transition; it does not validate loaded-track rendering or audio.

A candidate using one native screen-refresh event instead of repeated glyph refreshes also produced an incomplete screen, with duplicate STATUS/BEAT FX strips. It was withdrawn from both source and device. The previous theme library was restored and its hash checked against the original test package. These failed candidates are not retained. The later bounded redraw fix below has narrower, unloaded-deck hardware evidence.

<a id="doc-recovering-a-module--display-comparison"></a>
##### Display comparison

Static analysis can recover image substitutions, panel geometry, labels, pixel conversion and drawing order. Compare the surrounding state as well as each drawing function. Native text and box rendering still depend on the player's renderer and resources; matching arguments alone does not establish matching screen output.

The reference's separate dark-image conversion is enabled at initialization when `RX3_THEME` starts with `d`. Its pixel function preserves the transparency key and colours whose expanded RGB channel spread exceeds 23. Other pixels are attenuated using integer arithmetic. This conversion must not be applied to every normal dark-mode draw merely because of its name. The launcher currently selects `switch`; the existence of the conversion alone does not establish which image path runs in that configuration.

The image hook, dark pixel function and initialization branch have been compared in Ghidra. This establishes the static branch and conversion rules, not a complete screen comparison. Remaining visual checks include both theme states, selected and idle controls, loading and error states, native text clipping, and redraw transitions. Compare the same resources and screen state before attributing a difference to the source port.

<a id="doc-recovering-a-module--device-checks"></a>
##### Device checks

Use player SHA-1 `cf309238491e73cdbdc1f08a09f7a3177e079068`, the build identified in the handover. Confirm the live player before installing a test build.

1. Load a track and exercise both decks. Check transport and audio continuity while switching each stem selection.
2. Compare flat, 3 Band/RGB and Blue waveforms. Return to the full mix, load another track and repeat.
3. Check theme switching against the loaded track, and search for an accented title without its accents.
4. Check sample playback, retriggering, volume, LEDs, shared pad hooks and teardown with audio callbacks active.
5. Check four-role fallback, rapid track replacement and repeated pitch direction changes. Verify both Utility and shortcut theme switches.

Stop a device run if transport freezes, audio drops or the guards reject the player. Record the build hash and observed failure before changing another feature.

Before preparing the migration pull request, run `make test`, `make preflight`, and read the complete diff. Use Summary, Changes, Testing and Legal. State every unverified behaviour.

<a id="doc-recovering-a-module--theme-transition-result"></a>
##### Theme transition result

The retained fix applies the pending theme at the beginning of a native render pass and invalidates the active windows once. Root traversal skips visible header groups beneath their hidden parent control, so the fix queues those groups through the native child-list iterator and renders them in a second pass. It does not change their visibility flags or write the framebuffer. Repeating root redraws for four seconds has been removed.

Automated dark/light/dark/light transitions on RX3 1.19 preserved the central background, header and eight hot-cue cells without screen navigation. The tests injected the existing queued request after checking the process, library hash, mapping, symbol and idle state; they did not inject physical button events. The test package enabled only core, theme, Telnet and logging, with both decks unloaded. Utility switching, loaded tracks, audio continuity and the other modules remain unverified. The core still exposes KEY/STEMS tabs in this theme-only configuration; that pre-existing module-gating issue is separate from the redraw fix.

The retained implementation passes 91 tests, publication preflight and 39 binary-address checks. Regression tests cover stable theme state within a render pass, window invalidation before root rendering, header rendering after the root, actual child-list iteration and a bounded exit for an unexpected cyclic iterator.

---

<a id="doc-runtime-framework"></a>
### Shared runtime framework

<!-- source: docs/runtime-framework.md | sha256: 927d8170fcdcc6c8aa0a624f0b94a5621d5a235153d4eb69a173578024020d9b -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

Decision: the core provides shared services. A module owns its behaviour and state and depends on the public service contract in full. Reading another module's globals or calling a private core helper is not a supported extension mechanism. Existing contracts may be replaced to establish this boundary.

<a id="doc-runtime-framework--source-organization"></a>
##### Source organization

Public contracts live in `mod/modules/core/api/`, lifecycle and composition in `runtime/`, shared implementations in `services/`, firmware adapters in `firmware/`, panel helpers and translations in `ui/`, and probe formats in `diagnostics/`. The root retains manifests, shell installation, asset generation and the performance entry point. See [the directory guide](mod/modules/core/README.md).

Native notification rendering belongs to rbp: the firmware adapter calls `ui::Caution::set` using B051. The queue coordinates toolkit requests only; it neither replaces Emergency Loop nor controls the priority of native player warnings.

<a id="doc-runtime-framework--implemented-boundary"></a>
##### Implemented boundary

The library is still `librx3_core.so`. Separate compilation units establish ownership without adding a dynamic loader or assuming new symbols in the player's libc. This is source modularity, not independent binary delivery or crash isolation. The module descriptor is versioned and size-checked, but is not yet a stable dynamic ABI.

- `rx3_module_api.h` is the module entry contract. It exposes a service table, opaque hook handles and copied observations. It exposes no feature implementation or PCM context.
- `rx3_modules.c` handles configuration, descriptor validation, start, partial-failure cleanup, reverse-order stop and track notifications. It names no feature.
- `rx3_composition.c` lists the module descriptors. It is the only core file that names individual modules, and it names only their public descriptors.
- `rx3_hooks.c` owns detour records, trampolines and an exclusive address registry. A second owner cannot hook an overlapping range, including while the first owner is draining callbacks. Relocating a live handle is forbidden.
- `rx3_patch.c` is the ARM instruction-writing adapter. Modules reach it only through `write_guarded`, which compares before it writes.
- `rx3_log.c` owns the shared destination and log budget.
- `rx3_mix_state.c` owns one typed provider registration. Readers receive values, never the provider's buffers. Only the current provider can withdraw its registration. Missing providers and invalid decks produce an empty observation.

Every feature is a separate compilation unit: Asshole Mode, Browse Columns, Key Match, Keyshift, Logo, Now Playing, Samples, Search Latin, Stems, Stemwave and Theme. Each includes only its own files and `core/api`; the core includes no module file. Each unit links alone and imports libc names only (`tests/test_extracted_modules.py`), and Samples and Stems run their start, failure and stop paths against mock services. The Makefile and application compiler read the same units from `arm_hook.sources`; every unit also belongs to its module's `build_files` for packaging.

<a id="doc-runtime-framework--ownership-and-calling-rules"></a>
##### Ownership and calling rules

Startup and hook mutation run serially. Descriptors, services and callback code live until process exit. There is no hot unloading. `start` returns success only after it has acquired its required resources; failure invokes that module's `stop`, without stopping unrelated modules. `stop` must accept a partial installation. Unselected modules are not started or stopped by the new lifecycle manager.

A hook handle starts at zero. `detach_hook` restores the native entry point while retaining the trampoline; after callbacks have drained, `release_hook` releases it. A failed restoration keeps the allocation and address reservation. Modules must not clear their original callback when removal fails. The simple `uninstall_hook` service combines both operations and is only suitable when its callbacks are quiescent. Audio modules must use the two-phase lifecycle. The low-level ARM writer still requires hardware acceptance; host tests cannot establish safe instruction replacement on the player.

The instruction writer saves the previous bytes and rolls them back if restoring
RX permissions fails. It retains execute permission during the write. If both
RX restoration attempts fail, the previous instructions remain on an RWX page;
the operation reports failure. This preserves executable code but is not a
guarantee of restored page permissions or atomic live patching. The core retains
original callbacks on cleanup failure. Search Latin and Now Playing detach
their hooks and drain admitted native callbacks before releasing trampolines.

`track_will_load` runs on the native loading thread before the original load, allowing metadata invalidation before new text can be observed. `track_did_load` runs after the original load and the existing providers' load callbacks. Mix observations may run on the waveform thread. A provider must return promptly without allocation, I/O or waiting, and its code must remain resident after withdrawal. Logging and hook installation are not audio-thread services. Workers remain owned and joined by their modules.

<a id="doc-runtime-framework--ownership-map"></a>
##### Ownership map

| Module | Owns | Uses from the core |
| --- | --- | --- |
| Asshole Mode | Visibility policy, eye artwork | Titles, copied bitmaps |
| Browse Columns | Field selection, captions | Browse |
| Key Match | Matching policy, colours | Browse, image recolours, harmony |
| Key Sync | Shell configuration of Keyshift and Key Match | None in process |
| Keyshift | Pitch state, native pitch adapter, configuration, panel | Hooks, audio-start notifications, text observations, panels |
| Logo | Artwork, its size and its native placement | Native image replacement |
| Now Playing | Worker, sockets, player observations | Hooks, logging |
| Samples | Bank, settings, voices, pad policy, pad colours, panel | Input (pads, SHIFT, pad lights, mode keys), master audio stage, panels, memory, loader |
| Search Latin | Transliteration | Hooks, logging |
| Stems | Files and formats, payloads, per-deck mix, pad and light policy, panel | Input (pads, SLIP LOOP lights, blink clock), deck stream stage, providers, panels, memory, loader, track notifications |
| Stemwave | Waveform rendering | Hooks, mix observations, waveform copies, track notifications |
| Theme | Chrome and conversion policy, SHIFT + SHORTCUT, Utility row, waveform palette, pixel arena, watcher | Image variants and fill adapter, key handler, guarded writes, memory |
| Beat Jump variants, Decoder Sleep, Telnet, Logging variants | Shell lifecycle and guarded patches | None in process |

<a id="doc-runtime-framework--alternatives"></a>
##### Alternatives

A single large translation unit preserves accidental access to every private global. Merely moving its includes does not solve that. One independent shared object per feature would introduce loading order and overlapping hook ownership before the contracts are ready. Separate compilation with one composition root is the chosen first step; splitting the binary can follow once each feature passes the same contract and lifecycle tests.

<a id="doc-runtime-framework--acceptance"></a>
##### Acceptance

A migrated module must compile and link against the public API and mock services without the performance core or sibling modules. Test partial installation, ownership conflicts, cleanup and the behaviour it changes. Build through both Makefile and the application's manifest path, and verify the resulting ARM imports against the known player symbols. Compile generated module templates too.

The runtime changes in this migration have not yet run on hardware. Before deployment, exercise each module alone, the combined configuration, guard refusal, track replacement and the existing pad/SHIFT/audio acceptance sequence in CONTRIBUTING.md. A successful host build is not hardware validation.

<a id="doc-runtime-framework--notification-and-dsp-services-api-version-2"></a>
##### Notification and DSP services (API version 2)

`services->notices` now exposes `post`, `cancel` and `available`. A request contains a stable owner token, an owner-local ID, deck, priority, duration and UTF-16 text. The service copies up to 95 UTF-16 units and rejects longer or empty strings. It holds eight requests; a full queue returns `RX3_NOTICE_FULL`, and contention returns `RX3_NOTICE_BUSY` immediately. Producers must handle these results; an audio callback must never retry in a waiting loop. Accepted means queued, not displayed.

Owner/ID replacement updates a message without consuming another slot. Equal priorities retain FIFO order; higher priorities preempt. Duration starts on first display; time spent preempted counts toward expiry. Replacement restarts duration on its next display. The renderer owns a separate persistent text buffer and hides the previous notice before replacing that buffer. Native UI calls never run on producer threads, and recursive drawing cannot re-enter the pump. The existing translated startup warning now uses this service. Its language is selected before posting, then its text is copied.

The native adapter still needs the existing performance draw hooks. `available()` remains false until a usable renderer has run, and the disable switch clears queued notices. Messages on decks 0 and 1 are supported by the current adapter; global routing is reserved and explicitly rejected pending firmware verification. A module must not claim a notice was displayed merely because posting succeeded. Sentinel polling runs in the existing background watcher, not once per rendered frame.

Example inside a module that retains the service table from `start`:

```c
static const unsigned char notice_owner;
static const uint16_t ready[] = {'R', 'E', 'A', 'D', 'Y', 0};
struct rx3_notice notice = {
    &notice_owner, 1u, 0u, RX3_NOTICE_INFO, 3000u, ready
};
enum rx3_notice_result result = services->notices->post(&notice);
/* Handle FULL/BUSY or fall back to the module's status. */
```

`services->dsp` supplies interleaved stereo PCM16-to-float conversion, gain ramps, additive mixing, peak/mean-square measurements and integer milliseconds-to-frames conversion (rounded down). Counts are stereo frames, buffers belong to callers and ramps carry caller-owned state. Ramps continue across block boundaries and apply one gain to both channels. These functions allocate nothing, perform no I/O and add no libc imports. Finite PCM values are expected; there is no hidden limiter, normalization or clipping.

The scalar kernels `rx3_dsp_lerp` and `rx3_dsp_loop_edge` are shared inline operations, already used by Stems transitions and Samples loop edges. Existing PCM reconstruction and sample playback regression tests preserve their behaviour. The loop edge kernel retains the existing 32-frame edge on loops of at least 128 frames.

This implements reusable calculations, not a shared audio processing graph. Stream-stage arbitration and memory reservations arrived with API version 18 (below); resampling and public pitch adapters are still pending. The notification adapter and DSP refactor have not yet run on hardware.

<a id="doc-runtime-framework--startup-readiness"></a>
###### Startup readiness

The constructor clears the previous ready marker, then starts every configured module. Modules register their rows, images, handlers and stages first; each shared service installs its native hook when its first client arrives. Any module failure stops the ones already started and nothing is ready. The performance hooks follow only when a panel, an image contribution, Browse or titles need them; if one of them, or the audio-device hook, is rejected, every module is stopped and every hook removed. The ready marker and success log are published only after the whole selection succeeds. Readiness is an installation result, not proof of audio or rendering quality.

Logo registers its artwork as a native image replacement, which alone brings in the image tables. Its placement record is checked before changing it, and teardown restores the saved position only while the record still holds this module's value and no published table references the artwork. The seven light tab images are shipped alongside their dark variants.

<a id="doc-runtime-framework--panels-buttons-and-sliders-api-version-3"></a>
##### Panels, buttons and sliders (API version 3)

`services->panels` accepts a static `rx3_pad_row` through `register_row`, releases it through `unregister_row`, and queues render-thread selection through `open(panel_id)`. IDs 1-3 belong to Keyshift, Stems and Samples; 4-16 are available to additional clients. Registration rejects duplicate owners, invalid counts and sliders without accessors. Registering a panel is what makes the constructor install the shared rendering adapter before reporting readiness. Descriptors and callbacks must remain resident until runtime shutdown; arbitrary hot unload is not supported.

A client provides widget types, weights, captions, state/actions and slider accessors in its own units. Optional `kind` and RGB565 `colour` callbacks select presentation per deck, with slider accessors required when kind is dynamic. The framework owns layout, clipping, square button frames, selected/pressed states, slider tracks and caps, and touch capture. The same geometry drives rendering and touch. Leaving a button cancels it; sliders clamp at the track endpoints. Changing the panel during capture cancels the old gesture.

The Stems client declares one `RX3_PAD_TOGGLE_SLIDER` per available role. Tap toggles; holding for 350 ms then dragging changes volume relative to the initial gain. The core owns gesture recognition, geometry and RGB565-to-native-RGB888 accent conversion. API version 5 adds the optional `slider_visible` callback: Stems keeps partial volumes visible and hides a full-volume slider two seconds after release. Zero is off. The four percentages share one atomic word; enabling a muted role restores 100%. Changes use the existing 256-valid-frame interpolation before mixing the residual and prepared roles. Track loading resets the levels. Stemwave observes the nonzero role mask; it does not represent partial slider gain in its waveform amplitudes.

Samples declare one screen-wide slider plus a reset/readout button. Both deck halves access the same bank volume. No sample-specific drawing or coordinate calculation is part of the client.

The panel registry is compiled independently and exposed in the public service table. The native painter uses rbp adapters in the core's performance entry point. Panel clients do not draw or inspect the renderer's private state. API version 18 adds an optional `activate` callback, called with 1 when a row becomes the visible panel and with 0 whenever the core leaves or bypasses it; panel 3 replaces the native STATUS tab. `services->panels->refresh()` repaints the performance row from the render thread.


<a id="doc-runtime-framework--embedded-waveforms-api-version-4"></a>
##### Embedded waveforms (API version 4)

`services->waveform(deck, mask, destination, count)` copies the package's
amplitudes (0..31) on the native 150 Hz grid. Returns `count` on success, zero
when unavailable and `UINT32_MAX` when a package exists with an incompatible
axis. The destination belongs to the caller. The provider protects resident
package memory with its reader barrier; no provider pointers cross this API.

<a id="doc-runtime-framework--per-part-semantic-colours-api-version-6"></a>
##### Per-part semantic colours (API version 6)

`rx3_pad_row.part_colour(deck, widget, part)` optionally supplies an RGB565
semantic accent independently of selection. Zero means unknown/unavailable.
KEY uses it for the Camelot key actually shown by each stepper part. The core
renders the rail and preserves theme adaptation and the selected-state frame.

<a id="doc-runtime-framework--key-sync-configuration"></a>
##### KEY SYNC configuration

The Toolkit supplies `keyshift/sync-range.txt` to the runtime builder as module
content (integer 1–12, default 1). The module exports `RX3_KEY_SYNC_RANGE` through
`module_export`, including its restart detection. The KEY client declares a
second standard button only while a valid sync offer exists; the core owns its
layout, rendering and touch dispatch. No KEY-specific drawing is added.

KEY SYNC additionally supplies `sync-mode.txt`. New Toolkit preferences use `harmonic`, a one-semitone limit and no optional Energy Boost rules. Stored preferences and legacy missing-file defaults are preserved. API version 12 adds a copied harmonic reference and deck-key publication to the BROWSE service. Both clients use the observed native key set, the local MASTER and its effective transposed key; the KEY client never changes the MASTER through KEY SYNC. The pure shared solver is checked against the Python preview implementation. See [Transposition](#doc-transposition) for evidence and unavailable-reference behavior.

<a id="doc-runtime-framework--passive-panel-statuses-api-version-7"></a>
##### Passive panel statuses (API version 7)

`RX3_PAD_STATUS` declares a readable, non-actionable row element. The shared
painter omits button chrome and semantic accents; the shared touch machine
consumes the whole gesture without dispatching `fire` or a slider update. A
status becoming a button during the gesture remains passive until release.
Dynamic `kind` callbacks may now describe statuses without slider callbacks;
missing slider callbacks make a dynamically requested slider passive safely.
KEY uses the same slot for status and action to preserve touch geometry.

<a id="doc-runtime-framework--outlined-actions-api-version-8"></a>
##### Outlined actions (API version 8)

`RX3_PAD_OUTLINE_BUTTON` uses the regular release-action contract with a neutral
face, high-contrast caption and semantic outline (two pixels, three while held).
Shared steppers now keep their end actions neutral; only their value part may
use a full semantic fill. KEY supplies fixed −1/+1 labels and its target colours;
it does not own drawing or coordinates. Stem fills and status rendering remain
unchanged.

<a id="doc-runtime-framework--keyshift-boundary-api-version-9"></a>
##### Keyshift boundary (API version 9)

`keyshift/rx3_keyshift_module.c` owns the module descriptor, private state,
configuration, pitch hooks and panel. The core neither includes its private
headers nor calls its implementation. Only the composition root names it.
The native pitch effect adapter remains private to Keyshift; this is not a
shared audio processing graph or a firmware-independent DSP implementation.

The module descriptor now accepts audio-format, render-text and diagnostic
notifications. The core decodes the native glyph layout into a borrowed
`rx3_text_observation`; modules must not retain its text pointer. Keyshift
interprets the deck-key glyph and publishes its own refresh flag through the
existing `needs_refresh` panel callback. It cannot inspect renderer state.

The core installs the shared audio-start hook only when an active module
subscribes to audio-format notifications. Keyshift registers its panel and
pitch hook through the public service table. `detach_hook` and `release_hook`
are public services, preserving the two-phase audio hook teardown.

Shutdown closes notification admission and drains in-flight callbacks before
stopping modules. A module must not call runtime shutdown from a notification.
This drain covers lifecycle observations, not arbitrary native hook callbacks
or panel gestures; modules still own their hook quiescence. There is no hot
unload. Descriptor and panel storage remain resident.

Host tests link Keyshift without the performance core and exercise configuration,
manual pitch, track reset, harmonic sync, panel registration failure and hook
failure. A threaded test verifies notification draining before cleanup. These
checks do not establish audio fidelity or safe live patching on physical RX3.

Transport resets seed the pitch history directly, without first clearing it or
using per-frame integer modulo. The legacy stems fallback keeps its validated
PCM prefix rather than loading it again. Samples pack a 19-bit cursor and a
13-bit command generation into one ARM32 atomic word so an audio update cannot
overwrite a retrigger at the same cursor. Generation wraps after 8192 commands;
this assumes fewer than 8192 commands for one voice during a single mix callback.
The four-voice limit and eight-second sample limit remain unchanged.

Image recolours are invalidated when the source table, pixel offset or dimensions
change. Theme draws only enqueue image IDs. The existing watcher samples memory
and retries arena allocation every 250 ms. The render owner spends at most 8192
pixel visits (classification and conversion combined) and four job admissions
per outer render pass. It publishes only complete images, then requests native
invalidation. A partial job restarts if its source or conversion mode changes;
the old image remains visible until completion. The pixel budget is not a
measured millisecond deadline; large images can take several render passes.

Stems invalidate their loading generation at the start of a track replacement.
PCM/package reads and CRC checks observe cancellation between 64 KiB chunks;
waveform validation checks every 4096 columns. Cancelled allocations are released
without publishing them or changing the new track's status. A kernel read
already blocked on the USB device remains outside this cooperative cancellation
mechanism. Failure injection and pixel/audio equivalence checks live in
`tests/test_audit_regressions.py`, `tests/test_bounded_runtime.py` and
`tests/test_stem_package.py`; these are host tests, not RX3 acceptance.

<a id="doc-runtime-framework--native-browse-extensions-api-version-11"></a>
##### Native Browse extensions (API version 11)

`services->browse` shares the native row hook between Browse Columns and Key
Match. The core owns database requests on the native worker, record/string
allocator pairing, bounded UTF-16 transport with each queued row, and the extra
column's rendering. No database call runs on the paint thread. The feature
modules supply a field/caption or harmonic classification/image callbacks.
Registering another provider of the same kind fails without replacing it;
removing one provider preserves the other and its shared hook.

The first two columns keep their native sources. Browse Columns chooses only
the extra field. Registering a column hides the floating Browse LOAD images
and disables their list touch handlers, reclaiming the selected row for all
three values. Physical LOAD handlers and controls in other screens are unchanged.
The extra hooks are guarded, acquired only by the column provider and released
with it; Key Match alone retains the native LOAD controls.

<a id="doc-runtime-framework--deck-title-visibility-api-17"></a>
###### Deck title visibility (API 17)

`services->titles` registers one module-owned provider. The module owns title
visibility bits, toggle policy, eye coverage artwork and four precomputed themed
image variants. The core owns native identity checks, gesture capture and redraw
requests. `services->images->register_bitmap` copies a module's RGB565 pixels;
partial installation and teardown release only that module's registrations.
The Asshole Mode unit links and executes against mock public services alone.
Track text observers continue to receive original metadata. See
[the native contract and hardware checks](#doc-title-visibility).

<a id="doc-runtime-framework--asset-ownership-and-enforced-boundary"></a>
##### Asset ownership and enforced boundary

Feature artwork belongs to the feature, including its light variants:

| Owner | Packaged assets |
| --- | --- |
| Core | Shared glyph atlases and native STATUS/BEAT FX neutral frame |
| Keyshift | KEY selected, combined KEY/STEMS neutral, single KEY states |
| Stems | STEMS selected and single STEMS states |
| Samples | Three SAMPLES/BEAT FX states |
| Asshole Mode | Open/closed eye coverage compiled in `rx3_asshole_artwork.h` |
| Logo | User-supplied artwork installed by the Logo module |
| Theme | Conversion policy; it consumes contributors' light variants |

The combined neutral KEY/STEMS image belongs to Keyshift because it is only
used when both panels are available. A Stems-only selection uses its own single
tab. No optional module asset is packaged or staged by Core.

Each module stages its tab files through `stage_panel_asset` and publishes the
fixed native slot using `RX3_TAB_DARK_00..10` and `RX3_TAB_LIGHT_00..10`.
The shared loader knows slot numbers and RGB565 dimensions, not feature paths.
It ignores absent contributions, refuses missing selected dark assets, and
retains dark rendering when selected light variants are unavailable. Staging
preserves live files until the orchestrator commits; changed artwork requests
a restart even when its published path is unchanged. Slot allocation is part
of the renderer contract, not a dynamically extensible tab registry.

`tests/test_module_boundaries.py` scans every C/header include: modules may use
their own files and `core/api` only; public APIs may include public APIs only;
the core includes no module file. There is no exception. The test also pins
Core's shared-only asset inventory and checks package ownership, and
`tests/test_extracted_modules.py` checks that every module unit links alone
against libc names.

<a id="doc-runtime-framework--shared-input-audio-images-memory-and-loading-api-version-18"></a>
##### Shared input, audio, images, memory and loading (API version 18)

These services replace the last private couplings between the core and its
features. Each one owns its native hooks, installs them for its first client,
and detaches, drains and releases them after its last. A failed restore keeps
the trampoline and passes every event through untouched.

**Input.** `services->input` owns the pad dispatcher, SEND_KEY, the two pad
light refreshes and the physical pad-mode dispatcher. Pad handlers run in
priority order (Samples 10, Stems 20); the first that consumes an event ends
it, otherwise the player handles it exactly once. The event carries the code,
operation, native channel, resolved deck and pad mode. SHIFT is tracked per
channel before key handlers run; a key handler may consume a key (Theme takes
SHORTCUT while SHIFT is held) or only watch it (Samples). `claim_mode_keys`
asks the core to close its panels when a physical pad-mode key is pressed on
the path that inlines SLIP LOOP.

**Pad lights.** A module declares, per deck and control (pads 0 to 7, SHIFT),
whether a light is native, on, dim or blinking, and its colour. The core maps
controls to native LED IDs, writes them, and keeps the rules each native
refresh needs: the SLIP LOOP refresh changes only colours for steady lights,
the unit-wide refresh sets states too. Blinking uses the shared clock
(`blink_on`, `blink_restart`), which the on-screen controls read as well, so
LEDs and toggles keep one parity. No module sees an LED ID.

**Audio stages.** `services->audio` offers two typed stages with one owner
each: the deck stream after TimeStretch (deck, reader, position, frames) and
the master bus before the talkover attenuator. Deck identity is published by
the core's PcmReader::load adapter. Stage callbacks may not allocate, read
files or wait; release drains them before returning.

**Images.** `services->images` owns the private extended table and the
optional light table, their publication and their selection. Logo replaces a
native record with its pixels; once a published table references them they
stay for the life of the process. Theme claims the variants with a policy: a
`drawn` callback that queues conversions and a `fill` callback the core's fill
adapter consults while the light table is shown, never while the core paints
its own panels. Theme reads records through `native_image` and publishes
converted pixels with `publish_variant`; it never writes a table.

**Memory.** `services->memory` is one ledger for stems, sample banks and the
theme arena. A module reserves before it allocates, settles once the pages are
resident, and releases when it frees them. A reservation is granted when the
available RAM, less what other owners still have in flight, covers the bytes
and leaves the caller's floor: the player reserve for Stems, the arena floor
for Theme, none for Samples. Each module keeps its own ceilings (Stems 512 MiB
across both decks, the sample bank 16 MiB).

**Loading.** `services->loader` runs module jobs on one background worker, one
at a time, in order. Stems submits a job whenever a deck has a new request and
the job loads whatever is pending, newest per deck; Samples loads its bank as
one job. Release drops the owner's queued jobs and waits for its running job,
which sees `stopping()` between bounded reads. Formats, validation and
cancellation by track generation stay in the modules.

**Guarded writes and providers.** `write_guarded` replaces at most eight
firmware bytes only while they still hold the expected value; Theme uses it
for the Utility row and the waveform palette. `provide_mix` and
`provide_waveform` register the single provider Stemwave reads.

Host tests cover dispatch order, consumption, light mapping, the blink clock,
stage ordering, the ledger rule, loader ordering and release, and each
module's start, failure and stop paths against mock services. None of this
has run on an RX3: pad and LED behaviour, audio timing and live hook
replacement still need the hardware acceptance sequence.

---

<a id="doc-runtime-reinsertion-plan"></a>
### Runtime reinsertion and recovery plan

<!-- source: docs/runtime-reinsertion-plan.md | sha256: 4b9c99cbf4aa0a7b27b8a9047e9ae26208efa824b7d1182cfa386aec2b2d78c9 -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

<a id="doc-runtime-reinsertion-plan--contract"></a>
##### Contract

Reinserting an unchanged mod must leave the running `rbp` PID, its loaded core,
its hook order and its audio state unchanged. The orchestrator may recheck the
drive and repoint drive-dependent links. A changed module set, core binary,
startup setting or resource consumed only at startup requires a planned restart
when the media guard permits one. Unknown firmware, patch words or process state
must stop before writes.

The first local branch merges PR #34 with the current core layout. It preserves
the same-boot removal of the former `librx3_stems.so` preload. A second commit
avoids replacing unchanged core/logo images and avoids recreating stems/sample
links when they already point at the selected directory. Those changes do not
establish the full contract below.

<a id="doc-runtime-reinsertion-plan--verified-code-observations"></a>
##### Verified code observations

| Area | Current behavior | Consequence to test or change |
| --- | --- | --- |
| No-restart path | The core now publishes its PID on readiness; reuse requires that PID and an executable mapping of the installed core inode. The orchestrator also checks that the live `rbp` executable is the guarded file before proceeding, and a replacement launch checks its own PID marker. | Host tests cover stale markers, old/deleted mappings and executable mismatches; verify `/proc/<pid>/maps` and continuity on an RX3. |
| Core assets | Core binary and artwork are now compared and staged without changing live paths. Changed assets request a restart; unchanged files retain their inode. | Device validation must show that an unchanged insertion keeps the PID and that changed artwork appears only after a safe restart. |
| Samples | The active bank name, settings and numbered WAV contents now form a startup generation. A moved bank with identical bytes may repoint the live link; a changed or disabled bank stages its link transition and requests a restart. | Host tests cover moved, changed-name and changed-audio banks. Measure hashing cost and validate pad state/playback on the device. |
| Module removal | The ordered module index and active deck switches are now exported as `RX3_RUNTIME_MODULE_SET`. Removing or disabling a feature while Core remains selected requests a restart. | Host tests cover that comparison; removing Core itself still needs an explicit unload and guarded-word migration. |
| Recovery | Core and Logo changes are published after `rbp` stops. Old files remain in a private same-filesystem stage until the replacement is ready, and rollback restores them before relaunching the previous process. | Host tests cover deferred, partial-commit and optional-file rollback. Device and launch-failure validation remain; Samples links and module removal are not yet transactional. |
| Concurrency | `mod/autoexec.sh` uses the fixed `/tmp/rx3-runtime` workspace and now claims `/tmp/rx3-runtime.lock` before clearing it. | A concurrent invocation stops; a lock left by SIGKILL fails closed until reboot or manual inspection. Host contention is tested; device launcher behavior remains to verify. |
| USB after restart | The orchestrator waits for the new `rbp` to open its USB procfs channels, then sends `connect` and `mount` directly. The former block `add` replay could invoke the udev rule that runs `decrypt_autoexec.sh` again. | Host tests check message routing and missing mounts. Measure time to visible USB database and confirm no second autoexec launch on an RX3. |

<a id="doc-runtime-reinsertion-plan--decision-matrix"></a>
##### Decision matrix

| Event | Expected action |
| --- | --- |
| Same image, settings, startup resources and mount | Recheck state, keep PID and links unchanged. |
| Same image and settings, drive returns under another device name | Repoint drive-dependent links; keep PID. |
| New core, changed startup asset, changed sample bank or settings | Stage the new generation; restart only when the media guard says it is safe. |
| Module removed or disabled | Compare the complete desired module set with the live one; restart safely to withdraw the old feature. |
| Unexpected patch word, unrecognized binary or ambiguous live process | Stop without installing anything. |
| Another DJ drive mounted and restart required | Defer the change without stopping playback or replacing live resources. |
| SHIFT held on either deck when the USB runtime starts | Bypass this insertion before logging, locking, module loading or patching; an unreadable panel frame also bypasses it. Already active live mods require a restart to clear. |
| Startup or readiness failure after a restart | Restore the prior binary, core, resources and preload together, then verify the restored player. |

<a id="doc-runtime-reinsertion-plan--work-sequence"></a>
##### Work sequence

1. Record the desired and live generations: core hash, ordered module set,
   startup settings and startup resources. Keep drive-dependent stems paths out
   of that identity. Module selection and Samples content markers are
   implemented; an older build without them restarts once. Core removal still
   needs an explicit unload path.
2. Split preparation into read-only planning, private staging and one committed
   transition. A no-op does not rewrite assets. A deferred restart does not
   replace files used by the current process. Core/Logo and changed Samples
   links use private staging; a moved identical bank can repoint its live link.
3. Check the actual `rbp` executable, loaded core and current readiness. Avoid
   using a stale ready marker as sole evidence. State why a restart is requested
   in the session log. PID-bound readiness, executable identity and core
   mapping checks are implemented locally; device proof remains.
4. Make recovery generation-aware: preserve previous core/art files until the
   replacement process is ready, restore them on failure and test a second
   insertion after recovery. Core/Logo rollback and a subsequent file commit
   are host-tested; full orchestrator and device tests remain.
5. Exercise unchanged, moved, changed, removed, interrupted and two-drive
   cases in host tests. Validate the active core, framebuffer and useful input
   response in the emulator, then verify PID and playback continuity on an RX3.
6. On the RX3, test both SHIFT buttons held from before insertion through USB
   recognition, an ordinary insertion with the loading notice, and reinsertion
   after a mod is already active. Confirm the first two cases from the live
   process and UI, not from absence of a notice alone. Check that the one-frame
   EUP read does not interfere with normal panel input.

No hardware claim follows from host tests or the ARM build alone. The current
CI failure must also be resolved before release qualification.

---

<a id="doc-rx3-startup-incident"></a>
### RX3 startup incident, 2026-09-28

<!-- source: docs/rx3-startup-incident.md | sha256: 7b82e41f33831cc63b2932486d44d0c3f5db7ade7594af36d9de3dce144c081e -->


The operator reported that inserting DJ FRANCOIS restarted rbp, briefly showed the mod, then returned to an unmodified player without any control input. No audio or player restart was initiated during this investigation.

<a id="doc-rx3-startup-incident--evidence-and-limits"></a>
##### Evidence and limits

The mounted drive's manifest selects firmware 1.19 and eleven modules: core, decoder-sleep, beatjump-32bars, beatjump-no-quantize, keyshift, key-match, key-sync, browse-columns, stems, search-latin and logo. It selects neither logging nor telnet. The 2,664,448-byte autoexec.bin matches its manifest SHA-256, `3bc8fe52649079d50dd3c139656d2b6e889aabda84e8d0aef40794d32262cd02`.

The surviving USB files are mod-previous.txt, rbp_stdout-previous.txt and rbp_stdout.txt. They contain an active-hook message, repeated PcmReader::load guard refusals, two unqualified Segmentation fault lines, and a separate launch with no preload. They do not identify the crashed process or prove that these records describe the latest image. They must not be presented as a backtrace or a confirmed cause of this incident. The full session log for the latest insertion is absent.

After the direct network was reconnected, 169.254.177.105 refused TCP port 23. RAM logs, the current player mappings, and kernel diagnostics could not be read. The fifty checks performed by scripts/check_addresses.py against the owner-local stock 1.19 player all passed; this does not verify live device memory or the installed hook binary.

<a id="doc-rx3-startup-incident--confirmed-source-defect-and-correction"></a>
##### Confirmed source defect and correction

The performance-core constructor previously ran whenever the shared library was loaded, including in utilities launched with an inherited LD_PRELOAD. Before checking any player prologue it configured the shared log and truncated /tmp/rx3-performance.ready. It could then attempt firmware-specific accesses inside a different executable. This makes guard refusals and child-process faults plausible, and a missing readiness marker can cause the orchestrator to restore the previous player. It is a concrete defect, but remains an unconfirmed explanation of this particular restart.

The constructor now reads /proc/self/comm and proceeds only for rbp. A missing, unreadable or different process identity returns before logs, readiness files, modules or firmware addresses are touched. The destructor also returns unless initialization was admitted for the player. No new dynamic imports were added. Host tests execute the real constructor and destructor control flow with stubbed firmware boundaries, check utility names and read failures, preserve an existing readiness marker in the rejected process, and retain player cleanup ordering.

<a id="doc-rx3-startup-incident--initial-hardware-check"></a>
##### Initial hardware check

The operator rebuilt the drive with the corrected core, Telnet and verbose logging. The new manifest identifies a 2,678,784-byte image with SHA-256 `d98ee04d19ffe1cf9736ed38af2358ad48d0a83d57401f26e5e3933acc3a50af`. No firmware key was accessed by the investigation.

Read-only Telnet checks on the reconnected device found rbp PID 3491 unchanged from uptime 129.82 to 373.65 seconds (244 seconds of direct observation). Its mappings include /root/pdj/librx3_core.so, LD_PRELOAD names that object, and /tmp/rx3-performance.ready contains ready. Device and corrected local core share MD5 `d7f15200df255436a4faa0839ce96ebb`. Current player stdout contains no segmentation fault, and a kernel-log search found no segfault, oops, killed-process or out-of-memory report. The reported thermal value increased from 59 to 61 degrees Celsius. No audio, player restart or deployment was initiated by the investigator; operator interaction appears in the keyshift logs. This confirms the corrected hook remains loaded during this short hardware observation, not a prolonged thermal or stems-playback validation, nor a retrospective proof of the original crash cause.

The repeated startup pass also exposed two independent prepare-hook failures: Key Match and Browse Columns leaked module_export's no-change return status when settings were already present. Their prepare hooks now explicitly return success after exporting settings. A shell regression exercises initial application, unchanged reapplication without restart, and genuine missing-core failure for both modules. All 25 module API, Key Match and Browse Columns tests passed. This shell correction is local only and was not deployed into the running session.

The first startup log's inactive-core warning conflicts with the live ready marker, mappings and active-hook log. Its exact logging/lifecycle timing remains unresolved. Preserve session.txt, mod.txt, rbp_stdout.txt and rbp_restore.txt together with process mappings and kernel diagnostics if a restart recurs.

Owner-local copies and artifact hashes are under local/research/rx3-restart-20260928/. The mounted USB contents were not changed.
The follow-up Telnet transcript is preserved as local/research/rx3-restart-20260928/reconnected-session.txt.

---

<a id="doc-samples-local-projects"></a>
### Local sample projects

<!-- source: docs/samples-local-projects.md | sha256: 8b06f45ca6da4cb1e1e6ce414daa2ffcc80809ac1d3a8d21d8e6cb5ff9bce977 -->


The work is kept in `~/.rx3-toolbox/sample-projects/`: one project by
key path and audio copies named by their footprint. New sounds
And the pads read from a key are copied to that computer. The project remains
recoverable even if the original audio file disappears. No network access.

Each modification is transmitted to the local backup; the requests are
serialized and the latest consolidated changes. An immediate copy in
browser storage protects pending changes. The interface
Distinguished current backup, successful local backup, failed and sent state
on the key. A failure proposes Retry and prevents changing key before the
local backup. Projects are found by selecting the same path;
a change in volume name is not automatically identified.

Creation, bank change, name, pads, volume, SHIFT,
abolition and active bank remain local. "Save to USB Flash Drive"
send all modified banks, select active and then apply the
deletions. Modification of samples is suspended during this shipment.
Local backup is declared synchronized only after complete success.
Writing is protected by bank by the existing service; Failure
between two banks may leave a partial export, reported as unsynchronised.
The project remains intact to try again. Local audio copies are kept.

Validation: `test sample drafts.py`, `samples drafts.cjs`, bank tests
existing pre-listening; synthetic pywebview path targeted in `verify samples.py`.

---

<a id="doc-stem-package"></a>
### Package of items `.rx3stem`, versions 2 and 3

<!-- source: docs/stem-package.md | sha256: 454401e63b98c02bec3b82a23510c5e484d2e717272a9febcc9ebffb48f0b8e0 -->


Only one file `RX3 STEMS/<song name>.rx3stem` contains the items
their description and their waveforms. Automatic export and import
Toolkit manual produce this format. The old format `RX3STM1` and its
sidecars remain legible; they are not rewritten at simple reading.

<a id="doc-stem-package--contenu"></a>
##### Contenu

The package contains a binary index and an internal JSON manifest. Roles
currently offered by the Toolkit are voice or voice + battery. The bass
separate remains legible in old packages. Instrumental (or other instruments with several
stems) remains calculated from the original mix; his waveform is included.
The package is autonomous for its stems and waveforms; the original piece
The reader remains required for the complete mix and the remaining instruments.

- Each selected item is included in stereo PCM 44,1 kHz, signed 16 bits,
on the player's time grid, with its explicit role in the index.
- The waveform section contains 150 Hz columns of each role, including
the residual. It keeps the PWV3 or PWV5 format of the template when it is
is compatible. Without a usable template, a PWV5 grid is calculated and
the analysis identity is zero: no Rekordbox analysis is invented.
- Manifesto indicates version, roles, frame duration, format, metadata
of the piece, SHA-256 of the source file and prepared parameters provided.
- The entrances carry length, offset and CRC32. The reader refuses the
overlaps, unknown roles, truncated data, divergent temporal axes,
non-zero reserved fields and section corruptions.

The header is 64 bytes, little-endian: `<8sIIIIQQ24s>` — magic `RX3PKG2\0`,
version 2 or 3, header size 64, number of entries, input size 64,
Total size, number of frames and 24 bytes reserved null.
Each entry `<IIQII32s>` describes type, role, offset, length, CRC32,
zero reserved field and ASCII name supplemented by zeros. The types are PCM=1.
waveform=2 and manifest=3; PCM bits are voice=2, battery=4, bass=8.
The sections are contiguous: PCM in the order of roles, waveform, manifest.
Internal PCM `RX3STM1` and waveform `RX3WAV1` formats remain versioned.
The limit of the package is 512 MiB, included in the shared budget of both decks.

<a id="doc-stem-package--publication-et-lecture"></a>
##### Publication and reading

Toolkit prepares and verifies the complete package before a single publication
atomic with rereading. A waveform impossible to generate fails this
preparation; the old package remains present. The ancient `.rx3drums`,
`.rx3bass` and `.rx3wave` are withdrawn only after successful publication.
The cache and pre-listening read bounded sections of the package.

The core worker loads the package in memory, checks its sections and publishes
all the roles at once. An invalid package is refused in full.
The `waveform` service of the framework (API 4) copies amplitudes under the same
Reader barrier that the PCM; Stemwave does not retain any pointer to
the private state of the supplier.

<a id="doc-stem-package--stemwave-et-niveau-de-preuve"></a>
##### Stemwave and level of evidence

Enable `RX3 STEMWAVE=1` with the Stems provider. Detailed Waveforms
then use embedded amplitudes for partial selections.
The complete mix finds the native rendering. RX3WAV3 analyzes each combination
Audio separately; the envelopes are not added. The Blue preview still retains its historical native filter.
An incompatible axis retains the native waveform and produces a diagnosis.
Old files without embedded waveform now retain native rendering.

Validated on firmware 1.19 in QEMU on September 26, 2026: "DO IT", package
vocal + waveforms vocal/instrumental, activation instrumentale et vocale,
reading, pause, restoration of the full mix. Traces explicitly indicate
`stems package: PCM and embedded waveform verified` puis
`stem waveform: rendered embedded package amplitudes`.
Session : `rx3-emulator/outputs/rx3-machine/20260926-104838`.
One, two and three PCM items are also tested on the host side and
by C drive. The three display modes and fidelity to RX3 physical
remain to be validated; emulation does not certify them.

<a id="doc-stem-package--inspection-et-migration-dune-copie-de-travail"></a>
##### Inspection and migration of a working copy

Depuis `rx3-toolbox` :

```sh
python3 -m app.stems.package inspect '/chemin/morceau.rx3stem'
python3 -m app.stems.package migrate --drive '/chemin/copie-cle' \
  --track '/chemin/copie-cle/Contents/artiste/album/morceau.aiff'
```

The migration retains the existing PCMs and describes them as coming from the
format v1, without retrospectively certifying their separation. It rebuilds
waveforms and checks that the length of the song corresponds to the stems.
For the current test, only the copy `rx3-emulator/build/media/stemwave-usb`
has been amended; `~/Desktop/key` remained intact.

<a id="doc-stem-package--waveform-combinations-rx3wav3"></a>
##### Waveform combinations (RX3WAV3)

New packages retain RX3PKG2 framing, with an RX3WAV3 version-3 waveform
member. The 128-byte header, 64-byte directory entries, and six-byte column
stride are unchanged. Masks 1..3 represent INST/VOCAL, or 1..7 with DRUMS;
bits are INST=1, VOCAL=2, DRUMS=4. Silence is implicit. Every curve is analyzed
from the exact reconstructed PCM combination, with its own PCM hash.

Each 150-Hz cell stores BLUE/PWV3 (one byte), RGB/PWV5 (big-endian word),
and PWV7 (three bytes, low/mid/high). PWV7 replaces the approximate stacked
0..31 band heights of RX3WAV2. The new version prevents confusing those
representations. Readers retain RX3WAV1/2 support; old v2 BLUE/RGB remain
usable, while detailed 3Band falls back until its waveform is regenerated.
Verified cached PCM is reused without repeating separation.

The PWV7 analysis uses the same quantized stereo-to-mono projection as RGB,
Butterworth low-pass 300 Hz, band-pass 250–1200 Hz and band-pass 3000–9000 Hz.
Integer millisecond peaks feed envelopes with 300/200/100 ms look-back and
0.99/0.98/0.97 release factors. Gains come from 1200 whole-track windows,
are peak-limited and quantized to hundredths; the high band has a cosine
transfer. There is no new storage cost, no intermediate-volume combinations.

Core waveform service formats: 0 BLUE, 1 RGB, 2 legacy band heights, 3 PWV7.
PWV7 envelopes overlap: the renderer converts their boundaries to successive
coloured layers with the native mixed palette, rather than stacking their
absolute heights. Firmware display modes remain BLUE=0, RGB=1, 3Band=2.
Full mix continues to use the native waveform. Overview handling is unchanged.

An optional hash-pinned real-export regression uses
`RX3_WAVE_3BAND_MANIFEST` (operator-local JSON with source/dat/ext/2ex paths
and hashes). It compares the entire calculated PWV7 byte stream with the
export, not an image or a few samples. This does not certify every codec or
hardware rendering.

<a id="doc-stem-package--waveforms-facultatives-et-calcul-diffr"></a>
##### Optional Waveforms and Deferred Calculation

The box "Calculating the waveforms of the stems" is checked by default and its choice
is stored in the interface. It applies to separation and import.
Unchecked, it allows to publish PCMs without launching waveform analysis.
It does not remove waveforms from a re-used package. The choice does not make
part of the identity of the separation cache.

A single audio package retains the magic `RX3PKG2\0`, but uses **version 3
package header** and manifest. Its input waveform exists in
index with zero length and CRC; It contains no byte.
The manifest bears `waveform: null` and keeps the SHA-256 of the source piece.
The PCM and manifest sections remain mandatory and not empty. One length
waveform null is prohibited in version 2. Former readers refuse the
version 3; You must install the updated Stems module for these packages.
Packages with waveforms remain in version 2, with an RX3WAV3 section.
These two version numbers relate to separate structures.

The reader reports voluntary absence by `0xfffffffe` to the waveform service.
Stemwave then keeps the original display before any write, preview included.
The incompatible axis diagnosis remains `0xffffffff`.

In Stems, **Preparing the items** processes the selected playlist: preparation
in three items, conversion of old formats, addition of missing battery
and completion of waveforms. Valid complete packages are retained. APIs
maintenance of waveforms remain available for compatibility.
They check the complete package and the identity of the song
original, reuse PCMs and preserve their provenance. The new package
is checked before atomic replacement; an error or cancellation before
publication keeps the old. The external manifest is updated after the
package; an error writing at this stage leaves audio usable but can
require a new recalculation of this manifest.

Size limits and estimates take into account choice. Add
waveforms can make a single audio package too voluminous close to the limit:
the deferred calculation controls this limit before analysis and then keeps the package.

<a id="doc-stem-package--gain-preserving-pcm-format-3"></a>
##### Gain-preserving PCM (format 3)

New preparations bypass audio-separator's output peak normalization and write
floating-point intermediate WAVs. Input normalization, where the architecture
uses it, is still undone before encoding. PCM stays stereo s16 at 44.1 kHz.
The RX3STM1 header's format field is 3; bytes 32–35 contain a little-endian
float32 playback scale in [1, 64], with bytes 36–63 zero. Stored samples are
divided by this scale to fit s16; the reader restores it before mixing.
NaN, infinity, out-of-range scales and nonzero remaining bytes are rejected.
Format 2 keeps its zero-filled reserved field and unit gain.

The preview, waveform analysis, standalone loader and package loader use the
same scale. RAM and file size remain unchanged. An older mod rejects format 3,
so reinstall the mod before using newly prepared stems on the RX3. Existing
normalized files cannot recover their true scale from their header; regenerate
the affected role from the original track. The separator cache identity changed.

Validation: `test stems gain` exercises >0 dBFS preservation, cancellation,
preview transport, every waveform mask, native mixing and malformed gains.

<a id="doc-stem-package--hauteurs-rgb-hors-plage"></a>
###### RGB heights off the beach

The PWV5 calculation cap heights at 31 before encoding. A peak in a
millisecond excluded from the normalizer can otherwise produce a height greater than
31; a binary mask would drop that height to zero or low
value. The ceiling keeps a full peak. It also corrects an overflow
present in a column of the native reference Ladies
a voluntary difference with Pioneer export. RGB waveforms already
prepared can be recalculated from the Stems screen, without further separation.

---

<a id="doc-stems-migration"></a>
### Migration of release items v0.5.2

<!-- source: docs/stems-migration.md | sha256: 9d9f600bee243e1a29ac2f0e6656ab5ca1b5c0f37a16f25d12f4bcbf56ed2b50 -->


Release verified on GitHub on September 27, 2026: [v0.5.2](https://github.com/Tratosca/rx3-toolkit/releases/tag/v0.5.2). The local and remote annotated tag corresponds to `2a49406c3d75113ada74ed0190dfcf1618275baa`, commit `73bf2cedda4d1bab4666ae7f43efce59da265255`.

The published generator calls `write sidecar(..., sample format="s16")` ([source of release](https://github.com/Tratosca/rx3-toolkit/blob/v0.5.2/tools/rx3 stems/job.py)). The `RX3STM1` container contains a 64-byte header followed by stereo PCM16 at 44.1 kHz. The new package can embed this file without changing a single audio byte.

<a id="doc-stems-migration--parcours-dans-stems"></a>
##### Route in Stems

1. Select the USB drive and open its library or export XML.
2. Select the playlist to prepare.
3. Click **Prepare the items**. The mode is set to **voice + battery + instrumental**, with the fast preset (`quick`, Democs to a shift) for recalculations. The old quality and number settings no longer alter this behavior.
4. The same job checks each title: it keeps valid complete packages, adds the battery to existing voices, converts old files and completes the Blue/RGB/3Band waveforms. No preset change alone triggers a new separation of a valid package.
5. Cancel or restart the same button to interrupt or resume. Completed titles are retained. Only the selected playlist tracks are processed.

There is no more migration window or separate waveform completion button. Former `stems migrant` calls delegate to the same preparation job with their selection of titles; they no longer offer conversion into two stems.

<a id="doc-stems-migration--ce-qui-change-dans-les-fichiers"></a>
##### What changes in files

**Title already with voice and battery:** exact copy of the old stems in the current package and CPU calculation of waveforms for combination of stems. No audio separator or encoder is launched for the existing Stem. The decoding of the original piece is only used for waveform analysis and length verification.

** Missing battery:** the existing separation engine produces the missing battery from the original piece. Only this new Stem is encoded and aligned. The historic vocal stem remains unchanged. A model can calculate multiple outputs internally; His new vocal results never replace the old stem.

Historical files are copied and verified in `RX3 STEMS/backup-v0.5.2` before any replacement. A different backup is never overwritten. The new package is checked and published by atomic replacement. The old supplementary files are kept. An error in calculation or cancellation before publication leaves the old stem usable. An interruption after publication keeps the package finished and its backup.

The remux does not correct a historical misalignment and does not claim to certify its provenance. Incompatible lengths are refused; no silent adjustment masks the difference. Old floating files created outside the standard v0.5.2 path are not implicitly converted to PCM16.

Recent packages in two items also follow this path: their voice is copied without reencoding, and the source of the new battery calculation is recorded separately. Recent packages are associated with their source by the embedded SHA-256, even if the external manifest is missing. A modified source triggers a new preparation; a corrupted package is reported without crushing.

Migrant packages are intended for the current mod. No migration was executed on a real key during development.

<a id="doc-stems-migration--prvisualisation"></a>
##### Preview

With prepared waveforms, sounds arrive in binary blocks of two seconds in a low latency audio context; play is available from the first block. When it already works, play and seek start without waiting for promise; switching changes the winnings directly. A pause also cancels a start still waiting to wake up the context.

A local worker analyzes PCM combinations signed by bounded blocks. It keeps filters between blocks and calculates envelopes by selection; Stem envelopes are not simply added. The 3Band, Blue and RGB performances cover the whole piece and follow the active items. The style is preserved locally. No analysis calculation or Python call is required when switching. This pre-listening representation does not claim a pixel to pixel identity with the graphics resources of the RX3 player.

<a id="doc-stems-migration--vrifications"></a>
##### Verifications

The tests cover bit-to-bit copying, backup, recovery, refusal of a different backup, addition of battery without voice replacement, differences in length, cancellation before publication and actual creation of waveforms on synthetic audio. The JavaScript tests cover the synchronous audio path, the non-stop switching or Python call, the local seek, outdated responses, cancellation during the audio alarm, cancellation of identical signals and continuity of filters between blocks. The acoustic latency of the output device and the reading of packages on real RX3 still need to be measured.

<a id="doc-stems-migration--chargement-progressif-de-la-prvisualisation"></a>
##### Progressive loading of preview

Packages with prepared waveforms use a strictly local HTTP server
(`127.0.0.1`, ephemeral port, random token per session). No arbitrary file
The two-second PCM slots of the session are available.
The original file is decoded in the background by FFmpeg. The transfer transports
original float32 and PCM16 studs, without audio base64 encoding
Conversion loops per sample to Python. The gain of each stem is
returned in the browser, with the same rounded float32 and the same management
silence as the reader.

The roles are programmed on the same Web Audio clock with several blocks
in advance. Switching acts on persistent gains without restarting
sources. An already loaded displacement is local; an area still absent is
requested as a priority, with possible waiting time for its reception. One
sub-feed suspends promotion to the last available block. Closing
or a song change cancels requests and releases the decoder and server.
The files without prepared waveforms keep the previous scan path.

Local measures of 27 September 2026 on Antisocial (323.76 seconds, voice + battery):
- former Python course: 8.58 s to produce all Base64 blocks, excluding
transport pywebview and build buffers in the browser;
- new Python course: metadata in 25 ms, first block in 78 ms;
- Real WKWebView: first block ready in 239 ms, metadata included, with
88 200 frames on 14 277 888 loaded. The test is silent and does not measure
audio output latency or performance on Windows.

Tests : `tests/stems_audio.cjs`, `tests/stems_preview.cjs`,
`tests/test tems preview.py`. They cover early start,
block synchronization, winnings, priority seek, pause, answers
obsolete, cancellation, source integrity and server restrictions.

---

<a id="doc-title-visibility"></a>
### Deck title visibility — Asshole mode

<!-- source: docs/title-visibility.md | sha256: 7782d306b31c2babf7d7abb23016dd6a80ea7130a41474be465ae766dc14848b -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

Status: second hardware run painted both eyes, but tapping did not toggle them.
The current candidate repairs screen gating and replaces pixel strokes with
supersampled bitmap artwork; hardware retest pending. See
[the hardware findings](#doc-hardware-feedback-20260929).

<a id="doc-title-visibility--dj-behaviour"></a>
##### DJ behaviour

An optional screen module replaces each performance deck's musical-note icon with
an eye. A completed tap hides or restores that deck's title. A drag outside the
button cancels the gesture, even if the finger returns before release. The two
decks are independent. New tracks retain the current choice; restart restores
visible titles. Other track metadata, BROWSE and Now Playing remain unchanged.

The visible eye occupies the native note position. Its 38 × 50 touch target stays
inside the title background, before the title text. No extra pad tab is needed.

<a id="doc-title-visibility--firmware-evidence"></a>
##### Firmware evidence

The local extracted **rbp 1.19** used for inspection has SHA-256
`60bcbd8876116bf09f0d8f747f95d7c7d3081ebd39d6fe14d56005a22f7f3b09`.
This implementation was derived from native objects, not from a newer MOLE binary.

- `ui_CTRL_COUNTER_CounterInfoUpdate` (`0x002899d8`) selects the active winscape's
  deck-counter instances **2480** and **2569**.
- The exported native object properties identify title group **64**, title text
  **62**, and musical-note image **61** in the table at `0x0052b0e8`.
  The suffixes 22/24/25 in symbol names are not runtime IDs. The first hardware
  run exposed this mismatch; the module loaded but could not match its objects.
- `Obj_CTRL_COUNTER_GRP_TITLE_TEXT_TITLE_24` (`0x00538f00`) contains local bounds
  `(135,15)-(599,48)`. `NS_GlyphText_CreateFromProperty` (`0x00279414`) copies
  those bounds to glyph offset `0x18`.
- The native music-icon property (`0x00538ee8`) starts at `(107,15)` and uses
  image ID `0x0bf3`. The background property (`0x00538f2c`) starts at `(96,4)`.
- The adapter checks native object **identity** inside the active counter, in
  addition to the cheap geometry/image-ID filter. Shared music icons and similar
  text elsewhere do not match.
- Native lookup, invalidation, render-origin and rectangle-fill entry points have
  byte guards. An unexpected ABI disables the adapter. Firmware 1.20 is listed
  alongside existing core modules but still requires its own hardware acceptance;
  these 1.19 observations are not a 1.20 measurement.

Text observers run before display suppression. The original text buffer is never
changed. A toggle requests native invalidation of the entire title group, including
its background and icon, on the UI thread. No framebuffer patching or track-list
lookup is introduced. Touch handling requires the performance-screen gate and the
same current native counter instance that supplied the eye's geometry. The
counter, title group and icon must also remain visible.

The title-visibility service owns native gestures and invalidation; the module
owns visibility state and artwork through its provider. Module API version is 17. The eye uses 26 × 24 RGB565 bitmap variants with supersampled edges,
rendered in one native image call. The shared image service copies each bitmap
once; native image resources and their caches are not overwritten.

<a id="doc-title-visibility--host-verification"></a>
##### Host verification

`python3 -m unittest tests.test_title_visibility tests.test_framework`

Tests execute the C service and adapter against fake native UI objects. They cover
independent toggles, owner lifecycle, restart state, gesture cancellation, exact
object matching, unmodified metadata, new-track state, screen gating, translated
hitboxes, both theme colours, invalidation and adapter refusal. This is **not**
evidence that the hardware painted the eye or that native invalidation latency is
acceptable. `make hook` checks ARM compilation; the full suite checks integration.

<a id="doc-title-visibility--additional-hardware-acceptance-all-not-run"></a>
##### Additional hardware acceptance (all NOT RUN)

These cases supplement the [0.6.0 acceptance plan](docs/acceptance/0.6.0/ACCEPTANCE.md#doc-acceptance-0-6-0-readme).
Prepare two tracks with distinct titles, including a long accented title, plus a
third track for replacement. Export them normally; enable Asshole mode and core.
Repeat with Asshole mode alone, then alongside KEY/STEMS/Samples/Theme/Now Playing.

| ID | Action | Expected result |
| --- | --- | --- |
| AH-01 | Boot, load both tracks | Both titles visible; two open eyes replace notes, no overlap |
| AH-02 | Tap left eye, then right eye, then restore each | Only the selected title changes; correct open/closed icon |
| AH-03 | Hold, drag off, return, release; start outside then drag onto eye | No unwanted toggle and no native action triggered |
| AH-04 | Hide, load the third track, unload/reload USB, load again | Choice retained on that deck; no title flash; other deck unaffected |
| AH-05 | Use the long accented title, leave playing for 60 seconds, hide/restore repeatedly | No text residue or scrolling leakage; full title restored |
| AH-06 | Hide, enter BROWSE/search/info/settings, touch the former eye position, return | Native screen works; no invisible eye action; hidden state retained |
| AH-07 | Change dark/light theme, return from other screens, refresh displays | Eye remains legible, no old note or crossed-eye residue |
| AH-08 | Play both decks; operate tempo, cue, KEY, STEMS and Samples | Audio and non-title deck controls unaffected |
| AH-09 | Inspect BROWSE and Now Playing while a title is hidden | Original metadata remains available in those features |
| AH-10 | Restart; then build without the module and restart | First: titles visible. Second: native notes and titles, no eye touch interception |
| AH-11 | Repeat on firmware 1.20 | Same results; record version and core hash separately |

Capture before/after screens and logs for each firmware, including the built core
hash. Record toggle latency and any audio underruns during AH-08; do not infer
performance from the host gesture tests.

<a id="doc-title-visibility--second-trial-input-diagnosis"></a>
##### Second-trial input diagnosis

A HEADER_LAYER text draw cleared `overlay_seen_us`, even while performance
controls remained visible. This disabled both eye and custom-tab interception
until another ZOOM/GRID draw. The screen gate now reads `BrowseUiIf` display
state, as native touch dispatch does: `UiNotifyDispInfoUpdate` at `0x000ff58c`
publishes player states 1/2, BROWSE 3, and other distinct states for other views.
Native object identity and show checks remain required for each eye.
`TouchStatus` carries pixel coordinates; the previous speculative 4096-unit
conversion also corrupted lower-screen touches and has been removed.
Host tests now execute the complete touch hook for press/release, browser
exclusion and a return to the second player view, without any fresh tab draw.
The next hardware trace records eye hitbox origins and hidden-state transitions.

A second input defect omitted the native window translation from hitboxes.
`NS_GlyphRender_InitialOffsetPos` excludes type 0x14 windows, while its ABS
variant includes them. Normal counter windows start at (10,584)/(650,584), with
a (0,-4) child translation. The adapter now adds the live ancestor window's
signed position for touch coordinates only; drawing remains window-local.
Tests use these independent native property values, rather than an assumed
render origin of (0,580). A missing window disables touch on that eye.

<a id="doc-title-visibility--ownership-module-api-17"></a>
##### Ownership (module API 17)

Asshole Mode owns hidden-deck state, the toggle callback, eye coverage and themed
RGB565 variants. Core accepts an exclusive `rx3_title_provider` and handles only
native object identity, touch capture and invalidation. Bitmap registration copies
pixels into Core-owned native records; the module withdraws its title provider
before releasing image registrations. These descriptors remain resident for the
process lifetime. This is not a hot-unload protocol.

---

<a id="doc-transposition"></a>
### Transposition reference and compatibility

<!-- source: docs/transposition.md | sha256: 7c032435461e509b307a5f8379f896bfacb8bd3332d61e0937ede2e3684fe171 -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

The Harmonic mixing category contains independent Key Shift and Key Match modules. Key Sync requires both and owns the automatic mode and range settings. Key Shift alone exposes only the manual stepper. BROWSE suggestions and KEY SYNC share the optional Key Match rule mask. New desktop preferences use compatible mode, a one-semitone allowance and no extensions. Saved preferences are retained. Old runtime packages without settings keep their historical defaults; newly generated packages always contain explicit values.

<a id="doc-transposition--reference-contract"></a>
##### Reference contract

The BROWSE service publishes a copied local MASTER index, effective Camelot key and 24-bit native compatibility set. KEY SYNC consumes this contract; it does not infer that the other deck is MASTER. The reference deck has an inert MASTER status. No local MASTER, unknown reference data or a stale source key produces no sync action.

The native set is captured when BROWSE processes its track list. If BROWSE has not supplied a usable set yet, KEY SYNC waits for that data. A load notification clears the corresponding published key and native snapshot. A reference-deck change rejects the previous deck's snapshot. A published source key inconsistent with the snapshot also rejects it. The service carries source keys separately from shifts and rotates the accepted set with a transposed MASTER. The native Traffic Light display flag remains in control of BROWSE highlighting. Native green classifications remain authoritative; the module no longer adds presumed classic matches independently.

The stored music-ID device byte identifies a storage source, not a deck. Both decks may load from the same USB source. MASTER association uses the explicit native per-deck flag and never derives a deck number from that byte. Network or ambiguous MASTER states are unavailable to KEY SYNC.

<a id="doc-transposition--static-firmware-evidence"></a>
##### Static firmware evidence

The inspected 1.19 rbp SHA-256 is `60bcbd8876116bf09f0d8f747f95d7c7d3081ebd39d6fe14d56005a22f7f3b09`. `GetTrafficTargetTrackInfo` at `0x001c7da8` calls `CmnFunc_CmnInfo_GetSyncMasterPlayerNo`, checks local MASTER flags via `CmnFunc_CmnInfo_IsMasterON` at `0x0018579c`, and then obtains the playing music ID. Its native fallback can consult the on-air player; the modification requires an unambiguous local MASTER for sync offers.

`UpdateTrafficLightKeySet.part.0` at `0x001c7e9c` populates the four key IDs at BROWSE context offsets `0x10b08` through `0x10b14`. `GetTrafficLightOnFlg` compares candidates against those values. The shared service copies those actual values instead of substituting a generic wheel formula. IDs are one-based, interleaved A/B; the public contract is zero-based. The MASTER accessor's first eight instruction bytes are checked before use on ARM.

This is static 1.19 evidence and host-test coverage, not hardware validation or proof of other firmware versions. On an unsupported MASTER accessor, the service returns an unavailable reference.

<a id="doc-transposition--preview-and-checks"></a>
##### Preview and checks

The preview reads no USB drive, player or music library. Its fictional MASTER is 8A, with a declared native example set of 7A, 8A, 8B and 9A. All candidate colours and KEY SYNC results are calculated by the Python service using the current controls. The pure C solver and Python implementation are compared across 82,944 combinations of source key, reference key, selected rules, mode, range and existing shift. Native-set tests include an observed set that differs from classic wheel adjacency, MASTER changes, source-device independence, pitch changes and load invalidation. WebKit verification covers both languages at 880x560.

Not yet run on hardware. Hardware acceptance must check changing MASTER while KEY is open, loading a new MASTER track, transposing MASTER before reopening BROWSE, source-drive changes, native Traffic Light settings and the absence of an actionable KEY SYNC on MASTER.

<a id="doc-transposition--deck-key-metadata"></a>
##### Deck key metadata

Key Shift observes `UiBrowseComm_SetPlayTitleLine` and `UiBrowseComm_ConvInfoListToDeckList` after the native browse communication task updates its deck cache. `getUiPlayKeyLinePointer` uses deck indices 0 and 1; category 15 contains the UTF-16 key. The observer performs no database request or drawing. An empty or invalid key clears the previous value. Decoder loading still resets pitch, but does not erase newer metadata. Text observation remains a fallback if the guarded native hooks cannot be installed.

The machine emulator reproduced a missing DECK 2 key with DECK 1 empty: the native panel showed 1A and Key Shift showed KEY --. Observing the native deck cache made Key Shift show 1A for that same load. Hardware validation remains pending.

MASTER changes also use the latest published deck key immediately. If the native Browse compatibility snapshot still belongs to the previous MASTER or track, Key Sync temporarily uses the classic Camelot set (same key, relative major/minor, adjacent wheel numbers). A matching native snapshot takes precedence once available, preserving its exact key set. No MASTER or an unknown key yields no automatic action.

---

<a id="doc-troubleshooting"></a>
### Troubleshooting

<!-- source: docs/troubleshooting.md | sha256: 4892e3b533c22d5a01170c0da10d1e8e305d6f8043cb9147ffa08cc6aeec1b05 -->

<!-- SPDX-License-Identifier: MPL-2.0 -->

Symptoms, in the order you are likely to hit them. Each heading is linkable.

<a id="doc-troubleshooting--macos-says-the-application-is-damaged"></a>
##### macOS says the application is damaged

It is unsigned, and macOS refuses unsigned applications that carry a download marker. Clear the marker on the unpacked `.app`, wherever you actually put it, not on the `.zip`:

```sh
xattr -rc "/path/to/XDJ-RX3 Toolkit.app"
```

Control-click then Open used to be enough. Recent macOS releases no longer offer that path for an unsigned application.

On Windows the equivalent is a SmartScreen dialog: choose **More info**, then **Run anyway**.

<a id="doc-troubleshooting--nothing-happens-when-i-insert-the-drive"></a>
##### Nothing happens when I insert the drive

Check three things, in this order:

1. the file is named exactly `autoexec.bin`, lower case, no second extension;
2. it sits at the root of the drive, not in a folder;
3. it was built for a firmware the RX3 is actually running, which is `1.19` or `1.20`.

If the RX3 does not see the drive at all, it is formatted as something other than FAT32 or exFAT, or it was unplugged without ejecting. It is always one of those two.

A key file that is empty, or that holds something other than the key on its first line, produces an `autoexec.bin` the RX3 decrypts to garbage and silently ignores. There is no error on the device.

<a id="doc-troubleshooting--the-drive-disappears-after-the-patch-is-applied"></a>
##### The drive disappears after the patch is applied

Applying a module restarts the player. The restart misses the announcement the drive made when you inserted it. The runtime now waits for the replacement player's USB channels, then sends it the mounted drive's `connect` and `mount` messages directly. In the log this reads `announced mounted /dev/... to rbp pid ... via USB1` (or `USB2`). It does not replay the block-device hotplug event, which could rerun `autoexec.bin`.

The player may still need time to read the drive database after this announcement. Keep the drive inserted while it loads; do not unplug and reinsert it to force detection. Timing and UI behavior still need RX3 hardware validation.

<a id="doc-troubleshooting--the-interface-does-not-come-back"></a>
##### The interface does not come back

Remove the drive and power cycle. The RX3 returns to stock, because nothing was written to it.

To find out why, rebuild with the **Session logging** module ticked, reproduce, and read `RX3_RUNTIME/session.txt` from the drive on your computer. See the two sections below.

<a id="doc-troubleshooting--there-is-no-session-log-on-the-drive"></a>
##### There is no session log on the drive

Expected. Session logging is a module of its own and is not selected by default, so an ordinary build writes nothing to the drive at all.

Tick **Session logging** in the builder to get `RX3_RUNTIME/session.txt` and the player's output. **Eject the drive from the RX3 when that build is in use, never pull it out**: the player keeps the log file open for as long as it plays, so pulling the drive out mid-write can corrupt it. The open handle also stops the kernel releasing the device, which is why a drive pulled out while logging comes back under a different name.

<a id="doc-troubleshooting--the-session-log-says-stop-or-failed"></a>
##### The session log says STOP or FAILED

Delete `autoexec.bin` from the drive before using the RX3 again.

`STOP:` means a precondition failed and nothing was modified. The most common one is `STOP: unsupported rbp SHA-1`, which means the player binary is not one the runtime recognises. That is a firmware other than `1.19` or `1.20`, or a build of one of them this project has not seen.

A drive that was removed and pushed back in without a power cycle used to report that same `STOP`, because the player binary carried the writes of the first run and no longer matched the state it started from. It no longer does: guarded patches are put back to their stock values before the comparison, so an already-patched session is recognised and the log says `accepted rbp SHA-1: … (already patched; normalises to …)`.

`FAILED:` means something went wrong during modification and the previous state was restored automatically. The exception is a player that exits straight after being relaunched: there the previous state is what just died, so the stock binary is put back instead and this runtime's shared objects are taken out of the preload. The log then says `stock rbp restarted`.

Either way, attach the full `session.txt` when reporting the problem.

<a id="doc-troubleshooting--slip-loop-pads-7-and-8-still-create-loops"></a>
##### Slip Loop pads 7 and 8 still create loops

No valid `.rx3stem` matched the loaded track. This is the intended fallback, not a failure: an unprepared track behaves exactly like stock.

<a id="doc-troubleshooting--a-prepared-track-has-no-stem-controls"></a>
##### A prepared track has no stem controls

The stem and the audio file must share exactly the same name before the extension. `Artist - Title.mp3` needs `Artist - Title.rx3stem`. A trailing space, a different dash character, or a renamed audio file all break the match.

Compare the names on the drive, not the names in your library. Rekordbox cuts a filename to 44 characters when it exports the track, so a long title reaches the drive shortened while the library keeps it whole. The app applies the same cut. A stem generated before it did needs the same treatment: keep the first 44 characters of the name and the `.rx3stem` extension.

Check also that `RX3_STEMS` sits at the root of the drive and not inside another folder.

<a id="doc-troubleshooting--the-instrumental-still-has-the-vocal-in-it"></a>
##### The instrumental still has the vocal in it

The vocal pad works, the instrumental pad does not, and the vocal is as loud as ever rather than merely leaking. The stem and the audio the deck plays are on different timelines.

You used an older version: please generate the track again with a current version. An MP3 or AAC file declares samples its encoder prepended, which FFmpeg drops but the deck plays; a stem built without accounting for them sits about 25 ms early, which is far more than subtraction tolerates. Releases before this handling shipped are affected only for lossy sources that declare padding, which is why some of your tracks work.

If the run reports that the padding could not be measured, the source is one the pipeline could not line up. Convert it to WAV or FLAC and generate it again.

<a id="doc-troubleshooting--the-app-reports-a-missing-runtime"></a>
##### The app reports a missing runtime

Use **Install** in Advanced options, Runtime tab. Or point `RX3_SEPARATOR` and `RX3_FFMPEG` at your own installation of audio-separator and FFmpeg, which the application prefers over its own copy.

<a id="doc-troubleshooting--runtime-installation-refuses-to-start"></a>
##### Runtime installation refuses to start

No Python between 3.10 and 3.13 was found on your computer. Install one from [python.org](https://www.python.org/downloads/) and retry. The newest supported one installed is the one used.

<a id="doc-troubleshooting--every-track-fails"></a>
##### Every track fails

If separation itself completes and then every track fails, the managed environment is incomplete. Use **Install** again in Advanced options, Runtime tab. The same button completes an environment that already exists, which is the fix for a runtime installed by an older version.

If the failure mentions `No such file or directory: 'ffmpeg'`, the runtime is from a build that did not yet bundle FFmpeg. Reinstall the runtime, or install FFmpeg so it sits on `PATH`.

<a id="doc-troubleshooting--separation-fails-partway-with-an-ffmpeg-filter-error"></a>
##### Separation fails partway with an FFmpeg filter error

The FFmpeg on your `PATH` is missing a filter the pipeline needs. Install the separation runtime, which brings a complete copy the application prefers, and the runtime summary will name the filter that was missing.

If you set `RX3_FFMPEG` yourself, that override is used as given and a gap in it is reported rather than worked around. Point it at a complete build or unset it.

<a id="doc-troubleshooting--the-gpu-is-idle-during-separation"></a>
##### The GPU is idle during separation

The runtime was installed for a different accelerator. The Runtime tab says so. Select **Reinstall**, which rebuilds the environment rather than completing it, because a CPU-only PyTorch cannot be accelerated afterwards.

The job log reports a fallback to the CPU whenever one happens.

On an Intel Mac this is expected and cannot be changed: audio-separator gates its Metal path on an ARM processor.

<a id="doc-troubleshooting--the-waveform-still-shows-the-full-track"></a>
##### The waveform still shows the full track

Expected. The waveform is precomputed from the file and is not rebuilt from the modified audio stream, so it does not follow the pad state.

<a id="doc-troubleshooting--stems-or-leds-are-wrong-across-two-decks"></a>
##### Stems or LEDs are wrong across two decks

Reproduce with one prepared track per deck, then attach both `RX3_RUNTIME/session.txt` and `/tmp/rx3-stems.log` from the device. The second file needs the Telnet module to be reachable.

---

<a id="doc-ux-audit-dj"></a>
### UX audit "made by a DJ" — XDJ-RX3 Toolkit

<!-- source: docs/ux-audit-dj.md | sha256: ece19660bda25e36dfd9e992ba5e0f18dfe5f6cc1f04cc53d428d6c2e7f67add -->


<a id="doc-ux-audit-dj--top-10-des-quick-wins"></a>
##### Top 10 quick wins

The formulations below are proposals, not changes made. The detailed findings give the current texts EN/FR, the evidence and the reading of the persona.

| # | Change directly applicable | Priority · effort | Evidence and detail |
|---|---|---|---|
| 1 | Make current hidden introductions visible; place the useful sentence under the title, without banner. | P1 · S | `app/ui/web/app.css:88` · O1 |
| 2 | Replace "Create mod" / "Build the mod" with **"Prepare USB drive" / "Prepare USB drive"**, only when the destination is a USB drive; use "Prepare Files" / "Prepare Files" for another folder. | P1 · S | `app/ui/web/index.html:78`, `app/localization/fr.json:54` · M1 |
| 3 | Show **" USB Drive" / "USB Drive" at the bottom of the sidebar, with the full path accessible. | P1 · S | `app/ui/web/app.js:198` · O2 |
| 4 | Replace the destination "Browse" with **"Choose Destination" / "Choose Destination"**; explain selecting the key itself. | P1 · S | `app/ui/web/index.html:115`, `app/ui/web/index.html:311` · O3 |
| 5 | Replace "Separation engine and cache" / "Separation engine and cache" with **"Installation and storage of items" / "Stem setup and storage"**. | P1 · S | `app/ui/web/index.html:364`, `app/ui/web/stems.js:54` · S1 |
| 6 | Give direct access **"Listen to Stems" / "Listen to Stems"** from Preparation to the existing listening panel. | P1 · S | `app/ui/web/index.html:348`, `app/ui/web/index.html:362` · S5 |
| 7 | Replace "To" / "At destination" with **"Registered Stems" / "Saved items"**, and "Imported" / "Imported" with **"Selected Files" / "Selected files"**. | P2 · S | `app/localization/fr.json:347`, `app/ui/web/stems-listen.js:127` · S6 |
| 8 | Replace active bank asterisk with **" — used on the RX3 player" / " — used on the deck"** in the selector. | P1 · S | `app/ui/web/samples.js:524` · A3 |
| 9 | After recovery of the encryption key, display **« Ready encryption key. You can prepare your USB drive." / "Encryption key ready. You can now prepare your USB drive.** with an explicit button to Modules. | P1 · S | `app/ui/web/app.js:655`, `app/ui/web/app.js:752` · K7 |
| 10 | In the USB control, replace "Remove mod" / "Remove mod" with **"Remove modules from this USB drive" / "Remove modules from this USB drive"**, and add the shutdown/remove procedure into a foldable help. | P1 · S | `app/ui/web/index.html:65`, `README.md:308` · R1 |

<a id="doc-ux-audit-dj--les-3-changements-structurants"></a>
##### The 3 structural changes

1. **Make the USB flash drive the visible context of the work.** Keep Modules as the initial screen and the five destinations. In Modules, present, in this order: destination, initial preparation if necessary, choice of modules, writing action. The sidebar remains the USB inspection point. Each screen displays its actual destination, even if it differs from other screens. **P1 · M** — O2–O6, M1, K1–K8; `app/ui/web/app.js:192`, `app/ui/web/stems.js:470`.
2. **Organize Stems around "prepare, listen, use on the RX3 player".** Make the necessary installation immediately accessible; prefer rekordbox export of the key; present playlist, items to prepare, quality, duration, destination; then give access to listening and gestures on the RX3 player. Manual import and storage remain accessible, with the same operations. **P1 · M** — S1–S10; `app/ui/web/index.html:290`, `app/ui/web/index.html:348`.
3. **Use the same benchmarks of choice up to the result.** Key name, bank name, role of items, colors and stable gestures; distinguish selection, recording on USB and activation on RX3 player. A result must say what is ready and what action follows. Keep material wording and legal content. **P1 · M** — A3–A4, L2, K7, T1–T3, R1; `app/ui/web/app.js:741`, `app/ui/web/samples.js:491`.

<a id="doc-ux-audit-dj--cadre-et-niveau-de-preuve"></a>
##### Framework and level of evidence

Static checkout `/Users/fbrille/ Dev/rx3/rx3-toolbox`, 27 September 2026, HEAD `256596c`, with many pre-existing modifications. The lines quoted correspond to the work files read, not necessarily the commit. No code, setting, user file or device has been changed; Only this report is written. No network, download, install, commit or write test.

Prior reading of `PRODUCT.md`, `.claude/STYLE.md` and `README.md`. Inspection of all HTML/CSS/JS files named in the application, `rx3-mock.js`, the four SVG Key Match and both catalogues. The texts of the modules also come from `mod/categories.json` and manifests: `app/localization/  init  .py:24` add them to the catalog. A few targeted readings from message producers are only used to identify actually presentable texts; no recommendation to modify services, bridge or audio.

`make app` was not launched. Static analysis is enough here and avoids the effects of application on files; even the USB inspection can perform a writing test (`app/services/drive.py:73`). No old visual validation results are repeated as current evidence. Sizes, colours, orders and masking rules are **checked in code**; The DJ's feeling and the risk of loss of reference are ** persona** inferences. No overflow, perceived contrast or behaviour on real material is declared tested.

**Single personna:** Professional DJ owner of an XDJ-RX3, accustomed to playlists, rekordbox export and RX3 player controls; not comfortable with files and software installation. He must not mentally translate a computer operation into a musical result.

**Priorities:** P1 = lost or blocked; P2 = friction or jargon; P3 = finish. ** Relative presentation effects:** S = text, style or local displacement; M = reorganization of several states/components; L = transverse site. These efforts do not include any changes in service. When a problem cannot be solved by presentation, the limit is explicit.

The proposals retain the five destinations, existing operations, local operation and material wording (`PRODUCT.md:7`). No new main navigation screen, framework, build or network dependency. No banners or disclaimer added. The aid is included in the relevant control or in a leaflet. New texts are reported **« absent → »** ; the values between brackets come from the already available state or from a presentation format, without new service contract.

<a id="doc-ux-audit-dj--parcours-reconstitu--ce-que-le-dj-rencontre"></a>
##### Reconstituted course: what the DJ meets

| Step | What happens in the current interface | What the DJ understands and does; probable rupture |
|---|---|---|
| First opening | Modules is initial; browser language and default system theme. Initialization, then automatic conditions if no encryption key or task displayed. `app/ui/web/index.html:72`, `app/ui/web/i18n.js:49`, `app/ui/web/components.js:4`, `app/ui/web/app.js:759`. | He is waiting to choose his USB drive; It must first include a download and accept conditions. K1–K3. |
| Branchement USB | No connection detection shown in the frontend: the lower control opens the inspection, then a folder selector. `app/ui/web/app.js:800`. | Physical connection is not enough; select the right location. O2-O3. |
| selected USB | Report, initial destination assignment Modules; opening export in Stems if present and no open library; initial assignment of destination. `app/ui/web/app.js:192`, `app/ui/web/stems.js:470`. | He thinks he has defined a common key; a subsequent change may leave previous destinations. O4. |
| Modules | Categories, switches, harmonic subsettings, summary, encryption key and destination. `app/ui/web/app.js:317`, `app/ui/web/app.js:500`, `app/ui/web/index.html:87`. | He chooses DJ uses, but "activated" and "Create mod" do not say what is already on the key. M1–M5. |
| Stems preparation | Library, playlist, destination, messages per piece, waveforms, parts to separate, quality, installation/stocking. `app/ui/web/index.html:290`. | It must find the prerequisites under the settings; XML rivals known USB export. S1–S4. |
| Listen to Stems | Panel under "Import and Listen", after manual import; Saved source or selected files; Original and three possible roles. `app/ui/web/index.html:348`, `app/ui/web/stems-listen.js121`. | He may think he has to import his results to listen to them; the meaning of the active buttons is not explained. S5–S7. |
| Stems commands on RX3 | Guide in the module, Pads/Tactile screen modes, animated sequences. `app/ui/web/app.js:453`, `app/ui/web/rx3-mock.js:282`. | He's looking at how to play in Stems, while the help is in Modules. S10. |
| Logo | Choice of image, preview, framing, preview theme and adaptation of greys; possible logo activation; back Modules to write. `app/ui/web/logo.js:117`, `app/ui/web/index.html:273`. | The preview seems finished, but the image is not yet on the key. L1–L3. |
| Samples | Key required; bank, grid, inspector, test, volume and SHIFT; separate recording and activation. `app/ui/web/samples.js:491`, `app/ui/web/samples.js:574`. | He can play pads, but not distinguish registered bank, bank used and module present on USB. A1–A6. |
| Settings | Appearance of the app, language, short About. `app/ui/web/index.html:383`. | He does not know immediately whether "Clear" changes the app, RX3 or preview. T1. |
| Download key | Conditions → scrolling → acceptance → overall task → result as a path. Accessible on opening, by the dedicated button, or by creation without key. `app/ui/web/app.js:621`, `app/ui/web/app.js:677`, `app/ui/web/app.js:772`. | He waits to be able to prepare his USB drive; The exit does not clearly indicate where to resume. K1–K8. |
| Return to original state | Removing files from USB inspection; procedure for extinguishing/withdrawal/restarting in the README, absent from this check. `app/ui/web/app.js:809`, `README.md:308`. | It confuses deletion of encryption key, deletion of USB files and shutdown of changes in memory. A1. |

<a id="doc-ux-audit-dj--valeurs-par-dfaut-et-points--conserver"></a>
###### Default values and points to keep

| Check item | DJ Reading and Proposed Decision |
|---|---|
| Browser language, system theme; stored preferences. `app/ui/web/i18n.js:43`, `app/ui/web/components.js:4`. | Keep. The app should not impose a dark theme because it is DJing. Correct only the scope wording, T1. |
| Selection rebuilt from manifest `default` values when the app opens. `app/ui/web/app.js:586`. Beat Jump, Key Shift, Key Sync and Stems default to selected; Key Sync requires Key Match. | Keep decisions produced; display "selected for next preparation", M1–M2. Do not present the selection as a USB statement. |
| KEY SYNC harmonic, ±1 half-tone; additional key match rules at zero; third column BPM. `app/ui/web/app.js:28`. | Keep; explain the scope of the rules, M2. |
| Stems voice + instrumental, waveforms checked unless previously preferred; default quality High quality, auto acceleration. `app/ui/web/stems.js:21`, `app/ui/web/stems.js:407`, `app/stems/separation.py:476`. | Keep choices; make the cost readable in time, S3–S4. No new performance promises. |
| Bank new `bank1`, mode Once, SHIFT unchecked; volume/level values from limits. `app/ui/web/samples.js:33`, `app/ui/web/samples.js:606`, `app/ui/web/samples.js:709`. | Maintaining limits and behaviour; better name the bank and clarify activation, A3–A6. Eight visible locations do not mean eight simultaneous readings: the voice limit comes from `limits.maxVoices`, `app/ui/web/samples.js:389`. |
| Logo adjusted in its area, centered, dark glimpse, inversion of activated greys; local image restoration. `app/ui/web/logo.js:50`, `app/ui/web/logo.js:381`. | Keep; distinguish preview, local preference and presence on USB, L2–L3. |
| Confirmation before withdrawal, deletion of bank, deletion of key and abandonment of changes; initial focus on Cancel. `app/ui/web/components.js:32`, `app/ui/web/samples.js:714`. | Keep it: the DJ keeps its sounds and does not trigger a deletion while trying to move forward. Specify the objects concerned. |
| USB export usable without XML, samples already on USB listenable via `audioPath`, existing colors and preview. `app/ui/web/stems.js:228`, `app/ui/web/samples.js:51`, `app/ui/web/samples.js:452`. | Keep. Do not report the unused legacy `samples.hearKept` string or already fixed functions as current defects. |

<a id="doc-ux-audit-dj--constats--ouverture-et-cl-usb"></a>
##### Findings — USB flash drive and opening

<a id="doc-ux-audit-dj--o1--les-phrases-qui-donnent-le-mode-demploi-sont-invisibles"></a>
###### O1 — The sentences giving instructions for use are invisible

- **Where:** all screens; `app/ui/web/app.css:88`, `app/ui/web/index.html:76`, `app/ui/web/index.html:131`, `app/ui/web/index.html:207`, `app/ui/web/index.html:282`.
- **What the DJ sees:** a title and action. The sentences on the duration of the samples, the preparation before the set, the integration of the logo and the dependencies exist but all the `.lede` header are hidden.
- **Where he picks up:** the title "Stems" tells him neither that the files must be prepared before the set, nor what makes them available on the RX3 player.
- **Proposal:** display a sentence under each title, with header height adapted to return to line. Keep the current Stems sentence. For Modules, give the desired result; move the explanation of dependencies next to related choices.
- **EN** (`app/localization/en.json:46`, `modules.lede`): "The necessary modules are automatically activated. → "Select the functions to add to your XDJ-RX3, then prepare your USB drive. "
- **EN** (`app/localization/en.json:46`, `modules.lede`) : « Required modules turn on automatically. » → « Choose the features to add to your XDJ-RX3, then prepare your USB drive. ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--o2--la-cl-usb-perd-son-identit-dans-la-barre-latrale"></a>
###### O2 — The USB drive loses its identity in the sidebar

- **Where:** lower USB control; `app/ui/web/index.html:42`, `app/ui/web/app.js198`, `app/ui/web/app.css:83`, `app/ui/web/app.css:288`.
- **What the DJ sees:** "Selected USB Flash Drive". The path is only in the overflight; no visible name or active mark when inspection is opened (`app/ui/web/app.js:136`).
- **Where he picks up:** with his set key and emergency key, he no longer knows which one he prepares without leaving his screen.
- **Proposed:** keep this control below; 16 px USB icon, name on the first line, "View Content" / "View content" on the second, background selected during inspection. Name derived from the existing path, full path displayed on the keyboard. Do not display "ready" on the only proof of a selection.
- **EN** (`app/localization/en.json:421`, `ui.driveSelected`): "Selected USB flash drive" → " USB flash drive · {name}".
- **EN** (`app/localization/en.json:421`, `ui.driveSelected`) : « USB drive selected » → « USB drive · {name} ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--o3---parcourir--ne-dit-pas-o-slectionner-la-cl"></a>
###### O3 — "Browse" does not indicate where to select the key

- **Where:** Modules and Stems; `app/ui/web/index.html:111`, `app/ui/web/index.html:308`, `app/ui/web/app.js:800`, `app/ui/web/app.js:833`, `app/ui/web/stems.js:443`.
- **What the DJ sees:** "Destination", "none", then "Browse", opening a folder selector. The same word is also used to choose the encryption file.
- **Where he picks up:** he can select `Contents`, `PIONEER`, a playlist or a Mac folder: he does not know "root".
- **Proposal:** contextualized wording of each button, without changing globally `common.browse`. Above the selector, persistent help **absent → FR "To prepare a USB stick, select its name, without opening a folder inside. / EN « To prepare a USB drive, select the drive itself without opening a folder inside it. **. Keep the choice of a file for existing uses.
- **EN** (`app/localization/en.json:53`, `modules.output`): " Destination" → "USB drive or destination folder".
- **EN** (`app/localization/en.json:53`, `modules.output`) : « Write to » → « Destination USB drive or folder ».
- **FR** (`app/localization/en.json:11`, `common.browse`) : « Browse » → « Choose destination ».
- **EN** (`app/localization/en.json:11`, `common.browse`) : « Browse » → « Choose destination ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--o4--changer-de-cl-nactualise-pas-forcment-les-destinations"></a>
###### O4 — Change of key does not necessarily update destinations

- **Where:** shared context and Stems; `app/ui/web/app.js:206`, `app/ui/web/app.js:671`, `app/ui/web/stems.js:470`, `app/ui/web/stems.js:218`.
- **What the DJ sees:** a key selected from the sidebar; Modules and Stems keep their destinations empty. The Stems library already opened also remains the previous one.
- **Where he picks up:** he selects his key B and assumes that his next preparations will go on, while the destination can stay A. Done in frontend; No actual writing tested.
- **Proposed:** do not overwrite your choices. Display close to each action its ** effective destination**, with its name first, path in detail. When it differs from the USB context: local help **absent → EN « Destination: {destination}. The selected key in the sidebar is {drive}. Destination: {destination}. The USB drive selected in the sidebar is {drive}.** and existing button of choice. Distinguish also **"Music read since" / "Music read from"** from **"Stems recorded in" / "Stems saved to"**.
- **Priority / effort: P1 · M.**


<a id="doc-ux-audit-dj--o5--louverture-parle-de-connexion--une-application-locale"></a>
###### O5 — The opening talks about connecting to a local application

- **Where:** initialization; `app/ui/web/index.html:426`, `app/ui/web/app.js:897`, `app/ui/web/app.js:921`, `app/ui/web/i18n.js:23`.
- **What the DJ sees:** "Connect to Toolkit...", then eventually "Reconnect". Before loading the catalogue, HTML is English; an early error can even display a translation ID.
- **Where it picks up:** looking for an RX3 cable or Internet connection, while the local interface starts. The failure of an image loading also uses `ui.unavailable` (`app/ui/web/logo.js:298`) and accuses all application.
- **Proposal:** place the boot in a stable initial state of content; no current floating load strip. Provide local FR/EN backup text and keep an actionable error. For the image: **absent → FR "Cannot display this image. Choose another image. / EN « Cannot display this image. Choose another image. "**.
- **EN** (`app/localization/en.json:381`, `ui.connecting`) : « Connection to the Toolkit... → "Opening of the app...".
- **EN** (`app/localization/en.json:381`, `ui.connecting`) : « Connecting to the toolkit... » → « Opening the app… ».
- **EN** (`app/localization/en.json:383`, `ui.retry`): "Reconnect" → "Retry".
- **EN** (`app/localization/en.json:383`, `ui.retry`) : « Reconnect » → « Try again ».
- **EN** (`app/localization/en.json:382`, `ui.unavailable`): "The Toolkit does not answer. Click Reconnect. → "The application could not complete the loading. Click Retry."
- **EN** (`app/localization/en.json:382`, `ui.unavailable`) : « The Toolkit is not responding. Click Reconnect. » → « The app could not finish loading. Click Try again. ».
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--o6--le-rapport-usb-mlange-fichiers-prsents-et-dernier-passage-sur-la-platine"></a>
###### O6 — The USB report mixes files present and last passage on the RX3 player

- **Where:** USB inspection; `app/ui/web/app.js156`, `app/ui/web/app.js162`, `app/ui/web/app.js168`, `app/ui/bridge.py:344`.
- **What the DJ sees:** "Mod", "Firmware", plug-in identifiers as they are, then loaded or deactivated at the last boot. The music account depends on `music.present`, without a dedicated presentation of `music.unreadable`, yet available.
- **Where it picks up:** it can read historical information as a control of the current RX3 player; an illegible export presented with meters does not tell him to do it again in rekordbox. A list such as `beatjump-no-quantize` does not match the names he has chosen.
- **Proposal:** order: music and playlists → modules present on this key → bank used → last recorded start details. Use localized names known for modules, keep identifying only in detail or if unknown. If export is unreadable, display **absent → EN « L Reexport your playlists from rekordbox, then update the key. » / EN « The rekordbox export on this USB drive cannot be read. Export your playlists again from rekordbox, then refresh the drive. * ; keep error details. If absent, keep the existing message and indicate the same export gesture, without empty false library. Keep the read-only state visible with its action, vocabulary T5.
- **EN** (`app/localization/en.json:25`, `drive.mod`) : "mod" → "modules on this USB drive".
- **EN** (`app/localization/en.json:25`, `drive.mod`) : « Mod » → « Modules on this USB drive ».
- **FR** (`app/localization/en.json:30`, `drive.lastRun`): "Loaded at the last start" → "Loaded at the last recorded start".
- **EN** (`app/localization/en.json:30`, `drive.lastRun`) : « Loaded at last startup » → « Loaded at the last recorded startup ».
- **FR** (`app/localization/en.json:31`, `drive.refused`): "Deactivated at last start" → "Not loaded at last recorded start".
- **EN** (`app/localization/en.json:31`, `drive.refused`) : « Disabled at last startup » → « Not loaded at the last recorded startup ».
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--constats--modules"></a>
##### Constats — Modules

<a id="doc-ux-audit-dj--m1--les-interrupteurs-ressemblent--une-activation-immdiate"></a>
###### M1 — Switches look like immediate activation

- **Where:** list, summary and main action; `app/ui/web/app.js:317`, `app/ui/web/app.js:557`, `app/ui/web/app.js:677`, `app/ui/web/index.html:78`.
- **What the DJ sees:** blue switches, "activated modules", then "Create mod". The changes are written only in preparation action.
- **Where he picks up:** he closes the app thinking he has activated the functions; or he doesn't dare "create a mod" on his RX3 player.
- **Proposal:** keep switches, but title summary **"To save to your USB drive" / "To save to your USB drive"** when this destination is chosen. Show destination and next action to the fixed button. Without destination, give a visible button of choice and its pattern; do not leave the only diagnosis at the bottom of the summary. Success: contextualized result, not just a number of bytes.
- **FR** (`app/localization/en.json:54`, `modules.build`): "Create mod" → "Prepare USB flash drive".
- **EN** (`app/localization/en.json:54`, `modules.build`) : « Build the mod » → « Prepare USB drive ».
- **EN** (`app/localization/en.json:360`, `modules.selectedCount`): one: "{count} module activated"; other: "{count} modules enabled" → one: "{count} module selected"; other: "{count} modules selected".
- **EN** (`app/localization/en.json:360`, `modules.selectedCount`) : one : « {count} module on » ; other : « {count} modules on » → one : « {count} module selected » ; other : « {count} modules selected ».
- **FR** (`app/localization/en.json:56`, `modules.build`): "{bytes} written in {path}" → "Preparation completed in {path}. "
- **EN** (`app/localization/en.json:56`, `modules.built`) : « {bytes} written to {path} » → « Preparation completed in {path}. ».
- **Variant folder:** "Prepare files" / "Prepare files". Do not say "ready USB drive" if only any destination is known. The number of bytes remains in the result details.
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--m2--le-mixage-harmonique-demande-de-lire-un-arbre-de-dpendances"></a>
###### M2 — Harmonic mixing requires reading a tree of dependencies

- **Where:** Key Shift/Key Match/Key Sync; `app/ui/web/app.js:331`, `app/ui/web/app.js:364`, `app/ui/web/app.js:412`, `mod/modules/key-sync/manifest.json:20`, `mod/modules/key-match/manifest.json:39`, `mod/modules/core/api/rx3 harmony.h:33` (Camelot values only).
- **What the DJ sees:** "Required by", "Requires", several sub-sets, a green box disabled and +2/+7/+4 rules. Key Match can be selected by Key Sync without additional rule checked.
- **Where he picks up:** he doesn't know if he activated a transposition, an indication in BROWSE or both. "Adapting the tone" does not say to which reference.
- **Proposal:** show one function sentence per module; Subsets visible only when selected, relational details unfoldable. Keep dependencies. Specify MASTER and qualify Camelot numbers in steps; keep the names Energy Boost and existing music aid. Overview accessible by **"See in BROWSE" / "Preview in BROWSE"**, instead of "i" (`app/ui/web/app.js:254`).
- **Proposed copy:** In both localizations, say “Match the MASTER key” instead of “Match the other deck’s key”, and “Nearest compatible key” instead of naming the KEY MATCH mechanism. Label Energy Boost as “+2 Camelot” or “+7 Camelot”; these numbers are not semitones. The original French and English strings remain in the localization files cited above.
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--m3---morceau-en-cours--promet-une-utilisation-inaccessible--ce-persona"></a>
###### M3 — "In progress" promises inaccessible use to this persona

- **Where:** category Diffusion; `mod/modules/now-playing/manifest.json:8`, `mod/modules/now-playing/manifest.json:38`, `app/ui/web/app.js:485`, `mod/categories.json:55`.
- **What the DJ sees:** an attractive use for its stream, followed by instructions **opened by default**: Python 3, terminal, command, UDP, JSON, external tool.
- **Where he picks up:** he thought he would send the title to his stream software; It must now realize a computer integration.
- **Proposed:** keep the module and instructions, fold the technical guide. Put the limit of use before the choice in the description, without banner. EN « Receive the information of the songs on the computer » → « Technical configuration for your distribution software » ; FR "Receive track information on your computer" → "Technical setup for your streaming software".
- **Exact current description:** FR "Transmit titles, BPM and ON AIR states to your computer for a stream overlay, a VJ screen or your song list. The RX3 continues to play your USB drive, without rekordbox or PRO DJ LINK. "; EN « Send track titles, BPM and ON AIR status to your computer for a stream overlay, VJ display or set list. The RX3 keeps playing from your USB drive, without rekordbox or PRO DJ LINK."
- **Exact description proposed:** FR "Transmits titles and BPM to compatible distribution software, to be configured separately. Title display is not included. / EN « Sends titles and BPM to compatible streaming software, which you configure separately. Title display is not included. It replaces the description of `mod/modules/now-playing/manifest.json:8`; keep ON AIR, USB-B and PRO DJ LINK in the guide. IU alone does not make this function usable without technical skills; do not invent an integration button.
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--m4--les-contrles-internes-prennent-le-nom-de-composants"></a>
###### M4 — Internal controls take the name of components

- **Where:** Advanced and Diagnostic; `app/ui/web/app.js:540`, `mod/modules/core/manifest.json:4`, `mod/modules/decoder-sleep/manifest.json:4`, `mod/modules/telnet/manifest.json:4`, `mod/modules/logging/manifest.json:4`, `mod/modules/logging-verbose/manifest.json:4`.
- **What the DJ sees:** Core, decoder-sleep, CPU alarms, Telnet and root password. Core not selectable is nevertheless presented in the advanced controls.
- **Where he picks up:** he thinks he has to choose an indispensable piece without knowing what it's for.
- **Proposal:** keep Diagnosis folded; rename Advanced **"Included Components" / "Included Components"** if the group contains only the current automatic components. Present their inclusion as a state, not an inaccessible choice. Keep the technical explanations and all Telnet precautions.
- **Exact texts:** FR/EN "Core" → "Common components" / "Shared components"; FR "Decoder Expectation (decoder-sleep)" → " Audio recovery after a Beat Jump"; EN « Decoder wait (decoder-sleep) » → « Audio recovery after a Beat Jump ». EN « Session log » → « Troubleshooting report » ; EN « Session logging » → « Troubleshooting report ». The benefit of the decoder remains **possible**, not guaranteed; technical figures in the details.
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--m5--la-compatibilit-ne-dit-pas-comment-lire-la-version-de-sa-platine"></a>
###### M5 — Compatibility doesn't say how to read the version of its RX3 player

- **Where:** summarized Modules; `app/ui/web/index.html:90`, `app/ui/web/app.js:759`, `README.md:102`.
- **What the DJ sees:** "RX3 Compatibility" then "1.19 / 1.20". These are the versions proposed by the software, not a detection of its RX3.
- **Where he picks up:** he ignores his version or believes the RX3 player already checked by the app.
- **Proposal:** keep the current list, add a local foldable help **absent → EN "View version on RX3 player" / EN "Find the version on your deck"**. Take the README gesture: USB flash drive removed, RX3 player on, **MENU (USILITY)** hold one second, version at the bottom of the menu. Do not add a false physical detection indicator.
- **FR** (`app/localization/en.json:48`, `modules.firmware`): "RX3 compatibility" → "XDJ-RX3 compatible versions".
- **EN** (`app/localization/en.json:48`, `modules.firmware`) : « RX3 compatibility » → « Compatible XDJ-RX3 versions ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--constats--stems-prparation-et-panneau-dcoute"></a>
##### Findings — Stems, preparation and listening panel

<a id="doc-ux-audit-dj--s1--linstallation-ncessaire-se-trouve-aprs-les-rglages"></a>
###### S1 — The necessary installation is after the settings

- **Where:** Stems bottom; `app/ui/web/index.html:364`, `app/ui/web/stems.js:52`, `app/ui/web/stems.js:203`, `app/stems/provisioning.py:342`.
- **What the DJ sees:** "Prepare the items" disabled, then "Separate Engine and Cache" below. The leaflet opens automatically if necessary: it is therefore not closed, but remains after all the previous content. The summary can be plain English "Missing: audio-separator and FFmpeg. Install the separation runtime to continue. "
- **Where he picks up:** he doesn't know which installation unlocks his button or where to find it.
- **Proposal:** up the existing band before Music when not ready; keep technical settings and storage at the bottom once ready. Present a local status text and keep the raw message in detail.
- **EN** (`app/localization/en.json:405`, `ui.runtimeSettings`): "Separation engine and cache" → "Installation and storage of stems".
- **EN** (`app/localization/en.json:405`, `ui.runtimeSettings`) : « Separation engine and cache » → « Stem setup and storage ».
- **FR** (`app/localization/en.json:150`, `stems.install`): "Install the engine" → "Install the preparation tools".
- **EN** (`app/localization/en.json:148`, `stems.install`) : « Install engine » → « Install stem preparation tools ».
- **FR** (`app/localization/en.json168`, `stems.needRuntime`): "Open Separation Engine and Cache, then click Install Engine. → « Install the preparation tools to create your items on this computer. "
- **EN** (`app/localization/en.json:166`, `stems.needRuntime`) : « Open Separation engine and cache, then click Install engine. » → « Install the preparation tools to create stems on this computer. ».
- **Limit:** the absence of Python can actually block the installation (`app/stems/provisioning.py:550`). Present the need for Python and the existing action, without pretending to install automatically. FR crude identical to EN « No Python ... interpret with the venv module was found. ... » → EN « Python {versions} is necessary to install the preparation tools. Install this version of Python and try again. / EN « Python {versions} is required to install the preparation tools. Install this Python version, then try again. » Original details retained; no development of the proposed installation.
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--s2--xml-concurrence-le-parcours-usb-que-le-dj-connat"></a>
###### S2 — XML competes with the USB path the DJ knows

- **Where:** Music; `app/ui/web/index.html:290`, `app/ui/web/stems.js:228`, `app/ui/web/stems.js:434`.
- **What the DJ sees:** a help that starts with XML, two buttons of the same weight, a path and a song count.
- **Where he picks up:** he returns to rekordbox looking for a new export while his key already contains what it takes.
- **Proposal:** put "Open USB Flash Drive" first visually and in text; Place XML in a flyer **"Other music source" / "Other music source"**. Keep the operation. Show source name, number of songs and playlist before the technical path.
- **EN** (`app/localization/en.json:153`, `stems.musicHint`): "Open an XML rekordbox export or USB flash drive containing a rekordbox export. → « Open the USB drive on which you exported your rekordbox playlists. "
- **EN** (`app/localization/en.json:151`, `stems.musicHint`) : « Open a rekordbox XML export or a USB drive containing a rekordbox export. » → « Open the USB drive you exported your rekordbox playlists to. ».
- **FR** (`app/localization/en.json:155`, `stems.fromExport`): "Open an XML export" → "Choose an XML export rekordbox".
- **EN** (`app/localization/en.json:153`, `stems.fromExport`) : « Open XML export » → « Choose a rekordbox XML export ».
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--s3--les-dtails-par-morceau-repoussent-les-choix-de-prparation"></a>
###### S3 — Details per piece push back preparation choices

- **Where:** library and preparation area; `app/ui/web/stems.js:163`, `app/ui/web/stems.js:287`, `app/ui/web/index.html:313`, `app/ui/web/index.html:321`, `app/ui/web/index.html:327`.
- **What the DJ sees:** a capacity line per piece, then waveform states per piece, before the parts and quality. The lists are not confined to the frontend.
- **Where it picks up:** with a long playlist, it runs a succession of "RX3 can load them" to reach the choice of voice/battery. Risk derived from the order DOM, no real scrolling measure.
- **Proposal:** order: source/playlist → parts → quality → waveform option → duration and destination. First show the number of songs affected by a refusal or limit; fold the details of the compatible songs in **"See details of the songs" / "Show track details"**. Keep refusals and their actions visible; do not change limits or selection.
- **FR** (`app/localization/en.json:463`, `stems.waveOption`): "Calculate the waveforms of the stems" → "Preparing also the waveforms of the stems".
- **EN** (`app/localization/en.json:463`, `stems.waveOption`) : « Calculate stem waveforms » → « Also prepare stem waveforms ».
- **FR** (`app/localization/en.json:464`, `stems.waveOptionHelp`): "Waveform adapts to activated items. Extension of time to prepare the items. Waveforms can be calculated later. → "On the RX3 player, the wave shape will follow the activated items. This option adds preparation time; You can throw it later. "
- **EN** (`app/localization/en.json:464`, `stems.waveOptionHelp`) : « Show waveforms for the active stems. Adds preparation time. You can calculate the waveforms later. » → « On the deck, the waveform will follow the active stems. This adds preparation time; you can run it later. ».
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--s4--la-qualit-est-explique-avec-la-mthode-de-calcul"></a>
###### S4 — Quality is explained with the calculation method

- **Where:** Quality and speed, installation; `app/ui/web/stems.js:73`, `app/ui/web/stems.js:63`, `app/localization/en.json:458`, `app/localization/en.json:458`, `app/localization/en.json:229`, `app/localization/en.json:227`.
- **What the DJ sees:** "four staggered passes", specialized model, 17,6 kHz; in installation, CPU, Metal, CUDA, ROCm, DirectML.
- **Where he picks up:** he knows how to judge a clean voice but not choose a computational library. The name "Normal" does not tell him whether this quality fits a set.
- **Proposed:** keep presets, their values and High quality by default. Display musical compromise in first sentence, keep bandwidth restrictions and model details in a flyer. Show Automatic as a normal choice; keep accelerators in advanced settings, renamed according to the hardware.
- **EN** (`app/localization/en.json:230`, `quality.normal.name`): "normal" → "equilibrium".
- **EN** (`app/localization/en.json:228`, `quality.normal.name`) : « Normal » → « Balanced ».
- **FR** (`app/localization/en.json:458`, `quality.quality.drums`): "Voice and battery: specialized model when available, with four staggered passes. Longer treatment. → "Voice and battery: longer preparation, with more treatment. Listen to the result before your set."
- **EN** (`app/localization/en.json:458`, `quality.quality.drums`) : « Vocals and drums: fine-tuned model when available, with four shifted passes. Takes longer. » → « Vocals and drums: longer preparation with more processing. Listen to the result before your set. ».
- **FR** (`app/localization/en.json:459`, `quality.normal.drums`): "Voice and battery: two staggered passes. → "Voice and battery: compromise between preparation time and treatment. "
- **EN** (`app/localization/en.json:459`, `quality.normal.drums`) : « Vocals and drums: two shifted passes. » → « Vocals and drums: a balance between preparation time and processing. ».
- **EN** (`app/localization/en.json:460`, `quality.quick.drums`): "Voice and battery: one pass. → "Voice and battery: preparation with the least treatment. "
- **EN** (`app/localization/en.json:460`, `quality.quick.drums`) : « Vocals and drums: one pass. » → « Vocals and drums: preparation with the least processing. ».
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--s5--couter-les-stems-prpars-ressemble--une-opration-dimport"></a>
###### S5 — Listening to prepared items looks like an import operation

- **Where:** subviews and listening; `app/ui/web/index.html:317`, `app/ui/web/index.html:348`, `app/ui/web/index.html:362`, `app/ui/web/stems.js:42`, `app/ui/web/stems.js:234`, `app/ui/web/stems.js:404`.
- **What the DJ sees:** Preparation and Import and listen. The listening panel is child of the second view, under two import file locations. After preparation, only the list of waveforms is updated by this manager.
- **Where he picks up:** "I've already prepared them, why should they be imported? He may choose unnecessary files to simply check a voice.
- **Proposal:** give the listening panel a common place after the results, with associated track above. Import keeps its block separate. Add a link « Listen to the items » / « Listen to the items » from the result; use existing listening and cooling operations.
- **EN** (`app/localization/en.json:407`, `ui.importView`): "Import and listen" → "Import existing items".
- **EN** (`app/localization/en.json:407`, `ui.importView`) : « Import & listen » → « Import existing stems ».
- **EN** (`app/localization/en.json:314`, `stems.importTitle`): "Manual import of stems" → "Associate your stem files".
- **EN** (`app/localization/en.json:314`, `stems.importTitle`) : « Manual stem import » → « Match your stem files ».
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--s6--le-panneau-dcoute-ne-reprend-pas-les-repres-de-jeu"></a>
###### S6 — The listening panel does not take back the game markers

- **Where:** listening transport; `app/ui/web/stems-listen.js:10`, `app/ui/web/stems-listen.js:43`, `app/ui/web/stems-listen.js:147`, `app/ui/web/app.css:138`, `app/ui/web/app.css:279`.
- **What the DJ sees:** To/Imported, Original/INST/VOCAL/DRUMS in visually similar groups; Original and roles may appear in a hurry simultaneously. Time in decimal seconds. The roles don't have their RX3 player colors.
- **Where he picks up:** he doesn't know if touching Vocal isolates or cuts the voice; 245.32 seconds requires a mental conversion to musical duration.
- **Proposal:** separate the source selection from the item commands and the Original button. Add a sentence **absent → EN "The illuminated items are audible. Touch a stick to cut or reactivate it. / EN « Bed stems are audible. Tap a stem to mute or enable it. * ; red INST, green VOCAL, blue DRUMS, preserved text and readable off state. Show time in `mm:ss`, without changing the accuracy of the drive. Name of the piece above the transport.
- **FR** (`app/localization/en.json:347`, `stems.listenDrive`) : "At destination" → "Registered Stems".
- **EN** (`app/localization/en.json:347`, `stems.listenDrive`) : « At destination » → « Saved stems ».
- **EN** (`app/localization/en.json:348`, `stems.listenImported`): "Imported" → "Selected files".
- **EN** (`app/localization/en.json:348`, `stems.listenImported`) : « Imported » → « Selected files ».
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--s7--limport-demande-au-dj-de-comprendre-un-compte-rendu-dsp"></a>
###### S7 — Import asks DJ to understand a DSP report

- **Where:** Manual import; `app/ui/web/stems.js:356`, `app/ui/web/stems.js:388`, `app/localization/en.json:320`, `app/localization/en.json:324`, `app/localization/en.json:326`, `app/localization/en.json:333`, `app/localization/en.json:334`; identical keys in EN at the same lines.
- **What the DJ sees:** estimated gain before even having imported, wefts removed, correlation, residual energy and decoder offset.
- **Where he picks up:** he wants to know if his voice is in the right place in the song; he has no business threshold to interpret these numbers.
- **Proposed:** keep voice and optional battery explicit in locations. First result: availability of listening and possible corrective action; technical details kept as such, without claiming certification. Do not convert a warning to success.
- **FR** (`app/localization/en.json:320`, `stems.importHeuristic`): "The gain is an estimate. No gain correction is applied. Listen to the reconstructed instrument before using it. → « Listen to the instrumental to check the result. The volume of your files is not fixed. "
- **EN** (`app/localization/en.json:320`, `stems.importHeuristic`) : « The gain is an estimate. No gain correction is applied. Listen to the rebuilt instrumental before using it. » → « Listen to the instrumental to check the result. Your file levels are not corrected. ».
- **EN** (`app/localization/en.json:324`, `stems.importShort`): "The stem is shorter than the untruncated mix. Re-export the entire piece, including the encoder offset." → "The item does not cover the entire piece. Re-export it with the same beginning and end as the original piece. "
- **EN** (`app/localization/en.json:324`, `stems.importShort`) : « Stem is shorter than the untrimmed mix. Re-export the complete track including encoder padding. » → « The stem does not cover the whole track. Export it again with the same start and end as the original track. ».
- **FR** (`app/localization/en.json:326`, `stems.importAlignment`): "Uncertain audio setting. Correlation: {correction}. Re-export the item with the start and end points of the original piece, without further processing. → « The setting of this item with the piece is uncertain. Re-export it with the same beginning and end, without further processing. "
- **EN** (`app/localization/en.json:326`, `stems.importAlignment`) : « Audio alignment is uncertain. Correlation: {correlation}. Export the stem with the original track's start and end points, without additional processing. » → « This stem may not line up with the track. Export it again with the same start and end, without additional processing. ».
- **Details retained:** value `{correction}`, particularity of the encoder, measures of `{ms}`, `{head}`, `{tail}`, `{gain}` and `{ratio}` remain accessible; the proposal separates the readable message from the data and does not remove it.
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--s8--certaines-instructions-dsignent-des-contrles-qui-nexistent-plus"></a>
###### S8 — Some instructions refer to controls that no longer exist

- **Where:** Stems and KEY SYNC warnings ; `app/ui/web/stems.js:109`, `app/localization/fr.json:434`, `app/localization/fr.json:377`, `app/localization/en.json:434`, `app/localization/en.json:377`, `mod/modules/key-sync/manifest.json:49`.
- **What the DJ sees:** "Uncheck Battery" while the interface offers two Voice + Instrumental / Voice + Battery + Instrumental buttons. The error KEY SYNC quotes "Find..." and two titles absent from the selector.
- **Where he picks up:** he looks for a non-existent box and unnecessarily reads the screen.
- **Proposed:** align all references to final visible headings, including after S1 and S5. No change in capacity.
- **FR** (`app/localization/en.json:434`, `stems.drumsModelImport`): "No quality available on this computer separates the battery. Uncheck Battery, or import a battery track into Import and Listen. → "This computer cannot prepare the battery with the available qualities. Choose Voice + Instrumental, or import a battery file. "
- **EN** (`app/localization/en.json:434`, `stems.drumsModelImport`) : « No quality on this computer separates drums. Uncheck Drums, or import a drums stem in Import & listen. » → « This computer cannot prepare drums with the available quality settings. Choose Vocals + instrumental, or import a drums file. ».
- **EN** (`app/localization/en.json:377`, `error.keySyncMode`): "Select "Align to current track" or "Find the closest compatible tone". → "Same tone as MASTER" or "closest compatible tone". "
- **EN** (`app/localization/en.json:377`, `error.keySyncMode`) : « Choose Match the playing track or Find the nearest compatible key. » → « Choose Match the MASTER key or Nearest compatible key. ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--s9--la-fin-dune-prparation-ne-distingue-pas-assez-rsultat-global-et-exceptions"></a>
###### S9 — The end of a preparation does not distinguish enough overall result and exceptions

- **Where:** Taskbar; `app/ui/web/app.js:698`, `app/ui/web/app.js:741`, `app/ui/web/app.css:238`, `app/ui/web/app.css:240`, `app/localization/en.json:450`.
- **What the DJ sees:** "Completed", a filled bar and possibly a long list of errors in an area of 96 px maximum height. Messages per piece and records share this area.
- **Where he picks up:** he understands "everything is ready" before discovering that an important piece has failed. Cancelled also receives a 100% bar (`app/ui/web/app.js:729`).
- **Proposal:** title composed from accounts already provided: **absent → EN « {ready} pieces ready · {failed} to check » / EN « {ready} tracks ready · {failed} to check »**, with singular variants. Details available under this balance sheet; adjacent listening action. Cancellation: Replace the full bar with the end of operation wording, without inventing a percentage of preparation. For long tasks, keep the overall progression and the current track; do not display an uncalculated remainder.
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--s10--apprendre-les-gestes-demande-de-quitter-stems-et-les-consignes-se-contredisent"></a>
###### S10 — Learning gestures asks to leave Stems and instructions contradict each other

- **Where:** Modules guide, previews and README ; `app/ui/web/app.js:453`, `app/ui/web/rx3-mock.js:301`, `app/ui/web/rx3-mock.js:330`, `app/ui/web/rx3-mock.js:392`, `mod/modules/stems/manifest.json:70`, `README.md:298`, `.claude/STYLE.md:42`.
- **What the DJ sees:** accessible guide in Modules, cyclical animation; README: battery 5, bass 6, instrumental 7, voice 8; current guide: instrumental 5, voice 6, battery 7. The glossary also includes a reference to items 7/8 with TODO.
- **Where he picks up:**he learns two incompatible gestures to cut the voice. No hardware validation in this audit slices which reflects the current RX3 player.
- **Proposal:** reuse the guide in Stems under **"On your XDJ-RX3" / "On your XDJ-RX3"**. Next to the animation, permanently display the tactile gesture already described: FR "Tick a st to cut or reactivate it. Hold and slide to adjust its volume. / EN « Tap a stem to mute or enable it. Hold, then drag to adjust its volume." These texts remain unchanged; moving their visibility, currently mainly driven by accessibility. Add previous/following manual steps or a leged fixed image to avoid waiting for a loop.
- **Limit of evidence:** before issuing a single numbered instruction, align README, glossary and guide with validated hardware reference. Do not add bass or arbitrarily choose a pad number. Documentary unification is recommended, not carried out.
- **Priority / effort: P1 · M.**


<a id="doc-ux-audit-dj--constats--logo"></a>
##### Constats — Logo

<a id="doc-ux-audit-dj--l1--ltat-vide-invite-dj--rgler-une-image-absente"></a>
###### L1 — Empty state already invites to set an absent image

- **Where:** Logo; `app/ui/web/index.html:214`, `app/ui/web/index.html:229`, `app/ui/web/logo.js:117`, `app/ui/web/logo.js:381`.
- **What the DJ sees:** a LOGO DJ preview and the area settings, zoom and framing, while no images have yet been selected.
- **Where he picks up:** he handles the zoom without results and doesn't know if he sets the demo logo or his future logo.
- **Proposal:** before choice, keep the preview and "Choose an image"; present the frame group disabled with its pattern, or reveal it only after choice. Keep useful choices of area accessible after selection. Current text retained: FR « Choose an image to frame your logo. / EN Choose an image to frame your logo. No disclaimer of preview.
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--l2--le-bouton-dominant-reste--remplacer-limage--quand-le-travail-est-fini"></a>
###### L2 — The dominant button remains "Replace image" when work is finished

- **Where:** Logo, notes and link Modules; `app/ui/web/index.html:209`, `app/ui/web/index.html:273`, `app/ui/web/logo.js:133`, `app/ui/web/logo.js:295`, `app/ui/web/logo.js:205`.
- **What the DJ sees:** his framed logo, "Replace image" at the top; The action Enable Logo is in the notes and the Modules link at the bottom. The image is stored on the computer, not written on USB by framing.
- **Where he picks up:** he estimates the work finished and removes his key without having prepared the files.
- **Proposed:** after selection, keep Replace image as secondary action. At the top, display the navigation action **"Continue in Modules" / "Continue in Modules"**, then select the module. This action does not trigger any writing. Keep Enable Adjacent Logo if necessary.
- **FR** (`app/localization/en.json:141`, `logo.buildHint`): "In Modules, activate Logo, then click Create mod. → "Your logo is ready to be integrated. In Modules, select Logo, then prepare your USB drive."
- **EN** (`app/localization/en.json:139`, `logo.buildHint`) : « In Modules, enable Logo, then click Build the mod. » → « Your logo is ready to include. In Modules, select Logo, then prepare your USB drive. ».
- **French localization proposal** (`app/localization/fr.json:375`, `logo.tick`): change the action from “Enable Logo” to “Select Logo”.
- **EN** (`app/localization/en.json:375`, `logo.tick`) : « Enable Logo » → « Select Logo ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--l3--cadrer-son-logo-demande-de-lire-des-dimensions-et-de-matriser-la-molette"></a>
###### L3 — Setting your logo requires reading dimensions and mastering the wheel

- **Where:** areas, labels and zoom ; `app/ui/web/logo.js:124`, `app/ui/web/logo.js:303`, `app/ui/web/logo.js:260`, `app/ui/web/index.html:245`, `app/ui/web/app.css:294`.
- **What the DJ sees:** "Classic", "Full width", pixels, a two decimal zoom multiplier; the wheel changes the framing in the preview. At 1180 px, the CSS rule limits the preview to 440 px and places the settings below.
- **Where he picks up:** he wants to see if his DJ name is in the area; the numbers do not help. By scrolling to the settings, it can inadvertently zoom in.
- **Proposed:** two small central zone silhouettes under choice; dimensions in a leaflet, not in buttons. Keep the Zoom and Direct Move cursor; reserve the wheel for scrolling until the preview has explicitly focused. Keep Refocus visible near the cursor. Under inversion, keep explanation on white/grey; Do not promise to reverse all colors.
- **FR** (`app/localization/en.json:372`, `logo.pane.classic`): "Classic" → "Central zone".
- **EN** (`app/localization/en.json:372`, `logo.pane.classic`) : « Classic » → « Centre area ».
- **FR** (`app/localization/en.json:133`, `logo.fit`): "Adjust image" → "Show whole image".
- **EN** (`app/localization/en.json:131`, `logo.fit`) : « Fit image » → « Show the whole image ».
- **FR** (`app/localization/fr.json:134`, `logo.fill`) : « Remplir la zone » → « Remplir la zone, en recadrant ».
- **EN** (`app/localization/en.json:132`, `logo.fill`) : « Fill area » → « Fill the area and crop ».
- **EN** (`app/localization/en.json129`, `logo.frameHint`): "Swipe the logo to move it. Scroll over the preview to zoom in. → « Drag the logo to move it. Adjust its size with Zoom."
- **EN** (`app/localization/en.json:127`, `logo.frameHint`) : « Drag the logo to move it. Scroll over the preview to zoom. » → « Drag the logo to move it. Use Zoom to adjust its size. ».
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--constats--samples"></a>
##### Constats — Samples

<a id="doc-ux-audit-dj--a1--le-clic-sur-un-pad-peut-modifier-un-inspecteur-hors-cran"></a>
###### A1 — Clicking on a pad can edit an off-screen inspector

- **Where:** grid and inspector; `app/ui/web/index.html:165`, `app/ui/web/index.html:190`, `app/ui/web/app.css:265`, `app/ui/web/samples.js:138`.
- **What the DJ sees:** grid then global settings, with the inspector below as early as 1190 px; the default window is 1180 px. A click selects a pad without bringing the inspector in sight.
- **Where it picks up:** it clicks "Add sample" in an empty box, but this click selects only the pad; The real button is lower.
- **Proposed:** in the stacked layout, bring the inspector directly to the grid and make it visible after selection of an empty pad. Keep the title "Pad {index}" and its color during the edition. Move bank volume and SHIFT after editor, with the rest of the bank settings. In sufficient width, keep the arrangement side by side.
- **EN** (`app/localization/en.json:65`, `samples.addSound`): "Add a sample" → "Add a sample".
- **EN** (`app/localization/en.json:65`, `samples.addSound`) : « Add a sample » → « Add a sample ».
- **Unchanged text, clarified action:** the visual link of the box must lead directly to the corresponding addition check; the click of a completed pad retains its selection function. No audio changes.
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--a2--aprs-ajout-la-slection-passe-au-pad-suivant"></a>
###### A2 — After adding, the selection goes to the next pad

- **Where:** added one or more samples; `app/ui/web/samples.js:534`, `app/ui/web/samples.js:560`.
- **What the DJ sees:** he adds a sound to pad 1, then the inspector shows pad 2 when it exists. The code advances after each file and selects the next location.
- **Where he picks up:** he thinks the import failed, or rules the color of the bad pad.
- **Proposal:** after simple addition, keep selected the pad filled; After multiple addition, select the first completed pad and report the range in the editor. New text **absent → FR « Samples added to the pads {first} to {last}. / EN "Samples added to pads {first}–{last}.**; singular variant. Keep the number of locations provided by the boundaries.
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--a3---enregistre--ne-signifie-pas--utilise-sur-la-platine"></a>
###### A3 — "Recorded" does not mean "used on the RX3 player"

- **Where:** bank, selector and activation; `app/ui/web/samples.js:491`, `app/ui/web/samples.js:518`, `app/ui/web/samples.js:574`, `app/ui/web/index.html:153`.
- **What the DJ sees:** registered badge, an asterisk in the selector and enable bank sometimes disabled. A new bank is not automatically activated if another bank is already active.
- **Where he picks up:** he prepares his set bank, the backup, then finds the old one on the RX3 player.
- **Proposed:** two separate informations: backup and bank used. Replace `*` with **‘ — used on the RX3 player' / ' — used on the deck'** in the selector, and show this bank near the recording button. If another bank is active, say its name; keep the existing explicit activation. If changes prevent activation, give the adjacent reason.
- **FR** (`app/localization/en.json:113`, `samples.makeActive`): "Activate bank" → "Use this bank on RX3 player".
- **EN** (`app/localization/en.json:111`, `samples.makeActive`) : « Activate bank » → « Use this bank on the deck ».
- **EN** (`app/localization/en.json:115`, `samples.clean`): "Recorded" → "Recorded on the USB drive".
- **EN** (`app/localization/en.json:113`, `samples.clean`) : « Saved » → « Saved to USB drive ».
- **EN** (`app/localization/en.json:106`, `samples.bankHint`): "A USB flash drive may contain several sample banks. The RX3 loads the active sample bank." → "You can register multiple banks on the USB drive. RX3 player uses one bank at a time. "
- **EN** (`app/localization/en.json:104`, `samples.bankHint`) : « A USB drive can hold several sample banks. The RX3 loads the active sample bank. » → « You can save several banks to the USB drive. The deck uses one bank at a time. ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--a4--enregistrer-des-samples-nexplique-pas-comment-les-rendre-jouables"></a>
###### A4 — Save samples does not explain how to make them playable

- **Where:** Samples and Samples module; `app/ui/web/samples.js:574`, `app/ui/web/samples.js:694`, `app/ui/web/app.js:453`, `mod/modules/samples/manifest.json:15`, `app/ui/web/index.html:187`.
- **What the DJ sees:** successful recording and SLIP LOOP instruction. The Samples module is disabled by default; This screen does not offer the equivalent of the Enable Logo button.
- **Where he picks up:** he saved his bank well, but may never have prepared the corresponding module on the key.
- **Proposed:** as a bank, show separately the presence of the module reported by the key and the selection for the next preparation. If necessary, provide a link to the module in Modules, then leave writing to its explicit action. New text **absent → EN « Registered bank. To play your samples, select Samples in Modules and then prepare this USB flash drive. / EN « Bank saved. To play your samples, select Samples in Modules, then prepare this USB drive. Only when the stage is missing or remains unknown. Do not say that a selected module is already installed. Keep SLIP LOOP and the protection of hot wines in the existing aid.
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--a5--une-case--cocher-change-le-sens-du-clic-sur-toute-la-grille"></a>
###### A5 — A check box changes the direction of the click on the entire grid

- **Where:** test pads; `app/ui/web/index.html:172`, `app/ui/web/samples.js:138`, `app/ui/web/samples.js:626`, `app/ui/web/app.css:187`.
- **What the DJ sees:** "Test the pads"; depending on this box, the same pad selects a sound or plays it. The selected colours are indicated only by a small tablet; selection and reading use generic blue accent.
- **Where he picks up:** he wants to set a pad, but triggers a sound, or clicks to listen and opens the editor. The little tablet does not evoke its illuminated pads.
- **Proposal:** present the two existing modes as two exclusive choices **absent → EN « Edit pads » / « Play pads » ; IN "Edit pads" / "Play pads"**. Use the sample color for the edged and played state, with a textual reading indication; keep the editing selection separate. Show Stop it by the gate. Keep the limit of votes and existing reading methods.
- **EN** (`app/localization/en.json:92`, `samples.simulateHint`): "Enable to play with mouse or keys 1 to 8. Escape stops all samples. Disable to edit pads. Listening resumes your settings on this computer, without simulating the audio processing of RX3. → « Play with mouse or keys 1 to 8. Escape stops all samples. Return to Edit pads to change your sounds. "
- **EN** (`app/localization/en.json:91`, `samples.simulateHint`) : « Enable to play with the mouse or keys 1–8. Esc stops all samples. Disable to edit. Uses your playback settings on this computer, without simulating RX3 audio processing. » → « Play with the mouse or keys 1–8. Esc stops all samples. Return to Edit pads to change your sounds. ».
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--a6--les-rglages-simples-sont-encombrs-par-les-rglages-secondaires"></a>
###### A6 — Simple settings are cluttered by secondary settings

- **Where:** inspector, bank name, volume; `app/ui/web/samples.js:181`, `app/ui/web/samples.js:310`, `app/ui/web/samples.js:606`, `app/ui/web/index.html:178`.
- **What the DJ sees:** name and color before extract and listen; two volume levels; `bank1` as the original name; Fields Accurate start/duration at 100th of a second.
- **Where he picks:** to choose eight seconds of a jingle, he must first understand all the inspector; "initial" does not indicate when this volume will be used.
- **Proposal:** Order the inspector as sound → excerpt and listening controls → playback mode → name/colour → level. Keep the existing numeric fields and limits; no new audio analysis or waveform is required. Add “Excerpt start in the file” help. Default new bank names should be localized as `Banque-1` (French) and `Bank-1` (English), within existing naming restrictions; do not rename existing banks. Show percent units for both bank volume and pad level.
- **EN** (`app/localization/en.json:110`, `samples.volume`): "Initial volume of the bank" → "Volume at loading of the bank".
- **EN** (`app/localization/en.json:108`, `samples.volume`) : « Initial bank volume » → « Volume when the bank loads ».
- **FR** (`app/localization/en.json:76`, `samples.modeHold`): "Maintened" → "During support".
- **EN** (`app/localization/en.json:76`, `samples.modeHold`) : « While held » → « While held ».
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--parcours-critique--obtenir-la-cl-de-chiffrement-de-la-platine"></a>
##### Critical course — get RX3 player encryption key

The user need is the one named "key decryption" in the brief. The official vocabulary of the application remains **key encryption / encryption key**, according to `.claude/STYLE.md:19`. This file is not a USB drive and this path does not read a secret directly from a connected RX3 player. The code includes archives published by the manufacturer (`app/firmware/key source.json:2`); their network availability has not been verified and no download has been launched.

<a id="doc-ux-audit-dj--chemin-complet-et-embranchements"></a>
###### Full path and connections

| Situation | Current status and action verified | Point to make obvious for DJ |
|---|---|---|
| No key on startup | `boot()` calls `openTerms()` if the task area is hidden. `app/ui/web/app.js:767`. | Why this download precedes his work; the possibility of doing so later. K1. |
| Key missing in Modules | Path "none", Obtain encryption key, Browse; size note. `app/ui/web/app.js:604`. | One common action; It's not a choice of USB drive. K2, K8. |
| Prepare with a destination but without key | The button can be active; `startBuild()` opens the conditions and stops there. `app/ui/web/app.js:574`, `app/ui/web/app.js:678`. | The button does not prepare the files yet; first preparation to explain. K1, K7. |
| Key already found | Full path, hidden download. Proposed deletion only for the key retained by the application. `app/ui/web/app.js:604`. | Status ready, no further recovery required. K8. |
| Manually Selected File | Choosing an existing file; `setKey()` sets its path to the screen. `app/ui/web/app.js:819`. | Selected file is not synonymous with successful verification. K8. |
| Open conditions | Seven paragraphs, scrolling zone; Blocked to bottom; button blocked until acceptance. `app/ui/web/index.html:441`, `app/ui/web/app.js:621`. | Read in the right language, see where to scroll, understand the weight of the download. K3–K4. |
| Cancel / close before agreement | Close the conditions; no download is requested by this button. `app/ui/web/app.js:829`. | Return to the task and return to the same stage later. K1. |
| Agreement | Closure of the modal, explicit request for recovery; overall monitoring. `app/ui/web/app.js:648`. | See a stable progression and downloaded object. K5. |
| Another task occupies the app | The operation can return the current task error; the modal has already closed. `app/ui/web/app.js:650`, `app/localization/en.json/182`. | Wait for the named task and have clear access to the new trial. K6, T2. |
| Transfert | Two parts configured; total size 252 802 747 bytes, approximately 253 MB decimals. `app/firmware/key source.json:7`, `app/firmware/key source.json:14`, `app/ui/bridge.py:431`. | Understandable size and advancement; Do not look for two files to open. K5. |
| Check / read | Archives controls, then read message with undetermined progress. `app/firmware/key source.py:204`, `app/ui/bridge.py:435`. | The transfer is not the whole operation; wait for the result. K5. |
| Judgment requested | Cancel calls existing cancellation; return "requested" then cancelled. `app/ui/web/app.js:838`, `app/ui/bridge.py:445`. | A judgment requested is not yet an effective stop. K6. |
| Network interrupted | Error with archive name and reason; data already received announced retained. `app/localization/en.json:300`, `app/localization/en.json:300`. | Connect and try again, without manipulating the archive. K6. |
| Verification refused | Invites to update the app or manually choose a file. `app/localization/en.json:301`, `app/localization/en.json:301`. | Do not bypass the verification; manual proposal reserved to who already has the file. K6. |
| Retest | Re-open conditions; Reusable valid archive, partial transfer resumed if the server allows. `app/ui/web/app.js:621`, `app/firmware/key source.py170`, `app/firmware/key source.py189`, `app/firmware/key source.py:361`. | Do not promise a byte resumption in any case. K6. |
| Success | Message with path; reread the key; no automatic `startBuild()`. `app/ui/web/app.js:655`, `app/ui/web/app.js:752`. | The USB preparation remains to be requested explicitly. K7. |
| Subsequent suppression | Confirmation; Remove the saved key and partial downloads; update. `app/ui/web/app.js:658`. | Do not remove modules already prepared on USB; Don't restore the RX3 player. K8, R1. |

<a id="doc-ux-audit-dj--k1--le-tlchargement-arrive-avant-son-explication"></a>
###### K1 — The download arrives before its explanation

- **Where:** first opening and button Prepare; `app/ui/web/app.js:770`, `app/ui/web/app.js:678`, `app/ui/web/index.html:441`.
- **What the DJ sees:** "Before downloading the encryption key", immediately, with the Modules screen in the background.
- **Where he picks up:** he doesn't understand why his RX3 player would need a computer key, or should he plug it into the computer.
- **Proposed:** retain the stage and consent; give at the top of the modal a usage sentence, distinct from the legal text: **absent → FR "This initial preparation allows you to create files that your XDJ-RX3 will load from the USB drive. "This initial setup lets you create the files your XDJ-RX3 will load from the USB drive. **. Replace the closing button with Later, without changing its action. If the modal is delayed, the Modules summary keeps the recovery link.
- **EN** (`app/localization/en.json:303`, `terms.title`): "Before downloading the encryption key" → "Initial preparation: encryption key".
- **EN** (`app/localization/en.json:303`, `terms.title`) : « Before downloading the encryption key » → « Initial setup: encryption key ».
- **FR** (`app/localization/fr.json:14`, `common.cancel`) : « Annuler » → « Plus tard ».
- **EN** (`app/localization/en.json:14`, `common.cancel`) : « Cancel » → « Later ».
- **Scope:** replacing `common.cancel` for this modal only. Keep Cancel elsewhere and agree before each download. No silent recovery.
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--k2--deux-objets-diffrents-sappellent--cl"></a>
###### K2 — Two different objects are called "key"

- **Where:** Summary Modules, Manual Choice and Acquisition; `app/ui/web/index.html:100`, `app/ui/web/app.js:604`, `app/localization/en.json:51`, `app/localization/en.json:295`.
- **What the DJ sees:** Encryption key / none / Get / Browse, near the USB destination. The phrase `modules.keyLede` exists but is not inserted here.
- **Where he picks up:** he thinks he has to look for a file on his USB drive or in rekordbox.
- **Proposal:** retain the term of the glossary and accompany it once: **absent → FR "The encryption key is a file necessary for preparation. The application can retrieve and store it on this computer. / EN « The encryption key is a file needed for preparation. The app can retrieve it and keep it on this computer.**. Show the status and the recovery button before the path; key pictogram for this file, USB pictogram for support.
- **EN** (`app/localization/en.json:366`, `modules.needKey`): "Add a encryption key to create the mod. → "Get the encryption key to prepare your USB drive."
- **EN** (`app/localization/en.json:366`, `modules.needKey`) : « Add an encryption key to build the mod. » → « Get the encryption key to prepare your USB drive. ».
- **FR** (`app/localization/en.json:295`, `modules.keyFetchNote`): "Archive source Pioneer: {bytes}. Only the encryption key is kept. → « Initial download: {bytes}, from the Pioneer DJ source archive. Only the encryption key is kept at the end. "
- **EN** (`app/localization/en.json:295`, `modules.keyFetchNote`) : « Pioneer source archive: {bytes}. Only the encryption key is kept. » → « Initial download: {bytes}, from the Pioneer DJ source archive. Only the encryption key is kept when complete. ».
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--k3--le-consentement-est-lisible-seulement-dans-une-petite-fentre-dfilante"></a>
###### K3 — Consent is readable only in a small scrolling window

- **Where:** conditions; `app/ui/web/index.html:443`, `app/ui/web/index.html:452`, `app/ui/web/app.css:256`, `app/ui/web/app.js:639`, `app/ui/web/i18n.js:49`.
- **What the DJ sees:** about 40% of the window height at the maximum for text, or 224 px at 560 px; a box disabled and the language selector only in Settings, behind the modal.
- **Where he picks up:** he tries to tick before he reaches the bottom, or can't easily change a memorized language that he doesn't understand.
- **Proposed:** keep all text and scroll condition. Show FR/EN in the modal above the text; keep the bottom of the modal visible with the box and actions. Give the body the remaining space rather than an arbitrary limit of 40vh when space is available. Show download size near the button. Do not check in its place and do not shorten the legal text.
- **FR** (`app/localization/en.json:311`, `terms.scroll`): "Read the conditions down to check the acceptance box. → « Scroll the conditions down to activate the box "I have read and I accept these conditions". "
- **EN** (`app/localization/en.json:311`, `terms.scroll`) : « Read and scroll to the end to enable acceptance. » → « Scroll to the end of the terms to enable the “I have read and accept these terms” checkbox. ».
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--k4--le-changement-de-langue-change-aussi-des-informations-de-fond"></a>
###### K4 — Language change also changes background information

- **Where:** conditions and editorial rule; `app/localization/en.json:304`, `app/localization/en.json:304`, `app/localization/en.json:306`, `app/localization/en.json:306`, `app/localization/en.json:309`, `app/localization/en.json:309`, `app/localization/en.json:310`, `app/localization/en.json:310`, `.claude/STYLE.md:46`.
- **What the DJ sees:** EN explains verification, local preservation and removal of the rest; FR talks about "moddable" USB drive and "unlock" a mode. FR also prohibits the marketing of a key-based mod; This wording does not appear in the corresponding EN paragraph. EN names MPL 2.0, FR no. EN explains where to delete; FR explains the consequence on future mods.
- **Where he picks up:** by seeking clarification in the other language, he gets another explanation and other formulations of responsibility. These are verified textual deviations, **not a legal conclusion**.
- **Concrete proposal for presentation:** add identical headings of scope without removing a sentence: **absent → EN « Download and storage » / EN « Download and storage »**, **FR « Use and responsibility » / FR « Use and responsibility »**, **FR « Delete the encryption key » / FR « Delete the encryption key »**. Keep all conditions before acceptance. Do not substitute single versions in a single UX pass.
- **To be resolved before publication of new legal texts:** editorial reconciliation with README and the NOTICE reference requested by STYLE; no `NOTICE` file was found in this checkout. The exact legal wording remains out of the proposal to rewrite here so as not to arbitrarily choose which obligations to delete or add. The word "moddable" is not recommended elsewhere; its replacement under conditions must be part of this explicit reconciliation.
- **Priority / effort: P1 · M** for presentation and consistency; validation of the unestimated fund.

<a id="doc-ux-audit-dj--k5--la-progression-raconte-larchive-pas-lavancement-utile"></a>
###### K5 — Progress tells the archive, not useful advancement

- **Where:** download and global bar; `app/ui/web/app.js:709`, `app/ui/web/app.js:717`, `app/ui/bridge.py:431`, `app/localization/en.json:298`, `app/ui/web/i18n.js:38`.
- **What the DJ sees:** "Pioneer source archive, part 1 by 2", a bar; then "Reading the key..." and an undetermined bar. Bytes received/total exist in progress data, but the frontend does not display them for the key.
- **Where he picks up:** he doesn't know if he should wait, open an archive, or why the bar changes appearance after the transfer.
- **Proposed:** two stable phases: download and then retrieve/verification, without inventing a percentage during the indeterminate phase. Show the bytes already provided in MB/MB and the actual percentage. Leave the archive names in detail. Total size calculated from metadata, not an IU constant of 250.
- **EN** (`app/localization/en.json:298`, `job.keyDownload`): "Downloading Pioneer source archive, part {part} on {count}" → "Download Pioneer DJ files · {part}/{count}".
- **EN** (`app/localization/en.json:298`, `job.keyDownload`) : « Downloading Pioneer's source archive, part {part} of {count} » → « Downloading Pioneer DJ files · {part}/{count} ».
- **FR** (`app/localization/en.json:299`, `job.keyRead`): "Reading the encryption key in the archive" → "Recovering the encryption key...".
- **EN** (`app/localization/en.json:299`, `job.keyRead`) : « Reading the encryption key from the archive » → « Retrieving the encryption key… ».
- **Units:** for a Mo/MB presentation, actually convert bytes to base 10; Do not rename Mio/MiB without conversion. Existing conditions can maintain their approximation of about 250 MB.
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--k6--ressayer-ou-annuler-exige-de-retrouver-soi-mme-lentre-du-parcours"></a>
###### K6 — Retrying or canceling requires re-entering the course

- **Where:** failure and interruption; `app/ui/web/app.js:648`, `app/ui/web/app.js:722`, `app/ui/web/app.js:838`, `app/localization/en.json:300`, `app/localization/en.json:301`, `app/firmware/key source.py170`, `app/firmware/key source.py189`.
- **What the DJ sees:** opaque ZIP name and technical reason; Cancel disappears at the end of the task, without a button in the result. The recovery button still exists in Modules.
- **Where he picks up:** he thinks he needs to search for the ZIP, delete a download or reinstall the RX3 player; After cancellation he doesn't know what's left.
- **Proposal:** result with explicit action **"Retry download" / "Retry download"** which reopens existing conditions. Separate error details, without losing them. Cancellation: **absent → EN « Download stopped. You can restart it from Modules. / EN « Download stopped. You can restore it from Modules. "** ; display this state only after confirmed shutdown. If a task occupies the app, give a link to its progress, without canceling this task automatically.
- **EN** (`app/localization/en.json:300`, `error.keyNetwork`): "Unable to download {name}: {reason}. Check the connection, then try again. Data already received are retained. → « The download was interrupted. Check your Internet connection, then try again. Data already received are retained. "
- **EN** (`app/localization/en.json:300`, `error.keyNetwork`) : « Couldn't download {name}: {reason}. Check the connection, then try again. Data already downloaded is kept. » → « The download was interrupted. Check your internet connection, then try again. Data already downloaded is kept. ».
- **EN** (`app/localization/en.json:301`, `error.keyPackage`): "The {name} check failed. Update the Toolkit or select an encryption key file with Browse. → « The downloaded files did not pass the check. Update the Toolkit before trying again. "
- **EN** (`app/localization/en.json:301`, `error.keyPackage`) : « Verification failed for {name}. Update the Toolkit or select an encryption key file with Browse. » → « The downloaded files did not pass verification. Update the Toolkit before trying again. ».
- **Details:** `{name}` and `{reason}` remain available; the alternative of a previously held key file remains in the K8 manual options. No verification bypass and no exact resumption promise when the server ignores partial resumption.
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--k7--russite--un-chemin-de-fichier-remplace-la-prochaine-action"></a>
###### K7 — Success: a file path replaces the next action

- **Where:** end of download; `app/ui/web/app.js:655`, `app/ui/web/app.js:666`, `app/ui/web/app.js:752`, `app/ui/web/app.js:677`.
- **What the DJ sees:** "Completed" then "Encryption key saved in {path}"; the selection is updated. The initial click on Create mod is not restarted.
- **Where he picks up:** he is looking for if he has to move this file to his USB drive, or believes that all the preparation is complete.
- **Proposal:** status ready in summary, path kept in details, button **« Continue in Modules » / « Continue in Modules »**. If already in Modules, highlight the preparation button and its destination. Writing remains explicitly requested by the DJ, not triggered when the download returns.
- **FR** (`app/localization/en.json:297`, `modules.keyFetched`): "Encryption key saved in {path}" → "Encryption key ready. You can prepare your USB drive."
- **EN** (`app/localization/en.json:297`, `modules.keyFetched`) : « Encryption key saved to {path} » → « Encryption key ready. You can now prepare your USB drive. ».
- **Detail retained:** `{path}` remains available under condition; this path should not be presented as a copying instructions. If no destination is chosen, the next check highlighted is his choice.
- **Priority / effort: P1 · S.**

<a id="doc-ux-audit-dj--k8--chemin-import-manuel-et-suppression-ont-trop-de-poids"></a>
###### K8 — Path, manual import and removal have too much weight

- **Where:** key present or absent; `app/ui/web/app.js:604`, `app/ui/web/app.js:658`, `app/ui/web/app.js:819`, `app/ui/web/index.html:104`.
- **What the DJ sees:** a long path, Browse and Delete encryption key side by side. A manually selected key fills the state without proof of validation; The download is then hidden.
- **Where it picks up:** it picks up a file at random to unlock the button, or deletes the key thinking of deactivating the modules.
- **Proposal:** main state "Available encryption key" / "Encryption key available" only for the recognized key; for manual choice "Selected File" / "File selected". Consolidate path, manual selection and deletion in **"Manage Encryption Key" / "Manage Encryption Key"**. Keep a visible exit after file not found: choose another file or return to the recovery path with agreement.
- **FR** (`app/localization/en.json:11`, `common.browse`): "Browse" → "Choose an encryption key file".
- **EN** (`app/localization/en.json:11`, `common.browse`) : « Browse » → « Choose an encryption key file ».
- **EN** (`app/localization/en.json:388`, `ui.forgetKeyBody`): "The saved encryption key and partial download will be deleted. You will need to recover the encryption key to create a new mod. → « The encryption key and partial downloads will be removed from this computer. Files already prepared on your USB drive will remain in place. You will need to recover the encryption key for a future preparation. "
- **EN** (`app/localization/en.json:388`, `ui.forgetKeyBody`) : « This deletes the saved encryption key and any partial download. You will need the encryption key again to build another mod. » → « The encryption key and partial downloads will be deleted from this computer. Files already prepared on your USB drive will remain. You will need to retrieve the encryption key for a future preparation. ».
- **Scope:** new text to Browse specific to the key selection; do not replace the button on the other screens. Keep current rules protecting a manual file and confirmation of deletion.
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--constats-transversaux--rglages-graphismes-cohrence-et-tats"></a>
##### Transversal findings — Settings, graphics, consistency and states

<a id="doc-ux-audit-dj--t1--trois-thmes-concernent-trois-choses-diffrentes"></a>
###### T1 — Three themes concern three different things.

- **Where:** Settings, Clear Theme module, Logo; `app/ui/web/index.html:392`, `app/ui/web/index.html:253`, `mod/modules/theme-white/manifest.json:4`, `app/localization/en.json:412`.
- **What the DJ sees:** Appearance, Clear Theme and Overview Theme. The help Settings returns to Logo, while the real appearance of the RX3 player depends on the Clear Theme module.
- **Where he picks up:** he chooses Clair in Settings and expects to find this theme on the RX3; The clear preview is also not a module activation.
- **Proposed:** appoint the three litters, maintain their choices and independence. In Settings, put language and appearance in two compact groups; By the way, it can be brief. Do not add any technical settings in this general destination.
- **EN** (`app/localization/en.json:411`, `ui.appearance`): "Appearance" → "Appearance of application".
- **EN** (`app/localization/en.json:411`, `ui.appearance`) : « Appearance » → « App appearance ».
- **FR** (`app/localization/en.json:412`, `ui.appearanceHint`): "This setting changes the theme of the Toolkit. Set the RX3 preview separately in Logo. → "For the RX3 player screen, select Clear Theme in Modules. "
- **EN** (`app/localization/en.json:412`, `ui.appearanceHint`) : « This changes the Toolkit theme. Adjust the RX3 preview separately in Logo. » → « For the deck’s screen, select Light theme in Modules. ».
- **EN** (`app/localization/en.json:368`, `logo.screenTheme`) : « Theme of the preview » → « Overview on light or dark background ».
- **EN** (`app/localization/en.json:368`, `logo.screenTheme`) : « Preview theme » → « Preview on a light or dark screen ».
- **EN** (`app/localization/en.json:416`, `ui.immediateSettings`): "The amendments apply immediately. → "The language and appearance of the application apply immediately. "
- **EN** (`app/localization/en.json:416`, `ui.immediateSettings`) : « Changes apply immediately. » → « App language and appearance changes apply immediately. ».
- **Priority / effort : P2 · S.**

<a id="doc-ux-audit-dj--t2--les-erreurs-se-rptent-et-les-russites-courantes-dplacent-le-contenu"></a>
###### T2 — Errors repeat and common successes move content

- **Where:** common messages; `app/ui/web/app.js:64`, `app/ui/web/app.js:97`, `app/ui/web/components.js:55`, `app/ui/web/components.js:70`, `app/ui/web/app.js:208`, `app/ui/web/app.css:247`.
- **What the DJ sees:** an error may appear both in the overall toast and in the state of the screen. A simple USB record also displays a state of success above the card. The toast fixed at the bottom right can occupy the same space as the progression.
- **Where it picks up:** it can count two failures instead of one or look for a new problem at each update. The result moves as he reads.
- **Proposed:** an error related to a field or screen remains in the right place with its action; task error in its result area; only one main display, technical details unfoldable. Reserve success announcements to content states, without a read/refresh banner. Provide a stable place for long progression. Keep destructive confirmations.
- **FR** (`app/localization/en.json181`, `error.detail`): "Operation failure: {detail}" → "Operation failed. See the details below."
- **EN** (`app/localization/en.json:179`, `error.detail`) : « Operation failed: {detail} » → « The operation did not complete. See the details below. ».
- **Details:** `{detail}` is moved under "Technical details" / "Technical details", never deleted. Known errors must remain accurate; the generic text is only a fold. No universal "Retry" triggering uncontextualized writing.
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--t3--les-codes-dj-existent-mais-changent-entre-les-reprsentations"></a>
###### T3 — DJ codes exist, but change between performances

- **Where:** colors, icons, previews; `app/ui/web/app.css:17`, `app/ui/web/app.css:172`, `app/ui/web/app.css:187`, `app/ui/web/index.html:22`, `app/ui/web/rx3-mock.js:292`, `app/ui/web/rx3-mock.js:392`, `app/ui/web/rx3-mock.js:210`, `app/ui/web/rx3-mock.js:422`, `app/ui/web/key-match-green.svg:1` and the three corresponding SVGs.
- **What the DJ sees:** blue applicative accent, pads represented by a grid icon of six boxes while the editor presents eight, DRUMS light blue in the pads help and pure blue in the touch aid, neutral listening roles. The previews show an impossible time "0:67".
- **Where he picks up:** he looks for the same benchmarks as playing; A DRUMS button must be recognizable without rereading, and an impossible time diminishes the credibility of the preview.
- **Precise graphic proposal:** keep the SVG Key Match with their native drawing 28 × 26 and their colors, with a text legend; do not replace them with generic pellets. Standardize the Samples icon in 2 × 4 boxes. Define the semantic colors of roles in the IU and reuse them for guides, listening and legends: INST red, VOCAL green, DRUMS blue; the luminance detail must correspond to the material representation concerned, not be arbitrarily replaced on the RX3. Correct in both languages the fictitious data "0:67" → " 1:07".
- **To be retained:** Blue accent reserved for the actions of the app, green success reserved for the results; Do not recolor all the app in orange on the grounds that rekordbox uses it. The material labels BROWSE, MASTER, KEY, STEMS, SLIP LOOP, RELEASE FX and VOL remain unchanged. Rekordbox codes are appreciated here from the assets and representations of the repository, without comparison live to an external version.
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--t4--les-dtails-de-12-px-occupent-la-place-des-dcisions"></a>
###### T4 — The details of 12 px occupy the place of decisions

- **Where:** typography and spacing; `app/ui/web/app.css:6`, `app/ui/web/app.css:66`, `app/ui/web/app.css:91`, `app/ui/web/app.css:147`, `app/ui/web/app.css:265`, `app/ui/web/app.css:270`.
- **What the DJ sees:** 13 px body, 12 px aids and paths, many cards separated by 24 px; summary Modules placed before the list in 1040 px, inspector Samples and checks Logo stacked in 1190 px.
- **Where he picks up:** small window, his attention goes to paths, technical settings and maps before the musical gesture. At the default size, the pad editor is already closer to the grid.
- **Proposal:** instructions for decision in 14 px, secondary in 12 px; key name and action in 14 px semi-gras. Keep existing spacings of 8/16/24 px but use 8 px between an instruction and its control, 16 px between related choices, 24 px between tasks. At 880 × 560, summarize destination/step in one line before modules, then develop the rest on demand; do not first reserve a large map of technical settings. Test the return to the FR line before changing the column thresholds. No reduction of the labels by truncation to make hold the window.
- **Priority / effort : P2 · M.**

<a id="doc-ux-audit-dj--t5--les-units-et-les-messages-de-dpannage-demandent-une-traduction-informatique"></a>
###### T5 — Units and troubleshooting messages require computer translation

- **Where:** sizes, import and messages relayed; `app/ui/web/i18n.js:38`, `app/localization/en.json:274`, `app/localization/en.json:278`, `app/localization/en.json:288`, `app/localization/en.json:443`, `app/localization/en.json:436`, `app/ui/web/stems.js:55`.
- **What the DJ sees:** Gio/Mio/Kio, gross number of bytes, "Reestablish process detection", separation code, package of stems, frames and cache. Some messages are English even with the French interface.
- **Where it picks up:** no concrete action corresponds to "restore detection"; delete a file in RX3 STEMS or understand a process code exceeds its DJ usage.
- **Proposal:** first the musical object, the consequence and the action actually available; technical figures in detail. Sizes in Mo/Go with correct conversion, durations in minutes/seconds. Present raw texts as retained details, without betting an arbitrary error in a certain false cause. Diagnostic lines shall not become unverifiable technical requirements.
- **EN** (`app/localization/en.json:278`, `stems.processUnknown`): "Cannot check if music library software is open. Restore process detection before proceeding. → "Cannot verify that rekordbox is closed. Close rekordbox, then click Check again. If blocking persists, keep the error details for troubleshooting. "
- **EN** (`app/localization/en.json:278`, `stems.processUnknown`) : « Cannot check whether the library application is running. Restore process detection before continuing. » → « Cannot check that rekordbox is closed. Close rekordbox, then click Check again. If this remains blocked, keep the error details for troubleshooting. ».
- **FR** (`app/localization/en.json:443`, `stems.separatorFailed`): "The separation engine stopped with the {code} code. Details: {detail} » → « The preparation of the items has stopped. Check the error details before trying again. "
- **EN** (`app/localization/en.json:443`, `stems.separatorFailed`) : « The separation engine stopped with code {code}. Details: {detail} » → « Stem preparation stopped. Check the error details before trying again. ».
- **FR** (`app/localization/en.json:470`, `stems.waveInvalid`): "Package of illegible stems. Prepare this piece again. → « Unable to read stem files. Prepare this piece again."
- **EN** (`app/localization/en.json:470`, `stems.waveInvalid`) : « Cannot read the stems package. Prepare this track again. » → « Cannot read the stem files. Prepare this track again. ».
- **Details and limits:** `{code}` and `{detail}` remain available. Relaunching does not guarantee repairing process detection. The replacement of imported items that now requires file manipulation remains a product limit: do not invent a "Replace" button without existing operation.
- **Priority / effort: P1 · M.**

<a id="doc-ux-audit-dj--constat--retour--ltat-dorigine"></a>
##### Finding — Return to original status

<a id="doc-ux-audit-dj--r1--retirer-les-fichiers-et-retrouver-la-platine-dorigine-sont-confondus"></a>
###### R1 — Remove files and find the original RX3 player are confused

- **Where:** USB inspection, confirmation, result; `app/ui/web/index.html:65`, `app/ui/web/app.js:809`, `app/localization/en.json:385`, `app/localization/en.json:386`, `README.md:308`, `app/services/mod.py:78`.
- **What the DJ sees:** "Delete mod", then a number of deleted files. The procedure of stopping, extinguishing, removing the key and restarting is not in the app. Removing the encryption key is another visible action.
- **Where he picks up:** he may think he has to uninstall something in the RX3 player or thinks that deleting the encryption key immediately disables his functions.
- **Proposed:** keep the removal of files explicit and confirmed, with the name of the key. Separate in a foldable helper "Use the deck without modules" / "Use the deck without modules" from the action that cleans the USB. Take the README sequence exactly as gestures: **absent → FR "Stop reading. Turn off the RX3 player. Remove the prepared USB drive. Turn the RX3 player back on. / EN "Stop playback. Turn off the deck. Remove the prepared USB drive. Turn the deck on again.**. Do not imply that a reading key removal is sufficient.
- **EN** (`app/localization/en.json:39`, `drive.removeMod`): "Delete mod" → "Delete modules from this USB drive".
- **EN** (`app/localization/en.json:39`, `drive.removeMod`) : « Remove the mod » → « Remove modules from this USB drive ».
- **EN** (`app/localization/en.json:385`, `ui.removeDriveTitle`): « Remove the mod from this USB drive? → "Remove modules from this USB drive?".
- **EN** (`app/localization/en.json:385`, `ui.removeDriveTitle`) : « Remove the mod from this USB drive? » → « Remove modules from this USB drive? ».
- **EN** (`app/localization/en.json:386`, `ui.removeDriveBody`): " USB flash drive: {path}<br>The mod files will be deleted. → « USB flash drive: {path}<br>Module files and their logs will be deleted. Your music, stems and sample banks will be preserved. "
- **EN** (`app/localization/en.json:386`, `ui.removeDriveBody`) : « USB drive: {path}<br>The mod files will be removed. » → « USB drive: {path}<br>Module files and their logs will be removed. Your music, stems and sample banks will be kept. ».
- **Proposed result:** FR « Modules removed from this USB drive. Your music, stems and sample banks are preserved. » / EN « Modules removed from this USB drive. Your music, items and sample banks have been kept." replaces the two forms of `drive.removed` (`app/localization/en.json:41`, `app/localization/en.json:41`); number of files in details. Do not declare the RX3 player already returned to the original state since the only result on USB.
- **Priority / effort: P1 · S.**


<a id="doc-ux-audit-dj--vocabulaire"></a>
##### Vocabulaire

This table covers the fixed technical terms identified in screens, their aids, conditions and messages that can be relayed. The free values of an external error may contain other terms: their totality cannot be statically recorded. The material wording and known DJ terms are not to be arbitrarily "simplified".

**Proposed editorial convention:** keep the necessary technical terms in a searchable detail; use an understandable object or gesture in the main course. The replacement of a title never promises a new capacity. The associated findings have priority and effort; This table constitutes their lexical inventory, not a second catalogue of defects without proof.

| Current term EN / FR or visible raw text | Why the DJ stops | Proposition EN | Proposition FR | Evidence / finding |
|---|---|---|---|---|
| Mod / mod; build / create mod | He doesn't know what will be installed or where. | Prepare USB drive ; module files | Prepare the USB flash drive; module files | `app/localization/en.json:54`, `app/localization/fr.json:54` · M1 |
| Modules | Required names of destinations; may evoke components. | Keep **Modules**, explain “features for your XDJ-RX3” | Keep **Modules**, explain "functions for your XDJ-RX3" | `PRODUCT.md:7`, `app/localization/en.json:45`, `app/localization/fr.json:45` · O1/M1 |
| Module on / module activated | Can mean already active on the RX3 player. | Module selected | Selected module | `app/localization/en.json:360`, `app/localization/fr.json:360` · M1 |
| Requires / Needed by (both localizations) | Computer relationship, no mix action. | Included with {feature} | Included with {feature } | `app/localization/en.json:49`, `app/localization/fr.json:49`, `app/localization/en.json:365`, `app/localization/fr.json:365` · M2 |
| Firmware | Unusual software version; not detection. | XDJ-RX3 software version | XDJ-RX3 Software Version | `app/localization/en.json:28`, `app/localization/fr.json:28` · M5 |
| Build settings / Mod settings | Preparation and installed condition are confused. | To save to your USB drive | To save to your USB drive | `app/localization/en.json:417`, `app/localization/fr.json:417` · M1 |
| Write to / Destination | Destination of what, and what object to choose? | Destination USB drive or folder | USB flash drive or destination folder | `app/localization/en.json:53`, `app/localization/fr.json:53` · O3 |
| Browse / Parcourir | Same word for file and technical secrecy; can also remind BROWSE. | Choose destination / Choose encryption key file | Choose destination / Choose encryption key file | `app/localization/en.json:11`, `app/localization/fr.json:11` · O3/K8 |
| Absolute path / path such as `/Volumes/... ` | He recognizes the name of his key, not his system notation. | Drive/folder name ; full location in details | Key/folder name; full location in details | `app/ui/web/app.js:116` · O2/O4 |
| Encryption key / encryption key | Confusion with USB flash drive. | Encryption key — file needed for preparation | Encryption key — file necessary for preparation | `app/localization/en.json:51`, `app/localization/en.json:51` · K2; **Glossary retained** |
| Source archive / archive source | He thinks he needs to extract or program something. | Initial download ; source archive in details | Initial download; source archive in details | `app/localization/en.json:295`, `app/localization/en.json:295` · K2; **Glossary retained** |
| Maintenance mode / mode maintenance | He can look for a combination of buttons or fear a repair. | Keep legal term ; explain initial preparation in the task heading | Keep the legal term; explain the initial preparation in the course title | `app/localization/en.json:304`, `app/localization/en.json:304` · K1/K4; **Glossary retained** |
| “moddable”, “unlock a special mode” (French copy) | Gives an opaque and different explanation of EN. | Task heading: Initial setup | Course title: Initial preparation | `app/localization/en.json:304` · K4; **no single substitution under conditions** |
| GPL, fingerprint, licences, MPL 2.0 | It is not used to prepare his music. | Keep unchanged in the full terms, under a clear heading | Keep under full conditions, under a clear heading | `app/localization/en.json:304`, `app/localization/en.json:307`, `app/localization/en.json:309` · K4; ** legal meaning intact** |
| Archive part / part of archive; Opaque ZIP | He thinks he has to open several files. | Downloading Pioneer DJ files · {part}/{count} | Download Pioneer DJ files · {part}/{count} | `app/localization/en.json:298`, `app/localization/fr.json:298`, `app/firmware/key_source.json:6` · K5/K6 |
| Failed verification / failed verification | No obvious next action. | Downloaded files did not pass verification ; update Toolkit | The downloaded files did not pass the check; Update Toolkit | `app/localization/en.json:301`, `app/localization/fr.json:301` · K6 |
| Retained key / saved key | Where is it kept? | Encryption key saved on this computer | Encryption key saved on this computer | `app/localization/en.json:387`, `app/localization/fr.json:387` · K8 |
| Separation engine / separation engine | He doesn't know what to install. | Stem preparation tools | Stem preparation tools | `app/localization/en.json:148`, `app/localization/fr.json:150` · S1 |
| Runtime / environment / environment | Detail of incomprehensible installation for this persona. | Preparation tools ; installation | Preparation tools; installation | `app/stems/provisioning.py:351`, `app/stems/provisioning.py:685` · S1/T5 |
| audio-separator, FFmpeg, PyTorch, pip | Names of components used instead of a usable condition. | Installing preparation tools ; component names in details | Installation of preparation tools; component names in details | `app/stems/provisioning.py:354`, `app/stems/provisioning.py:606` · S1/T5 |
| Python interpreter, venv | True prerequisite, not a term that can be erased by renaming it. | Python {versions} is required to install the preparation tools | Python {versions} is necessary to install the preparation tools | `app/stems/provisioning.py:550` · S1; keep the actual limit |
| Run on / Calculation on ; Accelerator | The DJ doesn't choose a calculation method. | Processing hardware · Automatic | Equipment used · Automatic | `app/localization/en.json:147`, `app/localization/fr.json:149` · S4 |
| CPU only / CPU only | Acronym not useful for its current choice. | Computer processor | Computer processor | `app/localization/en.json:235`, `app/localization/fr.json:237` · S4 |
| Apple Silicon (Metal), NVIDIA CUDA, AMD ROCm, DirectML | Mixture of materials and technologies. | Apple chip / NVIDIA graphics card / AMD graphics card / Windows graphics acceleration | Apple Piece / NVIDIA Graphic Card / AMD Graphic Card / Windows Graphic Acceleration | `app/localization/en.json:236`, `app/localization/en.json:238` · S4; exact terms kept in detail |
| XML export; library (both localizations) | He knows his USB export and playlist. | USB rekordbox export first ; rekordbox XML export under Other music source | Export rekordbox on key first; export XML rekordbox under Other music source | `app/localization/en.json:151`, `app/localization/fr.json:153` · S2 |
| Source / output / destination | It must distinguish what is read from what is prepared. | Music read from / Stems saved to | Music read since / Stems recorded in | `app/ui/web/index.html:300`, `app/ui/web/index.html:310` · O4 |
| Model / preset / passes / shifted passes | The mechanism does not indicate the time or the useful result. | Quality setting ; longer/faster preparation | Quality adjustment; longer/faster preparation | `app/localization/en.json:458`, `app/localization/en.json:458` · S4; technical detail retained |
| Frequencies above 17.6 kHz | Real but cumbersome technical limit at the first level. | Frequency-range limitation, in quality details | Frequency limit, in quality details | `app/localization/en.json:227`, `app/localization/en.json:229` · S4; Don't deny it |
| Cache / local cache | He may think he removes the items from his USB drive. | Copies kept on this computer | Copies kept on this computer | `app/localization/en.json:290`, `app/localization/fr.json:290` · T5 |
| Clear cache / Clear cache | Purpose of removal not properly identified. | Delete saved copies on this computer | Delete copies kept on this computer | `app/localization/en.json:291`, `app/localization/en.json:291` · T5; keep confirmation |
| GiB, MiB, KiB / Gio, Mio, Kio ; bytes / octets | Numbers and units that it does not connect to the usual free space. | GB / MB, with decimal conversion | Go / Mo, with decimal conversion | `app/ui/web/i18n.js:38`, `app/localization/en.json:215`, `app/localization/fr.json:217`, `app/localization/fr.json:274` · K5/T5 |
| Symbolic link / symbolic link | No recognizable object on the screen. | Choose the actual music folder, not a shortcut | Choose the folder that contains the music, not a shortcut | `app/localization/en.json:273`, `app/localization/en.json:273` · T5; exact term in detail |
| Process detection / process detection | He has no action bearing that name. | Close rekordbox, then Check again ; if still blocked, keep the error details | Close rekordbox, then check again; if blocking persists, keep details | `app/localization/en.json:278`, `app/localization/fr.json:278` · T5 |
| Read-only; writable (both localizations) | It only counts to be able to register. | Cannot save to this USB drive. Choose another drive. | Could not record on this USB drive. Choose another key. | `app/localization/en.json:37`, `app/localization/fr.json:37` · O3/T5 |
| Package / pack of stems | The DJ is looking for a piece and his stuff, not a container. | Stem files | Stem files | `app/localization/en.json:470`, `app/localization/fr.json:470` · T5 |
| Encoding / encodage | Technical step without associated gestures. | Preparing {role} | Preparation: {role} | `app/localization/en.json:286`, `app/localization/fr.json:286` · T5 |
| At destination / At destination; Imported / Imported | Source of misidentified listening; The selected files are not necessarily written. | Saved stems / Selected files | Saved stems / Selected files | `app/localization/en.json:347`, `app/localization/fr.json:347` · S6 |
| INST, VOCAL, DRUMS, INSTRUMENTAL | Tags of commands to recognize, even if English. | Keep control labels ; explain Instrumental, Vocal, Drums nearby | Keep controls; explain Instrumental, Voice, Battery nearby | `app/ui/web/stems-listen.js:10`, `app/ui/web/rx3-mock.js:392` · S6/S10; **do not translate physical command** |
| Alignment, correlation / setting, correlation | He must know if the sound starts in the right place. | Stem may not line up with the track | Stem may not be set with the piece | `app/localization/en.json:326`, `app/localization/fr.json:326` · S7 |
| Factor gain / gain factor; Standardization / standardization | Digital ratio without listening threshold. | Export again at the original level, without processing | Re-export to the original level, without treatment | `app/localization/en.json:328`, `app/localization/en.json:328` · S7; figures in detail |
| Residual energy / residual energy | No reliable DJ conclusion to draw value alone. | Listen to the instrumental ; analysis details | Listen to the instrumental; details of the analysis | `app/localization/en.json:334`, `app/localization/en.json:334` · S7; value retained |
| Audio frames / frames; encoder padding / encoder offset | Length/calage details, not a gesture in rekordbox. | Export the full track with the same start and end | Re-export the complete piece with the same beginning and end | `app/localization/en.json:324`, `app/localization/fr.json:324`, `app/localization/en.json:333`, `app/localization/fr.json:333` · S7 |
| Loss / no loss; subtraction / subtraction | The DJ must choose an export format, not understand the calculation. | Export as WAV, AIFF or FLAC without lossy compression | Export in WAV, AIFF or FLAC, without loss compression | `app/localization/en.json:322`, `app/localization/en.json:322` · S7; format and constraint retained |
| Time stretching / time stretching | Term to be linked to a musical action. | Export again without changing track length or tempo | Re-export without changing the duration or tempo of the song | `app/localization/en.json:327`, `app/localization/fr.json:327` · S7 |
| Clipped to 16 bits / bounded in 16 bits | He needs to know what to listen to, not count the samples. | Clipping detected ; listen for distortion | Sensing detected; check to listen to the absence of saturation | `app/localization/en.json:288`, `app/localization/en.json:288` · T5; number/format in detail, technical "sample" retained |
| Error code / engine code | Don't say what to do. | Stem preparation stopped ; error details | The preparation of the items was stopped; error details | `app/localization/en.json:443`, `app/localization/fr.json:443` · T5 |
| RX3_STEMS, original/source file, collision | Rename files by hand comes out of the DJ course. | Track name ; “Two tracks use the same exported name” | Name of the song; "Two pieces have the same name in export" | `app/localization/en.json:436`, `app/localization/en.json:436`, `app/localization/en.json:446`, `app/localization/en.json:446` · T5; do not invent an automatic resolution |
| Bank / banque ; active bank / banque active | Bank included after explanation ; active must designate what will play. | Bank used on the deck | Bank used on RX3 player | `app/localization/en.json:104`, `app/localization/fr.json:106`, `app/ui/web/samples.js:524` · A3 |
| Initial volume / volume initial | Initial when? | Volume when the bank loads | Volume at bank loading | `app/localization/en.json:108`, `app/localization/fr.json:110` · A6 |
| RGB, #RRGGBB ; ASCII, underscore | Data entry constraints. | Choose a colour ; name example “Set-1” | Choose a color; example name "Set-1" | `app/localization/en.json191`, `app/localization/en.json193`, `app/localization/en.json189`, `app/localization/en.json191`, `app/samples/bank.py:341` · T5; preserve existing validation |
| Classic / Classic ; canvas dimensions | The DJ sees an area, not a web of pixels. | Centre area / Full width | Central area / Full width | `app/localization/en.json:372`, `app/localization/fr.json:372`, `app/ui/web/logo.js:311` · L3 |
| Invert greys / reverse grays | Unspeakable without results shown. | Adapt whites and greys for a light screen | Adapt white and grey to light screen | `app/localization/en.json:369`, `app/localization/fr.json:369` · L3 ; keep the exact explanation and preview |
| Core / decoder-sleep / decoder wait / CPU wakeups | Names of mechanisms without musical choice to make. | Shared components / Audio recovery after a Beat Jump | Common Components / Audio recovery after a Beat Jump | `mod/modules/core/manifest.json:4`, `mod/modules/decoder-sleep/manifest.json:8` · M4 |
| Logging / journal / verbose / diagnostics | Troubleshooting presented as a mix function. | Troubleshooting report / Detailed troubleshooting report | Troubleshooting / Detailed Troubleshooting Report | `mod/modules/logging/manifest.json:4`, `mod/modules/logging-verbose/manifest.json:4` · M4 |
| Telnet, root password / mot de passe root | Real technical handling; No synonym makes it simple. | Technical troubleshooting access (Telnet) | Technical troubleshooting access (Telnet) | `mod/modules/telnet/manifest.json:8` · M4; details and conditions of use retained |
| Terminal, source folder, command / terminal, dossier source, commande | The persona can't use them. | Technical setup for streaming software | Technical configuration of the distribution software | `mod/modules/now-playing/manifest.json:40`, `mod/modules/now-playing/manifest.json:47`, `app/ui/web/app.js:490` · M3; commands kept in details |
| UDP port, firewall, JSON / port UDP, pare-feu, JSON | Integration requires non-personal skills. | Connection details for the streaming software | Diffusion Software Connection Details | `mod/modules/now-playing/manifest.json:41`, `mod/modules/now-playing/manifest.json:48` · M3; Technical values retained |
| Overlay | The useful result is the title displayed in the stream. | Track-title display in your stream | Displaying titles in your stream | `mod/modules/now-playing/manifest.json:8` · M3; do not promise that the product |
| Energy Boost +2/+7, Experimental +4 | Can be confused with a number of half-tones. | Energy Boost · +2/+7 Camelot ; Experimental · +4 Camelot | Energy Boost · +2/+7 Camelot ; Experimental · +4 Camelot | `mod/modules/key-match/manifest.json:39` · M2 ; keep the existing musical warning |
| Maximum transposition | Musical term possibly known; the number must keep its reference. | Maximum key shift (semitones) | Maximum transposition (halftones) | `mod/modules/key-sync/manifest.json:34`, `mod/modules/key-sync/manifest.json:44` · M2 |
| Reconnect / Reconnect | He's looking for a physical connection that doesn't exist. | Try again | Try again | `app/localization/en.json:383`, `app/localization/fr.json:383` · O5 |
| Stock / uninstall / restore / reflash | The DJ wants his original functions back. | Use the deck without modules | Use RX3 player without modules | `README.md:308` and no help in `app/ui/web/index.html:63` · R1 |

<a id="doc-ux-audit-dj--termes-du-brief-qui-ne-doivent-pas-devenir-de-faux-constats"></a>
###### Terms of the brief that must not become false findings

- **Sidecar / sidecar file (`.rx3stem`)** is in `.claude/STYLE.md:25`, but no current main wording of the catalogues or inspected frontend uses "sidecar". Do not pretend that a screen asks. **Explicit evolution of the proposed glossary for consumer prose:** EN **stem file** / FR **Stem file**, with exact extension only in detail. Keep "sidecar file" as a technical term where necessary. Do not infer that a single format is still used everywhere.
- **exFAT / FAT32** appear in the README prerequisites (`README.md:74`), not in a formatting selector of the five screens inspected. Do not invent this selector or add formatting. If these terms must be shown: EN **USB drive format supported by the XDJ-RX3 (FAT32 or exFAT)** / FR ** USB drive format accepted by the XDJ-RX3 (FAT32 or exFAT)**, keeping the exact names and without promising newly verified external compatibility.
- **Decryption** describes the need in the brief; official replacement is not proposed. Keep **encryption key / encryption key** in texts, accompanied by explanation K2. Do not use "deactivation key": this would invent a licensing mechanism.
- **BPM, tone, hot cue, pad, sample, items, export rekordbox** are the vocabulary of the persona: keep. "Sample" remains the sound of the pad; "sample" remains the technical audio unit (`.claude/STYLE.md:22`). For **deck**, keep DECK 1/DECK 2 as screen labels; "RX3 player" means the complete apparatus. To complete the TODO in the glossary will have to preserve this distinction.
- **Power cycle**, still TODO (`.claude/STYLE.md:28`): **explicit proposed evolution of the glossary**, EN **turn the deck off and on again** / FR ** Turn off and turn on the RX3 player**. The original return procedure also includes reading stop and key removal, R1.

<a id="doc-ux-audit-dj--cohrence-fren-et-chane-documentaire"></a>
##### Coherence FR/EN and documentary channel

The phrases proposed to the DJ are at your service; Buttons use infinite. **rekordbox**, **XDJ-RX3**, format names and hardware labels remain accurate. The other capitals kept in the previews are screen markers, not forgotten chains to translate. The visible shell "Share information..." of `mod/categories.json:64` can become EN **« Share track information with your computer. * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * ** → **"Transmit the piece's information to your computer. This P3 · S patch is M3 and does not change the announced capacity.

The changed wording should be reflected in their references: `modules.needOutput`, `stems.needOutput`, `stems.needRuntime`, `logo.buildHint`, `stems.drumsModelPreset`, `stems.drumsModelImport`, `stems.drumsModelUnknown`, `stems.cpuFallback`, `error.key`, `error.keySyncMode`. Example final reference: **FR "Select the USB drive or folder where to save files. » / EN « Select the USB drive or folder where you want to save the files. **, followed by the direct link **"Choose destination" / "Choose destination"**; for installation, direct link to **"Stem installation and storage" / "Stem setup and storage"**. Don't get the DJ an old button name.

The README promises a simple preparation on USB and a return to origin by extinguishing/withdrawing/restarting (`README.md:8`, `README.md:308`), but still quotes tabs "Stems preparation" and "Installation Modules", a manual choice of firmware and different roles/pads (`README.md:150`, `README.md:217`, `README.md:298`). This documentary divergence does not justify adding these old steps to the IU. **Editorial recommendation associated with S10, P1 · M:** name current destinations, describe the compatibility displayed rather than an absent selector and publish a single validated physical instructions. This audit does not rewrite any of these files.

<a id="doc-ux-audit-dj--vrifications-de-lecture--effectuer-aprs-une-ventuelle-implmentation"></a>
##### Reading checks to be performed after possible implementation

These criteria are validation objectives, **not tests performed**. They remain in existing operations and can first be checked with local presentation data, without writing on a real key.

| Situation presented to the DJ | Success expected in less than 30 seconds | Findings concerned |
|---|---|---|
| First opening without encryption key | He explains why initial preparation is requested, finds his language and knows how to defer it or read the conditions. | O1, K1–K4 |
| Two USB flash drives, then change selection | It calls the music source and the actual destination of each screen, without guessing from a path alone. | O2–O4 |
| Selected modules, no file yet prepared | It distinguishes selection and presence on USB, and finds the following action. | M1–M5 |
| Installation Stems absente | He sees the installation before the settings and understands the limit if Python misses. | S1 |
| Playlist long, a song refused | He sees the number of pieces involved, rules voice/battery and quality, and identifies the piece to be corrected. | S2–S4, S8–S9 |
| Stems preparation completed | It listens to a song without importing a file, includes the audible items and the Original button. | S5–S7 |
| Touch preview/pads | It finds the same roles and understands touch versus hold/slide without waiting several loops. | S10, T3 |
| Framed logo | He knows that the logo is prepared locally and where to ask for its writing on the key. | L1–L3 |
| Sample added to pad 1 | It finds this selected pad, can listen, sees the bank used and the status of the Samples module. | A1–A6 |
| Download interrupted then successful | It recovers the retest action, reads the conditions, understands the result and voluntarily resumes Modules. | K5–K8 |
| Return to origin | It distinguishes removal of modules from the USB, deletion of the encryption key and extinction/restart of the RX3 player. | R1 |
| FR/EN, light/shadow, 880 × 560 and 1180 × 820 | It finds action, blocking pattern and destination without text cut or displacement due to ordinary refreshment. | O5, T1–T5 |

The current state already has the right DJ objects — USB export, playlists, pads, stems and RX3 preview. The priority is to make their chain obvious, show what has actually been recorded and reserve computer details where they help solve a problem.


<a id="doc-ux-audit-dj--mise-en-uvre-autorise--27-septembre-2026"></a>
##### Authorized implementation — 27 September 2026

The instruction "applies all these recommendations" allows implementation after the audit. The above line references describe the audited state; they are not renumbered after the amendments. This section describes the result. No dependency, no framework, no audio service or Python-JS contract has been added or modified. No commit, key download, network access or trial on real USB drive.

<a id="doc-ux-audit-dj--correspondance-avec-les-constats"></a>
###### Correspondence with findings

| Constat | Implementation in the interface |
|---|---|
| O1 | Use phrases displayed under titles; decision instructions in 14 px. |
| O2 | Key name, USB pictogram, access to content and active status in the sidebar; full location in the inspection. |
| O3 | Select destination contextualized and help explaining to select the key name, without entering its folders. |
| O4 | Actual destination with the preparation Modules; divergences with the context key indicated in Modules and Stems. Existing choices are retained. Music source and destination of separate items. |
| O5 | Local starter vocabulary, FR/EN backup before loading catalogues and image-specific message. Initial status covering the work area, without current connection band. |
| O6 | Music first, explicit unreadable export, localized module names and history of the last folded start. |
| M1 | "Selected" modules, visible destination, USB preparation or files according to the known destination; selection and presence on USB remain distinct. |
| M2 | Display settings for selected modules, folded relationships, MASTER reference and not explicit Camelot, View button in BROWSE. |
| M3 | Limit of explicit dissemination integration; command and configuration stored in a folded guide. |
| M4 | Trade names for components and troubleshooting; automatic inclusion indicated for Core. The group remains "Technical Components and Settings", because decoder-sleep remains selectable: it would have been misleading to rename it entirely "Included Components". Details and technical access retained. |
| M5 | Local help MENU (USILITY), without a fictitious RX3 player detection indicator. |
| S1 | Installation necessary up before music; translated state and gross detail retained. Back to the bottom when the tools are ready. |
| S2 | USB export on the first level; XML under Other music source. |
| S3 | Parts and quality before wave forms; Details of compatible pieces and already ready-to-be-folded wave shapes. Refusal and actions remain visible. |
| S4 | Quality compromise in first sentence, model and restrictions in detail. Explicit and folded material choices; values and defects retained. |
| S5 | Choice of song and listening common to both views, independent of import; access from the preparation result. |
| S6 | Separate source of controls, INST/VOCAL/DRUMS colours, gesture indication and time mm:ss. Original no longer shows the roles as simultaneously selected. The audio mask sent remains unchanged. |
| S7 | Mandatory voice, optional battery; advice on listening after import, technical measures kept in a leaflet. |
| S8 | References to real titles, including stem modes, KEY SYNC and installation. |
| S9 | Assessment of prepared and checked pieces; import counted as a result; separate details. Hidden bar after cancellation or failure. |
| S10 | Touch guides also available in Stems and Samples, permanent legend and manual steps. Former adversarial mapping of four items removed from the README and reference 7/8 not established removed from the glossary. Material reserve detailed below. |
| L1 | Box deactivated as long as no image was selected; visible explanation. |
| L2 | Continue in Modules becomes the main action after choice; secondary replacement, no automatic writing. |
| L3 | Silhouettes of zones, dimensions in detail, explicit wording, zoom to one decimal place; Only for framing when the preview is focused. |
| A1 | Inspector next to grid to default size; selection of an empty pad brings control of addition in view. Bank volume and SHIFT after publisher. |
| A2 | After adding, selection kept on the first completed pad; message from the added pad or range. |
| A3 | Bank used named, separate record state, suffix legible in selector, backup pattern before activation. Existing activation retained. |
| A4 | Presence of Samples module on the distinguished key of its selection for the next preparation; access to Modules if necessary. |
| A5 | Explicit Edit/Play modes; separate pad colour and read state, readable name, Stop everything. |
| A6 | Sound then extract/listening, mode, name/color and level; group extracts/listening side by side in the wide inspector. New local banks, volumes in %. |
| K1 | Purpose of initial preparation before conditions; Later shut down without getting the key back. |
| K2 | Distinction of different encryption / USB support, explanation and pictograms; initial download size displayed. |
| K3 | Language accessible in the modal, body using the available height, actions kept at the bottom. Language change reset reading and consent. |
| K4 | Three headings added; the seven legal paragraphs and the wording of acceptance remain strictly identical to the state before intervention. Reconciliation of the substance left to explicit validation. |
| K5 | Existing transfer meters displayed in decimal MB/MB; Indeterminate recovery phase retained, no percentage invented. |
| K6 | Explicit retest reopening conditions; Distinguished confirmed cancellation of the application; readable errors with archive and reason kept in details. Access to the current task in case of occupation. |
| K7 | Key ready then Continue in Modules; no automatic stringing to USB writing. |
| K8 | Distinguished available status of the manual file; Advanced folded management, manual choice and always accessible recovery. Deletion limited to the saved key, with confirmation explaining its scope. |
| T1 | Appearance of the application, module Clear theme and background of the overview appointed separately. |
| T2 | An operation error attached to its screen; searchable details; disappearance of USB playback and bank backup ads that doubled the content states. Progression in its place, global messages out of its area. |
| T3 | Sample Icon 2 × 4; Colors of harmonized roles; SVG Key Match retained; time 1:07 corrected. |
| T4 | Useful body and instructions in 14 px; inspectors side by side at 1180 px. At minimum width, Modules starts with choices, with destination and action in the header. |
| T5 | Correct decimal presentation of sizes and storage; vocabulary of local copies, stem files, shortcuts and recovery after error. Diagnostic translation keys retain their parameters so as not to lose Python data. |
| R1 | Removal of named and confirmed modules; Music/Stem/bank storage explained; number of files in detail and gestures back to RX3 player without modules in a separate help. |

<a id="doc-ux-audit-dj--vrifications-ralises"></a>
###### Audits carried out

- **41 passed tests**: `tests.test localization`, `tests.test key sync settings`, `tests.test tems screen`, `tests.test module consistency`, `tests.test docs hygiene`. Node `sample preview.cjs` and `stems preview.cjs` also end without error.
- **84 native rendering configurations pywebview**: FR/EN, light/shadow, requested windows 880 × 560, 1180 × 820 and 1440 × 900, six surfaces and second view Stems. The real web area measures 32 px less in height, because of the native title. No horizontal overflow, target less than 28 px, form control without name or unsolved translation key detected in this matrix.
- **43 successful route controls**: simulated pre-installation, diverging destination, sample addition, manual key file, consent and language change, transfer/failure/cancellation/success, draft preservation, destructive confirmations, preparation and import contracts. No automatic write call after successful key recovery.
- Contrasts of text/surface pairs tested at 4.5:1 threshold. The Impeccable sensor reported a width animation on the progression bar; this transition has been withdrawn.
- Exact comparison of the seven legal paragraphs and acceptance EN/FR with the working copy before intervention: identical.
- Changes in the translation of modules remain in their manifestations. No changes to service files, bridge or audio processing.

Reproducible proof: [native test harness](app/ui/web/design-audit/verify_ui.py), [validation results](app/ui/web/design-audit/dj-verification.json). The bench uses only simulated responses, except the local metadata allowed by its whitelist. The first pass detected the storage field too narrow; confirmation made the 84 configurations without anomaly. A correction of the test scenario (save your sample before changing the key) allowed the functional controls to be completed with `--flows-only`, keeping the confirmation rendering matrix. The prints of the final sources are recorded with the results.

<a id="doc-ux-audit-dj--limites-maintenues-volontairement"></a>
###### Voluntary limits

**K4 — legal basis.** The audit does not propose a reconciled legal version. The differences between EN/FR and the absence of NOTICE remain to be resolved before new conditions are published. The intervention concerns reading and access to consent, not obligations.

**S10 — hardware reference.** No validation on XDJ-RX3 n The numbers in the existing guide are therefore not a new validated material reference. The help added in Stems resumes the tactile gesture established in the texts of the repository, without adding a numbered map. README and glossary no longer affirm the old contradictory mapping.

Automated native testing does not validate Windows/WebView2, actual network acquisition, real USB drive, audio or hardware behavior. Screen capture by the native control tool was not available; rendering findings are based on DOM measurements actually painted in pywebview, not on human visual certification.


<a id="doc-ux-audit-dj--corrections-aprs-retour-visuel"></a>
###### Corrections after visual return

- Modules: two columns scrolling independently, including 880 px; The deactivation aid is in the right panel.
- Empty USB state: text across the width; the icon column is used only in the presence of the icon.
- Destination Modules/Stems: Remove the reference to the "Browse" button.
- Renowned Help **Disable mod**: "Stop the RX3, connect the USB drive to the computer and delete the autoexec.bin file from the USB drive. Future uses of the key will not activate the mod. » Version EN corresponding. This instruction replaces the previous aid R1; file removal operation remains separate.
- Installation and storage of items: open section, directly accessible equipment and storage; only the technical diagnosis remains foldable. The music source no longer displays a legend without a chosen source.
- "On your XDJ-RX3" renamed **Tutorial**, and **Tutorial** in English.

Validation of this correction: **13 successful targeted tests**, then new complete native matrix of **84 configurations without anomaly** and **56 successful course controls**, including independent scrolling in the 12 size/language/theme combinations. The results and prints of the sources are updated in `app/ui/web/design-audit/dj-verification.json`. No real USB network, download or support used.


<a id="doc-ux-audit-dj--rgression-de-hauteur-des-catgories-modules"></a>
###### Category height reduction Modules

The user capture revealed a gap in the previous validation: the absence of horizontal overflow did not guarantee that the options remained visible. In the new strained column, the automatic grid lines were compressed; categories then masked their options with `overflow: hidden`.

Fixed: `#modules .categories { grid-auto-rows: max-content; }`. Each category retains the height of its contents; scrolling always belongs to the column, regardless of the right panel. The bench now checks the inside height of each open category and the limits of its switches, in the 12 size/language/theme combinations. Result: **84 completed and 80 completed controls**. The earlier validation statements did not cover this vertical trimming defect.


<a id="doc-ux-audit-dj--tutoriel-du-logiciel"></a>
###### Software Tutorial

Requested addition of a destination **Tutorial / Tutorial** before Modules in the sidebar. The FR/EN guide explains the choice of the key, the selection of modules, the recovery of the encryption key and the installation of the mod, then the optional paths Stems (preparation, import, listening), Samples and Logo, the settings and deactivation. Shortcuts open existing screens without triggering operation. Modules remain the initial screen. Product and disposal instructions are updated for this new destination.

Validation: six successful localization tests, **96 native configurations without anomaly and 95 successful controls** including opening the tutorial, its shortcut to Modules and the presence of all side buttons in the minimum window. Simulated data only; no acquisition of real USB drive or operation.


<a id="doc-ux-audit-dj--installation-intgre-sans-panneau-droit"></a>
###### Integrated installation without right panel

At the request of the user, Modules now presents a list over the entire width. **Install mod** opens the destination and confirmation route. Without an available key file, **Continue** opens existing conditions; no download without explicit agreement. After acquisition, back to installation confirmation, without automatic writing. The download remains followed in the taskbar. No consent required to start. Compatibility, manual choice, key recovery and deletion remain accessible under Installation Options. The tutorial follows this path; user retouches of the French text outside this path are kept.

Validation: **13 successful targeted tests**, **120 native configurations without anomaly**, **101 successful controls**. The matrix includes the installation window with options closed and open to all three sizes, in both languages and themes. Explicit controls: lack of key request on startup, opening of destination without key, consent from installation, return to confirmation after acquisition and absence of installation triggered by acquisition alone. The tests remain fully simulated, without any actual USB download or support.


<a id="doc-ux-audit-dj--menu-installer-le-mod-et-simplification-usb--27-septembre-2026"></a>
###### Menu Install mod and USB simplification — 27 September 2026

- Permanent entry "Install mod" after Stems: summary of all checked modules, the chosen logo, sample banks and their registration status, the source and destination of the items, and then installation destination. The button was removed from Modules. Stem files and banks remain in their respective screens.
- Complete removal of the display of the last recorded boot and technical details in the USB screen. The selected medium appears under its name, without prefix " USB drive".
- Renowned aid "Disable mod in case of emergency"; procedure for deleting retained `autoexec.bin`.
- Validation: 13 targeted tests; 120 simulated pywebview configurations (FR/EN, light/shadow, three sizes), 105 successful path checks, no rendering defects detected by the controls. No operation on a real USB drive, no download. Evidence: `app/ui/web/design-audit/dj-verification.json`.


<a id="doc-ux-audit-dj--logo-automatique-stems-simplifi-et-prvisualisation-locale--27-septembre-2026"></a>
###### Automatic logo, simplified Stems and local preview — 27 September 2026

- Choosing an active image Logo via normal module selection rules. Warnings of activation and referrals to Modules have been removed. The Logo canvas remains a framing tool.
- In Stems, Open XML appears next to Open USB Flash Drive. Deletion of the wording Music read since, the estimate of preparation, the choice of destination, the ordinary details of the songs and the choice to generate waveforms. Warnings of refusal or ability remain usable; the preparation targets the selected USB drive and systematically includes waveforms.
- Preview contains the Piece Selector, the entire waveform, the Stem and Play/Pause commands. Removal of source buttons, separate viewing bar and update. Clicking on the waveform and the arrow keys/Home/End move the playback.
- Pre-listening loads once the song and its tracks, by transfers of ten seconds. The winning swings, pause and viewing then remain in Web Audio, without rebuilding or calling Python. An anti-click transition of 256 frames accompanies the gains, without stopping the transport. The waveform represents the entire original piece. Former pre-listening operations remain available; three session operations were added for this explicitly requested route. Temporary data are local, released after transfer; The buffer budget is limited to 1 Gio. A piece exceeding this budget is not previewed.
- The waveforms of the RX3 player are already calculated on CPU after finishing the tracks. No parallelism between the separation of a piece and the waveforms of the previous one was added; it would require separate management of the submission, cancellations and publication.
- All existing material guides and their mocks have been moved into Tutorial. Installation and storage of stems becomes Advanced settings, without shutter Technical details.
- Validation: 27 successful separate targeted tests (location, selection, Stems screen, Python/bridge pre-listening and Web Audio interactions), followed by 120 simulated pywebview configurations and 109 successful controls, with no fault detected. Audio tests use only synthetic temporary files; No real USB flash drive, no RX3 hardware validation or download. Proof of rendering and route: `app/ui/web/design-audit/dj-verification.json`.


<a id="doc-ux-audit-dj--correction-de-la-vue-tutoriel--27-septembre-2026"></a>
###### Correction de la vue Tutoriel — 27 septembre 2026

The previous view stacked a separate leaflet and demonstrations, with a duplicate Samples section. The harmonic preview had retained its floating window behavior. In addition, the rendering of the modules reconstructed the guides and reset their progress.

The view now presents one topic at a time: First installation, Samples, Stems, Harmonic Mixing, Logo, Diffusion, Settings or In case of emergency. Each subject brings together its stages and mocks. The harmonic preview remains in the page. The rendering of the guides is independent of the Module switches; the masked demonstrations are stopped. The FR/EN texts correspond to current paths, including automatic logo activation and systematic waveforms.

Audit: 13 successful targeted tests and rendering matrix extended to 204 configurations covering each topic, both languages, two themes and three sizes. The observed user window kept an old IU in memory; It has not been recharged to maintain its condition.


<a id="doc-ux-audit-dj--retour-aux-tutoriels-contextuels--27-septembre-2026"></a>
###### Back to contextual tutorials — September 27, 2026

At the request of the user, the Tutorial entry and its subject view are deleted. The material guides and their mocks are placed with each module; Samples, Stems and Logo screens contain their preparation help. First installation is moved to Install mod. The Associated Modules section disappears from the interface, without changing the dependency rules that determine the selection.

Disable mod in case of emergency is a permanent title and text in the USB screen. The procedure proposes, RX3 turned off and key connected to the computer, rename autoexec.bin as autoexec.bin.disabled or delete autoexec.bin. It indicates how to restore the original name after a renaming.

Validation: 13 successful targeted tests; 156 simulated rendering configurations also covering open guides, without detected defects. No USB flash drive files have been renamed or deleted.

---

<a id="doc-waveform-formats"></a>
### Waveform formats of stems

<!-- source: docs/waveform-formats.md | sha256: 8e26aa82a4e512128470a2acc5ac34d3f1966fbe6278197b7fd9f945386d7e5e -->


The Toolkit prepares together **Blue, RGB and 3Band** for the seven
audible combinations of the three-stem mode. No choice of format or confirmation My Settings is
necessary. Changing the RX3 display therefore does not require recalculation for the
new packages.

<a id="doc-waveform-formats--calcul-et-compatibilit"></a>
##### Calculation and compatibility

The installed engine uses NumPy and SciPy to decode the source once,
Filter blocks of two seconds in memory and produce all three formats.
He does not write PCMs or intermediate filtering. The memory estimate is
limited to 512 Mio; beyond, or without this engine, the previous path remains in use.
This estimate is not a memory measurement available on the computer.

The old packages remain legible. **Prepare the items** completes the formats
missing in the selected playlist, in the same job as migration and
addition of battery. Three already complete and valid items packages are
retained. There is no window or separate completion button.

The completion checks the identity of the source, copies existing PCMs without
separation and reencoding and replacing the package in an atomic manner. Cancellation
does not publish the current song; the pieces already finished remain valid.
Old My Settings format and print profiles no longer condition
this journey. Explicit format APIs remain available for compatibility.

<a id="doc-waveform-formats--lecture-et-contrat-binaire"></a>
##### Reading and binary contract

The RX3PKG2 container is kept. The complete preparation uses RX3WAV3,
MULTI format, 150 columns/second: one Blue byte, two RGB, three 3Band.
RX3WAV4 single format remains legible. Number 4 refers to this variant of
storage; Using version 3 for all three formats is not a regression.

The current mod provides the format chosen on the RX3. For an old package where
format missing, it retains the native waveform of the original piece, which does not
Then do not reflect the cut items. The sound of the poles remains usable.
Preview directly uses the stored columns.

<a id="doc-waveform-formats--mesures-et-validation"></a>
##### Measurements and validation

On Antisocial (5 min 24 s), the integrated path produced the three formats and
seven combinations in **17.274 s**, including worker launch, during a test
local also accompanied by automated tests. The Old Full Path
measured 37,216 seconds. The warm prototype was 13.430 s. These measures exclude
separating and publishing the package on USB; These are not guarantees.

The 2,040,306 bytes of the section are identical to the complete reference:
`1f89e913beef729aff6982d2a3c41ed18576a30c03af8d26bbee4046644f3ea2`.
See [in-memory waveform trials](#doc-waveform-in-memory-tests) for tested signals and corpus.
Windows, distributed package and a physical RX3 player are not validated by these
Local testing.

---

<a id="doc-waveform-in-memory-tests"></a>
### Waveforms in memory: test results

<!-- source: docs/waveform-in-memory-tests.md | sha256: 49cf5bd179cc521fefddf844dadc6207ef80dfa52b597193dbeae3fc16b8dc71 -->


Tests of 27 September 2026 on the local Python engine 3.12.13 with NumPy 2.5.2
and SciPy 1.18.0 already installed. No change in production path during
this pass: the prototype and its scripts are in
`local/research/waveform-memory-20260927/`.

<a id="doc-waveform-in-memory-tests--rsultat-sur-antisocial"></a>
##### Result on Antisocial

« Ed Sheeran - Antisocial (Extended MK Remix) », 323,7616 secondes, voix,
battery and instrumental, **seven combinations and three formats**:

| Variante | Time measured |
|---|---:|
| Previous built-in path, FFmpeg filters and intermediate files | 37,216 s |
| SciPy filters in memory, reference encoding | 17,820 s |
| Vectorized filters and encoding, decoded source in a file | 13,780 s |
| Flow decoding, seven combinations fed by the same blocks | **13,430 s** |

The last trial includes decoding, restoration of earnings, reconstruction of
combinations, filtering, pick extraction, Blue/RGB/3Band encoding, fingerprints
PCM and writing of the waveform section. It does not include the cold launch of
Python/SciPy, initial package check or USB release. A passage
per variant, not an average or a debit guarantee on another computer.

**Gain compared to the current three formats: ×2.77, i.e. -64 per cent. **
The exploratory target of less than 15 seconds is reached on this piece.

The whole section of 2,040,306 bytes is identical byte per byte to the
reference. SHA-256:
`1f89e913beef729aff6982d2a3c41ed18576a30c03af8d26bbee4046644f3ea2`.
The seven fingerprints of the reconstructed PCMs are identical. No difference Blue, RGB
or 3Band. The original MP3 and package remain unchanged.

<a id="doc-waveform-in-memory-tests--comment-le-prototype-fonctionne"></a>
##### How the prototype works

FFmpeg only decodes the MP3 once, towards a pipe. Two blocks
seconds feed the seven combinations; role PCMs are read directly
in the package. Winnings are applied once per block before combinations.
The rules of float32 and stereo silence remain the same.

Each combination retains its SciPy `lfilter` filter states between the blocks.
Peaks are reduced immediately to 150 Hz cells for Blue and 1 kHz
for RGB/3Band. Blue/RGB encoding is vectored; standards and windows
3Band keep their order of operations. The treatment keeps accumulators
from peaks to final normalization, without keeping the PCM complete.

The stream variant does not write **no PCM file or temporary filtering**.
She writes only the final waveform section and the test report.
Process RSS peak: **363 757,568 bytes**, approximately 364 MB decimals, against
480–483 MB for the first variants. This value includes Python/SciPy and
role mapping pages. Audio blocks are bounded; the peak tables,
remain proportional to the duration. It is not a universal pillar for
All the pieces.

<a id="doc-waveform-in-memory-tests--vrifications"></a>
##### Verifications

- Eight synthetic cases: silence, impulses at block borders, noise with
full-scale exceedance, several frequencies; at 44,1 and 48 kHz.
Blue, RGB and 3Band compared to the current calculation: zero byte different.
- One- or two-second block cutting: identical outputs on these eight cases,
including the last incomplete cell.
- Complete antisocial: 7 × 48 565 columns, three formats, identical to the reference.
- Real body: **eight exports and 401 250 columns 3Band**, exact comparison to
Pioneer files, test passed in 17,959 seconds. Sources and analyses
are checked by the test. This corpus check affirms 3Band identity; it
does not claim to revalidate the entire RGB/Blue corpus.
- Flow decoding identical to the existing decoding; longer and longer sources
short than the axis of the rejected stems.
- Cancellation during decoding: spread exception and stopped child process
then harvested. Full integration into the application's line of work remains
to be validated when replacing the worker.

SciPy uses a different filter production than FFmpeg: these tests
validate the **final bytes** on the mentioned signals and corpus, not an identity
universal filtered float64 samples. Windows and distributed package
have not been tested in this pass.

<a id="doc-waveform-in-memory-tests--dcision-propose"></a>
##### Proposed decision

The results justify the integration of the calculation in memory and the three formats
default. The format selection and My Settings alerts can then be
deleted. For old single format packages, complete waveforms without
Make the separation again. Keep the existing fold when the appropriate engine is
absent, check memory limits before allocation and preserve mechanism
of Atomic Publication. This pass tests the solution; it is not active yet
These changes produce.

<a id="doc-waveform-in-memory-tests--reproduction-locale"></a>
##### Reproduction locale

From the root, with the Python installed:

```sh
ENGINE_PYTHON='/Users/fbrille/Library/Application Support/RX3 Stem Studio/runtime/bin/python'
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/test_filters.py
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/test_stream.py
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/test_corpus.py
PYTHONDONTWRITEBYTECODE=1 "$ENGINE_PYTHON" local/research/waveform-memory-20260927/benchmark_stream.py
```

Evidence: `filter-tests.json`, `stream-tests.json`, `corpus.json`, `streamed.json`
and `streamed.rx3wave`, in the same local folder. The scripts refer to the
local user corpus; no third-party audio data is added to the public code.

<a id="doc-waveform-in-memory-tests--intgration-effectue"></a>
##### Integration

The production path now uses `wave memory.py`, loaded by the worker
optionally installed engine. The FFmpeg decoding inherits the process group
cancelable; temporary exits are cleaned in case of error. Calculation
previous is available if SciPy is absent or the estimate exceeds 512 Mio.
The three formats are prepared by default; choice of format and alerts
My Settings have disappeared from the user path. Old files can
be completed without modification of the PCMs.

Real Integrated Code Test: **17.274 s** on Antisocial, three formats,
seven combinations, complete section strictly identical to SHA-256 above.
Launch of the worker is included; tests were running simultaneously. None
Writing on the original key. Report:
`local/research/waveform-antisocial-20260927/production-memory.json`.

Validation of integration: 108 Python tests passed (acceleration, formats,
packages, migration, recovery, modes, winnings, cache and localization), three scenarios
Successful JavaScript (Sems screen, preview and audio), and nine native controls
successful pywebview. The completion window is checked in FR/EN, themes
light/shadow at 880 pixels, without overflowing or unsolved wording. Tests
include the cancellation of the worker and the withdrawal without accelerated engine.

---

<a id="doc-waveform-performance-antisocial"></a>
### Calcul des waveforms — Antisocial (MK Remix)

<!-- source: docs/waveform-performance-antisocial.md | sha256: 00c99b0966f2c7081e38bc293b4eacb577015c6da20620a3d377b9048e7a6078 -->


Local measure of 27 September 2026 on "Ed Sheeran - Antisocial (Extended MK Remix)", exact duration 323,7616 seconds. Format **Blue**, conforming to the setting recorded in `Desktop/key/RX3 STEMS/waveform-settings.json`.

The three audible items are voice, battery and instrumental. The package stores voice and battery; The instrumental is rebuilt from the original piece. The calculation covers the **seven non-empty combinations** at 150 columns/second, or 48,565 columns per combination. So these are not three independent waveforms.

<a id="doc-waveform-performance-antisocial--rsultats"></a>
##### Results

- Current Code, Application Python 3.14.7: **75.920 s**.
- Current code, control with same engine Python 3.12.13: **59.123 s**.
- Prototype vectorized, Python engine 3.12.13 + NumPy installed: **10,038 s**.
- Writing the test package and verifications of the PCM: **0,235 s** additional.

**Identical interpreter gain: ×5.89 (−83%).** Compared to the current application environment: ×7.56, with a change in interpreter in addition to vectorization. The three outputs are identical byte for byte.

These measures cover `waveform.build`: MP3 decoding, reconstruction, temporary files, filtering, peak reduction, encoding and waveform validation. Initial extraction of the package is out of timing. Data is read on local storage; This is not a transfer measure to a physical USB drive. One passage per variant, with no statement of average or Windows performance.

<a id="doc-waveform-performance-antisocial--o-passe-le-temps-actuel"></a>
##### Where is the current time?

| Step | Secondes | Prototype |
|---|---:|---:|
| Reconstruction of the seven combinations | 45,351 | 0,771 |
| PCM reading and return of gain | 14,271 | 0,289 |
| Reduction of peaks | 7,469 | 0,283 |
| FFmpeg process, including decoding | 7,365 | 7,576 |
| Blue encoding | 0,087 | 0,145 |

Detailed timings are inclusive: `columns` includes FFmpeg, peaks and encoding; Do not add up all JSON counters.

<a id="doc-waveform-performance-antisocial--pistes-dacclration-par-priorit"></a>
##### Acceleration paths, by priority

1. **Vector the PCM processing and peaks in the existing engine.** The prototype replaces the Python loops of `mixing.reconstruct static`, `hear.read pcm` and `wave dsp.peaks` with NumPy operations. This is the demonstrated gain. NumPy is already present in the separation engine, but absent from the light environment of the application: the recommended integration passes through a worker of this engine, without installing a new dependency in the interface. Keep a current fold if the engine is missing. Keep the order of rounded float32, gain correction and stereo silence rule.
2. **Reduce intermediate files and repeated passages.** `waveform.py:143–168` read the original and the items for each combination; `wave dsp.py:187–201` writes then reads two float64 releases for Blue. On this piece, these only outputs represent about 1.60 GB written and then re-read. Treating the seven combinations per block and reducing peaks over filtering would avoid part of the I/O. Gain remaining unmeasured; keep the filter states between blocks and the exact column boundaries.
3. **Straighten the filtering of combinations.** After vectorization, FFmpeg represents about three quarters of the time. Test two workers, then adapt to CPU and storage, instead of running seven calculations per piece without limit. Gain not measured and not necessarily linear; monitor disc restraint, memory, cancellation and coexistence with separation.
4. **For 3Band, also vectorize slippery window envelopes.** `wave dsp.three band` repeats a loop of 100 to 300 milliseconds for each column. The Blue benchmark does not measure this cost. An acceleration of this path requires its own reference and binary comparison; Blue results do not generalize to other formats.

<a id="doc-waveform-performance-antisocial--livrables-et-intgrit"></a>
##### Deliverables and integrity

Everything is under `local/research/waveform-antisocial-20260927/`: reproducible scripts, JSON timings, reference waveform, vectorized waveform and `.rx3stem` test package. The original prototype is limited to this file. Its subsequent integration is described below.

- Identical reference and vectorized waveforms, SHA-256: `fb4a9a671e7270a1ddc8c006e3e55ac3619c94697305dbbc2ec6a78e640404d5`.
- Test package: `Ed Sheeran - Antisocial (Extended MK Remix).rx3stem`, 114 564 750 bytes, validated by `package.read`, PWV3 format, seven combinations.
- PCM identical voice and battery in the test package; No new separation.
- SHA-256 of the MP3 and original package unchanged. No replacement in `Desktop/Key`.

The previously displayed 1–2 minute order of magnitude corresponds well to the current code on this example. After integration and multi-format validation of the prototype, this estimate will have to be reviewed; Now announcing ten seconds for all computers and keys would be unwarranted.

<a id="doc-waveform-performance-antisocial--intgration-du-chemin-acclr"></a>
##### Integration of the accelerated path

The accelerated path is now integrated. `wave acceleration.py` launches
`wave worker.py` with the already installed Python engine. Application does not depend
not directly from NumPy and does not install anything; the existing calculation remains available
if the engine/NumPy is missing. Errors occurring during a calculation are not
not masked by a new automatic calculation.

- Vectorized reconstruction with identical gain correction and stereo silence.
- Two combinations processed per batch, with reading/correction of shared roles.
- Up to two competing filters; for the three formats together,
return to one if the available temporary space does not cover both lots.
- 3Band vectorized slippery window frames and envelopes; large tables
transferred to binary rather than JSON; rounded and encoding
retained. Intermediate filtering files still exist.
- Processes recorded in the existing cancellation control, context transmitted
the threads and closure of the worker at the end of the calculation or in case of error.
- Independent worker included in the packaging recipe; distributed package and
Windows not validated during this pass.

Complete antisocial: **Blue 6.529 s**, **×11.63** vs. previous code
executed by the same application Python (75,920 s). The Waveform Blue completes
is identical byte for byte at reference. **3Band 16,114 s**, identical byte
for byte to the section of the original packet corrected for gain. Original files
no publication on the key.

Validation: 80 tests performed, 78 successful and 2 ignored due to lack of external fixings.
The seven new tests check the seven masks with gain, the four
Outputs (Blue/RGB/3Band/all formats), 3Band window limits, equality
between parallel calculation and folding, monotonous progression, worker errors,
the cancellation and absence of the engine. A future work may remove
temporary filtering files themselves; it will require the maintenance of the
filters and exact column boundaries.

<a id="doc-waveform-performance-antisocial--calcul-des-trois-formats-ensemble"></a>
##### Calculation of the three formats together

Complete antisocial, even seven combinations: **37,216 s** with final path
accelerated and no more than two filterings. The first serial test took 43.544 seconds.
An intermediate test competing with the tests took 35,200 seconds:
make an average or assign this deviation to a single optimization.

The all sizes section occupies **2 040 306 bytes**, compared to **340 531 bytes** for
Blue alone, or **1 699 775 additional bytes** (approximately 1.5% of the audio package)
114.6 MB). Blue and 3Band outputs extracted are identical to references
actual; the full section is also the same between the serial calculation and
the parallel calculation (SHA-256 `1f89e913beef729aff6982d2a3c41ed18576a30c03af8d26bbee4046644f3ea2`).

Product recommendation: calculate the three default formats becomes reasonable
to remove the choice and recalculations when changing the setting
RX3. The measured compromise is about 31 seconds extra per piece of
Five minutes 24 seconds compared to Blue alone. A thousand pieces still represent several
hours: it's not free. The unique format remains the product behavior
current; the benchmark all formats did not change this choice or write on the key.

<a id="doc-waveform-performance-antisocial--intgration-du-calcul-en-mmoire"></a>
##### Integration of calculation into memory

The integrated path now prepares Blue, RGB and 3Band together: **17.274 s**
on Antisocial with the seven combinations, worker included. Same result
byte for byte at full reference. See
[the in-memory trials](#doc-waveform-in-memory-tests) et
[the current path](#doc-waveform-formats). Previous measures
page remain the historical results of FFmpeg paths and single format.

---

<!-- END INTEGRATED DOCS -->
