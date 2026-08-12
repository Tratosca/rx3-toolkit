# Quick Start

Sixteen steps, from a computer with nothing installed to a track playing in
stems on the RX3. Read [the warnings in the README](../README.md#before-you-start)
first if you have not.

Do the steps in order. Each one tells you what you should see, and what to do
when you do not see it.

Two words you will need. A **stem** is one part of a track on its own, here the
vocal or everything except the vocal. **Source separation** is the process that
splits a finished mix back into those parts, using a machine-learning model on
your computer.

Budget about 20 minutes for steps 1 to 10, then a few minutes of separation per
track. `[TODO: to be measured]`

## 1. Check the firmware version

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

## 2. Open a terminal

A **terminal** is a window where you type commands instead of clicking. You need
it once, at step 5, and only on macOS. Open it now so it is ready.

- **macOS:** press `Command` + `Space`, type `Terminal`, press `Return`.
- **Windows:** press the Windows key, type `Terminal`, press `Enter`.
- **Linux:** press `Ctrl` + `Alt` + `T`, or find Terminal in your applications.

**What you should see:** a window with a blinking cursor after a short line of
text ending in `$`, `%` or `>`. That line is the prompt. You never type it.

**If it does not work:** on Windows, `cmd` opens the same thing under an older
name. On Linux without a desktop shortcut, look for Konsole, GNOME Terminal or
xterm.

## 3. Download RX3 Mod Generator

Go to the [Releases page](../../releases) and download the RX3 Mod Generator
archive matching your computer: Windows x64, macOS Apple Silicon, macOS Intel,
or Linux x64. Unpack it wherever you keep applications.

**What you should see:** an unpacked application named `RX3 Mod Generator`, with
`.exe` on Windows and `.app` on macOS.

**If it does not work:** if the Releases page is empty, no packaged version has
been published, and you will have to build from source instead. See
[Contributing](../CONTRIBUTING.md). Never download a build offered in an issue,
a comment, or a mirror.

## 4. Download RX3 Stem Studio

From the same [Releases page](../../releases), download the RX3 Stem Studio
archive for the same platform. Unpack it next to the first one.

**What you should see:** an unpacked application named `RX3 Stem Studio`.

**If it does not work:** the two applications are separate downloads. Taking
only one of them is the usual mistake. You need both.

## 5. Clear the macOS quarantine attribute

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

**What you should see:** nothing at all. The command prints no output and gives
you a fresh prompt. That is success.

**If it does not work:** `No such file or directory` means the path is wrong.
Run the command against the unpacked `.app` wherever you actually put it, not
against the `.zip` and not against a folder containing it. On Windows, expect a
SmartScreen dialog instead; choose **More info**, then **Run anyway**.

## 6. Export a playlist from Rekordbox to the USB drive

In Rekordbox, export the playlist you want to the USB drive, exactly as you
would for any gig. The drive must be FAT32 or exFAT.

**What you should see:** on the drive, a `Contents` folder holding the audio
files and a `PIONEER` folder holding the library.

**If it does not work:** if the RX3 later refuses to see the drive at all, it is
formatted as something else or it was unplugged without ejecting. It is always
one of those two.

Leave the drive connected to your computer. You are not finished with it.

## 7. Export your Rekordbox collection as XML

In Rekordbox, use the collection XML export. Stem Studio reads this file to find
where your audio files live on disk and which tracks belong to which playlist.

**What you should see:** a single `.xml` file, usually several megabytes.

**If it does not work:** the option lives in Rekordbox preferences, under the
Advanced or View section depending on your version. It is a different thing from
exporting to a drive, which you did at step 6.

## 8. Open RX3 Stem Studio

Launch the application you unpacked at step 4.

**What you should see:** a window with fields for the XML export, the playlist,
and the destination, plus a panel saying the separation runtime is missing.

**If it does not work:** on macOS, a "damaged" or "cannot be opened" dialog
means step 5 did not take effect on this application. Repeat it against this
exact `.app`.

## 9. Install the separation runtime

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

## 10. Choose the export, the playlist and the destination

In the main window, select the XML file from step 7, then the playlist to
process, then the USB drive from step 6 as the destination.

**What you should see:** the playlist name and its track count in the window.

**If it does not work:** an empty playlist list means the XML is from a
different Rekordbox library, or the export is stale. Re-export it.

## 11. Generate the stems

Start the job.

Each track is decoded, separated, and written as one `.rx3stem` file. That file
is a **sidecar**: it sits beside the audio and carries the vocal part, and the
RX3 subtracts it from the mix to produce the instrumental. Separation is the
slow phase, a few minutes per track, and it will keep your machine busy. A GPU
changes that by an order of magnitude. `[TODO: to be measured]`

**What you should see:** a per-track progress percentage, then an `RX3_STEMS`
folder at the root of the USB drive holding one `.rx3stem` file per track, named
exactly like its audio file.

**If it does not work:** a track that fails is reported and the queue carries
on, so let it finish and read the log. If every track fails immediately, the
runtime is incomplete: use **Install** again in Advanced options, Runtime tab.
Details in [Troubleshooting](troubleshooting.md#every-track-fails).

## 12. Open RX3 Mod Generator and select the firmware

Launch the application from step 3, and select firmware `1.19`.

**What you should see:** a list of modules, most of them already ticked: Beat
Jump ±32, Immediate Beat Jump, Faster decoder polling, and Vocal and
instrumental controls. Diagnostic Telnet access is present and unticked. Leave
the defaults alone for a first run.

**If it does not work:** an empty module list from a packaged release means the
download is incomplete. Unpack the archive again.

## 13. Choose the encryption key file

Select your RX3 encryption key file.

This project does not distribute that key and cannot. It exists in source code
Pioneer published publicly. Obtaining it, and deciding whether you may use it,
is your call, and it is the one step in this guide that nobody can do for you.

**What you should see:** the path to your key file in the field.

**If it does not work:** the key file is a text file whose first line is the
key. A file that is empty, or that holds something else, produces an
`autoexec.bin` the RX3 silently ignores at step 15.

## 14. Build the file and eject the drive

Choose the root of the USB drive as the output folder, then select
**Build autoexec.bin**. When it finishes, eject the drive properly.

`autoexec.bin` is the encrypted image the RX3 looks for on every drive you
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

## 15. Insert the drive into the RX3

Order matters. With the drive **disconnected**, power the RX3 on and wait until
the interface is fully loaded and responsive. Only then insert the drive.

Do not touch the controls, do not remove the drive, and do not cut power while
the interface stops and restarts.

**What you should see:** the interface goes away for a few seconds and comes
back. On the drive, a new `RX3_RUNTIME/session.txt` file whose last line reads
`=== complete ===`.

**If it does not work:** if the interface does not come back, remove the drive
and power cycle; the RX3 returns to stock. If `session.txt` contains a line
starting with `STOP:` or `FAILED:`, delete `autoexec.bin` from the drive and
read [Troubleshooting](troubleshooting.md#the-session-log-says-stop-or-failed).

## 16. Play a track in stems

Load one of the tracks you prepared at step 11, then select Slip Loop mode.

**What you should see:** pads 7 and 8 lit, pad 7 red for the instrumental and
pad 8 green for the vocal. Each is an independent switch. Both on plays the full
mix, one on plays that part alone, both off is silence. Press pad 8 and the
vocal drops out.

While the sidecar is still loading, both pads blink; they hold their colour once
it is resident.

Open Beat Jump mode on the same track. Pads 7 and 8 now read `32` and jump 32
beats, and repeated presses fire immediately instead of waiting for the grid.

**If it does not work:** pads 7 and 8 creating loops as usual means no
`.rx3stem` matched this track. That is the intended fallback, not a failure. The
sidecar and the audio file must share exactly the same name before the
extension. See
[Troubleshooting](troubleshooting.md#a-prepared-track-has-no-stem-controls).

## Returning to stock

Stop playback, power the RX3 off, remove the drive, and power on without it.
Everything is gone.

Leaving the drive in re-applies `autoexec.bin` on the next power-on. To stop
that for good, delete `autoexec.bin` from the drive.
