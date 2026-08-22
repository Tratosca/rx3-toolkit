<!-- SPDX-License-Identifier: MPL-2.0 -->
# Engineering reference

How this toolkit works, and what we learned about the player while building it.

It assumes you (or your AI) know C, shell and Linux, and nothing about DJ equipment. You do not need any of
this to *use* the applications; please start from the [README](README.md) for that.

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

Everything you see on the screen (browser, waveforms, effects, settings) is
that one process. It is not stripped, which is the single fact that makes any of
this work: symbol names survive, so the binary can be read rather than guessed
at.

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

At runtime the effective root is a 60 MiB `tmpfs` assembled from the system and
application images. Because more than one filesystem can be mounted at `/`, the
*last* matching entry in the mount table is the live one: anything inspecting
mounts has to read it that way or it will report the wrong filesystem.

---

## 2. How a mod runs without flashing anything

The player has a maintenance path: on boot it looks for a specific encrypted
image on a USB volume and, if present, runs a script from inside it. That is the
entire mechanism. We write to the stick, never to the player.

The consequence worth internalising: **power off, remove stick, power on, and the
player is stock again.** There is nothing to uninstall because nothing was
installed. It also means a mistake cannot brick anything, **as long as it does not write to the system persistent partitions**, which this project will focus on not doing. The worst case is a
player that fails to start the modified application and falls back, or a crash during a gig.

### The autoexec image

The image is an ISO 9660 filesystem carrying a startup script and the runtime it
launches, encrypted sector by sector so the player will accept it.

| | |
| --- | --- |
| Cipher | AES-256-CBC |
| Unit | independent 512-byte sectors |
| Initialisation vector | the sector index as a 32-bit little-endian integer, then 12 zero bytes |
| Key input | the first line of a key file you supply |
| Effective key | the first 31 bytes of that line, followed by one zero byte |

That 31-byte quirk is not a design choice, it is a bug preserved for
compatibility: the original code copies the key with a bounded string copy that
reserves a byte for a terminator. Using the first 32 bytes directly produces a
different key and an image the player rejects.

Two practical consequences. Rock Ridge extensions must be enabled or the startup
script loses its executable bit. And the image size must stay a multiple of 512
bytes, because the encryption unit is a sector.

The key is yours to supply. It is not in this repository and never will be.

### The hook

Features are implemented as a shared library injected into the application with
`LD_PRELOAD`. It is compiled as an ARMv7 shared object, linked `-nostdlib`; libc
and pthread symbols resolve against the host process at load time.

One build flag is load-bearing and worth knowing about before it bites you. At
`-O2`, Clang rewrites `memcmp(a, b, n) == 0` into a call to `bcmp`, which this
player's libc does not export. The hook then fails to load with an undefined
symbol, silently, and every run falls back to stock behaviour with nothing in any
log to say why. The rewrite happens after the front end, so no warning fires.
`-fno-builtin-memcmp -fno-builtin-bcmp` prevents it, and a test pins the
resulting symbol set so it cannot come back.

### Modules

Each feature is a directory under a firmware version, described by a
`manifest.json`. The desktop application, the command line and the release
packager all read the same manifests rather than keeping their own lists.

| Field | Meaning |
| --- | --- |
| `id` | stable identifier |
| `firmware` | the exact firmware revision this targets; must match the directory name |
| `runtime_directory` | one directory name written into the image |
| `namespace` | shell prefix for every lifecycle callback, so modules cannot collide |
| `default` | selected unless the user says otherwise |
| `selectable` | `false` for internal services, which cannot be picked directly |
| `order` | load order; dependencies must sort earlier |
| `requires` / `conflicts` | module relationships |
| `files` | what to copy into the image, and what must be executable |
| `build_files` | headers this module owns at compile time |
| `arm_hook` | the ARM source and target this module compiles, if any |

The build resolves dependencies, rejects cycles and conflicts, and writes the
resolved load order into the image. Asking for one feature therefore pulls in the
internal core it depends on, without the caller having to know.

### The orchestrator

Insertion runs entirely through the manufacturer's own path. Nothing in this
project installs a hook into the boot sequence:

```text
player powered on
USB insertion
  the vendor's udev rule fires
  the vendor's decrypt script runs
    decrypts the image with the key and mounts it
    runs the startup script inside, as root
```

From there, one shared orchestrator does the work for every module: discovery,
validation, guarded writes, restarting the application, rollback and logging.
Each module contributes an adapter and its payload, and nothing else. Adding or
removing a module requires no change to the orchestrator — which is the whole
point of the manifest indirection.

**Before it modifies anything, it verifies all of the following, and refuses the
entire run if any one fails:**

