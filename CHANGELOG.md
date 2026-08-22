<!-- SPDX-License-Identifier: MPL-2.0 -->
# Changelog

## Unreleased

### Added

- `make payload` assembles the mods into a runnable payload directory: a manifest, the preloaded hook and the assets. That directory is the whole of what this project exposes to anything that runs it. No import, no path and no target reaches the other way. A test reads the performance-row geometry back out of the hook's C and fails if the two copies drift.

- The complete `ui::KeyInput::KeyCode` table, 146 codes with their names, in REFERENCES.md appendix A. Extracted statically from `keyCodeAsText()`, which is a comparison tree over the same 16-bit field the stems feature already reads: decompile it, take the (code, pointer) pairs, resolve the pointers in `.rodata`. The four pad-mode selectors are `0x4113`-`0x4116` and the eight pads `0x4117`-`0x411e`; the extraction independently reproduces `Pad7 = 0x411d` and `Pad8 = 0x411e`, the two values the mod already had hard-coded from an unrelated route. Six codes the decompiler folded into range comparisons were read off their guards rather than guessed.

- Pioneer's bitmap font format, decoded, in REFERENCES.md under "The bitmap font". `NS_FONT_ID_ISO8859_w.bin` has no header and no offset table: it is a flat array of 189-byte cells, 14 x 27 pixels at **4 bpp**, 422 glyphs indexed by `codepoint - 0x20`, covering ASCII, Latin-1, Greek, Cyrillic and the euro sign. The file is 42 bytes short of 422 full cells because the last glyph's all-zero descender rows are not written. Earlier attempts read it as 1 bpp and 4 bpp at several widths and got noise; the cell height was the missing piece, and 210 leading zero bytes looked like a 30-row cell when they are a 27-row space followed by the first three blank rows of `!`.
- The typeface is named rather than guessed: **Helvetica Neue LT W1G**. rekordbox 7 declares `font-family="HelveticaNeueLTW1G"` in three of its own skin SVGs, and W1G (Linotype's "World 1 Glyph set", Latin plus Greek plus Cyrillic) is exactly the repertoire of the firmware's font file. Two unrelated artefacts, one answer. It is licensed and not shipped: scanning all 2144 files in the rekordbox bundle for genuine sfnt table directories finds four, all Chromium's `SpiderSymbol` icon font.

### Fixed

- **The hook stopped loading, silently, and every run fell back to stock behaviour.** At `-O2` clang rewrites `memcmp(a, b, n) == 0` into a call to `bcmp`, which rbp's libc does not export; the library then fails to load with no link error and no warning, because the rewrite happens in the optimiser, after every diagnostic the front end could have produced. The symptom looked nothing like the cause: a run painted 17 730 non-black pixels, exactly the stock figure, which reads as a startup problem rather than a missing mod. `-fno-builtin-memcmp` suppresses the rewrite, and `tests/test_hook_symbols.py` now reads the `.dynsym` of both builds, with its own small ELF parser so no external tool is needed, and fails on `bcmp`, on any import outside the set rbp is known to export, and on the flag being dropped from the Makefile. This is the second time an unresolved symbol has cost this project a long debugging round; it is the first time a test will catch it.
- The label generator's typeface was refitted against ground truth and is now Helvetica Neue **Regular at 22**, not Light at 24. The fourteen BEAT FX captions in the caption artwork segment cleanly into individual letters, giving nineteen of Pioneer's own capitals. Cap height is a consistent 16 px with `O C G S` overshooting to 17, which is itself evidence they are font renderings rather than hand artwork. Sweeping face against size over those glyphs, Regular 22 gives 29.3 mean absolute error per pixel where Light 24 gives 61.3. The earlier fit matched whole-word ink extents, which is a weaker signal because weight and size trade against each other and still fit a box.
- The reference said the pad blink uses a 50 ms period; it is 500 ms, and that is a half-period: one second on, one second off.
- The performance row is painted once per pass instead of once per intercepted draw: 6 draws where there were 331 over the same run. Deciding what to replace was also keyed on the deck's window, which a deck shares with its info strip; it now keys on the widget subtree that actually owns the pads, so nothing outside the row is intercepted on the way past.

### Changed

- The `PATCHED` badge is gone. The `KEY` and `STEMS` tabs already answer the question it was there to answer, and the header is Pioneer's again.

- The payload build finishes a browse key the way rbp does, so the emulator can drive the browse section without a front panel. `BrowseUiIf::InputKey` (`0x000cfc58`) marks the record with `UiKey_KeyPush` and, if it is accepted, posts an eventflag with `set_flg(*0x032671f4, 1)`; `Ui_EventTask` (`0x001e79a0`) consumes it and runs `BrowseKeyProcessing` inside the rest of the transaction: `CheckBrowseRequestCancelCommand`, a 300 ms repeat window, `BrowseCommandCancel`, and the `KeyComplete`/repaint. Calling the handler directly skipped all of that, so the hook now posts the flag and falls back to the direct pump only when the flag id looks uncreated. Whether this moves the browse mode on screen is not demonstrated.

- The update-container codec is gone from `tools/rx3_firmware/`, along with its description in the documentation. The toolkit authors `autoexec.bin` and nothing else, which is what the build engine has always used; a test asserts the removed symbols stay removed, and another fails the build if the container format is described in prose again.

- Tools address the files an operator keeps locally by the role they fill, not by a path asserting where they came from, resolved through a gitignored `artifacts.toml`. See `docs/artifacts.md`.

- The emulator moved to its own repository. What remains here is the payload format it consumes.

- The root filesystem documentation no longer sends everyone through `make_rootfs`. The published source package carries the built `initramfs.tar.gz` beside the sources, so reading the filesystem is archive handling on any of the three operating systems, and WSL2 is needed only by someone who wants to rebuild it. Reported in #23. The document still stops at an unpacked filesystem: it does not say what inside it the app is later pointed at, and it says plainly that a manufacturer-built archive stays on the machine that unpacked it.

### Known issues

- **The pad row draws no text at all**, so the pad-label template can never be captured as designed. Measured: twelve window subtrees issue text draws (`0x01 0x02 0x03 0x06 0x07 0x08 0x09 0x0b 0x0c 0x10 0x11 0x16`), and the pad subtree `0x17`/`0x18` is not among them. Those labels are images. The comment in the source describing the template as a clone of "the stock deck-2 KEY label" describes something that does not exist.

- **Pioneer's own artwork settles the style.** The image table is a run of 44-byte records at offset 0 followed by pixel data, the same record layout the mod already manipulates in memory, with width at `+4`, height at `+6`, format at `+0x18` and the pixel offset at `+0x20`. The first pixel offset is exactly 5581 x 44, and format 2 is RGB565 with the palette offset set to the file length as a no-palette sentinel. Reading it needs nothing new.

Ids `0x1439..0x1470` hold the BEAT FX captions at 160x40, and every caption ships four variants: dim or white lettering on a black or blue ground. That is the whole colour language of this interface. It is monochrome, and blue marks the selected item. Measured exactly: ground `(0,0,0)` or `(0,125,230)`, ink `(98,101,98)` or `(255,255,255)`.

The firmware ships fonts, and they are the wrong ones. `gui/system/fontdata` holds `decker.ttf` ("Decker Bold") and `sazanami-gothic.ttf`; measured against the real captions they are 11.1 px and 14.8 px out, so Decker is a display face and sazanami the CJK fallback. The UI font is `gui/pset/fontdata/NS_FONT_ID_ISO8859_w.bin`, 79 758 bytes in Pioneer's own format, since decoded above.

Rasterisation was matched rather than the file. Pioneer's glyphs quantise to sixteen grey levels, which is 4-bit anti-aliasing, and their vertical stems are solid with the anti-aliasing only on curves, which is hinting. Supersampling matched the pixel totals but softened the stems and looked wrong at zoom, so the lettering is drawn once at final size, hinted, to reach their stroke mass, with the coverage quantised to sixteen steps.

- **Cloning does not carry the font.** With the donor made selectable, four different donor subtrees were captured successfully and every one rendered the control label at exactly 19 px, the same as the header donor and the same 2x-stock size the labels have always had. So the long-standing premise that the cloned glyph determines the face is false, at least for size: either the font follows the window the draw is retargeted into, or it lives outside the 0x54 bytes that are copied. Fixing the font therefore needs a different mechanism, and drawing the labels as images the way Pioneer does is now the more likely route.

- The on-screen controls still wear the header's typeface, at twice the size of a stock label, and selected still looks like unselected. Both come from the same place: the controls are drawn by cloning one of rbp's own text objects, and the colour fields on that object are not plain RGB. `NS_PALRender_DrawText` decodes them three different ways depending on the pixel format of the window being drawn into, which it takes from `DS_GR_GetWindowInfo` rather than from the object. Feeding it RGB888 painted magenta lettering on green; RGB565 painted green; sweeping all 256 low-byte values moved the green channel alone and never lifted red or blue off zero. Until the format reported for the pad layers is identified, the drawing code inherits those colours rather than guessing at them. That is also the explanation for an older note in the source that every literal colour "looked foreign".

The eight prepared tab bitmaps are still shipped and still loaded at run time, because that colour question is what stands between the row and being drawn entirely from the host's own model. They go when it is answered.

## 0.5.2

A runtime built on Windows loads its modules again.

### Fixed

- An `autoexec.bin` built on Windows stopped with `STOP: one or more runtime modules violate their contract`, one `FAILED: unsafe runtime module directory` per selected module. The index naming the modules to load was written with the building machine's line endings, and the shell that reads it took the trailing carriage return as part of the directory name. Affects 0.5.0 and 0.5.1 built on Windows; 0.4.0 predates the index.

## 0.5.1

Reinserting the drive works. It used to be refused, and before that it was what the deck made you do, because applying a module emptied the media list. The runtime also stops writing to the drive unless you ask it to.

### Fixed

- Reinserting a drive without a power cycle no longer stops with `STOP: unsupported rbp SHA-1`. The check hashes the whole player binary, so a session this runtime had already patched no longer matched the state it started from. The guarded words are put back to their stock values before the comparison, which answers the question the check means to ask (is this the binary I know?) without being fooled by our own writes. A guarded word holding neither value still survives normalisation, and the word-by-word audit that follows still rejects it before anything is written.
- Reinserting a drive no longer restarts the player. A drive pulled out as `sda` comes back as `sdb`, so it mounts somewhere else; the sidecar directory is read once at load time, so a moved path meant stopping and relaunching. That froze the screen and emptied the media list, which is what made the drive get pulled again. The player is handed one fixed path, re-pointed on each insertion, and a reinsertion now changes nothing.
- A player that exits straight after being relaunched is rolled back to the stock binary instead of to the previous bytes. On a reinsertion those previous bytes are the patched ones, so the rollback relaunched exactly what had just died. The runtime's shared objects come out of `LD_PRELOAD` with it.
- The log of the run that applied the patch survives the next insertion, in `session-previous.txt`. The player's cumulative output carries a marker per launch, so one run's crash no longer reads as the next run's.

### Added

- **Session logging** is a module of its own, and it is not selected by default: an ordinary build now writes nothing to the drive at all. Tick it to get `RX3_RUNTIME/session.txt` and the player's output. Eject the drive rather than pulling it out while that build is in use, because the player keeps the log open for as long as it plays. That open handle is also what stopped the kernel releasing the device, which is why a drive came back under another name.
- The log names what forced a restart, and each module says what it saw that made it ask.

### Changed

- A relaunched player is given up to the same eight seconds, but the wait ends as soon as every module has written its readiness file, a second in practice. The media that is already mounted is announced to it as soon as the process is alive, rather than after the readiness verdict.
- Everything the RX3 executes moved from `runtime/` to `mod/`. The word said *when* the code runs, which the directory above it does too: `apps/` and `tools/` are runtimes of their own, and two of them are literally named `rx3_runtime`. `mod/` says what the directory holds and matches the word the documentation already uses when it speaks to a DJ. The `runtime_directory` key in a module manifest, the `RX3_RUNTIME/` folder written to the drive, and the separation runtime are unrelated names and keep theirs.

### Known issues

- A drive still takes several seconds to reappear after a module is applied. The runtime announces it about a second after the player is relaunched, so what remains is on the device side: the player is seen to crash twice before a third launch sticks, and the log reports `rejected: unexpected PcmReader::load prologue` on those attempts. The binary patch that widens the image table stays applied even when the hook gives up installing it, which leaves the player accepting identifiers it has no records for. Under investigation.

## 0.5.0

The two applications became one, and the stems half answers the questions it used to leave the operator guessing at.

### Changed

- `RX3 Mod Generator` and `RX3 Stem Studio` ship as a single application, `XDJ-RX3 Toolkit`, with a **USB Runtime** tab and a **Vocal Stems** tab. One download per platform replaces two; the `XDJ-RX3-Mod-Generator-*` and `XDJ-RX3-Stem-Studio-*` archives are retired in favour of `XDJ-RX3-Toolkit-*`. `make gui` and `make stems-gui` become `make app`. The per-user data directory keeps its old name, so an installed separation runtime is found rather than downloaded again.
- Secondary text follows the desktop appearance instead of a fixed `#555555` chosen against a light window. On a dark desktop the help text in Advanced options was grey on grey at roughly 1.6:1; it is now above 8:1 in both appearances, and follows a mid-session appearance change.
- The progress line says which track is being worked on (*track 3 of 20*) rather than how many are behind it, which read one short of reality.
- A preset resolves to an architecture rather than to a fixed model, and picks it from what the machine accelerates. The best models in the catalogue are roformers, which are PyTorch checkpoints; the ones that reach a GPU without PyTorch are MDX-Net, which are ONNX graphs. Where PyTorch runs on the GPU (CUDA, Apple Silicon, ROCm) both presets now run the roformer, and **Fast** is the same model over fewer passes rather than a weaker one. Where it does not (DirectML, whose PyTorch backend is pinned far behind what a roformer needs, and any CPU-only build) both run MDX-Net, giving up about 2.4 dB of vocal SDR to reach the hardware that is there. The summary under the selector states which of the two you are getting, because one preset is no longer one offer.
- **Fast** no longer overrides the segment size. It used to ask for 512 against the model's own 256 on Apple Silicon and ROCm, which is what selected the PyTorch route for an ONNX model, at the cost of running it at double the context its weights were trained for, blurring the mask in both directions. The architecture split does that job now, so every model runs at its own segment size. On a Mac, this also lifts MDX-Net's 17.6 kHz band limit, above which nothing was ever separated and the air of a vocal stayed in the instrumental.
- CoreML is still not used on a Mac: it is offered and enabled, but cannot take an MDX-Net graph whole: it claims 151 of 178 nodes across 28 partitions, so the work stays interleaved with the CPU, which is what the activity monitor was showing. An Intel Mac reaches no GPU at all, since audio-separator gates MPS on the processor being ARM.
- The `mdxc_overlap` help text said "Higher is better and slower". It is the opposite on a roformer: the option is a step in seconds, so a higher value advances the prediction window further and stitches the result from fewer passes. For `vocals_mel_band_roformer` the chunk is 11.0 s, which makes the default of 8 a 27% overlap and anything from 11 up a single pass with none at all. Anyone who raised it for quality was lowering it.
- Measured throughput is keyed by preset as well as by architecture and accelerator. Both presets run the same model on most machines and differ by roughly a factor of two in passes, so one shared rate was wrong for each of them in turn. Rates recorded under the old key are re-measured.
- Modules sit at one level, `runtime/modules/<id>/<firmware>/`, named after the `id` their manifest declares. Three of them were a level deeper, under an `access/`, `buffer/` or `beatjump/` category that no document described, so the path could not be guessed from a `requires` entry. Manifests are unchanged and the on-device layout is unaffected.
- The offline beat jump patchers moved out of `runtime/` to `tools/rx3_patcher/`, invoked as `python3 -m tools.rx3_patcher.<name>`. They run on a workstation, not on the deck, which is the line `runtime/` draws.
- `make hook` and `make test` discover module headers and regression guards instead of listing them. Adding a module no longer means editing the Makefile.
- Both Beat Jump modules now declare `requires: ["decoder-sleep"]`, so selecting either one brings the faster decoder polling with it. `decoder-sleep` moves from manifest order 30 to 8, because the build engine loads a dependency before what needs it; it can still be selected on its own.
- The feature list shows every module, including internal ones. The performance core appears greyed out and ticks itself when Key Shift or Stems is selected. Ticking a module ticks what it requires, and unticking one unticks whatever would be left requiring it. The propagation reads the manifests, so a new dependency needs no interface change.

### Added

- **Fast** and **High quality** presets, and **Custom** for anything tuned by hand. Both run the best-scoring vocal model and differ in `mdxc_overlap`, so switching between them needs no second download. Editing a model or parameter in Advanced options switches the setting to Custom rather than leaving a preset name on a configuration it no longer describes.
- A duration estimate, stated before the run from the playlist's own track lengths and corrected from the machine's measured speed as it goes. Measured speeds are kept in `throughput.json` per architecture and accelerator, so later runs start calibrated.
- A standing notice that separation occupies the machine, and a confirmation before any run estimated at more than ten minutes.

## 0.4.0

Two reasons a sidecar was ignored or left the vocal in the instrumental. Both affect tracks prepared by any earlier version, which have to be generated again.

### Fixed

- Sidecars are named with the truncation Rekordbox applies when it exports a track to a drive, keeping the first 44 characters of the stem. A track whose library filename is longer reached the drive shortened while its sidecar kept the full name, and the deck never matched the two. Two tracks that collide only once truncated are now reported as ambiguous, as they always should have been.
- Stems for mp3 and AAC sources are aligned to the deck's decoder rather than FFmpeg's. Those containers declare the samples their encoder prepended; FFmpeg drops them and the deck plays them, which left the stem 25 ms early and the vocal fully audible in the instrumental while the vocal pad still worked. Existing sidecars for such sources have to be generated again. Delete them, or the run keeps them as already generated. WAV, AIFF and FLAC sources were never affected.

The manifest gained `encoderDelayFrames`, the padding each stem was pushed back by.

## 0.3.0

First tagged release. Git history was reset to a single commit at this point, so there is nothing before it to compare against. The tables below translate names used in earlier unreleased builds and in any external tutorial written against them.

### Renamed

Modules and applications were renamed so that each name describes what the code actually does. There is no compatibility alias anywhere: a path from an older tutorial will simply not exist. Use this table to translate.

| Old | New |
|---|---|
| `XDJ-RX3 Toolkit Builder` (application) | `RX3 Mod Generator` |
| `apps/xdj-rx3-toolkit-builder/` | `apps/rx3-mod-generator/` |
| `apps/xdj-rx3-toolkit-builder/builder.spec` | `apps/rx3-mod-generator/mod_generator.spec` |
| `org.xdjrx3.toolkit.builder` (macOS bundle id) | `org.xdjrx3.mod.generator` |
| `XDJ-RX3-Toolkit-*.zip` / `.tar.gz` (release archives) | `XDJ-RX3-Mod-Generator-*.zip` / `.tar.gz` |
| `tools/rx3_runtime/builder.py` | `tools/rx3_runtime/build.py` |
| `tools/rx3_runtime/build_runtime.py` | `tools/rx3_runtime/cli.py` |
| `tools/rx3_stems/engine.py` | `tools/rx3_stems/provisioning.py` |
| `tools/rx3-firmware/` | `tools/rx3_firmware/` |
| `patches/` | `runtime/modules/` |
| `patches/beatjump/32bars/` | `runtime/modules/beatjump/beatjump-32bars/` |
| `patches/beatjump/no_quantize/` | `runtime/modules/beatjump/beatjump-no-quantize/` |
| `patches/buffer/decoder_sleep/` | `runtime/modules/buffer/decoder-sleep/` |
| `patches/access/telnet/` | `runtime/modules/access/telnet/` |
| `patches/stems/` | `runtime/modules/stems/` |
| `autoexec.sh` (repository root) | `runtime/autoexec.sh` |
| `tests/test_toolkit_builder.py` | `tests/test_mod_generator.py` |

Module identifiers are unchanged. `beatjump-32bars`, `beatjump-no-quantize`, `decoder-sleep`, `stems` and `telnet` still select the same modules on the command line and in the manifests. The name of the project itself, XDJ-RX3 Toolkit, is unchanged.

Everything the RX3 executes now lives under `runtime/`. Everything above it runs on your computer.

### Changed

Documentation was rewritten. The single README became a short landing page plus `docs/`, with a Quick Start that runs from a bare computer to a track playing in stems without a forward reference. See `docs/`.

Two corrections to earlier documentation, both resolved against the code:

- The accelerator table in `apps/rx3-stem-studio/README.md` claimed CUDA used the default PyTorch wheels. It uses an explicit index, `cu130`, or `cu126` on cards below compute capability 7.5 (`tools/rx3_stems/provisioning.py`).
- The count of guarded words for Beat Jump was stated as thirteen in one file and twelve in another. The count is no longer documented; the offsets in `runtime/modules/beatjump/beatjump-32bars/1.19/patch.py` are the reference.

### Note on earlier versions

The troubleshooting table used to carry a fix attributed to "v0.2.1". No tag or release corresponds to that version, so the fix is described without it.
