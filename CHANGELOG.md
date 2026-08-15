<!-- SPDX-License-Identifier: MPL-2.0 -->
# Changelog

## Unreleased

### Added

- The emulator window is watchable. When Pillow is importable the framebuffer is
  unpacked in C and handed to Tk in memory as a PPM, rather than being encoded
  to PNG and re-read from disk every tick: 3.5 ms per frame against 220 ms, and
  the archive PNG that `report.json` cites is now written on a slow tick instead
  of on every refresh. The pure-stdlib path is unchanged and still the fallback,
  so a clean clone gains no dependency. Pillow's `BGR;16` widens 5- and 6-bit
  channels with its own rounding, so a correction table — measured at import,
  not hard-coded — keeps the two paths identical across all 65 536 RGB565 words.
- A front-panel strip under the screen: STATUS, BEAT FX, the tabs a profile
  installs, and the open panel's control row for both decks. The rows are
  rebuilt when the tab changes, because KEY has three control columns and STEMS
  two. A test reads the geometry back out of the hook's C and fails if the two
  copies drift.
- `--duration 0` runs until the window is closed, so a session can be left open.
- The physical keys above the screen — SOURCE, BROWSE, TAG LIST, PLAYLIST,
  SEARCH, MENU, the encoder push, BACK and the two LOAD keys — are injectable,
  through rbp's own dispatch rather than a synthesised device. `InitUiBrowseKey`
  registers each into a 230-entry table at `pushKey + index * 16 + 12`, and
  `UiKey_KeyPush` marking a record is the whole of pressing a key. MENU is held
  for three seconds, as it is on the deck, because the handler measures the
  duration. Both entry points are prologue-guarded like every other direct call
  into rbp.

- The complete `ui::KeyInput::KeyCode` table, 146 codes with their names, in
  `docs/rx3-key-codes.md`. Extracted statically from `keyCodeAsText()`, which is
  a comparison tree over the same 16-bit field the stems feature already reads:
  decompile it, take the (code, pointer) pairs, resolve the pointers in
  `.rodata`. The four pad-mode selectors are `0x4113`–`0x4116` and the eight pads
  `0x4117`–`0x411e`; the extraction independently reproduces `Pad7 = 0x411d` and
  `Pad8 = 0x411e`, the two values the mod already had hard-coded from an
  unrelated route. Six codes the decompiler folded into range comparisons were
  read off their guards rather than guessed.

- The emulator window can press rbp's own player keys: the four pad-mode
  selectors and the eight pads, per deck. These are `PlayerInnards` methods
  rather than browse-table entries, so pressing one needs a real object and a
  real `uif::IKeyInput`. The object is latched from the `PlayerInnards`
  constructor, since no physical key ever arrives under emulation to supply
  one; the event carries the code at `+8`, the 1-based channel at `+10` and
  press or release in the low nibble of `+11`, with `ui::KeyInput`'s vtable at
  `+0` — omitting that vtable segfaulted rbp, because `IKeyInput` is an
  interface and the handlers call virtual methods on it.

  With this the mod's own pad hooks execute under emulation for the first time:
  a HOT CUE press produces `pad mode selected: custom panel returned to STATUS`
  from `hooked_on_key_hot_cue`, which had never once run outside hardware.

- The emulator command channel is a plain file rather than a FIFO. The FIFO
  needed a rendezvous on both sides and delivery was unreliable in practice —
  whole runs arrived in which no command was seen at all while every readiness
  check passed, and holding one descriptor open made it no better. The runner
  already wrote the same command to `touch.command` and replaced it atomically,
  so reading that has no rendezvous to miss and nothing to lose; the sequence
  number was always what distinguished a new command from a re-read.

- The emulator starts far more often, though not reliably. Twelve consecutive
  runs brought DirectFB up, which was claimed here as fixed; a later control run
  failed again at 4/10 checks, so the rate improved and the fault did not go
  away. Treat any single run as evidence only once `directfb_started` is true. The emulator's own command-poll thread
  was competing with `DirectFBCreate` from the moment the library loaded — the
  FIFO it used to wait on blocked, so the thread cost nothing during startup,
  while polling a file costs a wake-up per interval. It now stays quiet for the
  first eight seconds and polls every 150 ms rather than every 50 ms, which is
  still well inside a click's reaction time. Nothing can be sent before the
  window exists anyway.

