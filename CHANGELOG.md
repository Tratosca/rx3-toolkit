<!-- SPDX-License-Identifier: MPL-2.0 -->
# Changelog

## Unreleased

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
