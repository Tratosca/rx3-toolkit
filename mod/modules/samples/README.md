<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🥁 Sample pads

Press SLIP LOOP until the pads reach the sample page: the button already steps through the player's own pages, and this is the one after them. Your hot cues are left alone. Press any pad mode button to leave, or SLIP LOOP once more to go back to the player's first page.

At most four samples can play simultaneously, across both decks and all modes. A fifth start is refused without cutting an existing voice. Stopping a voice or letting it finish frees a slot; retriggering an already playing one-shot uses its existing slot. The desktop simulation enforces the same limit, including pending audio preparation.

Each pad plays once, while held, in a loop, or as a latch (press again to stop without looping). Holds track both decks: releasing one pad does not silence the other deck while it still holds that sample. Leaving the sample page stops holds, loops and latches; one-shots finish naturally.

With `shift.silence=1`, pressing SHIFT alone stops all samples. Loops use a 32-frame edge ramp to reduce splice clicks, except for sounds shorter than 128 frames. The desktop preview applies the same ramp and master gain curve.

Drag the on-screen volume bar to set the sample level. Touch the displayed volume to restore the bank default. The master and microphone talkover affect the mixed result.

The host writer produces numbered WAV files with stereo PCM16 audio at 44.1 kHz. It keeps the first eight seconds of each sound. Settings contain a default volume from 0 to 100 and an RGB colour for each pad.

The source port includes loading, playback, pad LEDs and volume controls. It has not been validated on hardware. Off by default.

## Disable it

Create `/tmp/rx3-samples.off` on the player to keep the module out until the next power cycle.
