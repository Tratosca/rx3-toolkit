# XDJ-RX3 Toolkit

Adds ±32 beat jumps, faster decoder polling, and vocal/instrumental pad control
to a Pioneer DJ XDJ-RX3, from a file on your USB drive. Nothing is flashed. A
power cycle restores the stock system.

Two applications ship with it. RX3 Mod Generator writes the file the RX3 reads.
RX3 Stem Studio prepares the stems, which are the separated vocal and
instrumental parts of a track.

## What you need

| | |
|---|---|
| Device | XDJ-RX3, any hardware revision |
| Firmware | `1.19` |
| Computer | Windows x64, macOS (Intel or Apple Silicon), or Linux x64 |
| USB drive | FAT32 or exFAT, exported from Rekordbox |
| Key | An RX3 encryption key file, which this project does not distribute |
| Disk | About 1.5 GB for the separation runtime, plus 50 MB to 650 MB per model |

Time: about 20 minutes to set everything up, then a few minutes of separation
per track. An NVIDIA, AMD or Apple Silicon GPU changes that by an order of
magnitude.

The encryption key is not in this repository and never will be. It exists in
source code Pioneer published publicly. Finding it, **and deciding whether you may use it, is on you**. However, the Pioneer-distributed archives `pioneerdj_xdj_rx3.tar.bz2.00` and `pioneerdj_xdj_rx3.tar.bz2.01` available on the [Pioneer GPL/LGPL source code site](https://www.pioneerdj.com/en/support/open-source-code-distribution/gnu-open-source-license/) does contain the material to compile the RX3's Linux `initramfs`, which does happen to expose the key in `/usr/local/pdj/aes256.key`. See [Extracting the initramfs](docs/extract-initramfs.md).

## Before you start

Read this please.

Nothing is written to any ROM, NAND or flash memory ofthe RX3. The way this unit boots, and the way Pionner wanted to be able to run on it their own maintenance/repair scripts made this possible "live", on RAM, without any flash.

When the patch is applied, if the application does not survive eight seconds, the previous
unpatched is restored automatically. Power off, remove the drive, power on, and the
device is stock (and very probably under warranty) again. 

There is no firmware backup step because there is nothing to back up.

What can still go wrong is a crash or an unresponsive interface, which is a real
problem in the middle of a set even though it costs you nothing permanently.
Test at home first. Keep a second, unmodified Rekordbox drive in the bag.

Running unofficial code on any device is in general likely to affect the manufacturer warranty. As usual on that kind of projects, assume it does, but I'm confident it does not on that very specific device

This is for educational purposes. I cannot be held responsible if it causes a
crash during a $50k DJ set, or, far less plausibly, if it bricks your device. I
do wish you the opportunity to play the $50k gig tho.

This project is not affiliated with, endorsed by, or connected to Pioneer DJ or
AlphaTheta. Product names identify the tested hardware and nothing more.

Stem Studio separates the tracks you feed it, on your computer. What you are
entitled to do with those tracks, and with the stems that come out, is your
responsibility and depends on where you live and what you licensed.

## Quick Start

Do the steps in order. 

This guide assumes you already have at least one Rekordbox prepared USB stick with some songs and playlists in it.

### 1. Check the firmware version

Disconnect every USB drive from the RX3 and power it on normally. Hold
**MENU (UTILITY)** for more than one second, then scroll to the bottom of the
Utility screen.

**What you should see:** a line reading `VERSION No.` followed by `1.19`.

**If it does not work:** if the version is anything other than `1.19`, stop
here. This project neither updates nor downgrades firmware, and applying it to
another version does nothing, because the RX3 refuses a player binary it does
not recognise. AlphaTheta documents the update procedure
[in its own support article](https://support.alphatheta.com/en-US/articles/5097637194137?product=4416587179673).

Close Utility and power the RX3 off.

### 2. Download RX3 Mod Generator & Stem Studio 

Go to the [Releases page](../../releases) and download the RX3 Mod Generator
archive matching your computer: Windows x64, macOS Apple Silicon, macOS Intel,
or Linux x64. Unpack it wherever you keep applications.

Do the same for Stem Studio if you want to generate stems.

### 3. Clear the macOS quarantine attribute

Skip this step on Windows and Linux.

Both applications are unsigned, so macOS refuses to open them and often reports
them as damaged. The **quarantine attribute** is a marker your browser attaches
to anything it downloads, and clearing it is what lets an unsigned application
run. In the terminal from step 2, type the two lines below, replacing each path
with the real location of the unpacked application. Drag the application onto
the terminal window to insert its path.

```sh
xattr -rc "/Applications/RX3 Mod Generator.app"
xattr -rc "/Applications/RX3 Stem Studio.app"
```

**If it does not work:** `No such file or directory` means the path is wrong.
Run the command against the unpacked `.app` wherever you actually put it, not
against the `.zip` and not against a folder containing it. 

On Windows, expect a SmartScreen dialog instead; choose **More info**, then **Run anyway**.

### 4. Optional : Stems

#### a. Optional : Generate a stem dedicated playlists

In Rekordbox, generate a playlist with the name you want and put all the songs you want stem generated into it. 
> I recommend you to try with a few songs first.

#### b. Export your Rekordbox collection as XML

In Rekordbox, use the collection XML export. Stem Studio reads this file to find
where your audio files live on disk and which tracks belong to which playlist.

**If it does not work:** the option lives in Rekordbox preferences, under the
Advanced or View section depending on your version. It is a different thing from
exporting to a drive, which you did at step 6.

#### c. Open RX3 Stem Studio

Launch the Stem Studio application you downloaded.

**If it does not work:** on macOS, a "damaged" or "cannot be opened" dialog
means step 5 did not take effect on this application. Repeat it against this
exact `.app`.

#### d. Install the separation runtime

Select **Set up…**, then **Install**.

Separation needs a large amount of software that is not in the download:
audio-separator, PyTorch and FFmpeg together weigh far more than the
application. Stem Studio installs them into a **virtual environment**, which is
a private folder of Python packages that does not touch the rest of your
computer.

**What you should see:** a progress log, then the setup panel disappearing.
This needs an internet connection, about 1.5 GB of disk space, and a Python
interpreter between 3.10 and 3.13 already installed on your computer.

**If it does not work:** if it refuses to start and mentions Python, install
Python 3.13 from [python.org](https://www.python.org/downloads/) and try again.
If it stops partway, select **Install** again; the same button completes an
environment that already exists rather than starting over.

#### e. Load the XML file, the playlist and the destination

In the main window, select the XML file, then the playlist to
convert stems from, then your USB drive that contains the original songs you're converting.

> Exporting the stem dedicated playlist to USB is not necessary. The RX3 matches the stems with original songs via filename.


#### f. Generate the stems

Start the job.

Each track is decoded, separated, and written as one `.rx3stem` file. That file
is a **sidecar**: it sits beside the audio and carries the vocal part, and the
RX3 subtracts it from the mix to produce the instrumental. Separation is the
slow phase, a few minutes per track, and it will keep your machine busy. If your computer has a GPU, it will be much faster.

**If it does not work:** a track that fails is reported and the queue carries
on, so let it finish and read the log. If every track fails immediately, the
runtime is incomplete: use **Install** again in Advanced options, Runtime tab.
Details in [Troubleshooting](troubleshooting.md#every-track-fails).

### 5. Generate the mod RX3 Mod Generator

Open RX3 Mod Generator you downloaded from step 3, and select firmware `1.19`.

Select your RX3 encryption key file.

>[!CAUTION] 
This project does not distribute that key and cannot. It exists in source code
Pioneer published publicly. Obtaining it, and deciding whether you may use it,
is your call, and it is the one step in this guide that nobody can do for you.

Choose the root of the USB drive as the output folder, then select
**Build autoexec.bin**. When it finishes, eject the drive properly.

`autoexec.bin` is the encrypted file the RX3 looks for on every drive you
insert. It is the entire mod.

**What you should see:** the drive root now holding four entries.

```text
USB drive/
  autoexec.bin
  RX3_STEMS/
  Contents/
  PIONEER/
```

**If it does not work:** the generated image is decrypted and re-verified before
it is accepted, so a failure here means the key is wrong rather than the drive.
If an `autoexec.bin` already exists, the application asks before replacing it.

### 6. Apply the mod

Order matters. With the drive **disconnected**, power the RX3 on and wait until
the interface is fully loaded and responsive. Only then insert the drive.

Do not touch the controls, do not remove the drive, and do not cut power while
the interface stops and restarts.

**What you should see:** the interface goes away for a few seconds and comes
back. On the drive, a new `RX3_RUNTIME/session.txt` file whose last line reads
`=== complete ===`.

**If it does not work:** if the interface does not come back, remove the drive
and power cycle (which power chord if needed); the RX3 returns to stock. If `session.txt` contains a line
starting with `STOP:` or `FAILED:`, delete `autoexec.bin` from the drive and
read [Troubleshooting](troubleshooting.md#the-session-log-says-stop-or-failed).

### 7. Enjoy !

Load one of the tracks you prepared at step 5, then select Slip Loop mode.

**What you should see:** pads 7 and 8 lit, pad 7 red for the instrumental and
pad 8 green for the vocal. Each is an independent switch. Both on plays the full
mix, one on plays that part alone, both off is silence. Press pad 8 and the
vocal drops out.

While the sidecar is still loading, both pads blink; they hold their colour once
it is loaded.

Open Beat Jump mode on the same track. Pads 7 and 8 now read `32` and jump 32
beats, and repeated presses fire immediately instead of waiting for the grid.

**If it does not work:** pads 7 and 8 creating loops as usual means no
`.rx3stem` matched this track. That is the intended fallback, not a failure. The
sidecar and the audio file must share exactly the same name before the
extension. See
[Troubleshooting](troubleshooting.md#a-prepared-track-has-no-stem-controls).

### Returning to stock

Stop playback, power the RX3 off, remove the drive, and power on without it.
Everything is gone.

Leaving the drive in re-applies `autoexec.bin` on the next power-on. To stop
that for good, delete `autoexec.bin` from the drive.

## Documentation

| Document | For |
|---|---|
| [Extracting the initramfs](docs/extract-initramfs.md) | How to extract the initramfs of the XDJ-RX3 from Pioneer GPL
| [The RX3 mod](docs/mod-rx3.md) | Modules, applying, removing, reading the session log |
| [Stem Studio](docs/stem-studio.md) | Models, accelerators, tuning, managing the runtime |
| [Troubleshooting](docs/troubleshooting.md) | Symptoms and fixes |
| [Reference](docs/reference.md) | Commands, formats, addresses, hardware findings |
| [Contributing](CONTRIBUTING.md) | Building from source, tests, adding a module |
| [Changelog](CHANGELOG.md) | Renames, and what changed |

## License

Original source code is under the [Mozilla Public License 2.0](LICENSE).
Changes to MPL-covered files stay under the MPL; separate files may be combined
into a larger work under different terms, as the license permits. Third-party
components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Keys, firmware, manufacturer binaries and compiled payloads are not included in
this repository and are never release assets.