- The container's shim is built with `-Werror`, as the ARM hook already was.
  Its absence had just cost six runs out of six: a tracing helper was added
  whose definition never landed, because the edit matched a signature that had
  four parameters written as one. The calls compiled anyway on an implicit
  declaration and every run died at load with `undefined symbol: trace_open`.
  A warning was the only thing standing between that and a silent, total
  failure, and it was not being treated as one.

- Pioneer's bitmap font format, decoded, in `docs/rx3-font-format.md`.
  `NS_FONT_ID_ISO8859_w.bin` has no header and no offset table: it is a flat
  array of 189-byte cells, 14 x 27 pixels at **4 bpp**, 422 glyphs indexed by
  `codepoint - 0x20`, covering ASCII, Latin-1, Greek, Cyrillic and the euro
  sign. The file is 42 bytes short of 422 full cells because the last glyph's
  all-zero descender rows are not written. Earlier attempts read it as 1 bpp and
  4 bpp at several widths and got noise; the cell height was the missing piece,
  and 210 leading zero bytes looked like a 30-row cell when they are a 27-row
  space followed by the first three blank rows of `!`.
- The typeface is named rather than guessed: **Helvetica Neue LT W1G**.
  rekordbox 7 declares `font-family="HelveticaNeueLTW1G"` in three of its own
  skin SVGs, and W1G — Linotype's "World 1 Glyph set", Latin plus Greek plus
  Cyrillic — is exactly the repertoire of the firmware's font file. Two
  unrelated artefacts, one answer. It is licensed and not shipped: scanning all
  2144 files in the rekordbox bundle for genuine sfnt table directories finds
  four, all Chromium's `SpiderSymbol` icon font.

### Fixed

- **The hook stopped loading, silently, and every run fell back to stock
  behaviour.** At `-O2` clang rewrites `memcmp(a, b, n) == 0` into a call to
  `bcmp`, which rbp's libc does not export; the library then fails to load with
  no link error and no warning, because the rewrite happens in the optimiser,
  after every diagnostic the front end could have produced. The symptom looked
  nothing like the cause: the emulator painted 17 730 non-black pixels, exactly
  the stock figure, which reads as a startup problem rather than a missing mod.
  `-fno-builtin-memcmp` suppresses the rewrite, and `tests/test_hook_symbols.py`
  now reads the `.dynsym` of both builds — with its own small ELF parser, so no
  external tool is needed — and fails on `bcmp`, on any import outside the set
  rbp is known to export, and on the flag being dropped from the Makefile. This
  is the second time an unresolved symbol has cost this project a long debugging
  round; it is the first time a test will catch it.
- The label generator's typeface was refitted against ground truth and is now
  Helvetica Neue **Regular at 22**, not Light at 24. The fourteen BEAT FX
  captions in `imagedata.dat` segment cleanly into individual letters, giving
  nineteen of Pioneer's own capitals — cap height a consistent 16 px with
  `O C G S` overshooting to 17, which is itself evidence they are font
  renderings rather than hand artwork. Sweeping face against size over those
  glyphs, Regular 22 gives 29.3 mean absolute error per pixel where Light 24
  gives 61.3. The earlier fit matched whole-word ink extents, which is a weaker
  signal because weight and size trade against each other and still fit a box.
- `docs/reference.md` said the pad blink uses a 50 ms period; it is 500 ms, and
  that is a half-period — one second on, one second off.
- The performance row is painted once per pass instead of once per intercepted
  draw — 6 draws where there were 331 over the same run. Deciding what to
  replace was also keyed on the deck's window, which a deck shares with its info
  strip; it now keys on the widget subtree that actually owns the pads, so
  nothing outside the row is intercepted on the way past.

### Changed

- The green `PATCHED` badge is gone. The `KEY` and `STEMS` tabs already answer
  the question it was there to answer, and the header is Pioneer's again.

