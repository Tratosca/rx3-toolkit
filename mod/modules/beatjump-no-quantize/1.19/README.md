<!-- SPDX-License-Identifier: MPL-2.0 -->
# ⏩ Immediate Beat Jump

Repeated Beat Jumps fire **straight away** instead of waiting for the grid to
come round.

Stock behaviour lines each jump up to the next half-bar, which is fine for one
jump and infuriating for four in a row: you press, and the player politely waits.
With this on, press four times quickly and you have moved four times.

On by default. It needs *No more wait between beatjumps*, which the app ticks for
you.

## What it does not touch

Only the Beat Jump path changes. Everything else quantizes exactly as it did:

- Global **Quantize** stays on if you had it on
- **Hot Cues** still snap
- **Loops** still snap
- **Beat FX** are untouched

So if you liked quantized cues, you keep them. This is not a "turn off quantize"
switch.

---

What the change actually is, in one line of machine code:
[Reference → A worked example](../../../../REFERENCES.md#a-worked-example-longer-beat-jumps).
