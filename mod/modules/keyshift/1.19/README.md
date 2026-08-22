<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🎹 Per-deck key shift

Tune each deck up or down by up to twelve semitones, from the **KEY** tab on the
screen. The two decks are independent — shift one, the other stays where it is.

| Control | What it does |
| --- | --- |
| **KEY −** / **KEY +** | One semitone down or up |
| **The number in the middle** | Tap it and that deck goes back to `0` |

On by default. Nothing is written to the player: power off, pull the stick, and
it is gone.

## What it actually sounds like

Honestly? It depends which way you go, and this is worth knowing before you drop
it in a set.

Pioneer already shipped a pitch shifter — it is the Beat FX `Pitch` effect. It is
genuinely lovely going **down** and pretty rough going **up**. The one written
for this mod is the exact opposite: solid going up, weaker going down.

So the mod does not pick a favourite. It uses whichever engine wins the direction
you asked for, and switches between them for you. You get the good half of both.

Two things you may still hear when pushing pitch **up** a long way: a little
level ripple on dense material, and the occasional doubled transient. Both are
inherent to how this kind of shifting works, not something left unfinished.
Coming down, neither shows up.

Tuning is accurate to well under a cent, so a shifted deck stays in tune with an
unshifted one.

## If it does not appear

The **KEY** tab is drawn by the performance core, which the app adds for you when
you tick this module. If the tab is missing entirely, the mod did not load at
all — see [Troubleshooting](../../../../docs/troubleshooting.md).

---

How it works, why there are two engines, and the measurements behind every choice
in the shifter: [Reference → Key shift](../../../../REFERENCES.md#7-key-shift).
