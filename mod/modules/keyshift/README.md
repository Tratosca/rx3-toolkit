<!-- SPDX-License-Identifier: MPL-2.0 -->
# Per-deck key shift

The KEY tab shifts each deck by up to twelve semitones. Tap the left or right control to move one semitone. Tap the centre to return to neutral. Loading another track also returns that deck to neutral.

When the player displays a recognised track key, the panel shows the current Camelot key between fixed −1/+1 actions. A shifted key includes its signed semitone offset, for example `8A (-2)` or `12B (+12)`; an unshifted key has no offset suffix. Otherwise it shows the semitone offset. At the range limits, the pitch remains clamped and the unavailable action loses its colour rail.

The source port now attaches to the common time-stretch manager. Transport jumps, direction changes and a return from silence reset the pitch history. Raising pitch uses the runtime shifter; lowering uses the player's Pitch effect.

The previous implementation's listening results are recorded in the [reference](../../../../REFERENCES.md#7-key-shift). The new attachment, track-key recognition and transport resets have not been tested on an RX3. Native tests cover the control state and labels, not sound quality or audio continuity on the player.

Enabled by default. Key Shift requires only the core and exposes manual -1/reset/+1 controls. Key Match is independent. Selecting Key Sync adds both modules and enables the sync action through `RX3_KEY_SYNC`. The Key Shift adapter derives that flag from the orchestrator's loaded module registry and honors the Key Sync and Key Match off switches. All three cards live in Harmonic mixing; the core appears under Advanced.

The central key has a full Camelot face. The −1/+1 actions have neutral faces
and small target-colour rails. KEY SYNC has a neutral face and coloured outline.
The centre follows the transposed key.
The palette is sampled from [Mixed In Key's Camelot wheel](https://mixedinkey.com/camelot-wheel/)
and quantized to RGB565; light mode uses darker versions of the same hues.
Unknown keys and unavailable choices stay neutral. The compatible/unshifted
centre keeps its selection frame independently of the key colour.

KEY SYNC follows the local MASTER reported by the shared BROWSE service. It never offers to transpose the MASTER itself. The service copies the native Traffic Light key set and applies the MASTER's current semitone shift to both its reference key and its accepted keys. No known local MASTER or unavailable reference data means no sync offer. Reading the native set requires a BROWSE update; the implementation does not substitute an assumed Camelot policy before that data is available.

The Toolkit presents compatibility choices first, then KEY SYNC mode and maximum shift. New preferences use `harmonic`, one semitone and no optional Energy Boost rules. Existing stored values, including `identical`, are preserved. The generated module carries `sync-range.txt`, `sync-mode.txt` and the dependent Key Match `rules.txt`. Legacy runtime defaults for missing files remain unchanged.

Same key mode seeks the MASTER's effective key. Compatible mode accepts the observed native set and the selected directed +2/+7/+4 rules. Both seek the smallest additional shift, respect the configured range and the absolute +/-12 semitone bound, and prefer an exact match on equal-distance ties, then a positive shift. An already accepted key remains unchanged. Transposition preserves the track's major/minor mode.

The BROWSE preview uses fictional tracks with an 8A MASTER and an explicit native set. Its candidate is 2A: compatible mode offers +1 to 9A at the default range, while same-key mode needs a six-semitone allowance. Python preview results are checked against the shared C solver across all keys, modes and optional rule combinations.

While both keys are known, the comparison slot stays fixed: a sync action,
MASTER on the reference deck, KEY MATCH (compatible), IDENTIQUE (same key), or PAS DE SYNC when no correction
is available under the configured mode/range. The manual stepper therefore
does not resize when the relationship changes. Unknown keys hide this slot.

## Runtime ownership

Keyshift compiles in `rx3_keyshift_module.c` and uses only the public
`rx3_services` contract. Its state, KEY SYNC settings, pitch implementation and
panel belong to the module. The core delivers track-load, audio-format and
normalized text observations, and owns rendering and touch gestures.
`rx3_keyshift_*.h` files are private implementation details, never core includes.
The bundle remains one `librx3_core.so`; this boundary does not add hot unloading
or binary isolation. See `docs/runtime-framework.md` for lifecycle constraints.
