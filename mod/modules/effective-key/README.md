<!-- SPDX-License-Identifier: MPL-2.0 -->
# Heard key

With MASTER TEMPO off, the tempo fader changes the pitch as well as the speed, so a track analysed in 5A played at +5.95% is heard in 12A. With this module the deck shows the key you hear: the analysed key moved by the nearest whole number of semitones, 12 x log2(1 + tempo), plus any KEY shift. When the tempo sits more than 25 cents away from a semitone, the key gets a "~". With MASTER TEMPO on nothing changes.

Key Sync, the KEY tab colours and the KEY MATCH colours in BROWSE follow the heard key too.

How it works: Key Shift reads each deck's tempo and MASTER TEMPO state from the player's own status (`UiGetPlayTempoRate`, `UiGetPlayMasterTempo`) and rewrites only the screen copy of the deck's key line (`ConvertPlayTitle2Gui`), which the player makes again whenever `Ui_MemoryCueCommentUpdate` is set. The analysed key the other modules read is left untouched. Addresses are for firmware 1.19 and every one is guarded.

Not yet run on hardware. The tempo unit (0.01%) is read from the player's own display code and still needs a check on the deck, WIDE range included.
