<!-- SPDX-License-Identifier: MPL-2.0 -->
# Stem controls

The STEMS tab offers two to four independent controls per deck, according to the files prepared for that track. In Slip Loop mode, the same roles use these pads:

| Pad | Role | Required prepared file |
| --- | --- | --- |
| 5 | Drums | `.rx3drums`, alongside the vocal file |
| 6 | Bass | `.rx3bass`, alongside vocal and drums files |
| 7 | Instrumental, or the remaining instruments in a larger set | `.rx3stem` |
| 8 | Vocal | `.rx3stem` |

Prepared files live in `RX3_STEMS` at the drive root and use the track's basename. A vocal file enables vocal and instrumental controls. Adding a valid drums file enables a third role. Adding a valid bass file enables all four. The remaining instruments are computed from the original mix minus the separated roles.

Available pads blink while files load. A missing or invalid additional file reduces the set to the valid roles. A track without a vocal stem retains its native pad behaviour. Once loaded, the audio data stays in memory.

The source port uses the time-stretch playback stream and fades between selections over 256 valid audio frames. It has not been tested on an RX3. Native tests cover the mix, concurrent selection changes and file rejection. They do not establish audio continuity under device load.

The optional [waveform module](../stemwave/) changes the display for supported selections. It also needs device validation.

Enabled by default. Prepare tracks in the app's Stems preparation tab. See [Troubleshooting](../../../docs/troubleshooting.md#a-prepared-track-has-no-stem-controls) if a prepared track has no controls.

The loader caps total resident stem audio across both decks at 512 MiB and rechecks the available-memory estimate before each allocation, preserving 300 MiB for the player. The sum includes earlier roles in the pending set as well as the other deck. Mismatched optional lengths are rejected; only a contiguous valid prefix beginning with vocals is published. Not yet run on hardware.

The computer warns above 256 MiB per track, half the shared ceiling so two similarly sized tracks have equal room. This is an estimate, not a promise of available RAM, and headers are included in the displayed disk size. Not yet run on hardware.
