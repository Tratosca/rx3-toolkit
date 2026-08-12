# Stem Studio

Generating stems, choosing a model, and managing the separation runtime. For a
first run, follow the [Quick Start](quickstart.md) instead.

Separation happens on your computer. The RX3 never separates anything, and your
audio never leaves the machine.

## The job

1. Export your Rekordbox collection as XML.
2. Select the XML file and the playlist to process.
3. Select a destination and start.

Stem Studio writes an `RX3_STEMS` directory and a JSON manifest. Copy
`RX3_STEMS` to the root of the Rekordbox USB drive, or select the drive as the
destination and skip the copy.

A sidecar is matched to a track by exact basename, so `Artist - Title.mp3` needs
`Artist - Title.rx3stem`. Two tracks with the same basename are rejected rather
than guessed at, because the RX3 load interface exposes nothing that would tell
them apart.

Existing valid sidecars are kept on later runs, so an interrupted job resumes
where it stopped. A track that fails is reported and the queue continues. If the
destination is a mount point and it disappears mid-job, the run stops with an
explicit error instead of writing to a stale path.

Stem Studio never installs `autoexec.bin` and never writes to the RX3.

## Where things are stored

| Platform | Managed runtime and model cache |
|---|---|
| macOS | `~/Library/Application Support/RX3 Stem Studio` |
| Windows | `%LOCALAPPDATA%\RX3 Stem Studio` |
| Linux | `$XDG_DATA_HOME/rx3-stem-studio`, or `~/.local/share/rx3-stem-studio` |

`RX3_STEM_STUDIO_HOME` overrides that location. Model choices and tuning live in
`separation.json` beside the runtime.

## The separation runtime

Separation is performed by [audio-separator](https://github.com/nomadkaraoke/python-audio-separator),
which exposes the UVR model families. It is not inside the release archive:
audio-separator, PyTorch and FFmpeg together are two orders of magnitude larger
than the application.

The components are resolved in a fixed order, and the first hit wins:

1. the `RX3_SEPARATOR` and `RX3_FFMPEG` environment overrides;
2. `audio-separator` and `ffmpeg` on `PATH`;
3. the managed environment under the data directory.

Providing them yourself is therefore equivalent to letting the application
install them. A separator found on `PATH` is used as-is and reported as
unmanaged; it is neither rebuilt nor removed.

**Install** creates the managed environment. It needs an internet connection,
about 1.5 GB of disk space, more for a CUDA build, plus 50 MB to 650 MB per
model you actually use. It also needs a Python interpreter between 3.10 and 3.13
already installed on your computer to seed the environment; the newest supported
one it finds is used.

The same button completes an environment that already exists, which is the fix
when separation fails on a runtime installed by an older version. An environment
sitting on an interpreter that is now out of range is rebuilt rather than
patched.

Three constraints in that environment are deliberate:

- PyTorch comes from the CPU wheel index unless you select an accelerator,
  because the default Linux and Windows wheels carry multi-gigabyte CUDA
  payloads a CPU pipeline never touches.
- `librosa` is pinned below 1.0, because audio-separator still imports
  `audioread` and calls `get_duration(filename=...)`, both removed there.
- The seeding interpreter is capped at 3.13, because audio-separator pins
  `beartype` below 0.19, which rejects the separator's own annotations on 3.14.

FFmpeg is exposed to the separator under its plain name through a link, because
the separator invokes `ffmpeg` by name through pydub while the copy bundled by
imageio-ffmpeg is named after its platform and version.

An FFmpeg found on `PATH` is preferred over the bundled copy, but only once it
has been shown to carry every filter the pipeline uses: `aformat`, `apad`,
`aresample`, `astats`, `atrim` and `volume`. Builds configured without one of
them exist, and the failure would otherwise land partway through a job rather
than at startup. An incomplete copy is passed over for the bundled one, and the
runtime summary names the filter that was missing. An `RX3_FFMPEG` override is
exempt: it is your decision and the documented escape hatch, so a gap in it is
reported rather than acted on.

## Hardware acceleration

audio-separator picks its inference device at run time: CUDA, then Apple Silicon
Metal, then DirectML when explicitly enabled, then the CPU. The **Acceleration**
setting therefore controls which packages get installed, not which device runs.
A CPU-only PyTorch cannot be accelerated afterwards, so changing the setting
means installing the runtime again.

| Setting | PyTorch source | audio-separator extra | Notes |
|---|---|---|---|
| Automatic | whatever detection picks | matching extra | The default |
| NVIDIA CUDA | `cu130` index, or `cu126` below compute capability 7.5 | `gpu` | Linux and Windows. PyPI ships a CPU-only PyTorch for Windows, so an explicit index is required |
| AMD ROCm | `rocm6.4` index | `cpu` | Linux. ONNX models still run on the CPU |
| DirectML | CPU index | `dml`, plus `--use_directml` | Windows AMD and Intel GPUs. Experimental |
| Apple Silicon (Metal) | PyPI | `cpu` | MPS and CoreML, ARM Macs only |
| CPU only | CPU index | `cpu` | Works everywhere, slowest |

Detection picks Metal on ARM Macs, CUDA when `nvidia-smi` reports a GPU,
DirectML on other Windows machines, ROCm when a ROCm installation is present,
and the CPU otherwise. Intel Macs stay on the CPU whatever GPU they carry,
because audio-separator gates its Metal path on an ARM processor.

Selecting another accelerator states that the runtime needs reinstallation and
turns the button into **Reinstall**. Separation keeps running on the installed
one until you do. Reinstalling for a different accelerator rebuilds the
environment rather than completing it.

## Advanced options

The main window carries only the export, the playlist and the destination.
Everything else sits behind **Advanced options…**, in three tabs. The runtime
panel appears in the main window only while the runtime is missing, since
nothing can run without it.

**Runtime** installs, repairs and removes the managed environment, and selects
the accelerator. Uninstalling removes the environment and keeps the downloaded
models. When the separator in use came from `PATH`, the tab says so and offers no
removal.

**Models** lists every vocal-capable model of the four architectures, MDX, VR,
MDXC and Demucs, with its vocal SDR and whether it is on disk. The list is cached
locally so startup does not reach the network; **Refresh list** re-reads it. Only
the model in use is ever downloaded. Choosing another one fetches it on first
use, or immediately with **Download**. **Delete** frees a model's files.

The default is the best-scoring vocal model in the catalogue, so the list can be
ignored entirely.

**Parameters** exposes the options that apply to the selected model: the common
ones, plus the group belonging to its architecture. A parameter left at its
default is never passed on the command line, and a parameter belonging to
another architecture is never passed at all.

## Output

Sidecars are 44.1 kHz, stereo, int16 PCM by default, which halves resident
memory on the device relative to float32. Sources at another sample rate are
resampled. The frame count is aligned to the full track decoded at 44.1 kHz,
not derived from the separator output duration alone.

Normalization is pinned to 1.0 and gain is measured rather than assumed, because
the instrumental is computed on the device as full mix minus vocal and any level
mismatch leaves audible vocal behind. The mechanism is described in
[Reference](reference.md#audio-domain-and-gain).
