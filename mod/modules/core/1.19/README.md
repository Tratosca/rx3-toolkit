# Performance core, firmware 1.19

The shared object the performance features load into. Volatile: preloaded with
`LD_PRELOAD`, nothing is written to NAND.

This module owns no feature of its own. It provides:

- the hook broker, which is the sole owner of executable writes, checks each
  function's prologue and isolates failures by optional hook group;
- the on-screen additions, rendered by rbp's own `NS_PALRender` from a cloned
  `NS_GlyphText`, so fonts, clipping and palette are the firmware's;
- the controls' own face, cloned from a stock label inside the pad subtree
  rather than from the header — see [Two templates](#two-templates);
- the `KEY` / `STEMS` tab strip, which replaces the stock `ZOOM / GRID` images
  in their native render pass and reuses the captured `STATUS / BEAT FX`
  artwork rather than reconstructing a frame;
- touch, by routing a feature panel descriptor through repurposed native
  `BeatFxAndXPad` areas and restoring their stock geometry on the way out,
  including the held state a pressed control paints itself in;
- the one-second blink shared by the pads and the on-screen toggles.

The mod paints no badge of its own. Whether it is loaded is answered by the
`KEY` / `STEMS` tabs being there at all.

Features declare their dependency on this module in `manifest.json`, then
announce themselves through the environment their own `module.sh`
exports — `RX3_KEYSHIFT`, `RX3_STEMS_DIR` — so [key
shift](../../keyshift/1.19/README.md) works without sidecars and
[stems](../../stems/1.19/README.md) works without key shift. With neither
selected the core installs nothing and leaves rbp untouched.

The build adds this internal module transitively. It is not shown as an
independent checkbox because the core has no user-facing behaviour on its own.
An optional hook guard rejected by Stems disables Stems only; Key Shift follows
the same rule. A shared core-service failure still rejects the whole component.

## Two templates

Cloning is what carries the font: nothing in the drawing code sets one, so a
control wears whichever face its model was drawn in. There are two models, and
they are not interchangeable.

- **`pad_text_template`** — a stock label from the pad subtree (`0x17xx` left,
  `0x18xx` right), captured on the way into `NS_PALRender_DrawText` *before* a
  live panel replaces that same draw. The capture takes the first plausible
  label, then upgrades once to one that also carries a fill, which is a real
  button rather than a caption. This is the face the `KEY` and `STEMS` controls
  use.
- **`text_template`** — a header glyph. Twice the size of a pad label, and only
  a fallback, so a panel forced open before the row has ever drawn still shows
  something rather than nothing.

The row itself is painted from the pane backdrop (`0x14e9` left, `0x14ea`
right), which opens each pass over the row — one row per pass, rather than one
per intercepted call. Draws elsewhere in the subtree are the stock pad furniture
the panel stands in for and are dropped; draws *outside* it belong to Pioneer
and reach the renderer untouched. Keying that test on the deck's window instead
of the widget subtree is what used to swallow `AUTO CUE` and `QUANTIZE`.

## Palette, and why it is still inherited

The stock palette is known — frame `0x632c` (`#636563`, two pixels), selected
fill `0x7bef` (`#7b7d7b`) with black glyphs, inactive black with `#7b7d7b`
glyphs, all measured off `assets/key-selected_180x50.png`. What is not known is
the encoding the glyph's colour fields want.

`NS_PALRender_DrawText` decodes `+0x44` three ways, chosen by the pixel format
of the window it is drawing into — which it reads from `DS_GR_GetWindowInfo`,
not from the glyph. Format 2 takes the low byte alone, format 3 the whole word,
format 9 unpacks `0x00BBGGRR` into 5/6/5. Measured against the pad layers:
RGB888 painted magenta lettering on green, RGB565 painted green, and sweeping
all 256 low-byte values moved the green channel alone without ever lifting red
or blue off zero.

So `pioneer_theme` returns zero, which means "leave the cloned model's colour
alone". Settling this means identifying the format `DS_GR_GetWindowInfo` reports
for layers `0x17xx` / `0x18xx` and using that branch's encoding. Until then the
held state the touch layer tracks has nothing to paint itself with, and an
earlier note in the source that every literal colour "looked foreign" is
explained rather than repeated.

## Blink timing

`SubMiconTx::setFullColorLed` lights a blinking LED while
`floor((currentTimeMillis() − started_at) / period)` is even, so the period the
panel is given is the *half*-period: 500 ms is one second on, one second off.
`uif::Led::setState` also keeps an active blink whose period is not longer than
the one offered, so repeating the same period every refresh preserves the phase
instead of restarting it. The on-screen toggles recompute the same parity from
the same origin, which is what keeps them in step with the pads.

## Files

- `module.sh`: installs the shared object and decides when rbp must restart.
- `rx3_feature_api.h`: the rendering and touch contract implemented by feature
  panels.
- `rx3_core_hook.c`: the hook broker, shared services and feature composition
  root.
- `test_regressions.py`: guards for the core and the runtime orchestrator.