- **`UiObjectManager::init()` completes, and `startUp()` runs.** This is the
  blocker every other emulator limitation hung from, and it was one wrong byte
  in the shim.

  `common::GpioManager::GpioManager` opens `/dev/gpiodrv`, `lseek`s to the GPIO
  number and reads one byte, then hands it to a `GpioCallback` through a vtable
  slot. For `UsbStorageManager` that callback is `handleGpioMessage`, which
  filters GPIOs `0x7e` and `0xcc` — the USB **over-current** inputs — and
  forwards them to `notify_over_current`. Those lines are **active-low**:
  reading 1 returns immediately, reading 0 means a fault and tears the USB
  stack down through another virtual call and `request_usb_stop`. Our fake
  `/dev/gpiodrv` was an empty file, so every GPIO read either hit EOF or, once
  padded, read 0 — a permanent over-current fault, raised during construction,
  from which `init()` never returned.

  Filling that file with `1` instead of `0` is the entire fix. Every breadcrumb
  now balances, `init()` returns, and rbp opens 13 devices instead of 8 —
  including `/dev/subucom_spi1.0`, `/dev/subucom_spi2.0` and
  `/dev/tsc2007_2-0048`, i.e. opens #62–64 of the reference trace captured on
  real hardware. The front-panel micros and the touch panel are open for the
  first time under emulation.

  **Confirmed against the hardware.** Read over telnet from a running RX3, with
  a stick inserted: GPIO 126 and GPIO 204 both return `1`. The lines do idle
  high, so the emulator reports what the deck reports and the fix is right
  rather than merely effective. The same session confirmed the deck runs
  `/root/pdj/rbp` with no `-a`, where the emulator passes `-a`.

  Found with `--trace-init`, which installs guarded entry/exit breadcrumbs on
  the constructors `init()` calls: `PcController` entered and left,
  `UsbStorageManager` entered and never left, and one level down `GpioManager`
  entered 15 times but left 14. The vtable hop is exactly the edge a static call
  graph cannot follow, which is why a reverse walk from every blocking primitive
  had found no path from `init()` to any wait.

### Known issues

- The browse keys dispatch but change nothing on screen. Re-measured now that
  `init()` completes, and the browse mode is read directly out of `uiBrowse`
  (`0x0326f8b8`, since `getBrowseMode` is nothing but a `movw`/`movt` and an
  `ldr`): pressing SOURCE, BROWSE or TAG LIST leaves it at 1, on both routes.

  How rbp itself finishes a browse key is now known, from
  `BrowseUiIf::InputKey` (`0x000cfc58`): `UiKey_KeyPush` marks the record, and
  if it is accepted, `set_flg(*0x032671f4, 1)` posts an eventflag. `Ui_EventTask`
  (`0x001e79a0`) blocks in `wai_flg` on it and, for bit 1, calls
  `BrowseKeyProcessing` itself — wrapped in the rest of the transaction:
  `CheckBrowseRequestCancelCommand`, a 300 ms repeat window, `BrowseCommandCancel`
  and the `KeyComplete`/repaint. Driving the pump directly from the mod's own
  thread runs the handler and skips all of that. The hook now posts the flag
  instead, falling back to the direct pump when the flag id looks uncreated, and
  `--pump {0,1}` forces either route.

  Two things this ruled out. `UiCom_SndR232c` is not a message queue but the
  serial debug logger — a `vfprintf` behind a verbosity level — so its presence
  in `ChangeBrowseMode` meant nothing. And `ChangeBrowseMode` (`0x0010167c`)
  does not change the mode: it writes a pending flag and the requested mode into
  `browseCommand` at `0x0326906c` and returns 1 unconditionally, so its success
  never implied anything happened.

  Not yet answered: whether the eventflag route moves the mode at all. The
  probe that would say so — sampling the mode over a second and reading
  `browseCommand` beside it, to tell "nobody consumed the request" from "it was
  consumed and the mode still did not move" — has not yet produced a reading,
  because the run that carried it failed to paint. Note also that the eventflag
  **does** exist under emulation (id 17), so the task that consumes it is
  probably running; and that four earlier measurements were void, two from
  scripting mistakes and two because `run.sh` defaulted `RX3_EMULATOR_PUMP` to
  1 while the CLI never passed it through, so the eventflag route had never once
  executed.