1. the effective root mount really is a RAM filesystem;
2. the application's directory is not a separate mount;
3. the application's checksum is one it explicitly supports;
4. every location it intends to change currently holds either its stock value or
   the value it would write;
5. the application is stopped before its backing file is touched;
6. every write is read back and compared;
7. the replacement process survives eight seconds — otherwise the original bytes
   and preload state are restored and the application is started again.

Point 5 is not a nicety. Writing an executable's backing file while its pages are
mapped can kill the process with `SIGBUS`, and the failure looks nothing like a
patching bug.

Point 7 is what makes the whole approach safe to experiment with: the worst
realistic outcome is a few seconds of stock interface, not a device that needs
recovering.

Re-inserting a drive into an already-patched session is cheap by design. The
orchestrator restarts the application only for a location still holding its stock
value, or a module whose runtime part is not already live. Everything else is
recognised as done and skipped, so the interface neither freezes nor rescans.

The performance core still writes its diagnostic log to a path chosen for
compatibility with existing tooling, reachable only with the diagnostic shell
module enabled.

---

## 3. Changing a binary you did not write

Some features cannot be done from a preloaded library and need the application's
own machine code changed. The rule for all of them is the same, and it is the
most important idea in this codebase:

> Read the location first. If it does not hold exactly the bytes we expect,
> **stop**. Never write, never guess, never "try anyway".

A binary that does not match is a different binary. It might be a firmware
revision we have not studied, or a corrupted copy. Either way the safe response
is to refuse, and every patch path — on the device, offline, and under emulation
— implements that same guard and reads the value back after writing.

Each patch is stated twice: once for the device and once for the offline tool. A
test fails the build if the two ever disagree, because two copies of a constant
that drift apart is how you end up writing the right bytes to the wrong place.

### A worked example: longer beat jumps

The jump feature moves playback by a number of beats. Extending its maximum
touches five separate things, which is typical — a user-visible number is rarely
stored in one place:

