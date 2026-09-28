<!-- SPDX-License-Identifier: MPL-2.0 -->
# Stem controls

The STEMS tab offers INST and VOCAL for a track prepared with the vocal, and INST, VOCAL and DRUMS for a track prepared with the vocal and drums. INST is never a file: it is rebuilt from the original mix minus the prepared stems, so it carries the bass. In Slip Loop mode, pad 5 is INST (red), pad 6 VOCAL (green) and pad 7 DRUMS (blue); pad 8 keeps its native loop.

The Toolkit exports one self-describing `.rx3stem` package per track, with
all prepared PCM roles, an internal manifest and optional embedded waveforms.
See [the package format](../../../docs/stem-package.md).

Preparation offers two modes: VOCAL + INST (one stored PCM role, three
waveform combinations) and VOCAL + DRUMS + INST (two stored PCM roles,
seven combinations). The mode is chosen before quality. For three-part
preparation, all presets select a vocal-and-drums Demucs model, including on
CPU: Quality prefers htdemucs_ft with four shifts, Normal uses htdemucs with
two shifts, and Very fast uses htdemucs with one shift. Custom models are
validated for the selected roles. Import accepts both modes independently
of the automatic model's capabilities.

A private audio-separator worker keeps one model loaded for the preparation
job. Cache hits do not start it. Failures discard the worker; cancellation
and job completion close it. Installed model asset hashes are part of the
PCM cache identity; waveform versions are independent, so an update can
rebuild waveforms from verified PCM without separating again.

Verified manual imports from the same source, with the same roles, keep their
PCM, import hashes, checks and processing identity when reused. An older
waveform can be rebuilt as RX3WAV3 from that PCM without running separation.
A failed waveform calculation leaves the existing package untouched.


Touch controls follow the same order and omit unavailable roles. The package is loaded and validated as a unit; corrupt packages are rejected rather than partly activated.

The Toolkit no longer separates bass. Legacy `.rx3stem`, `.rx3drums` and `.rx3bass` files, and packages holding bass, remain readable: their bass plays, and its waveform is drawn, at the INST level. It has no pad or control of its own.
Legacy optional files can reduce the available set when invalid.

The source port uses the time-stretch playback stream and fades between selections over 256 valid audio frames. It has not been tested on an RX3. Native tests cover the mix, concurrent selection changes and file rejection. They do not establish audio continuity under device load.

Waveform adaptation is included with Stems. The Toolkit can skip waveform calculation, or calculate/recalculate it later per track without repeating separation. Audio-only packages use container version 3 and require the updated loader; they keep the original player display, including the overview. Available prepared waveforms follow the active stems. This still needs device validation.

Enabled by default. Prepare tracks in the app's Stems preparation tab. See [Troubleshooting](../../../docs/troubleshooting.md#a-prepared-track-has-no-stem-controls) if a prepared track has no controls.

The limits live in `rx3_stems_limits.h`; the computer reads the same values in `app/stems/limits.py`, and a test compiles the header to compare them. A track is loaded from 0.1 s to 31 min 42 s. The loader keeps a whole package resident (PCM, waveforms, index and manifest) and caps what both decks hold together at 512 MiB, so a package with drums is refused past about 24 min 54 s. It rechecks the available-memory estimate before each allocation, preserving 300 MiB for the player. The sum includes earlier roles in the pending set as well as the other deck. Mismatched optional lengths are rejected; only a contiguous valid prefix beginning with vocals is published for legacy files. Packages are all-or-nothing. Not yet run on hardware.

The computer refuses a track the loader would certainly reject, before separating or importing it, and says what to do. Above 256 MiB, half the shared ceiling, it warns instead: the deck refuses such a package only while the other deck holds more than the rest of the 512 MiB. The free memory at load time is not known on the computer, and no promise is made about it. Not yet run on hardware.

With RX3WAV3 and the conservative manifest allowance, duration thresholds are:

| Prepared roles | Above 256 MiB (shared-memory risk) | Maximum duration |
| --- | --- | --- |
| VOCAL | about 24 min 58 s | 31 min 42 s |
| VOCAL + DRUMS | about 12 min 27 s | 24 min 54 s |

The application calculates these thresholds from package sizes, not from
these rounded durations. RX3WAV3 keeps the six-byte waveform column stride.

Each available stem has one combined button/volume control. Tap to mute (0%) or enable (100%). Hold for 350 ms and move horizontally to adjust the volume relative to its initial value, without a jump on contact or a toggle on release. Intermediate levels keep their slider visible; at 100% it hides two seconds after release, and at 0% the button is off. Drums are blue, vocals green, instrumental red, with bass included in instrumental. A new track resets the levels. Gain changes use the existing 256-frame transition. This control has been exercised in the ARM emulator, not on hardware.
