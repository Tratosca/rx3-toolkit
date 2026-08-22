<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🎤 Vocal and instrumental controls

Drop the vocal, or keep only the vocal, on tracks you prepared beforehand.

Open **Slip Loop** on a prepared track. Pads 7 and 8 stop being loop pads and
become two independent switches:

| Pad | Colour | What it does |
| :--: | :--: | --- |
| **7** | 🔴 Red | Instrumental on / off |
| **8** | 🟢 Green | Vocal on / off |

The **STEMS** tab on screen gives you the same two switches per deck, if you
would rather tap the display.

On by default. Nothing is written to the player.

## What you need on the stick

One `.rx3stem` file per track, in a `RX3_STEMS` folder at the root:

```text
Your USB stick
├── Contents
├── PIONEER
└── RX3_STEMS
    └── Artist - Title.rx3stem
```

Make those in the app's **Stems preparation** tab — see the
[Quick start](../../../../README.md#3-prepare-your-stems-optional). The stem file
is matched to the track **by filename**, so it has to be named after the track it
came from. The app does that for you.

## What to expect

Both pads blink while the stem loads — one second on, one second off — then
settle on their colours. That is the file being read; on a big track it takes a
moment.

**A track with no stem file behaves exactly like stock.** Slip Loop stays Slip
Loop, the pads stay dotted. That is the intended fallback, not a failure. If a
track you *did* prepare has no controls, the filename probably does not match:
see [Troubleshooting](../../../../docs/troubleshooting.md#a-prepared-track-has-no-stem-controls).

Once a stem has finished loading it lives in memory, so pulling the drive after
that will not interrupt playback. Do not make a habit of it anyway.

The waveform display does not change. It is drawn from something else entirely
and does not know the vocal went away.

---

How the audio is actually swapped, and why the instrumental is the mix minus the
vocal: [Reference → Stems](../../../../REFERENCES.md#6-stems).