| | What changes |
| --- | --- |
| A | the jump distances themselves |
| B | the guard that decides whether a jump is allowed (jumps pads will be off when what's left is shorter in the jump direction) |
| C | the threshold that lights the corresponding indicator |
| D | which images the pads display |
| E | a branch that made repeated presses wait for the beat grid |

The interesting part is A. The new value cannot be encoded as an immediate by the
floating-point instruction at that site, so the patch loads the constant through
a general register, moves it into the FPU, and converts the negative-path
magnitude calculation to single precision. Every jump distance involved is
exactly representable in single precision, which is what makes that conversion
safe rather than merely convenient.

D is a compromise worth admitting: the shipped display resources contain no
image with an arrow for 32 beats jump, so the patch reuses a non-directional
image from another page. The jog display is untouched — it is driven by a
separate controller with its own glyph set, which has nothing suitable.

---

## 4. The display

### Extending the image table

The application draws from a table of several thousand fixed-size image records.
Every draw call resolves an image by index through one lookup function, and that
function rejects any index at or past the table's declared count. To show our own
artwork we need entries that do not exist.

The obvious approach — hook the lookup function — was tried and rejected. That
function runs continuously from the rendering path, so patching it while the
process is live opens a window where the code is half-written. The result
crashed shortly after activation. (The fallback worked correctly and restored the
stock application, which is the only reason that experiment was cheap.)

What works instead touches nothing hot:

1. Before the application starts, one guarded instruction is rewritten so the
   declared table size is larger.
2. At startup the hook allocates a second, larger table.
3. Every original record is copied across, with its pixel offsets adjusted so it
   still points at the original artwork.
4. Our own records occupy the new entries past the end.
5. Only when the whole table is ready is the global pointer swapped, in one
   atomic write.

The original artwork and indices are never modified. A model of the relocation
verifies every copied record as well as the new ones.

**The mistake this replaced is instructive.** An earlier attempt reused a block of
indices that looked unused. They were not: they were the colour swatches for the
source selector, and the display literally read "Aqua", "Blue", "Default". Because
drawing surfaces are decoded and cached, overwriting the pixels late could never
be made deterministic. Two apparently unrelated bugs — leaks into the source
screen, and colour names appearing in performance mode — turned out to be one
collision.

### The bitmap font

The player's fonts are flat arrays of fixed-size cells, one per glyph, in
codepoint order. No header, no offset table, no metrics.

| | Main Latin font |
| --- | --- |
| Row stride | 7 bytes |
| Cell size | 14 × 27 pixels |
| Bytes per cell | 189 |
| Glyphs | 422, covering Latin, Greek and Cyrillic |
| Index | codepoint − 32, so index 0 is the space character |

Pixels are 4 bits each, two per byte, leftmost pixel in the high nibble. The
value is coverage from 0 to 15 — plain anti-aliasing, no palette. That is where
the sixteen grey levels visible throughout the interface come from.

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

The file is 42 bytes shorter than 422 cells would be: the final glyph's trailing
blank rows are simply not stored, so a reader must zero-fill the tail. A sibling
font uses the same scheme with a different stride, which tells you this is a
house format with one fixed size per file rather than a one-off.

**What the file does not contain is advance widths.** Glyphs sit left-aligned in
their cell with the remainder blank, so proportional spacing has to come from
somewhere else — in this case a metrics function reached through a table
populated at runtime. Since that table is filled in dynamically, its contents
cannot be recovered by reading the binary; you would have to observe it running.
Deriving the advance from the ink extent plus a fixed side bearing is a usable
approximation, but visibly tight on pairs like `Y -` and `+1`.

### Matching the typeface

The face is Helvetica Neue LT W1G. That is identified rather than guessed, from
two independent artefacts that agree: the desktop library software declares that
family in its own interface graphics, and "W1G" is the vendor's World 1 Glyph
set — Latin, Greek and Cyrillic — which is exactly the repertoire of the font
file. The face is licensed and not redistributable, so our label builder
approximates it with a system cut instead of bundling it.

The approximation is fitted, not eyeballed. Fourteen captions in the shipped
artwork segment cleanly into individual letters along blank columns, giving
ground truth for nineteen capitals. Cap height is a consistent 16 pixels with
round letters overshooting to 17 — itself confirmation that these are real font
renderings rather than hand-drawn artwork. Sweeping weight against size over that
ground truth and scoring mean per-pixel error picks Regular at 22 points, clearly
ahead of the neighbours.

An earlier fit chose Light at 24. It had been scored on whole-word bounding
boxes, which is a weak signal: weight and size trade off against each other and
still match a box. Per-glyph pixel error does not have that failure mode.

### Reusing the host's typeface at run time

Nothing in the drawing code sets a font. A control wears whichever face the model
it was cloned from was drawn in — which means picking the right model *is* the
typography, and there are two of them:

- **A pad label**, captured on its way into the text renderer before a live panel
  replaces that same draw. The capture takes the first plausible label, then
  upgrades once to one that also carries a fill, since that is a real button
  rather than a caption. This is the face the added controls use.
- **A header glyph**, twice the size, kept only as a fallback so that a panel
  forced open before the row has ever drawn shows something rather than nothing.

The row itself is painted from the pane backdrop, which opens once per pass over
the row rather than once per intercepted call. Draws elsewhere in that subtree
are the stock furniture the panel stands in for and are dropped; draws *outside*
it belong to the vendor and reach the renderer untouched. Keying that test on the
deck's window instead of the widget subtree is what used to swallow unrelated
labels elsewhere on screen.

### The palette question, still open

Worth writing down because the honest state of it is "we know what, not how".

The stock colours are known, measured off the shipped artwork: a two-pixel frame,
a selected fill with black glyphs, an inactive state with grey glyphs. What is
*not* known is the encoding the glyph's colour field wants.

The text renderer decodes that field three different ways, choosing by the pixel
format of the window it is drawing into — which it reads from the window, not
from the glyph. One branch takes the low byte alone, one the whole word, one
unpacks a packed 24-bit value into 5/6/5. Measured against the real layers: one
interpretation painted magenta lettering on green, another painted green, and
sweeping all 256 low-byte values moved the green channel alone without ever
lifting red or blue off zero.

So the code returns zero, which means "leave the cloned model's colour alone".
Settling this means identifying the format the window actually reports for those
layers and using that branch's encoding. Until then, the pressed state the touch
layer already tracks has nothing to paint itself with. An earlier note in the
source that every literal colour "looked foreign" is thereby explained rather
than repeated.

### Two sizes of one face

One more thing that costs an afternoon if you miss it: **there are two sizes of
the same face in play.** The font file is a condensed cut, roughly half the width
and slightly taller, used for live text like track titles. The captions beside
the effect controls are pre-rendered artwork in the normal width. A label meant
to sit in that row must match the artwork, not the font file.

---

## 5. Front-panel input

Every physical control reports a 16-bit code. The complete list was recovered
**statically**: one function maps each code to a human-readable name for
diagnostics, so decompiling it and resolving the string pointers yields the whole
table without pressing a single button.

The decompiler folds some branches into range comparisons rather than
equalities, so six codes were re-read from their guard conditions rather than
inferred. As an independent check, the extraction reproduced the two pad codes
that had already been established much earlier by a completely different route.

This replaced a far worse plan. Mapping the panel by capturing traffic on the
internal bus needs one press per control, a person standing at the machine, and a
synchronisation window that is easy to miss — two attempts failed on exactly
that. Reading the table is one offline pass with no hardware involved.

Bus capture keeps one use: it alone tells you *which bit of which frame* carries a
control. But you do not need that to *inject* input. The handlers take an input
object whose layout is known — a 16-bit code, a channel selecting which deck, and
a press/release flag — so synthesising one is enough.

The complete code table lives in [Appendix A](#appendix-a-front-panel-codes).

---

## 6. Stems

The largest feature: replacing or removing the vocal from a track in real time,
from a sidecar file prepared on a computer.

### Hooking the audio path

Four sites are hooked with guarded trampolines: the function that hands decoded
audio to the mixer, the one that associates a file with a deck, the pad handler,
and the indicator refresh.

Each site has an eight-byte prologue guard. Three of them can have their stolen
instructions copied straight into the trampoline. The fourth begins with a
PC-relative load, whose meaning depends on where it sits — so that trampoline
loads a copy of the original constant before replaying the instruction after it.
This is the standard hazard of prologue-stealing hooks and the reason each site
is inspected individually rather than handled by one generic routine.

### Finding the right sidecar

The hook derives a track's base name and looks for a matching sidecar in a fixed
directory on the stick.

Two details make this harder than it sounds. The library software truncates a
filename to the first 44 characters when it exports a track, leaving the original
untouched — so the name on the stick is not the name in the library, and the
preparation tool has to apply the same truncation when naming sidecars. Trailing
spaces survive that cut on both sides and are not trimmed.

Second, two different tracks can truncate to the same name. The load interface
gives no reliable way to tell them apart, so the tool **refuses the collision**
rather than picking one arbitrarily. Truncation is applied before that comparison,
because two names that differ only past character 44 collide on the stick.

Sidecars load asynchronously into anonymous memory. The deck stays on the stock
audio path until loading finishes, after which the file on the stick is closed —
so pulling the drive after a completed load cannot invalidate a live mapping.
Allocation is refused if the payload would exceed 60% of the memory estimated to
be available or reclaimable.

### Getting the audio right

This is where the real engineering is, and both problems are silent failures:
everything appears to work and the result is subtly wrong.

The instrumental is computed as *full mix minus vocal*. That subtraction is only
valid if both come from the same decode. Any difference in phase, delay, gain or
sample rate leaves audible residual vocal.

**Delay** is introduced by the container. Compressed formats declare samples the
encoder prepended, and decoders normally drop them — so position zero of a normal
decode is not position zero of what the player's own decoder emits, padding
included. A delay of about a thousand samples puts the stem 25 ms ahead of the
mix, which leaves the vocal essentially untouched in the instrumental while the
isolated vocal still sounds perfectly fine. You will not hear the bug in the
thing you are listening to.

The encoder therefore decodes each source twice, with and without padding
removal, locates the trimmed decode inside the untrimmed one to measure the
padding exactly, and shifts the stem by that amount. Uncompressed sources declare
no padding and are unaffected. When the offset cannot be measured — a silent
decode has no unique pattern to locate — the stem stays on the separator's grid
and the run says so rather than guessing.

**Gain** is broken by the separator. Two of the common model architectures scale
the mix to a normalisation threshold before inference and emit the stem in that
scaled domain. A threshold below 1.0 therefore multiplies the vocal by some
factor and leaves the remainder of it in the instrumental — roughly −20 dB of
leftover vocal at the tool's own default of 0.9.

Pinning normalisation to 1.0 fixes the common case and is also the highest safe
value, since the writer converts to 16-bit integers in a way that wraps rather
than clips above full scale. But lossy codecs reconstructing inter-sample peaks,
or resampling from a higher rate, can still land above 1.0.

So the encoder measures instead of assuming: the pass that decodes the full track
also measures its true peak, and the stem is scaled back accordingly. One trap
here — the measurement has to be forced into floating point *ahead of* the
integer conversion, because filter chains are negotiated backwards from the
output format, and a measurement placed after the conversion reads values already
clamped to full scale and cheerfully reports no overshoot at all.

Only stems from architectures that scale the mix are corrected. The others leave
it alone. Correction restores the vocal to its true level, so anything that clips
is something that genuinely exceeded full scale in the source. The manifest
records the correction applied and the number of clipped samples per track.

Levels throughout are peak sample values relative to full scale, not perceptual
loudness. No loudness measurement is performed anywhere in this pipeline.

One last case: when the stock reader returns an all-zero region during a seek or
a buffer underrun, the hook leaves it alone. Subtracting a vocal from silence
would emit an inverted vocal. A 256-frame linear ramp covers each state change.

### Stems file format

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
| `0x40` | — | interleaved stereo audio |

The default is 16-bit to halve resident memory. The frame count is aligned to the
full track as decoded at 44.1 kHz, not to the separator's output duration.

The player's audio path runs at 44,100 frames per second — corroborated by the
constructor constants, the buffer sizes and the sample-rate converter it
instantiates. Sources at other rates are converted before they reach the hooked
buffer.

### Preparing sidecars on the host

Separation itself is not ours. The pipeline drives
[audio-separator](https://github.com/nomadkaraoke/python-audio-separator) and
FFmpeg as subprocesses, so nothing separation-related is linked into the release
archive — those dependencies together are two orders of magnitude larger than
the application.

Components are resolved in a fixed order, first hit wins: the `RX3_SEPARATOR` and
`RX3_FFMPEG` overrides, then whatever is on `PATH`, then a managed environment
installed under the user's data directory. Supplying your own is therefore
equivalent to letting the application install one; a separator found on `PATH` is
used as-is, reported as unmanaged, and never rebuilt or removed.

Three pins in that managed environment are deliberate and each has a reason:

- PyTorch comes from the CPU wheel index unless an accelerator is selected,
  because the default Linux and Windows wheels carry multi-gigabyte CUDA
  payloads a CPU pipeline never touches.
- `librosa` is held below 1.0, because audio-separator still imports `audioread`
  and calls `get_duration(filename=...)`, both removed there.
- The seeding interpreter is capped at 3.13, because audio-separator pins
  `beartype` below 0.19, which rejects the separator's own annotations on 3.14.

FFmpeg found on `PATH` is preferred over the bundled copy, but only once it is
shown to carry every filter the pipeline uses. Builds configured without one of
them exist, and the failure would otherwise land partway through a long job
rather than at startup. An explicit override is exempt: that is the documented
escape hatch, so a gap in it is reported rather than acted on.

The data directory keeps the name the earlier standalone application used, so a
runtime installed by that version is still found rather than downloaded again.
That name is load-bearing and should not be tidied up.

### Which model actually runs

The best models available are roformers, which are PyTorch checkpoints. The ones
that reach a GPU without PyTorch are MDX-Net, which are ONNX graphs. Neither
runtime is accelerated everywhere, and the split differs per platform:

| Accelerator | PyTorch | ONNX Runtime | Best available | Fastest |
| --- | --- | --- | --- | --- |
| NVIDIA CUDA | GPU | GPU | roformer, 12.6 dB | Demucs, 9.9 dB |
| Apple Silicon | GPU | mostly **CPU** | roformer, 12.6 dB | Demucs, 9.9 dB |
| AMD ROCm | GPU | **CPU** | roformer, 12.6 dB | Demucs, 9.9 dB |
| DirectML | **CPU** | GPU | MDX-Net, 10.2 dB | MDX-Net, 10.2 dB |
| CPU only | CPU | CPU | MDX-Net, 10.2 dB | MDX-Net, 10.2 dB |

On the first three the roformer is both better *and* quicker, so there is nothing
to trade. On the last two it is neither — DirectML's PyTorch backend is pinned far
behind what a roformer needs, and a CPU-only build has nothing to offload to,
where ONNX Runtime is the quicker of the two. Those machines give up 2.4 dB of
vocal separation quality to run on the hardware they have.

MDX-Net is also band-limited, with its wall at 17.6 kHz: above that nothing is
separated at all, so the air of a vocal stays in the instrumental the deck
reconstructs. That is a different kind of loss from a lower score, and it is why
the waveform-based Demucs is preferred for the fast path — it gives up quality
without giving up the top of the spectrum.

**Apple Silicon is the case worth explaining, because CoreML looks like it
works.** It is offered, it is enabled, and it does take most of the model — but
it cannot take the graph whole. On an MDX-Net model it claims 151 of 178 nodes
and splits them into 28 partitions, so the run spends its time shuttling tensors
back and forth with the CPU. That is why an ONNX model is not the answer there
even though a provider is listed. An Intel Mac never reaches Metal at all: the
separator gates that path on an ARM processor.

Because the accelerator determines the model, changing the accelerator can change
which model a given quality setting resolves to.

A quality setting is therefore not one model. It is one or more *variants* — a
list of candidate models plus the tuning each wants — and a setting always names
exactly one configuration. Editing anything by hand switches the setting to
Custom rather than leaving a preset's name on a configuration it no longer
describes. Candidates are a list rather than a filename because the catalogue
comes from upstream and can change; the first one actually offered is used, and
if none survive, the best-scoring model of that architecture is.

A setting gets a second variant when the trade-off it names cannot be expressed
the same way everywhere. Two flags record which inference runtime a given build
actually gets GPU work out of, and the preset picks its variant from them.

**Those two flags are answers to measurements, not to capability queries**, and
that distinction is the whole point. Neither is derivable from which extras were
installed — Metal and ROCm share those while behaving differently. Neither
follows from what the ONNX runtime claims to support, as the Apple Silicon case
above demonstrates: it reports CoreML, the separator enables it, and the work
still lands on the CPU. If you change one of these flags, say what you measured
and on what.

### The overlap parameter, and a click

The knob between the two best quality settings is the separator's `mdxc_overlap`.
Despite the name it is a *step* in seconds, not an amount of overlap: the chunk
is 11.0 s, the window advances that many seconds each time, so a **lower** value
means more passes and more inference.

The default of 8 gives 27% overlap. Stepping to 10 gives 9%, and measurably less
work. Stepping to 11 would be free — and is wrong. At the chunk length and above,
the step is clamped to the chunk and the passes stop overlapping at all, which
measured as a discontinuity every 11.0 s reaching 25× the surrounding
sample-to-sample difference, against 0.7× away from a boundary.

That is a click. And because the deck reconstructs the instrumental by
subtracting the stem, it lands in the instrumental too. The one second of overlap
that removes it costs essentially nothing: 0.399 s of compute per second of audio
at a step of 10, against 0.406 at 11.

### Estimating time honestly

Speed depends on the model, the device and whatever else the machine is doing, so
nothing in the interface quotes a fixed ratio. A first estimate comes from a table
of typical rates per architecture and accelerator and is marked as rough. As soon
as one track finishes, this machine's measured speed replaces it.

Measured rates are stored per architecture, accelerator **and** quality setting.
The last part matters: the top two settings run the same model and differ only in
how many passes they make over the audio, so one shared rate would be wrong for
each of them in turn.

Nothing here should ever grow a hardcoded duration. The seed rates are keyed on
the accelerator alone, precisely so that no measurement taken on one machine
becomes a claim about every machine.

### Pads and indicators

Stem controls are active only when the right pad mode is selected, no modifier is
held, the deck has a valid sidecar, and the event targets one of two specific
pads. Anything else is passed to the stock handler untouched.

The indicator list holds entries for both decks, so filtering by indicator
identity alone would disturb the other deck. The hook also checks the channel
stored in each entry.

While a sidecar loads, both pads blink, then hold colour once the audio is
resident. The blink uses the firmware's own timed state rather than a toggle
driven from the hook, so its cadence does not depend on how often the refresh
happens to call back. Note that the configured period is a *half*-period: the
indicator is lit while the elapsed count is even, so 500 ms means one second on,
one second off.

The waveform display is not modified. Its internal three-band representation is
not the audio buffer we process.

---

## 7. Key shift

The player has no key shift, and that absence is real rather than hidden: a
reachability census over all 17,745 functions in the binary found no dormant
subsystem waiting to be switched on. So this is built rather than unlocked.

### Two engines, picked by direction

The firmware *does* contain a complete granular pitch shifter — the `Pitch` beat
effect. It is excellent in one direction and poor in the other. Our own shifter
is the mirror image. So each direction gets whichever engine wins it.

Share of output energy still on the intended note, measured on a 440 Hz tone:

| Semitones | −12 | −7 | −5 | +5 | +7 | +12 |
| --- | --- | --- | --- | --- | --- | --- |
| The firmware's shifter | — | 99.9% | 99.9% | 52.7% | **15.8%** | 84.6% |
| Ours | 43.6% | 69.4% | 99.7% | 99.0% | **97.3%** | 93.8% |

The asymmetry is structural, not a bug in either. Raising pitch has to *repeat*
material — 0.414 s of source per second of output at +6 semitones — and that is
where grain splices become audible. Lowering pitch skips material instead, which
is far more forgiving. Both engines are driven at the exact equal-tempered ratio,
and the result lands within ±0.7 cents across the range.

### Where the pitch stage sits, and where it must not

It hooks the deck's playback blocks, 64 to 512 frames at a time — and both of
them, because the second replaces the first while Master Tempo is on. Hooking
only the first made the shift *vanish* under Master Tempo rather than sound
wrong, which is a much harder bug to read.

It deliberately does **not** sit on the buffer read that stems use. That read is
random-access, shared with the analysis scan, and measured on hardware only 13.6%
of its calls continue where the previous one stopped: two thirds re-read an
overlapping position and a fifth move backwards. A shifter carrying a sequential
grain cursor cannot live there, and the audible result was a stutter.

Stem mixing is indifferent to that access pattern because it is addressed by
absolute frame position, which is exactly why the two features hook different
places. This is the clearest example in the codebase of *where* a hook goes being
determined by measurement rather than convenience.

### Driving the firmware's engine

Two parameters matter, and one of them cost a long debugging session:

- **Depth**, fixed at the exact unity point of the effect's percentage curve,
  where its shift speed equals the requested percentage and the mix is fully wet.
  The constructor leaves it at zero, which is total bypass — the effect runs and
  never moves a sample. That is why key shift first appeared completely dead.
- **Percentage**, carrying the semitone. The usable range covers exactly −12 to
  +12. Percentages are integers here, so each semitone takes the closest one;
  the worst case is −9 semitones, 13 cents flat.

The engine also sizes its working buffers from a frame count set at
initialisation, so that field has to cover the largest block the hook can pass —
not the audio device's block size.

### Our shifter

Self-contained: no libc, no libm, no allocation. Two read heads walk a history
ring at the pitch ratio, half a grain apart, each windowed and cubically
interpolated. Every design value in it was measured, and three findings are worth
repeating because each one looks like a detail and is not:

- **Splices are aligned by correlation.** Without it, crossfading segments whose
  phases disagree forces a phase slew — and a phase slew *is* a frequency error.
  The whole shift came out at 97.9% of what was asked, 36 cents flat at −12.
- **Grain size depends on direction**, 512 frames up against 2048 down. Against
  an impulse train of eight hits at +7 semitones, a 2048-frame grain returns
  sixteen — every hit doubled — where 512 returns nine.
- **The crossfade stays amplitude-complementary.** The power-complementary
  alternative removes about a decibel of pumping on sustained noise and costs
  four spurious onsets, which is the worse trade.

Two artefacts remain, both inherent to time-domain shifting: roughly 2 dB of
level ripple above the input's own on broadband material, and occasional
transient doubling when raising pitch. Removing them needs a phase vocoder, and
cost is not the obstacle — the current stage measures 4 µs against a 1451 µs
block budget, with correlation bursts at 314 µs.

### Measuring both

Off the device, with both harnesses printing the same columns so the two can be
read side by side. The first runs the firmware's real ARM code under emulation;
the second compiles our shifter for the host.

```sh
python3 tools/rx3_firmware/emulate_pitch.py <application> --quality
python3 tools/rx3_firmware/measure_shifter.py
```

---

## 8. Faster decoder polling

Not a patch at all. After startup, a module sends two commands to the
application's own debug console on a loopback UDP port, changing the decoder
thread's sleep interval from 1 ms to 0.1 ms per deck.

The setting is volatile, alters neither flash nor the executable, and disappears
on power off. It costs CPU and guarantees no particular reduction in end-to-end
latency — it reduces one specific source of it. Failure is logged and does not
stop the runtime.

---

## 9. Building and running

Nothing here is installable through a package manager. There is no packaging
metadata and no console script; every entry point is invoked as a path.

### Make targets

| Target | Effect |
| --- | --- |
| `make help` | print the target list (the default) |
| `make hook` | cross-compile the ARM hook and assert the resulting binary |
| `make payload-hook` | compile the hook variant a payload ships |
| `make autoexec KEY=<path>` | build the runtime image; `KEY` is required and must exist |
| `make payload` | assemble the mods into a runnable payload |
| `make app` | run the desktop application from source |
| `make test` | run the regression guards, then the unit tests |
| `make preflight` | inspect every publishable file |
| `make clean` | remove the build directory and nothing else |

`PYTHON` defaults to `python3`, `BUILD_DIR` to `build`, `FIRMWARE` to `1.19`,
`CC` to `clang` unless the environment sets it. `MODULES` empty means "the
manifest defaults".

### The desktop application

One Tkinter window with a tab for each half of preparing a drive. It replaces two
earlier separate applications that shipped as two downloads for one workflow.

| File | Contents |
| --- | --- |
| `main.py` | the window, the two tabs, and the `--self-test` entry point CI smoke-tests |
| `mod_generator.py` | the **USB Runtime** tab: picks modules and writes the image |
| `stem_studio.py` | the **Vocal Stems** tab, plus the Advanced options dialog |
| `theme.py` | appearance detection, the shared styles, the path-row widget |

**Neither tab holds engine logic.** They drive `tools/rx3_runtime/` and
`tools/rx3_stems/` respectively, which is why the command line and the packager
can produce identical results without duplicating anything.

One rule in `theme.py` is worth stating because breaking it is easy and the
result is invisible to whoever broke it: light or dark is decided from the colour
Tk is actually painting, not from an operating-system query, and **nothing may
hard-code a foreground colour.** A fixed grey is unreadable in whichever
appearance it was not chosen for. Only classic Tk widgets, which the theme engine
does not reach, are recoloured by hand — the log pane is the single case.

```sh
make app                          # or: python3 apps/rx3-toolbox/main.py
```

### Command-line tools

Build a runtime with specific modules:

```sh
python3 tools/rx3_runtime/cli.py build --firmware 1.19 \
  --patch beatjump-32bars --patch stems \
  --key /path/to/keyfile --output build
```

`--patch` repeats; omitting it selects every module whose manifest sets
`default`. `--prebuilt-hook` accepts an already-compiled hook instead of invoking
the compiler.

Build and inspect a runtime image:

```sh
python3 tools/rx3_firmware/firmware_image.py autoexec \
  build/runtime build/autoexec.bin --key /path/to/keyfile
python3 tools/rx3_firmware/firmware_image.py verify-autoexec \
  build/autoexec.bin --key /path/to/keyfile
```

Encode a sidecar:

```sh
python3 tools/rx3_stems/make_sidecar.py vocals.wav "Artist - Title.rx3stem" \
  --match-full "Artist - Title.mp3" --separator-normalization 1.0
```

Patch a host copy of the application offline. Apply in this order when both are
needed; each refuses unexpected content, and applying then reverting in reverse
order restores the input byte for byte:

```sh
python3 -m tools.rx3_patcher.beatjump_32bars rbp -o rbp.32bars
python3 -m tools.rx3_patcher.beatjump_no_quantize rbp.32bars -o rbp.patched
```

### Environment variables

| Variable | Read by | Effect |
| --- | --- | --- |
| `RX3_SEPARATOR` | Stem Studio | path to a separator binary, instead of searching |
| `RX3_FFMPEG` | Stem Studio | path to FFmpeg; used as given, a missing filter is reported rather than worked around |
| `RX3_STEM_STUDIO_HOME` | Stem Studio | overrides the managed runtime and model cache location |
| `RX3_PREBUILT_HOOK` | packaging | path to the compiled hook; required when packaging, with no fallback |
| `RX3_STEMS_DIR` | on-device stems module | overrides the sidecar directory |
| `DECODER_SLEEP_NS` | on-device decoder module | overrides the polling interval |
| `CC` | build | compiler for the ARM hook |

### Prerequisites

| Component | Version | Notes |
| --- | --- | --- |
| Python | 3.12 in CI | no floor is declared or enforced |
| `cryptography`, `pycdlib` | pinned | `pycdlib` is imported lazily, with an external fallback |
| Clang and LLD | any recent | needed to compile the hook |
| FFmpeg | any complete build | must carry the `aformat`, `apad`, `aresample`, `astats`, `atrim` and `volume` filters |

Stem separation additionally needs a host Python between 3.10 and 3.13 to seed
its own environment; that range is enforced in code. The separator and FFmpeg run
as subprocesses, so no separation dependency is linked into the release archive.
Which accelerator an environment was built for is recorded beside it, because a
CPU-only build cannot be accelerated after the fact.

Cross-compilation flags:

```text
--target=arm-linux-gnueabi -march=armv7-a -marm -mfloat-abi=softfp -mfpu=neon
-fPIC -fno-stack-protector -fno-builtin-memcmp -fno-builtin-bcmp
-O2 -Wall -Wextra -Werror
-fuse-ld=lld -shared -nostdlib -Wl,--hash-style=sysv -Wl,--build-id=none
```

### Supported binaries

Four application checksums are accepted, all corresponding to firmware 1.19,
which has no sub-revisions. An unlisted checksum aborts before anything is
modified. This is the same refuse-rather-than-guess rule as every patch site.

### On the root password

The runtime does not need one. During filesystem analysis, on 10 August 2026,
the stock password hash was found to use a legacy algorithm with no adaptive
work factor that considers only the first eight characters, and it fell in about
three minutes. Neither the hash nor the plaintext is published. Only the
optional remote-shell module, disabled by default, uses the stock account at
all.

The finding has not been reported to the manufacturer, and no report is
planned. It is recorded here so that the state of it is not left to inference:
what is written above is the whole of what this project has done with it.

---

## Appendix A: front-panel codes

Recovered statically as described in [section 5](#5-front-panel-input). Codes are
16-bit values carried in the input object; the channel selects the deck.

### Pad mode selectors

| Code | Control |
| --- | --- |
| `0x4113` | Hot Cue |
| `0x4114` | Beat Loop |
| `0x4115` | Slip Loop |
| `0x4116` | Beat Jump |

### Performance pads

Pads 1 to 8 occupy consecutive codes from `0x4117` to `0x411e`. The last two are
the ones the stems feature claims.

### Browse controls

These travel a different path from the pads — a table pumped by the interface
cycle rather than the deck's own handlers, which is why they respond even when
the deck is not started.

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

Menu is worth calling out: the handler measures how long the key is held, so
tapping it is a *different gesture*, not a faster one.