- Real touch reaches rbp, but only sometimes. The emulator pushes a 6-byte
  `ts_data` into `/dev/tsc2007_2-0048` under a `<seq> t <x> <y>` verb — layout
  and calibration from 700 packets captured on hardware, X inverted, eight
  consecutive samples because `TouchAdValueHysteresis` debounces, then two
  releases. Breadcrumbs prove the chain works end to end: `TouchPanel::run` is
  alive, `TouchPanelComm::readFd` fires only when a packet is written, and
  `solveCoordToKey` — rbp's own resolver, never reached before in this project
  — has been observed firing.

  What is not reliable is delivery. Whole runs occur in which no command
  reaches the hook at all, including the coordinate and browse-key verbs that
  are otherwise dependable, while every readiness check in `report.json`
  passes. The prime suspect is scheduling rather than the channel: since
  `startUp()` began running, rbp spawns `SCHED_FIFO` priority-98 threads
  (`TouchPanel::run` calls `setschedparamFIFO(0x62)`, and the panel comms
  thread runs at the same priority on a 3 ms timer), and the emulator's poll
  loop is an ordinary `SCHED_OTHER` thread. Under QEMU with few cores that is
  enough to starve it. Holding one `O_RDWR` descriptor instead of re-opening
  per poll was tried and made things no better, so it was reverted to the
  rendezvous form that has the longer track record.
- `tools/rx3_emulator/patches.py` (the forced `startUp()` branch) is no longer
  needed: `init()` returns on its own, so `main` takes that branch unaided. It
  stays, off by default, as a documented negative result.
- **The pad row draws no text at all**, so the pad-label template can never be
  captured as designed. Measured: twelve window subtrees issue text draws —
  `0x01 0x02 0x03 0x06 0x07 0x08 0x09 0x0b 0x0c 0x10 0x11 0x16` — and the pad
  subtree `0x17`/`0x18` is not among them. Those labels are images. The comment
  in the source describing the template as a clone of "the stock deck-2 KEY
  label" describes something that does not exist.

- **Pioneer's own artwork settles the style, and it is in `imagedata.dat`.**
  That file is a table of 44-byte records at offset 0 followed by pixel data —
  the same record layout the mod already manipulates in memory, with width at
  `+4`, height at `+6`, format at `+0x18` and the pixel offset at `+0x20`. The
  first pixel offset is exactly 5581 x 44, and format 2 is RGB565 with the
  palette offset set to the file length as a no-palette sentinel. Reading it
  needs nothing new.

  Ids `0x1439..0x1470` hold the BEAT FX captions at 160x40, and every caption
  ships four variants: dim or white lettering on a black or blue ground. That is
  the whole colour language of this interface — it is monochrome, and blue marks
  the selected item. Measured exactly: ground `(0,0,0)` or `(0,125,230)`, ink
  `(98,101,98)` or `(255,255,255)`.

  The firmware ships fonts, and they are the wrong ones. `gui/system/fontdata`
  holds `decker.ttf` ("Decker Bold") and `sazanami-gothic.ttf`; measured against
  the real captions they are 11.1 px and 14.8 px out, so Decker is a display
  face and sazanami the CJK fallback. The UI font is
  `gui/pset/fontdata/NS_FONT_ID_ISO8859_w.bin`, 79 758 bytes in Pioneer's own
  format — not a linear bitmap at 1 or 4 bits per pixel, so it carries an offset
  table or per-glyph records and was left undecoded.

  Rasterisation was matched rather than the file. Pioneer's glyphs quantise to
  sixteen grey levels, which is 4-bit anti-aliasing, and their vertical stems
  are solid with the anti-aliasing only on curves — hinting. Supersampling
  matched the pixel totals but softened the stems and looked wrong at zoom, so
  the lettering is drawn once at final size, hinted, in Light to reach their
  stroke mass, with the coverage quantised to sixteen steps.

  Fitting fourteen of those captions gives the face: **Helvetica Neue Light at
  24**, at 1.1 px mean error — closer to Pioneer's own bitmap font than either
  TrueType Pioneer ships, which suggests theirs was rasterised from Helvetica or
  a metric clone of it. Earlier text here said Helvetica Neue at 23;
  reproducing Pioneer's widths to 1.3 px mean. An earlier fit against the
  KEY/STEMS tab artwork had chosen Arial Narrow Bold, which is 10.6 px out — the
  tab strip is the project's own drawing, not Pioneer's, and was never a valid
  reference. The generated labels now sit beside the stock ones essentially
  indistinguishable.

