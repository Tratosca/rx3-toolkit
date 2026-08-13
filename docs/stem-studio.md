# Vocal stems

The **Vocal Stems** tab of XDJ-RX3 Toolkit: generating stems, choosing a quality
preset, and managing the separation runtime. For a first run, follow the
[Quick Start](quickstart.md) instead.

Separation happens on your computer. The RX3 never separates anything, and your
audio never leaves the machine.

## The job

1. Export your Rekordbox collection as XML.
2. Select the XML file and the playlist to process.
3. Select a destination, pick a quality preset, and start.

The tab writes an `RX3_STEMS` directory and a JSON manifest. Copy
`RX3_STEMS` to the root of the Rekordbox USB drive, or select the drive as the
destination and skip the copy.

A sidecar is matched to a track by exact basename, so `Artist - Title.mp3` needs
`Artist - Title.rx3stem`. Rekordbox shortens long filenames when it exports a
track to a drive, keeping the first 44 characters, and the deck only ever knows
the shortened name; the sidecar is named the same way, from the library
file it separated. Two tracks that end up with the same name are rejected rather
than guessed at, because the RX3 load interface exposes nothing that would tell
them apart.

Existing valid sidecars are kept on later runs, so an interrupted job resumes
where it stopped. A track that fails is reported and the queue continues. If the
destination is a mount point and it disappears mid-job, the run stops with an
explicit error instead of writing to a stale path.

This tab never installs `autoexec.bin` and never writes to the RX3. That is
the **USB Runtime** tab's job.

## Where things are stored

| Platform | Managed runtime and model cache |
|---|---|
| macOS | `~/Library/Application Support/RX3 Stem Studio` |
| Windows | `%LOCALAPPDATA%\RX3 Stem Studio` |
| Linux | `$XDG_DATA_HOME/rx3-stem-studio`, or `~/.local/share/rx3-stem-studio` |

`RX3_STEM_STUDIO_HOME` overrides that location. The directory keeps the name the
separate Stem Studio application used, so a runtime installed by that version is
still found rather than downloaded again. Model choices and tuning live in
`separation.json` beside the runtime; measured separation speeds live in
`throughput.json`.

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

## Quality presets

The tab offers three settings.

| Setting | Model | Use it when |
|---|---|---|
| **Fast** | MDX-Net, a few tens of megabytes | Auditioning a playlist, or a long queue has to finish tonight |
| **High quality** | the best vocal roformer the catalogue offers, over more passes | The stems are going in a set |
| **Custom** | whatever you set | You tuned something by hand |

The presets trade a model, not a parameter. The roformer high quality runs
scores about 12.6 dB of vocal SDR; the MDX-Net model Fast runs scores about
10.2 dB from roughly a third of the inference. What that gap sounds like is a
little more instrument left in the acapella. MDX-Net models are band-limited
where the roformer is not, so the residue the deck cannot cancel sits at the
very top of the sibilance rather than anywhere with pitch in it.

High quality also asks for more passes than the model would take on its own,
through `mdxc_overlap`. Despite the name it is a hop divisor rather than an
amount of overlap: lowering it steps the prediction window less far along the
track, so the result is stitched from more passes and more inference is done.
The preset sits at 4, below the model's own default of 8.

How much time either actually costs depends on the model, the device and what
else the machine is doing, so nothing in the interface quotes a ratio. The
estimate under the selector answers it from this machine's own measured
throughput instead.

A preset names a candidate list rather than a single filename, because the model
catalogue comes from audio-separator and can change upstream. The first
candidate the catalogue actually offers is used; if none of them survive, the
best-scoring model of that preset's architecture is.

### Which runtime the fast model is executed by

An MDX-Net model is an ONNX file, but that does not decide what executes it.
audio-separator opens an ONNX Runtime session only while the segment size equals
the model's own internal `dim_t`; otherwise it converts the graph to PyTorch and
runs it on the Torch device. Both routes run the same network. Which one is
quicker depends on the machine:

| Accelerator | PyTorch | ONNX Runtime | Fast is routed through |
|---|---|---|---|
| NVIDIA CUDA | GPU | GPU | ONNX Runtime |
| Apple Silicon | GPU (Metal) | CoreML, **mostly on the CPU** | PyTorch |
| DirectML | CPU | GPU | ONNX Runtime |
| AMD ROCm | GPU | **CPU** | PyTorch |
| CPU only | CPU | CPU | ONNX Runtime |

Apple Silicon is the case worth explaining, because CoreML looks like it works.
It is offered, it is enabled, and it does take most of the model — but it cannot
take the graph whole. On an MDX-Net model it claims 151 of 178 nodes and splits
them into 28 partitions, so the run spends its time passing tensors back and
forth with the CPU, which is what shows up in Activity Monitor. Converted to
PyTorch and run on Metal instead, the same model separated a minute of audio in
12.1 s against 42.6 s.

The preset therefore asks for a segment size of 512 rather than the model's own
256 on those two accelerators, which is what selects the PyTorch route — and
incidentally doubles the context each chunk is separated with. It is the same
model file on every accelerator, so changing accelerator never downloads
anything, and never changes the preset you chose.

Changing a model or a parameter in Advanced options switches the setting to
**Custom**. A preset therefore always describes exactly one configuration, and
hand tuning is never quietly relabelled as something it is not.

## How long it takes

Once a playlist is selected, the tab states its track count, its total audio,
and how long separation should take. The first estimate comes from a table of
typical speeds per architecture and accelerator and is marked *(rough)*. As soon
as a track finishes, the real speed of this machine replaces it, and the
estimate is refined again at every progress tick. The measured speed is written
to `throughput.json` per architecture and accelerator, so later runs start
calibrated rather than guessing.

A run estimated at more than ten minutes asks for confirmation first, because it
will occupy the machine: keep the computer plugged in and awake, and close other
demanding applications. Shorter runs start without asking.

While the job runs, the status line names the stage, the track, its position in
the playlist — *track 3 of 20*, counting the one being worked on, not the ones
behind it — and the time remaining.

## Advanced options

The main window carries the export, the playlist, the destination and the
quality preset.
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

The quality presets pick from this list for you, so it can be ignored entirely.

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
