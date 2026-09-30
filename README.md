<!-- SPDX-License-Identifier: MPL-2.0 -->
<h1 align="center">XDJ-RX3 Toolkit</h1>

<p align="center">
  <b>More ways to play your XDJ-RX3, straight from your rekordbox USB drive.</b><br>
  Prepare stems, add sample pads, mix in key and make Beat Jump go further. No firmware flashing.
</p>

<p align="center">
  <a href="../../releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/Tratosca/rx3-toolkit?style=flat-square&color=ff5c00"></a>
  <a href="LICENSE"><img alt="MPL-2.0 license" src="https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square"></a>
  <img alt="RX3 firmware 1.19 and 1.20" src="https://img.shields.io/badge/XDJ--RX3%20firmware-1.19%20%7C%201.20-black?style=flat-square">
  <img alt="macOS, Windows and Linux" src="https://img.shields.io/badge/macOS%20%7C%20Windows%20%7C%20Linux-lightgrey?style=flat-square">
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

> [!IMPORTANT]
> This README describes the **current development version**. The latest [public release](../../releases), **v0.5.2**, is older and does not contain every feature below. Check the release notes for what your download actually includes. Several newer modules have passed local or emulator checks but still need a complete test on a physical RX3.

---

## What you get

Choose the features you want in the desktop app. It prepares your USB drive; your music stays where rekordbox put it.

| For your set | What the current development version adds |
| --- | --- |
| **Stems** | Prepare vocals and drums on your computer. On the RX3, bring **VOCAL**, **DRUMS** or **INST** in and out, or adjust their levels. INST includes the bass. The screen can follow your stem selection with Blue, RGB or 3Band waveforms. |
| **Harmonic mixing** | Shift either deck by up to 12 semitones. Optional **Key Sync** proposes a shift against the MASTER deck; **Enhanced Key Match** adds selected harmonic suggestions in BROWSE. You choose whether to apply the shift. |
| **Samples** | Put your own sounds on eight pads. Trigger once, hold, loop or latch; up to four voices can play at the same time across both decks. |
| **Beat Jump** | Jump 32 beats with pads 7 and 8. Optional immediate repeat makes consecutive jumps respond without waiting for another quantized step. |
| **Finding tracks** | Add a third BROWSE column for BPM, Camelot key, artist or duration; tap a heading to sort. Optional search without accents finds titles such as “NIÑO” when you type “NINO”. |
| **Display and broadcast** | Add a logo, choose a light screen, hide either deck title, or send Now Playing information to a computer over the rear USB-B connection. These are separate optional modules. |

The usual RX3 controls remain available unless a selected feature needs their screen space. **Key Shift or Stems uses the touchscreen positions normally occupied by ZOOM and GRID.** You can still use the player's normal playback, cueing and mixing controls. The [module guides](mod/modules) explain individual controls and limits.

Stems, Samples, the newer screen controls and Browse changes have **not yet passed full physical RX3 acceptance**. Browse with the extra metadata column has also felt slower than stock on hardware; work on that is under way. Try the exact USB drive and tracks at home before relying on them in a set.

### 🎤 Stems in standalone mode

The computer does the separation before your set. The RX3 plays your original track and the prepared stem package together; it does not separate music live. One `.rx3stem` package per track lives in `RX3_STEMS` on the USB drive. The current preparation flow makes **VOCAL + DRUMS + INST**; INST is the part of the original mix left after the prepared vocal and drums are removed. Older vocal-only packages still load. There is no separate bass pad in the current layout.

On a prepared track, the intended **Slip Loop** pad layout is **5 INST** (red), **6 VOCAL** (green), **7 DRUMS** (blue); **8** keeps its native loop. The **STEMS** touchscreen panel shows the parts available for that track. Tap a part to turn it off or back on; hold and drag to set its level. On a track without a valid stem package, Slip Loop stays native. This mapping is verified in code and the emulator, **not yet accepted on hardware**. [Stem controls and limits](mod/modules/stems/README.md).

### 🎹 Key Shift and Key Sync

