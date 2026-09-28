# Performance tab selection

The on-device tab strip follows the modules that actually registered a panel, not a module list cached by the Toolkit. KEY is Key Shift's panel; Key Sync and Key Match do not add another tab. The eight selection combinations are:

| KEY | STEMS | SAMPLES | Upper strip | Lower left | Lower right |
|---|---|---|---|---|---|
| off | off | off | native ZOOM / GRID | native STATUS | native BEAT FX |
| off | off | on | native ZOOM / GRID | SAMPLES | native BEAT FX |
| on | off | off | KEY full width | native STATUS | native BEAT FX |
| on | off | on | KEY full width | SAMPLES | native BEAT FX |
| off | on | off | STEMS full width | native STATUS | native BEAT FX |
| off | on | on | STEMS full width | SAMPLES | native BEAT FX |
| on | on | off | KEY / STEMS | native STATUS | native BEAT FX |
| on | on | on | KEY / STEMS | SAMPLES | native BEAT FX |

With both modules present, the upper cells keep their original 90 x 50 pixel footprint. A single module extends its native-derived artwork across the 180 x 50 pixel strip, and the whole strip handles touch. The custom strip sits below QUANTIZE and shares a two-pixel inner border with STATUS / BEAT FX. Its touch area ends above the lower row. If either KEY or STEMS is active, both native ZOOM and GRID touch controls are replaced; the Toolkit says so beside the module choices. If neither is active, the core passes the native strip through unchanged.

Touching an active KEY, STEMS or SAMPLES tab again returns to the native status/pad display. With SAMPLES absent, STATUS is shown and explicitly handles touch even while a custom panel is open. BEAT FX remains separate and available. Physical pad-mode buttons still return to the native display. A panel registration that disappears while another panel is visible is recovered on the next tab touch; normal module removal stops the whole hook.

The image-choice and touch functions are covered by `tests/test_runtime_transitions.py`. The machine emulator has painted and responded in the isolated KEY, isolated STEMS, isolated SAMPLES and combined cases. The compact combined-tab capture uses core SHA-256 `19cb0bf4c68cdb74eb4ef7ff6b665fb13852b47feda3611e0fc6406bdeff57d7`. Physical RX3 behavior requires later hardware validation.