- **Cloning does not carry the font.** With the donor made selectable, four
  different donor subtrees were captured successfully and every one rendered the
  control label at exactly 19 px — the same as the header donor, and the same
  2x-stock size the labels have always had. So the long-standing premise that
  the cloned glyph determines the face is false, at least for size: either the
  font follows the window the draw is retargeted into, or it lives outside the
  0x54 bytes that are copied. Fixing the font therefore needs a different
  mechanism, and drawing the labels as images the way Pioneer does is now the
  more likely route.

- The on-screen controls still wear the header's typeface, at twice the size of
  a stock label, and selected still looks like unselected. Both come from the
  same place: the controls are drawn by cloning one of rbp's own text objects,
  and the colour fields on that object are not plain RGB. `NS_PALRender_DrawText`
  decodes them three different ways depending on the pixel format of the window
  being drawn into, which it takes from `DS_GR_GetWindowInfo` rather than from
  the object. Feeding it RGB888 painted magenta lettering on green; RGB565
  painted green; sweeping all 256 low-byte values moved the green channel alone
  and never lifted red or blue off zero. Until the format reported for the pad
  layers is identified, the drawing code inherits those colours rather than
  guessing at them — which is also the explanation for an older note in the
  source that every literal colour "looked foreign".

## 0.5.2

A runtime built on Windows loads its modules again.

### Fixed

- An `autoexec.bin` built on Windows stopped with `STOP: one or more runtime
  modules violate their contract`, one `FAILED: unsafe runtime module
  directory` per selected module. The index naming the modules to load was
  written with the building machine's line endings, and the shell that reads it
  took the trailing carriage return as part of the directory name. Affects
  0.5.0 and 0.5.1 built on Windows; 0.4.0 predates the index.

## 0.5.1

Reinserting the drive works. It used to be refused, and before that it was what
the deck made you do, because applying a module emptied the media list. The
runtime also stops writing to the drive unless you ask it to.

### Fixed

- Reinserting a drive without a power cycle no longer stops with
  `STOP: unsupported rbp SHA-1`. The check hashes the whole player binary, so a
  session this runtime had already patched no longer matched the state it
  started from. The guarded words are put back to their stock values before the
  comparison, which answers the question the check means to ask — is this the
  binary I know? — without being fooled by our own writes. A guarded word
  holding neither value still survives normalisation, and the word-by-word
  audit that follows still rejects it before anything is written.
- Reinserting a drive no longer restarts the player. A drive pulled out as
  `sda` comes back as `sdb`, so it mounts somewhere else; the sidecar directory
  is read once at load time, so a moved path meant stopping and relaunching —
  which froze the screen and emptied the media list, which is what made the
  drive get pulled again. The player is handed one fixed path, re-pointed on
  each insertion, and a reinsertion now changes nothing.
- A player that exits straight after being relaunched is rolled back to the
  stock binary instead of to the previous bytes. On a reinsertion those
  previous bytes are the patched ones, so the rollback relaunched exactly what
  had just died. The runtime's shared objects come out of `LD_PRELOAD` with it.
- The log of the run that applied the patch survives the next insertion, in
  `session-previous.txt`. The player's cumulative output carries a marker per
  launch, so one run's crash no longer reads as the next run's.

### Added

- **Session logging** is a module of its own, and it is not selected by
  default: an ordinary build now writes nothing to the drive at all. Tick it to
  get `RX3_RUNTIME/session.txt` and the player's output — and eject the drive
  rather than pulling it out while that build is in use, because the player
  keeps the log open for as long as it plays. That open handle is also what
  stopped the kernel releasing the device, which is why a drive came back under
  another name.
- The log names what forced a restart, and each module says what it saw that
  made it ask.

### Changed

- A relaunched player is given up to the same eight seconds, but the wait ends
  as soon as every module has written its readiness file — a second, in
  practice. The media that is already mounted is announced to it as soon as the
  process is alive, rather than after the readiness verdict.
