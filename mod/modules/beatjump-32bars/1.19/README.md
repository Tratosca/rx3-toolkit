# ⏭️ Beat Jump ±32

The two outer Beat Jump pads become **−32** and **+32** beats instead of −8 and
+8. Eight bars in one press.

Open **Beat Jump** on any track and pads 7 and 8 now read `32`. The pad lights
and the availability rules follow along, so a jump that would run off the end of
the track still refuses like it always did.

On by default. It needs *No more wait between beatjumps*, which the app ticks for
you — thirty-two beats is a long way to ask the player to fetch in a hurry.

## One cosmetic compromise

The player ships no directional artwork for `32`, so the pads borrow the
non-directional `32` image from the Beat Loop page. It reads correctly, it just
is not a bespoke arrow.

The jog display is untouched: it is driven by a separate controller with its own
fixed set of glyphs, and there is no `32` in it.

---

What actually changes in the binary, and the floating-point trick the ±32 value
needs: [Reference → A worked example](../../../../REFERENCES.md#a-worked-example-longer-beat-jumps).
