<!-- SPDX-License-Identifier: MPL-2.0 -->
# BEAT FX frequency bands

The FX FREQUENCY buttons of Pioneer's DJM-900NXS2, DJM-A9 and DJM-V10, on the
three top COLOR FX buttons:

| Button | Band |
| --- | --- |
| SPACE | LOW |
| DUB ECHO | MID |
| SWEEP | HIGH |

- Lit: the band goes through BEAT FX. Dark: the band stays dry, around the effect.
- Each button toggles on its own; any combination works. All three are lit at start-up.
- All three lit is the stock BEAT FX, sample for sample.
- Roll and Slip Roll record only the lit bands, so they replay only those.
- SPACE, DUB ECHO and SWEEP no longer select their own COLOR FX. NOISE, CRUSH
  and FILTER keep theirs.

The bands are the player's own isolator crossover, read from rbp 1.19: about
284 Hz and 4649 Hz, fourth order (24 dB/octave), the three bands summing flat
within 0.04 dB. Pioneer does not publish the split its DJM mixers use for FX
FREQUENCY; this is Pioneer's split on this platform, not a measurement of a DJM.
Band changes ramp over 3.3 ms, the isolator's own smoothing time.

While a band is dark, the dry part passes through the crossover even when
BEAT FX is off: flat in level, with the crossover's phase.

The module is optional and disabled by default. Its runtime switch is
`RX3_BEATFX_EQ=1`; the shared core owns the key, LED and BEAT FX hooks.

Checked in the emulator (firmware 1.19, ECHO on MASTER, LEVEL/DEPTH at
maximum, a 60 Hz + 1 kHz + 10 kHz test track): each dark band comes back to its
dry level while the other two keep the echo, and all three lit match the stock
effect. **Real RX3 validation is pending**: effect tails, Roll, other effects,
CPU load. See
[the native contract](../../../REFERENCES.md#doc-beatfx-eq).
