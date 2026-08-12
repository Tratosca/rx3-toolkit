# Troubleshooting

Symptoms, in the order you are likely to hit them. Each heading is linkable.

## macOS says the application is damaged

It is unsigned, and macOS refuses unsigned applications that carry a download
marker. Clear the marker on the unpacked `.app`, wherever you actually put it,
not on the `.zip`:

```sh
xattr -rc "/path/to/RX3 Mod Generator.app"
```

Control-click then Open used to be enough. Recent macOS releases no longer offer
that path for an unsigned application.

On Windows the equivalent is a SmartScreen dialog: choose **More info**, then
**Run anyway**.

## Nothing happens when I insert the drive

Check three things, in this order:

1. the file is named exactly `autoexec.bin`, lower case, no second extension;
2. it sits at the root of the drive, not in a folder;
3. it was built for firmware `1.19`, and the RX3 is running `1.19`.

If the RX3 does not see the drive at all, it is formatted as something other
than FAT32 or exFAT, or it was unplugged without ejecting. It is always one of
those two.

A key file that is empty, or that holds something other than the key on its
first line, produces an `autoexec.bin` the RX3 decrypts to garbage and silently
ignores. There is no error on the device.

## The interface does not come back

Remove the drive and power cycle. The RX3 returns to stock, because nothing was
written to it.

Then read `RX3_RUNTIME/session.txt` from the drive on your computer, and see the
next section.

## The session log says STOP or FAILED

Delete `autoexec.bin` from the drive before using the RX3 again.

`STOP:` means a precondition failed and nothing was modified. The most common
one is `STOP: unsupported rbp SHA-1`, which means the player binary is not one
the runtime recognises. That is firmware other than `1.19`, or a `1.19` build
this project has not seen.

`FAILED:` means something went wrong during modification and the previous state
was restored automatically.

Either way, attach the full `session.txt` when reporting the problem.

## Slip Loop pads 7 and 8 still create loops

No valid `.rx3stem` matched the loaded track. This is the intended fallback, not
a failure: an unprepared track behaves exactly like stock.

## A prepared track has no stem controls

The sidecar and the audio file must share exactly the same name before the
extension. `Artist - Title.mp3` needs `Artist - Title.rx3stem`. A trailing
space, a different dash character, or a renamed audio file all break the match.

Compare the names on the drive, not the names in your library. Rekordbox cuts a
filename to 44 characters when it exports the track, so a long title reaches the
drive shortened while the library keeps it whole. Stem Studio applies the same
cut. A sidecar generated before it did needs the same treatment: keep the first
44 characters of the name and the `.rx3stem` extension.

Check also that `RX3_STEMS` sits at the root of the drive and not inside another
folder.

## The instrumental still has the vocal in it

The vocal pad works, the instrumental pad does not, and the vocal is as loud as
ever rather than merely leaking. The stem and the audio the deck plays are on
different timelines.

You used an older version: please generate the track again with a current version. 
An MP3 or AAC file declares samples its encoder prepended, which FFmpeg drops but the deck plays; a sidecar
built without accounting for them sits about 25 ms early, which is far more than
subtraction tolerates. Releases before this handling shipped are affected only
for lossy sources that declare padding, which is why some of your tracks work.

If the run reports that the padding could not be measured, the source is one the
pipeline could not line up. Convert it to WAV or FLAC and generate it again.

## Stem Studio reports a missing runtime

Use **Install** in Advanced options, Runtime tab. Or point `RX3_SEPARATOR` and
`RX3_FFMPEG` at your own installation of audio-separator and FFmpeg, which the
application prefers over its own copy.

## Runtime installation refuses to start

No Python between 3.10 and 3.13 was found on your computer. Install one from
[python.org](https://www.python.org/downloads/) and retry. The newest supported
one installed is the one used.

## Every track fails

If separation itself completes and then every track fails, the managed
environment is incomplete. Use **Install** again in Advanced options, Runtime
tab. The same button completes an environment that already exists, which is the
fix for a runtime installed by an older version.

If the failure mentions `No such file or directory: 'ffmpeg'`, the runtime is
from a build that did not yet bundle FFmpeg. Reinstall the runtime, or install
FFmpeg so it sits on `PATH`.

## Separation fails partway with an FFmpeg filter error

The FFmpeg on your `PATH` is missing a filter the pipeline needs. Install the
separation runtime, which brings a complete copy the application prefers, and
the runtime summary will name the filter that was missing.

If you set `RX3_FFMPEG` yourself, that override is used as given and a gap in it
is reported rather than worked around. Point it at a complete build or unset it.

## The GPU is idle during separation

The runtime was installed for a different accelerator. The Runtime tab says so.
Select **Reinstall**, which rebuilds the environment rather than completing it,
because a CPU-only PyTorch cannot be accelerated afterwards.

The job log reports a fallback to the CPU whenever one happens.

On an Intel Mac this is expected and cannot be changed: audio-separator gates its
Metal path on an ARM processor.

## The waveform still shows the full track

Expected. The waveform is precomputed from the file and is not rebuilt from the
modified audio stream, so it does not follow the pad state.

## Stems or LEDs are wrong across two decks

Reproduce with one prepared track per deck, then attach both
`RX3_RUNTIME/session.txt` and `/tmp/rx3-stems.log` from the device. The second
file needs the Telnet module to be reachable.