- Everything the RX3 executes moved from `runtime/` to `mod/`. The word said
  *when* the code runs, which the directory above it does too — `apps/` and
  `tools/` are runtimes of their own, and two of them are literally named
  `rx3_runtime`. `mod/` says what the directory holds and matches the word the
  documentation already uses when it speaks to a DJ. The `runtime_directory` key
  in a module manifest, the `RX3_RUNTIME/` folder written to the drive, and the
  separation runtime are unrelated names and keep theirs.

### Known issues

- A drive still takes several seconds to reappear after a module is applied.
  The runtime announces it about a second after the player is relaunched, so
  what remains is on the device side: the player is seen to crash twice before
  a third launch sticks, and the log reports
  `rejected: unexpected PcmReader::load prologue` on those attempts. The
  binary patch that widens the image table stays applied even when the hook
  gives up installing it, which leaves the player accepting identifiers it has
  no records for. Under investigation.

## 0.5.0

The two applications became one, and the stems half answers the questions it
used to leave the operator guessing at.

### Changed

- `RX3 Mod Generator` and `RX3 Stem Studio` ship as a single application,
  `XDJ-RX3 Toolkit`, with a **USB Runtime** tab and a **Vocal Stems** tab. One
  download per platform replaces two; the `XDJ-RX3-Mod-Generator-*` and
  `XDJ-RX3-Stem-Studio-*` archives are retired in favour of `XDJ-RX3-Toolkit-*`.
  `make gui` and `make stems-gui` become `make app`. The per-user data directory
  keeps its old name, so an installed separation runtime is found rather than
  downloaded again.
- Secondary text follows the desktop appearance instead of a fixed `#555555`
  chosen against a light window. On a dark desktop the help text in Advanced
  options was grey on grey at roughly 1.6:1; it is now above 8:1 in both
  appearances, and follows a mid-session appearance change.
- The progress line says which track is being worked on — *track 3 of 20* —
  rather than how many are behind it, which read one short of reality.
- A preset resolves to an architecture rather than to a fixed model, and picks it
  from what the machine accelerates. The best models in the catalogue are
  roformers, which are PyTorch checkpoints; the ones that reach a GPU without
  PyTorch are MDX-Net, which are ONNX graphs. Where PyTorch runs on the GPU —
  CUDA, Apple Silicon, ROCm — both presets now run the roformer, and **Fast** is
  the same model over fewer passes rather than a weaker one. Where it does not —
  DirectML, whose PyTorch backend is pinned far behind what a roformer needs, and
  any CPU-only build — both run MDX-Net, giving up about 2.4 dB of vocal SDR to
  reach the hardware that is there. The summary under the selector states which
  of the two you are getting, because one preset is no longer one offer.
- **Fast** no longer overrides the segment size. It used to ask for 512 against
  the model's own 256 on Apple Silicon and ROCm, which is what selected the
  PyTorch route for an ONNX model — at the cost of running it at double the
  context its weights were trained for, blurring the mask in both directions. The
  architecture split does that job now, so every model runs at its own segment
  size. On a Mac, this also lifts MDX-Net's 17.6 kHz band limit, above which
  nothing was ever separated and the air of a vocal stayed in the instrumental.
- CoreML is still not used on a Mac: it is offered and enabled, but cannot take
  an MDX-Net graph whole — it claims 151 of 178 nodes across 28 partitions, so
  the work stays interleaved with the CPU, which is what the activity monitor was
  showing. An Intel Mac reaches no GPU at all, since audio-separator gates MPS on
  the processor being ARM.
- The `mdxc_overlap` help text said "Higher is better and slower". It is the
  opposite on a roformer: the option is a step in seconds, so a higher value
  advances the prediction window further and stitches the result from fewer
  passes. For `vocals_mel_band_roformer` the chunk is 11.0 s, which makes the
  default of 8 a 27% overlap and anything from 11 up a single pass with none at
  all. Anyone who raised it for quality was lowering it.
- Measured throughput is keyed by preset as well as by architecture and
  accelerator. Both presets run the same model on most machines and differ by
  roughly a factor of two in passes, so one shared rate was wrong for each of
  them in turn. Rates recorded under the old key are re-measured.
- Modules sit at one level, `runtime/modules/<id>/<firmware>/`, named after the
  `id` their manifest declares. Three of them were a level deeper, under an
  `access/`, `buffer/` or `beatjump/` category that no document described, so
  the path could not be guessed from a `requires` entry. Manifests are
  unchanged and the on-device layout is unaffected.
