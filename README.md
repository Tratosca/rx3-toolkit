<h1 align="center">
  XDJ-RX3 Toolkit
</h1>

<p align="center">
  <b>Vocal &amp; instrumental stems, longer beat jumps, and more on your XDJ-RX3.</b><br>
  No flashing. No firmware surgery. Pull the USB stick out and your player is stock again.
</p>

<p align="center">
  <a href="../../releases"><img alt="Release" src="https://img.shields.io/github/v/release/Tratosca/rx3-toolkit?style=flat-square&color=ff5c00"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square"></a>
  <img alt="Firmware" src="https://img.shields.io/badge/XDJ--RX3%20firmware-1.19-black?style=flat-square">
  <img alt="Platforms" src="https://img.shields.io/badge/macOS%20%7C%20Windows%20%7C%20Linux-lightgrey?style=flat-square">
</p>

<p align="center">
  <a href="#what-you-get">What you get</a> •
  <a href="#quick-start">Quick start</a> •
  <a href="#playing-with-it">Playing with it</a> •
  <a href="#back-to-stock">Back to stock</a> •
  <a href="#roadmap">Roadmap</a> •
  <a href="#faq">FAQ</a> •
  <a href="#documentation">Docs</a>
</p>

<!-- Add a demo GIF or a photo of the pads here: ![demo](docs/assets/demo.gif) -->

---

## What you get

### 🎤 Vocal and instrumental on the pads

Prepare your tracks on your computer, load them on the RX3 the usual way, and
**Slip Loop** mode turns into stem control:

| Pad | Colour | What it does |
| :--: | :--: | --- |
| **7** | 🔴 Red | Instrumental on / off |
| **8** | 🟢 Green | Vocal on / off |

### ⏭️ 32-beat Beat Jump

Beat Jump gets a new **32-beat** mode. Repeated presses also fire
straight away instead of waiting for the grid to catch up.

### 🔌 Lives on the USB stick, not in the player

Everything runs from the stick and disappears when the power goes off. Any RX3 you plug your stick on will be modded. Nothing
is written to the player's internal memory, so there is no firmware to back up
and nothing to uninstall.

**Power off → pull the stick → power on → stock RX3.**

---

## What you need

