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
| Firmware | `1.19`, and only `1.19` |
| Computer | Windows x64, macOS (Intel or Apple Silicon), or Linux x64 |
| USB drive | FAT32 or exFAT, exported from Rekordbox |
| Key | An RX3 encryption key file, which this project does not distribute |
| Disk | About 1.5 GB for the separation runtime, plus 50 MB to 650 MB per model |

Time: about 20 minutes to set everything up, then a few minutes of separation
per track. An NVIDIA, AMD or Apple Silicon GPU changes that by an order of
magnitude. `[TODO: to be measured]`

The encryption key is not in this repository and never will be. It exists in
source code Pioneer published publicly. Finding it, and deciding whether you may
use it, is on you.

## Before you start

Read this. It is short and all of it is load-bearing.

Nothing is written to the RX3. The modules patch a copy of the player
application held in RAM, after checking that the filesystem it runs from is
RAM-backed. If the patched process does not survive eight seconds, the previous
bytes are restored automatically. Power off, remove the drive, power on, and the
device is stock again. There is no firmware backup step because there is nothing
to back up.

What can still go wrong is a crash or an unresponsive interface, which is a real
problem in the middle of a set even though it costs you nothing permanently.
Test at home first. Keep a second, unmodified Rekordbox drive in the bag.

This is for educational purposes. I cannot be held responsible if it causes a
crash during a $50k DJ set, or, far less plausibly, if it bricks your device. I
do wish you the opportunity to play the $50k gig tho.

Running unofficial code on the device is likely to affect your manufacturer
warranty. Assume it does.

This project is not affiliated with, endorsed by, or connected to Pioneer DJ or
AlphaTheta. Product names identify the tested hardware and nothing more.

Stem Studio separates the tracks you feed it, on your computer. What you are
entitled to do with those tracks, and with the stems that come out, is your
responsibility and depends on where you live and what you licensed.

## Start here

[Quick Start](docs/quickstart.md) takes you from a computer with nothing
installed to a track playing in stems on the RX3, in sixteen steps.

## Documentation

| Document | For |
|---|---|
| [Quick Start](docs/quickstart.md) | First run, start to finish |
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