- The offline beat jump patchers moved out of `runtime/` to
  `tools/rx3_patcher/`, invoked as `python3 -m tools.rx3_patcher.<name>`. They
  run on a workstation, not on the deck, which is the line `runtime/` draws.
- `make hook` and `make test` discover module headers and regression guards
  instead of listing them. Adding a module no longer means editing the Makefile.
- Both Beat Jump modules now declare `requires: ["decoder-sleep"]`, so selecting
  either one brings the faster decoder polling with it. `decoder-sleep` moves
  from manifest order 30 to 8, because the build engine loads a dependency
  before what needs it; it can still be selected on its own.
- The feature list shows every module, including internal ones. The performance
  core appears greyed out and ticks itself when Key Shift or Stems is selected.
  Ticking a module ticks what it requires, and unticking one unticks whatever
  would be left requiring it. The propagation reads the manifests, so a new
  dependency needs no interface change.

### Added

- **Fast** and **High quality** presets, and **Custom** for anything tuned by
  hand. Both run the best-scoring vocal model and differ in `mdxc_overlap`, so
  switching between them needs no second download. Editing a model or parameter
  in Advanced options switches the setting to Custom rather than leaving a
  preset name on a configuration it no longer describes.
- A duration estimate, stated before the run from the playlist's own track
  lengths and corrected from the machine's measured speed as it goes. Measured
  speeds are kept in `throughput.json` per architecture and accelerator, so
  later runs start calibrated.
- A standing notice that separation occupies the machine, and a confirmation
  before any run estimated at more than ten minutes.

## 0.4.0

Two reasons a sidecar was ignored or left the vocal in the instrumental. Both
affect tracks prepared by any earlier version, which have to be generated again.

### Fixed

- Sidecars are named with the truncation Rekordbox applies when it exports a
  track to a drive, keeping the first 44 characters of the stem. A track whose
  library filename is longer reached the drive shortened while its sidecar kept
  the full name, and the deck never matched the two. Two tracks that collide
  only once truncated are now reported as ambiguous, as they always should have
  been.
- Stems for mp3 and AAC sources are aligned to the deck's decoder rather than
  FFmpeg's. Those containers declare the samples their encoder prepended;
  FFmpeg drops them and the deck plays them, which left the stem 25 ms early and
  the vocal fully audible in the instrumental while the vocal pad still worked.
  Existing sidecars for such sources have to be generated again — delete them,
  or the run keeps them as already generated. WAV, AIFF and FLAC sources were
  never affected.

The manifest gained `encoderDelayFrames`, the padding each stem was pushed back
by.

## 0.3.0

First tagged release. Git history was reset to a single commit at this point, so
there is nothing before it to compare against. The tables below translate names
used in earlier unreleased builds and in any external tutorial written against
them.

### Renamed

Modules and applications were renamed so that each name describes what the code
actually does. There is no compatibility alias anywhere: a path from an older
tutorial will simply not exist. Use this table to translate.

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

Module identifiers are unchanged. `beatjump-32bars`, `beatjump-no-quantize`,
`decoder-sleep`, `stems` and `telnet` still select the same modules on the
command line and in the manifests. The name of the project itself, XDJ-RX3
Toolkit, is unchanged.

Everything the RX3 executes now lives under `runtime/`. Everything above it runs
on your computer.

### Changed

Documentation was rewritten. The single README became a short landing page plus
`docs/`, with a Quick Start that runs from a bare computer to a track playing in
stems without a forward reference. See `docs/`.

Two corrections to earlier documentation, both resolved against the code:

- The accelerator table in `apps/rx3-stem-studio/README.md` claimed CUDA used
  the default PyTorch wheels. It uses an explicit index, `cu130`, or `cu126` on
  cards below compute capability 7.5 (`tools/rx3_stems/provisioning.py`).
- The count of guarded words for Beat Jump was stated as thirteen in one file
  and twelve in another. The count is no longer documented; the offsets in
  `runtime/modules/beatjump/beatjump-32bars/1.19/patch.py` are the reference.

### Note on earlier versions

The troubleshooting table used to carry a fix attributed to "v0.2.1". No tag or
release corresponds to that version, so the fix is described without it.
