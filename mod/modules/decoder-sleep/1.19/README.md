<!-- SPDX-License-Identifier: MPL-2.0 -->
# ⚡ No more wait between beatjumps

The helper module. Nothing to see, nothing to press — it just makes the two Beat
Jump modules feel right.

The player checks for freshly decoded audio on a timer. Stock, that timer ticks
every millisecond, which is fine when you are playing forwards and noticeable
when you have just thrown the track thirty-two beats. This makes it tick ten
times more often, so audio turns up sooner after a big jump or a seek.

On by default, and the app ticks it automatically whenever you pick either Beat
Jump module. You can also select it on its own if that is all you want.

## Being honest about it

This is a real improvement in one specific place and not a magic latency fix.
It does **not**:

- make the buffer bigger;
- change jump distances, Quantize, or the grid;
- preload the track;
- promise you a fixed number of milliseconds back.

Whether you notice it depends on whether that timer was the thing holding you up.
Waking up more often also costs the player a little CPU. It is a trade, chosen
deliberately, not a free win.

Nothing is patched here at all — it is a setting sent to the running player, and
a power cycle puts it back. If it fails, it says so and the player carries on
with the stock timing.

---

How the setting is sent, and why it is not a binary patch:
[Reference → Faster decoder polling](../../../../REFERENCES.md#8-faster-decoder-polling).
