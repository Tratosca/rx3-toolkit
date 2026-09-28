<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🥁 Sample pads

Tap SAMPLES on the touchscreen to open its panel and assign the pads to samples. Tap the active SAMPLES, STEMS, KEY or BEAT FX tab again to return to STATUS. Selecting a different tab opens it directly. Physical pad-mode buttons change pad routing without closing the displayed panel; SLIP LOOP keeps its native pages and prepared stem controls. Your saved hot cues stay unchanged.

At most four samples can play simultaneously, across both decks and all modes. A fifth start is refused without cutting an existing voice. Stopping a voice or letting it finish frees a slot; retriggering an already playing one-shot uses its existing slot. The desktop simulation enforces the same limit, including pending audio preparation.

Each pad plays once, while held, in a loop, or as a latch (press again to stop without looping). Holds track both decks: releasing one pad does not silence the other deck while it still holds that sample. Changing panels or pad modes preserves playing sounds. A held sample still stops on the final physical release, even after leaving sample mode. Return to SAMPLES to stop a loop or latch with its pad.

With `shift.silence=1`, pressing SHIFT alone stops all samples. Loops use a 32-frame edge ramp to reduce splice clicks, except for sounds shorter than 128 frames. The desktop preview applies the same ramp and master gain curve.

Drag the on-screen volume bar to set the sample level. Touch the displayed volume to restore the bank default. The master and microphone talkover affect the mixed result.

The host writer produces numbered WAV files with stereo PCM16 audio at 44.1 kHz. It keeps the first eight seconds of each sound. Settings contain a default volume from 0 to 100 and an RGB colour for each pad.

The source port includes loading, playback, pad LEDs and volume controls. It has not been validated on hardware. Off by default.

## Disable it

Create `/tmp/rx3-samples.off` on the player to keep the module out until the next power cycle.
