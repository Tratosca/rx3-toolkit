<!-- SPDX-License-Identifier: MPL-2.0 -->
# Changelog

## Unreleased

The two applications became one, and the stems half answers the questions it
used to leave the operator guessing at.

### Changed

- Everything the RX3 executes moved from `runtime/` to `mod/`. The word said
  *when* the code runs, which the directory above it does too — `apps/` and
  `tools/` are runtimes of their own, and two of them are literally named
  `rx3_runtime`. `mod/` says what the directory holds and matches the word the
  documentation already uses when it speaks to a DJ. The `runtime_directory` key
  in a module manifest, the `RX3_RUNTIME/` folder written to the drive, and the
  separation runtime are unrelated names and keep theirs.
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
