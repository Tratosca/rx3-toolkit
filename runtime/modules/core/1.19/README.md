# Performance core, firmware 1.19

The shared object the performance features load into. Volatile: preloaded with
`LD_PRELOAD`, nothing is written to NAND.

This module owns no feature of its own. It provides:

- the hook broker, which is the sole owner of executable writes, checks each
  function's prologue and isolates failures by optional hook group;
- the on-screen additions, rendered by rbp's own `NS_PALRender` from a cloned
  `NS_GlyphText`, so fonts, clipping and palette are the firmware's;
- the `KEY` / `STEMS` tab strip, which replaces the stock `ZOOM / GRID` images
  in their native render pass and reuses the captured `STATUS / BEAT FX`
  artwork rather than reconstructing a frame;
- touch, by routing a feature panel descriptor through repurposed native
  `BeatFxAndXPad` areas and restoring their stock geometry on the way out;
- the `PATCHED` badge, and the one-second blink shared by the pads and the
  on-screen toggles.

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
