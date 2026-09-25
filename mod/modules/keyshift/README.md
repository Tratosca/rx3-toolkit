<!-- SPDX-License-Identifier: MPL-2.0 -->
# Per-deck key shift

The KEY tab shifts each deck by up to twelve semitones. Tap the left or right control to move one semitone. Tap the centre to return to neutral. Loading another track also returns that deck to neutral.

When the player displays a recognised track key, the panel shows the current Camelot key and the two neighbouring semitone choices. An asterisk marks a shifted key. Otherwise it shows the semitone offset. At the range limits, the unavailable choice reads `--`.

The source port now attaches to the common time-stretch manager. Transport jumps, direction changes and a return from silence reset the pitch history. Raising pitch uses the runtime shifter; lowering uses the player's Pitch effect.

The previous implementation's listening results are recorded in the [reference](../../../../REFERENCES.md#7-key-shift). The new attachment, track-key recognition and transport resets have not been tested on an RX3. Native tests cover the control state and labels, not sound quality or audio continuity on the player.

Enabled by default. The performance core is added as a dependency. If the KEY tab is absent, see [Troubleshooting](../../../../docs/troubleshooting.md).