Tap **KEY** on the touchscreen to move either deck up or down by semitones. The centre key returns that deck to its original key. **Key Sync** uses the MASTER deck and your chosen harmonic rules to propose a shift; it does not force every track into the same key. **Enhanced Key Match** can mark additional candidates in BROWSE. These functions can be selected separately; Key Sync needs Key Shift and Key Match.

### ⏭️ 32-beat Beat Jump

Choose **Beat Jump** and use pads **7** and **8** for −32 and +32 beats. The separate **Immediate Beat Jump** option changes how repeated jumps respond. It does not change your Hot Cues, loops or Beat FX.

### 🔌 The mod lives on your USB drive

The Toolkit puts `autoexec.bin` on the drive and runs the selected modules in the RX3's memory. It does not flash the player. To return to the stock RX3, **stop playback, power off, remove the mod drive, then power on**. A mod already running in memory remains active until that restart.

---

## What you need

| | |
| --- | --- |
| 🎛️ **Player** | XDJ-RX3 running firmware **1.19 or 1.20**. Other versions are not supported by this build. |
| 💻 **Computer** | macOS, Windows or Linux to prepare the drive. Stem preparation also needs a supported Python installation and room for its separation tools. **Intel Mac stem setup has an open compatibility issue** ([#21](https://github.com/Tratosca/rx3-toolkit/issues/21)). |
| 💾 **USB drive** | A normal rekordbox export on FAT32 or exFAT. Start with a spare drive and a short playlist. |
| 🔑 **First installation** | The app can obtain the required key from the manufacturer's published source package, after you read and accept its terms. |
| 🎤 **For stems** | Internet access for the initial separation-tools installation, about **1.5 GB** of computer storage, and enough free space on the USB drive for the prepared tracks. |

The app runs locally. Stem separation happens on your computer; the time and available acceleration depend on your tracks and machine.

---

## Before you start

**Treat this as an experimental set-up.** Test the USB drive, the features you selected and several prepared tracks on your own RX3 before a performance. Keep a clean rekordbox drive ready to use. The current development version still has open physical acceptance work, especially around screen transitions, Browse speed and startup notices.

- **Your music is not replaced.** Stems and sample banks are additional files. Check the destination shown in the app before writing to the drive.
- **The player can still crash.** The mod runs in memory, but a crash during a set is still a crash during a set. Stop playback and restart without the mod drive if the RX3 behaves unexpectedly.
- **Warranty and music rights still matter.** An unofficial mod may affect warranty support. You are responsible for the rights to copy, process and play your music.
- **This is an independent project.** It is not affiliated with or endorsed by Pioneer DJ or AlphaTheta.

---

## Quick start

The steps below describe the **current development app**. If you downloaded v0.5.2, follow that release's notes for its available screens and features.

### 1. Check your firmware

With the USB drive removed, start the RX3. Hold **MENU (UTILITY)**, then scroll to the version number. This project recognises **1.19** and **1.20**. If you have another version, stop here; do not try to force the mod onto it. [AlphaTheta's firmware instructions](https://support.alphatheta.com/en-US/articles/5097637194137?product=4416587179673).

Power the player off before preparing the drive.

### 2. Open the app and choose your USB drive

Check the [Releases page](../../releases) for the latest published build. The features described here are in the development version until a newer release is published; developers can run that version from this checkout using [Contributing](CONTRIBUTING.md). Do not assume the v0.5.2 download has the screens or features described below.

Export a few tracks or a playlist from rekordbox to your USB drive, wait for export to finish, then close rekordbox. Open XDJ-RX3 Toolkit and choose **the drive itself** in the USB screen, not `PIONEER`, `Contents` or a playlist folder. The drive name remains visible at the bottom of the sidebar. **Tutorial** in the app walks through the same preparation.

The app has **Modules**, **Samples**, **Logo**, **Stems**, **Install the mod** and **Settings**. Settings changes the app's language and appearance; **Light theme** in Modules changes the RX3's screen. The app works in English and French.

### 3. Prepare stems *(optional)*

You can install the mod without preparing stems. To use the stem pads:

1. Open **Stems**. The app can read the selected USB drive's rekordbox export or a rekordbox **Library XML** export. Choose the playlist you want to prepare. The prepared files go to the USB drive selected in the sidebar.
2. If prompted, choose **Install stem preparation tools**. This is a one-time download to your computer. The app shows whether the tools are ready and which processing hardware it will use.
3. Click **Prepare stems**. The current flow prepares vocals and drums, then lets the RX3 reconstruct INST from the original mix. It also prepares Blue, RGB and 3Band waveforms. Keep the computer awake until the playlist finishes.
4. Choose a track in the Stems preview, listen to each part and check its timing. If a track fails, read its result; completed tracks remain available. A reported vocal cancellation mismatch is still being investigated ([#25](https://github.com/Tratosca/rx3-toolkit/issues/25)).

Older compatible stem files can be completed or migrated without separating the audio again when their source and checks pass. The app keeps a backup of replaced v0.5.2 files. The separate **OverCue** export checkbox is experimental and is only for users who deliberately want files for a modded CDJ-3000; RX3 preparation does not require it. [Stem migration details](REFERENCES.md#doc-stems-migration).

Your drive will contain a folder like this:

```text
USB drive/
├── Contents/       rekordbox music
├── PIONEER/        rekordbox library
└── RX3_STEMS/      one .rx3stem package per prepared track
```

### 4. Choose the features and prepare your extras

In **Modules**, turn on the features you want. The app selects required companion modules for you. Choices here are **not yet written** to the USB drive.

| Want to… | Where to do it |
| --- | --- |
| **Play samples** | Open **Samples**. Make a bank, add sounds to the eight pads, set each pad's excerpt, level, colour and playback mode, then try it in **Play pads**. Changes are saved on this computer as you work. Choose the active bank and click **Save to USB drive** to send it to the stick; also select the Samples module. Samples are limited to eight seconds each and four simultaneous voices. |
| **Put your logo on the screen** | Open **Logo**, choose an image and adjust its framing in the preview. Selecting artwork turns on the Logo module; **Install the mod** writes it to the USB drive. |
| **Mix in key** | In **Modules**, choose Key Shift, Enhanced Key Match and/or Key Sync. Set the Key Sync range and harmonic rules there. Key Sync pulls in what it needs. |
| **See more in BROWSE** | Select **Third BROWSE column**, then choose BPM, Camelot key, artist or duration in its settings. Use the physical **LOAD** buttons with this layout. |
| **Change the screen or search** | Select **Light theme**, **Accent-insensitive search** or **Asshole mode** (hide track titles) in **Modules**. The title-eye controls are still awaiting physical RX3 acceptance. |
| **Send track info to a computer** | Select **Now playing**. Its [module guide](mod/modules/now-playing/README.md) explains the rear USB-B connection and the receiver. Integrated hardware validation is pending. |
| **Collect a troubleshooting report** | Select **Troubleshooting report** to write `RX3_RUNTIME/session.txt` when you insert the drive. The detailed report and Telnet access are technical options; leave them off for ordinary sets. |

Beat Jump, Immediate Beat Jump, Key Shift, Key Sync and Stems are selected by default in the development app. Samples, Browse Columns, Search Latin, Now Playing, Logo, Light theme and the other optional modules start off. You can see and change the exact selection in **Modules**.

### 5. Install the mod on the USB drive

Open **Install the mod**. Check the drive name, selected modules, logo and whether your sample bank and stems have actually been saved to that drive. **Installing the mod does not prepare stems or save your sample bank for you.**

On first installation, the app asks you to read and accept the terms before it retrieves the required key from the manufacturer's published source package. This may download roughly 250 MB. The key stays on your computer; the app checks the package against known fingerprints and removes the downloaded archive afterward. You can manage or delete the key under **Installation options**. [Key details](REFERENCES.md#doc-extract-initramfs).

When the recap and destination are right, click **Install the mod** and wait for it to finish. Eject the USB drive properly. It should now have `autoexec.bin` at its root:

```text
USB drive/
├── autoexec.bin    the selected mod
├── RX3_STEMS/      if you prepared stems
├── Contents/
└── PIONEER/
```

Your saved sample bank is also on the drive if you used **Save to USB drive** in Samples. The app can inspect the drive and remove the mod later without deleting your music, stems or sample banks.

### 6. Try it on the RX3

1. Start the RX3 **without** the mod drive inserted. Wait for its screen and controls to respond.
2. Insert the drive. Keep it in place while the player restarts its interface. A normal load may briefly show **MODS LOADING – KEEP USB**. The absence of that message alone does not tell you whether the mod loaded.
3. Load a track, check its normal playback first, then try one selected feature at a time. Check both decks and the return to BEAT FX and BROWSE before depending on the set-up.

If you need to **skip the mod for this insertion**, hold **SHIFT** on either deck while inserting the USB drive and keep it held until the RX3 recognises it. This is a startup bypass, not a way to remove a mod already running. To return to stock after a mod has loaded, power off and restart without the mod drive. The latest startup result is written to `RX3_RUNTIME/startup-probe.txt` on the drive; this bypass has local checks, with physical retest still pending.

<details>
<summary><b>How can I tell whether it loaded?</b></summary>

Try a selected feature with a suitable track. **Session logging** is off by default; turn it on in Modules if you need a report. It writes `RX3_RUNTIME/session.txt` to the drive. `=== complete ===` means installation finished; it does not prove every audio and control path works on hardware. A `STOP:` or `FAILED:` line calls for [Troubleshooting](REFERENCES.md#doc-troubleshooting), followed by a clean restart without the mod drive if the player is misbehaving.

</details>

---

## Playing with it

On a track you prepared, open **STEMS** or the matching **Slip Loop** pad page. Tap **VOCAL** or **DRUMS** to take that part out and tap again to restore it. Use **INST** for the remaining instruments and bass. On the touchscreen, hold and drag a part to set its level. A track without prepared stems keeps its normal Slip Loop controls.

Tap **KEY** for manual Key Shift. The left and right controls move the selected deck one semitone at a time; tap its centre key to reset. If you enabled Key Sync, check the proposed shift against the MASTER deck before applying it. Key Match suggestions in BROWSE are suggestions for a transition, not a guarantee that two melodies will sound good together.

In **Beat Jump**, pads 7 and 8 give you the longer jumps. In **Samples**, play the bank you saved as active on the USB drive; changing screens does not intentionally stop a playing loop or latch. The sample panel and the stored Hot Cues are separate.

With **Third BROWSE column**, tap a column heading to sort, tap it again to reverse, and use the physical **LOAD 1 / LOAD 2** buttons. The extra metadata can currently slow scrolling on a real RX3; the investigation remains open in [#15](https://github.com/Tratosca/rx3-toolkit/issues/15). If something does not respond as described, use the [troubleshooting guide](REFERENCES.md#doc-troubleshooting) and test again without the mod drive.

---

## Back to stock

1. Stop playback.
2. Power off the RX3.
3. Remove the mod drive.
4. Power on.

The RX3 starts with its stock software. To keep using that USB drive for ordinary rekordbox playback, remove the mod through the app's **USB drive** screen, or delete `autoexec.bin` from the drive. Your music, prepared stems and sample banks can stay. **Removing the file while the RX3 is already running does not undo the live mod**; restart the player.

---

## FAQ

<details>
<summary><b>Is this custom firmware?</b></summary>

No. The USB drive starts a mod that runs in memory. The Toolkit does not flash the RX3 or write its internal storage. A clean restart without the mod drive restores the stock player. [How it works](REFERENCES.md#2-how-a-mod-runs-without-flashing-anything).

</details>

<details>
<summary><b>Can it crash or affect a gig?</b></summary>

Yes. It is experimental software on the player you use to perform. Test your actual drive and tracks at home, keep a clean rekordbox drive ready, and use the stock restart procedure if anything feels wrong. A successful desktop test or emulator run is not the same as a full RX3 set.

</details>

<details>
<summary><b>Does every track need stems? Are originals changed?</b></summary>

No. Ordinary and prepared tracks can share the drive. Stem packages are separate from the original audio. A prepared track can still be refused if its package is corrupt, too large for the available memory or mismatched with the source. The app reports known size limits before preparation; the actual free memory on both decks can still differ during a set. [Stem limits](mod/modules/stems/README.md).

</details>

<details>
<summary><b>Where does the separation software go?</b></summary>

It stays on your computer, in a folder named `RX3 Stem Studio` under your account's application data. The **Advanced settings** section in Stems shows the installed preparation tools and processing hardware. The RX3 does not need those models; it only reads the finished stem packages on your USB drive.

</details>

<details>
<summary><b>Why are stems prepared before the set?</b></summary>

Separation models are too large and slow for this job on the RX3. Your computer prepares the files; the player only needs to load and mix them. The original audio remains your normal rekordbox track.

</details>

<details>
<summary><b>What if I update the RX3 firmware?</b></summary>

Check this project's supported versions again before using the mod. The player software can change between firmware versions, so an old `autoexec.bin` is not a safe assumption. After updating, start once without the mod drive before trying a newly prepared one.

</details>

<details>
<summary><b>What information leaves the RX3?</b></summary>

Ordinary stem preparation runs locally on your computer. The optional **Now playing** module sends track and deck status to a computer connected to the rear USB-B port; it is off by default. It does not require rekordbox running on that computer. See its [module guide](mod/modules/now-playing/README.md) for exactly what it sends and its untested hardware limits.

</details>

---

## Roadmap

The list is grouped by what you can play, what needs fixing, then ways to make the Toolkit easier and safer to use. It is not a release schedule. Open issues and PRs may describe work already in the development version; the remaining task is often to test it on the RX3.

### Mods

| Mod | What it would give you | Where it stands |
| --- | --- | --- |
| **Key Sync and effective key** | Finish Key Sync and show the key you actually hear when Master Tempo is off, as requested in [#28](https://github.com/Tratosca/rx3-toolkit/issues/28). | Key Sync is in the development version; the changing key display is planned. |
| **Hide track titles** | An eye for each deck so you can hide its title without affecting the other deck. | Implemented locally; RX3 input and display retest pending. |
| **Quantized stems** | Optionally bring a stem in or out on the next beat or bar. The current immediate response stays the default. | Planned; needs a reliable beat position in the audio path. |
| **LOW / MID / HIGH CUT for Beat FX** | Choose which frequencies enter an effect while leaving the dry track alone. Planned controls use SPACE, DUB ECHO and SWEEP, with an active light and adjustable cutoff. | Planned; audio and controls need testing. |
| **Connected RX3 ideas** | Explore Link Export over USB or Wi-Fi, live audio streaming and remote control from [#32](https://github.com/Tratosca/rx3-toolkit/issues/32) and [#37](https://github.com/Tratosca/rx3-toolkit/issues/37). | Contributor proposals, not supported features. SSH and screen streaming are research tools. |
| **Waveforms for tracks without rekordbox analysis** | Investigate a moving waveform for an unanalysed track, separate from the Browse request in [#15](https://github.com/Tratosca/rx3-toolkit/issues/15). | Research only. |

### Fixes

| Fix | What it would change | Where it stands |
| --- | --- | --- |
| **Ready-to-release builds** | Finish the checks needed to publish the next app and RX3 mod. [#39](https://github.com/Tratosca/rx3-toolkit/pull/39) proposes fixes to those checks. | PR open; the full release gate needs a fresh run. |
| **Fast, stable BROWSE and screen changes** | Remove the pause when Browse reloads track details; retest KEY/STEMS/BEAT FX transitions, title eyes and startup messages on a physical RX3. The third column and sorting from [#15](https://github.com/Tratosca/rx3-toolkit/issues/15) already exist. | Hardware tests found slow scrolling and screen faults; physical retest pending. |
| **Stem timing** | Resolve the source/stem alignment complaint in [#25](https://github.com/Tratosca/rx3-toolkit/issues/25), so removing vocals does not leave a doubled voice on affected tracks. | Reproduction and codec-specific cause still to confirm. |
| **Intel Mac stem setup** | Make tool installation and model selection work on affected Intel Macs ([#21](https://github.com/Tratosca/rx3-toolkit/issues/21)). | Open compatibility issue. |
| **Safe module loading** | Review the shared runtime changes in [#34](https://github.com/Tratosca/rx3-toolkit/pull/34) and [#35](https://github.com/Tratosca/rx3-toolkit/pull/35) before adding more modules. | PRs open upstream; final integration and device tests pending. |
| **Prove the features on the RX3** | Finish physical checks for STEMS/drums ([#13](https://github.com/Tratosca/rx3-toolkit/issues/13), [#17](https://github.com/Tratosca/rx3-toolkit/issues/17)), Samples ([#14](https://github.com/Tratosca/rx3-toolkit/issues/14)), Search Latin ([#29](https://github.com/Tratosca/rx3-toolkit/issues/29), [#30](https://github.com/Tratosca/rx3-toolkit/pull/30)) and Now Playing ([#20](https://github.com/Tratosca/rx3-toolkit/pull/20), [#32](https://github.com/Tratosca/rx3-toolkit/issues/32)). | Implemented in source; integrated hardware acceptance incomplete. |

### Improvements

| Improvement | What it would give you | Where it stands |
| --- | --- | --- |
| **More headroom in a long set** | Show CPU and memory use before a demanding combination of features affects playback. | Planned. |
| **Stem files that take less room** | Investigate the storage concern in [#18](https://github.com/Tratosca/rx3-toolkit/issues/18) while keeping stems in time with the track. | Research; no smaller format chosen. |
| **Easier app updates** | Improve the desktop update and signing experience raised in [#4](https://github.com/Tratosca/rx3-toolkit/issues/4). | Some setup improvements are already in the app; updating remains open. |
| **A base for future modules** | Review repeatable builds and rollback proposed in [#36](https://github.com/Tratosca/rx3-toolkit/pull/36) for selected [#37](https://github.com/Tratosca/rx3-toolkit/issues/37) ideas. | Infrastructure PR open; downstream features are on a contributor fork. |
| **A place to talk about the project** | Consider GitHub Discussions as requested in [#38](https://github.com/Tratosca/rx3-toolkit/issues/38). | Open suggestion. |

Have a request or a repeatable problem? Open an [issue](../../issues) with the RX3 firmware version, the app version and what happened.

---

## Documentation

| | |
| --- | --- |
| [Troubleshooting](REFERENCES.md#doc-troubleshooting) | What to check when a track, USB drive or module behaves unexpectedly |
| [Module guides](mod/modules) | Pad controls, settings and limits for each feature |
| [How the mod works](REFERENCES.md) | The player, USB start-up, audio and display details |
| [Contributing](CONTRIBUTING.md) | Building, testing and adding modules |
| [Legal position](LEGAL.md) | Software, sources, keys and distribution |
| [Changelog](CHANGELOG.md) | Changes in the development version |

---

## Contributing

Want to test a module, improve the DJ-facing wording or add a feature? Start with [Contributing](CONTRIBUTING.md). A repeatable report is especially useful: give the RX3 firmware, the exact USB drive set-up, the app version, the selected modules, the track type and the buttons you pressed. If you enabled **Troubleshooting report**, include `RX3_RUNTIME/session.txt`.

For development work, `make new-module ID=your-module` creates a module starting point; `make hook test preflight` runs the local build and checks. Those checks do not replace a real RX3 test. Do **not** attach your encryption key, manufacturer firmware, copyrighted music or private library data to an issue.

---

## License

[Mozilla Public License 2.0](LICENSE). Third-party software and assets are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Keys, manufacturer binaries and copyrighted music are not included in this repository or its releases.

Pioneer DJ, AlphaTheta, rekordbox and XDJ-RX3 are trademarks of their respective owners, used here to identify compatible products.

---

## Acknowledgements

Thanks to the people who documented the RX3, shared tests and module ideas, built audio separation tools, and tried the early versions on their own decks. Their reports are what turn a promising demo into a mod a DJ can actually use.
