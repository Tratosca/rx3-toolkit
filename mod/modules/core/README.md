<!-- SPDX-License-Identifier: MPL-2.0 -->
# ⚙️ Performance core

You never tick this one. It has no controls, does nothing on its own, and the app adds it for you whenever you pick **Key shift** or **Stems**.

It is the part that draws things on the player's screen: the **KEY** and **STEMS** tabs, the buttons inside them, the blinking, and the touch handling that makes tapping them work. Both features need it; neither works without it.

## What that means for you

**There is no badge.** The mod does not announce itself anywhere. The way you know it loaded is that the **KEY** and **STEMS** tabs are there at all, if you see them, it is running.

**The two features are independent.** Key shift works without any stem files, and stems work without key shift. Pick either, both, or neither.

**A failure is contained.** If something is not as expected when stems try to attach, stems switch themselves off and key shift carries on. It is not all-or-nothing.

**It looks like the player's own screen** because it is. Everything drawn goes through the player's own renderer, reusing its fonts and its artwork, rather than being painted over the top. That is deliberate: a panel that looked bolted on would also *behave* bolted on.

Nothing is written to the player. Power off, pull the stick, and every trace of it is gone.

---


---

# For whoever builds this

`rx3_core_hook.c` compiles into one library, `librx3_core.so`, with `make hook`. The variant that stood in for an emulator's front panel and screen left with the emulator; what is compiled is what a deck runs.

`tests/test_hook_symbols.py` reads the `.dynsym` of that library, so a change that pulls in a new import fails the build before it can fail on a deck.

---

How the on-screen additions are rendered, how the image table is extended, and the palette question that is still open: [Reference: the display](../../../../REFERENCES.md#4-the-display).
