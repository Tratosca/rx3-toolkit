<!-- SPDX-License-Identifier: MPL-2.0 -->
# The waveform follows your stems

The render port is implemented but has not been validated on a deck. Waveform adaptation follows the Stems setting.

The waveform reads the Stems module's selected and available roles. It waits for the player's redraw cycle before changing the columns. It handles flat, 3 Band/RGB and Blue display paths. Blue keeps the original overview so returning to the full mix can restore it.

With v2 `.rx3stem` packages, detailed columns use embedded waveform amplitudes
through the core's bounded copy service. Individual selections use their role's
analysis; combinations sum/clamp role envelopes. Full mix restores the native
waveform. An incompatible axis leaves the native waveform intact with a log.
Legacy stems retain the display filter, as does the Blue overview.

Validated with a real exported track under QEMU (firmware 1.19), including
play/pause and restoration of the full mix. See the [package specification
and evidence](../../../REFERENCES.md#doc-stem-package). Hardware validation remains pending.

Included automatically in Stems. There is no separate waveform module to select.

The implementation lives in `rx3_stemwave_*.h` and `rx3_stemwave_module.c`.