| | |
| --- | --- |
| 🎛️ **Player** | Pioneer DJ XDJ-RX3, firmware `1.19` only at the moment |
| 💻 **Computer** | macOS (Intel or Apple Silicon), Windows x64, or Linux x64 |
| 💾 **USB stick** | A normal Rekordbox export, FAT32 or exFAT |
| 🔑 **A key file** | Not distributed here — [see below](#the-key-file) |
| 📀 **Disk space** | ~1.5 GB, only if you want stems |

About **20 minutes** to set everything up. After that, stems take from a few
seconds to a few minutes per track. A GPU (NVIDIA, AMD, or Apple Silicon) makes
that dramatically faster.

---

## Before you start

**Read this bit.** It is short.

- **Nothing is flashed.** The toolkit does not write to the player's internal
  storage. It uses the maintenance mechanism Pioneer built into the RX3 to run
  software from a USB stick, and everything lives in memory until you power off.
- **There is a safety net.** If the modified player does not survive the first
  few seconds, the original one is put back automatically.
- **It can still crash.** Modified software on a live machine is modified
  software on a live machine. That matters rather a lot when the thing is
  plugged into a 20 kW PA. **Test at home. Test the actual stick, the actual
  tracks, several times. Keep a clean Rekordbox stick in the bag.**
- **Warranty.** Running unofficial software on consumer hardware may affect what
  the manufacturer is willing to do for you. Nothing here is permanent, but that
  is not a promise about anyone's warranty decisions.
- **Liability.** This is an educational and experimental project. If it crashes
  during your $50,000 set, that would be unfortunate. I do wish you the $50,000
  set.
- **Music.** Separation happens on your computer, on your files. What you are
  allowed to copy, process and perform depends on your licences and your
  jurisdiction, not on this tool.
- **Affiliation.** Not affiliated with, endorsed by, or connected to Pioneer DJ
  or AlphaTheta. Product names identify compatible gear and nothing more.

---

## Quick start

Do these in order. For your first go, I'd suggest you use a spare USB stick and two or three
tracks.

### 1. Check your firmware

Remove every USB stick, power the RX3 on, hold **MENU (UTILITY)** for a second,
scroll to the bottom.

```text
VERSION No. 1.19
```

Anything else and you should stop here — the toolkit is built against this exact
version and simply will not apply itself to another one. AlphaTheta documents
updating [in its support article](https://support.alphatheta.com/en-US/articles/5097637194137?product=4416587179673).

Power the RX3 back off.

### 2. Download the app

Grab the build for your computer from the [**Releases page**](../../releases) and
unpack it wherever you keep applications.

<details>
<summary><b>macOS says the app is damaged / Windows shows a warning</b></summary>

The app is not code-signed yet, hich means your computer suspects it could be malicious.

**macOS** — clear the quarantine flag your browser put on the download. Open the Terminal application, (in the Utilities folder), type `xattr rc` then drag the app into the window to fill in the path:

```sh
xattr -rc "/Applications/XDJ-RX3 Toolkit.app"
```

`No such file or directory` means the path is wrong: it must point at the
unpacked `.app` itself, not the `.zip` and not the folder around it.

**Windows** — SmartScreen will complain. Choose **More info → Run anyway**.

**Linux** — unpack and run; you may need to mark the file executable first.

</details>

### 3. Prepare your stems *(optional)*

Skip this if you only want the longer beat jumps.

1. In Rekordbox, make a playlist with the tracks you want stems for. Two or
   three, for a first run.
2. Export your Rekordbox collection **as XML** (Preferences → *Advanced* or
   *View*, depending on your version). This is not the same as exporting to a
   stick. The app reads it to find where your audio files are.
3. Open the app, go to the **Stems preparation** tab, and hit **Set up… → Install**.
   Separation needs a lot of software that is too big to ship in the download,
   so it gets installed once into its own private folder. You need an internet
   connection, ~1.5 GB free, and Python 3.10–3.13
   ([python.org](https://www.python.org/downloads/) if you have none — take 3.13).
   If it stops halfway, press **Install** again; it picks up where it left off.
4. Select your XML, your playlist, and your Rekordbox USB stick.
5. Pick a quality: **Fast** for big libraries, **High quality** for exposed
   acapellas. 
6. Start it. The app estimates how long the run will take, then corrects itself
   after the first track and remembers your machine's speed for next time.

Each track produces a `.rx3stem` file in a `RX3_STEMS` folder on the output folder you chose. If you didn't chose your Rekordbox USB stick as an output path, it's time to move that folder at the root of it

```text
Your USB stick
├── Contents    ← this holds your exported Rekordbox audio files
├── PIONEER
└── RX3_STEMS   ← the new one
```

> [!NOTE]
> The stem playlist itself does **not** need to go on the stick, but it totally can. The player
> matches stems automatically.

Keep the laptop plugged in and awake. If one track fails the queue carries on —
read the log at the end. If *every* track fails, the install is incomplete: run
**Install** again. See [Troubleshooting](docs/troubleshooting.md#every-track-fails).

### 4. The key file

The file we will make needs to be encrypted for the player to load it, so the app needs the matching key to
build it.

> [!CAUTION]
> **This project does not distribute that key, and never will.**

It is not a secret, though. Pioneer publishes the GPL/LGPL source archives for
the XDJ-RX3 (`pioneerdj_xdj_rx3.tar.bz2.00` and `.01`) on its
[open source distribution page](https://www.pioneerdj.com/en/support/open-source-code-distribution/gnu-open-source-license/),
and building the filesystem from them exposes the key. Getting it — and deciding
whether you may use it where you live — is the one step nobody can do for you.

Step-by-step: [**Extracting the RX3 initramfs**](docs/extract-initramfs.md).

### 5. Build the file for your stick

In the **Modules installation** tab: pick firmware `1.19`, choose the modules you want (some are automatically checked or unchecked depending on which mods you chose), pick your key file, pick the
**root of your Rekordbox stick** as the destination, then **Mod your RX3 !**.

Eject the stick
properly. It should now look like:

```text
USB stick/
├── autoexec.bin      ← the mod, this is the whole thing
├── RX3_STEMS/
├── Contents/
└── PIONEER/
```

### 6. Put it on the player

**Order matters.**

1. Power the RX3 on with the stick **out**.
2. Wait until the interface is fully loaded and responsive.
3. *Now* insert the stick.

The screen freezes, goes away for a few seconds and comes back. While that happens, do
not pull the stick, do not cut power, and do not mash the controls because
patience has apparently become obsolete.

<details>
<summary><b>Did it work?</b></summary>

The stick now contains `RX3_RUNTIME/session.txt`. Its last line should read:

```text
=== complete ===
```

**Interface did not come back?** Pull the stick and power cycle — unplug the
mains lead if you have to. The RX3 boots stock.

**Log says `STOP:` or `FAILED:`?** Delete `autoexec.bin` from the stick, then see
[Troubleshooting](docs/troubleshooting.md#the-session-log-says-stop-or-failed).

</details>

---

## Playing with it

Load one of your prepared tracks and open **Slip Loop**.

Pads 7 and 8 blink while the stem loads, then settle on red and green. They are
two independent switches — press pad 8 and the vocal drops out of the mix.

Open **Beat Jump** on the same track: pads 7 and 8 now read `32`.

Load a track with no stem and Slip Loop behaves exactly like stock. That is the
intended fallback, not a failure — if a track you *did* prepare has no stem
controls, then either you probably did something wron, or I did. See
[Troubleshooting](docs/troubleshooting.md#a-prepared-track-has-no-stem-controls) and only after open an issue..

---

## Back to stock

1. Stop playback.
2. Power off.
3. Pull the stick.
4. Power on.

Done. Nothing to uninstall, nothing to restore, nothing to reflash.

Leaving the stick in re-applies the mod at the next power-on. To turn it back
into an ordinary Rekordbox stick for good, delete `autoexec.bin` from it — your
music and your stems can stay.

---

## FAQ

<details>
<summary><b>Does this flash custom firmware?</b></summary><br>

No. Everything runs in memory and is gone the moment you power off without the
stick.
</details>

<details>
<summary><b>Can it brick my RX3?</b></summary><br>

The project does not write to the player's permanent storage, which removes the
usual reason custom firmware bricks things. That is not a mathematical proof that
nothing can ever go wrong. Unofficial software, own risk.
</details>

<details>
<summary><b>Can it crash?</b></summary><br>

Yes. Test it at home before you rely on it. Using a show as your first test would
be an admirably efficient way of turning software testing into performance art.
</details>

<details>
<summary><b>Does every track need stems?</b></summary><br>

No. Prepared and unprepared tracks live happily on the same stick.
</details>

<details>
<summary><b>Are my original files modified?</b></summary><br>

No. The stem is a separate sidecar file sitting next to the track.
</details>

<details>
<summary><b>Why only firmware 1.19?</b></summary><br>

The mod patches the player software at very specific places, and a firmware
update moves that code around. So the toolkit checks it is looking at the player
it expects, and refuses if it is not. Support
for other versions has to be added and tested deliberately.
</details>

<details>
<summary><b>Why are stems made on the computer and not on the player?</b></summary><br>

Because separation models are big and expensive to run. Doing the heavy work on
your laptop means better models, GPU acceleration, no waiting on the RX3, and
untouched originals. Improving the model later does not mean rewriting anything
on the player. The computer does the absurdly expensive maths; the DJ player gets
to carry on being a DJ player.
</details>

<details>
<summary><b>Can I update my firmware while this is installed?</b></summary><br>

There is nothing installed. Pull the stick and the unit is stock. But after a
firmware change, do not assume the toolkit still works — only use versions listed
as supported. **If you do update, please to a clean boot cycle, without the mod USB, just in case**.  
</details>

---

## Roadmap

What is being worked on next. No dates, no promises but this is the direction.

| | What it would give you | Status |
| --- | --- | :--: |
| **FX equalization** | The FX equalization of a DJM-900NXS2 to make your echoes and delays not go bang bang  | 💡 Planned |
| **Key sync between decks** | Nudge a deck by one or two semitones so two compatible tracks plays hamrmonically together | 💡 Planned |
| **Proper STEMS / KEY on the display** | The stem and key-shift on the screen are properly integrated and perfectly working | 🚧 In progress |
| **Polished interface** | Real icons, text and artwork for everything the mod adds, matching the stock look | 🚧 In progress |
| **Full system emulator** | From the U-Boot to the beat, to develop and test mods from the sofa (and open to anyone who does not own an RX3) | 🚧 In progress |
| **CPU and memory monitoring** | Headroom monitoring so heavier features stay safe to use for a whole set | 💡 Planned |

Want one of these sooner ? Or something else ? Say so in an issue, or build it yourself (see
[Contributing](#contributing)).

---

## Documentation

| | |
| --- | --- |
| [Extracting the initramfs](docs/extract-initramfs.md) | Getting the key out of Pioneer's published sources |
| [The RX3 mod](docs/mod-rx3.md) | Architecture, modules, applying and removing, session logs |
| [Vocal stems](docs/stem-studio.md) | Models, presets, accelerators, tuning |
| [Troubleshooting](docs/troubleshooting.md) | Symptoms, errors, fixes |
| [Reference](docs/reference.md) | File formats, commands, addresses, hardware findings |
| [Contributing](CONTRIBUTING.md) | Build from source, run the tests, write a module |
| [Changelog](CHANGELOG.md) | What changed |

---

## Contributing

Pull requests welcome — new modules, support for future firmware,
reverse-engineering notes, UI work, faster separation, testing on other systems,
or just better docs. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

**Reporting a bug?** Include your firmware version, your OS, the toolkit version,
the contents of `RX3_RUNTIME/session.txt`, and the steps to reproduce. For stem
problems, add the model, the quality preset, your CPU/GPU, and whether it affects
one track or all of them.

Please do **not** attach encryption keys, manufacturer firmware or binaries, or
copyrighted music.

---

## License

[Mozilla Public License 2.0](LICENSE). Changes to MPL-covered files stay under
the MPL; separate files may be combined into a larger work under other terms, as
the licence permits. Third-party components are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Keys, firmware, manufacturer binaries and copyrighted music are not in this
repository and are never release assets.

Pioneer DJ, AlphaTheta, Rekordbox and XDJ-RX3 are trademarks of their respective
owners, used here descriptively only.

---

## Acknowledgements

The open-source software running inside the RX3, the GPL/LGPL sources Pioneer
published, the reverse-engineering community, the people who build the
audio-separation models — and everyone who has ever looked at a perfectly
functional DJ player and asked:

> *"Yes, but what else can it do?"*
