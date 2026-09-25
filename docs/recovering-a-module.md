<!-- SPDX-License-Identifier: MPL-2.0 -->
# Porting a released runtime

The released runtime defines the behaviour to reproduce. Read each function and its surrounding state machine in Ghidra before writing it. A decompilation helps identify constants and branches; verify register use, pointer arithmetic and callback ordering in the disassembly.

The recovery target is the DJ's capabilities, not an identical internal architecture. Keep an existing implementation when it is more useful to the DJ and easier to maintain. In particular, native touch hooks replaced by the shared pad row are not missing features merely because their original function names disappeared. Compare the complete user action, resulting audio or display, fallback, and cleanup before deciding to port code.

Permission to use the reference is recorded in writing. The migration pull request must record the permission and the decision to defer attribution until merge in its Legal section. No supplied binary or unpacked resource is included in the repository. Local analysis material stays on the operator's machine.

## Method

Compare defined symbols and hook guards against the current core. Missing names identify work to inspect, but shared names do not prove shared behaviour. Compare known functions to calibrate the reading.

Trace each feature from configuration through hook installation, input, rendering or audio, and teardown. Shared hooks need an owner, and callbacks must finish before their data or trampoline is freed. An inner loop is not a complete feature.

Keep provisional addresses and disassembly evidence in local notes. [CONTRIBUTING.md](../CONTRIBUTING.md#supporting-another-firmware-build) requires the firmware hash, guard bytes and a result on hardware before an address is documented as verified in [REFERENCES.md](../REFERENCES.md).

## Current status

All migration changes remain uncommitted. The table distinguishes prior hardware observations from source work; compilation and native C tests do not establish device behaviour.

| Module | Source status | Hardware status |
| --- | --- | --- |
| [logo](../mod/modules/logo/) | Host conversion, container loading and dark/light image-table replacement. | The handover reports a byte-exact host conversion. The new light-table connection has no device run. |
| [stemwave](../mod/modules/stemwave/) | Refresh sequencing, three column render paths, Blue overview restoration and the four-role selection adapter. | The earlier hook fired on toggles. The new renderer and refresh request are untested on hardware. |
| [theme-white](../mod/modules/theme-white/) | Solid fills, lazy image conversion, shared-bitmap cache, light logo and optional tabs, Utility row, UI-thread switching and waveform palette. | Automated queued dark/light/dark/light transitions on 1.19 preserve the unloaded-deck background, header and eight hot-cue cells. Physical shortcut, Utility and loaded-track coverage remain pending. |
| [samples](../mod/modules/samples/) | Settings and WAV contract, resident bank loader, master mix, retriggering, shared pad routing, LEDs, volume strip and worker teardown. | No playback or pad validation. |
| [search-latin](../mod/modules/search-latin/) | Folding hook and configuration. | The handover reports installation. Search for an accented title using unaccented input remains untested. |
| [keyshift](../mod/modules/keyshift/) | Common time-stretch manager attachment, generated requests, transport resets, neutral on track load and Camelot labels. | The new attachment and key recognition need an audio and display comparison. |
| [stems](../mod/modules/stems/) | Playback hook, four-role selection, 256-frame fades, resident PCM16 loading, additional-file fallback, pad routing, LEDs and dynamic strip. | No comparison of the new audio path has been measured. |

Native tests cover waveform sequencing, settings and WAV rejection, the four-role mix, changes during fades, concurrent toggles, key recognition and labels, transport reset decisions, sample pad ownership, master mix order, slider capture across decks, memory reserve checks and failed hook restoration. ARM builds check the resulting imports. These checks do not validate device callback timing, audio continuity, display output or unloading.

The player hash, seven new or changed hook prologues and thirteen Utility words were checked against the supplied player image. The image lookup patch uses a file offset; the hook uses the corresponding virtual address. The regression suite pins that distinction. This is static evidence, not a hardware result.

Behavioural parity is not yet established. Diagnostic formatting, dark-image conversion and sustained performance refresh are present in the current source. The runtime coalesces worker redraw requests onto the render thread and repeats refreshes every 100 ms for a one-second window. This is an adaptation to assess against the visible result, not a missing function to copy back. Optional light tab files are accepted with a dark fallback; supplied artwork is not packaged.

## Recovery checkpoint, 2026-09-25

The supplied runtime decrypts to the archived analysis image byte for byte. All 26 payload files match the analysis tree, and the core hash matches the Ghidra export. The refreshed inventory covers 103 function bodies, 286 data symbols, 29 reference guards and 23 undefined ELF imports. There are 77 same-name source candidates and 26 candidates under replacement names. These are navigation links, not 103 proofs of equivalent behaviour.

The current source passes 88 tests and the publication preflight. The address checker reports 37 matching hook or patch checks against the local 1.19 player. This does not check every pointer, callback contract or runtime transition.

The pure pixel functions were compared against execution of the reference ARM instructions under Unicorn. Every RGB565 input was tested for the dark transform and six light cases: ordinary image, each of the two special replacement image classes, with artwork both enabled and disabled. All 458752 comparisons matched. Only the unsigned integer division import was substituted with integer division on the host. This establishes the tested pixel calculations, not image classification, conversion allocation, display timing or the appearance of a complete screen. The script and hash-bound results remain under the ignored local analysis directory.

| DJ capability | Existing implementation to retain and inspect | Remaining acceptance |
| --- | --- | --- |
| Mute and combine vocal, instruments, drums and bass | Four-role stems, native pad routing, shared on-screen row and 256-frame transitions | Both decks, missing additional files, rapid loading, audible transitions and uninterrupted transport |
| Shift a deck's key and return to neutral | Per-deck shifter, Camelot labels and shared time-stretch attachment; the current interface also offers key matching | Real audio at positive and negative shifts, track changes and transport changes |
| Play samples and adjust their level | Resident bank, shared volume strip, master mix and pads; retain the added hold and loop modes and per-pad gain | Trigger, release, retrigger, loop exit, microphone talkover and bank replacement |
| Make waveforms follow stem selection | Flat, RGB/3 Band and Blue rendering with saved Blue overview | Selection changes, return to full mix, display-mode changes and track replacement |
| Use a light display | Image and fill transforms, Utility choice, shortcut, optional light artwork | Full screen with a loaded track, both switching routes, logo and tab assets |
| Search with accent folding | Bounded in-place query folding after the native shaping function | Actual indexed search results for accented titles, rather than just the folding buffer |
| Display custom artwork | Host image conversion and dark/light logo replacement | Placement, transparency, fallback and reload on the deck |
| Jump 32 beats and jump without quantization | Existing guarded byte patches | Both directions and the resulting transport position |

The subsequent device session confirmed the live 1.19 player hash and loaded only core, theme, Telnet and logging. SHIFT + SHORTCUT changed some panels, but left the central area dark and replaced the hot-cue cells with a checkerboard. Leaving and returning to the deck screen restored the complete light background and all eight cells. This establishes an incomplete refresh during the shortcut transition; it does not validate loaded-track rendering or audio.

A candidate using one native screen-refresh event instead of repeated glyph refreshes also produced an incomplete screen, with duplicate STATUS/BEAT FX strips. It was withdrawn from both source and device. The previous theme library was restored and its hash checked against the original test package. These failed candidates are not retained. The later bounded redraw fix below has narrower, unloaded-deck hardware evidence.

## Display comparison

Static analysis can recover image substitutions, panel geometry, labels, pixel conversion and drawing order. Compare the surrounding state as well as each drawing function. Native text and box rendering still depend on the player's renderer and resources; matching arguments alone does not establish matching screen output.

The reference's separate dark-image conversion is enabled at initialization when `RX3_THEME` starts with `d`. Its pixel function preserves the transparency key and colours whose expanded RGB channel spread exceeds 23. Other pixels are attenuated using integer arithmetic. This conversion must not be applied to every normal dark-mode draw merely because of its name. The launcher currently selects `switch`; the existence of the conversion alone does not establish which image path runs in that configuration.

The image hook, dark pixel function and initialization branch have been compared in Ghidra. This establishes the static branch and conversion rules, not a complete screen comparison. Remaining visual checks include both theme states, selected and idle controls, loading and error states, native text clipping, and redraw transitions. Compare the same resources and screen state before attributing a difference to the source port.

## Device checks

Use player SHA-1 `cf309238491e73cdbdc1f08a09f7a3177e079068`, the build identified in the handover. Confirm the live player before installing a test build.

1. Load a track and exercise both decks. Check transport and audio continuity while switching each stem selection.
2. Compare flat, 3 Band/RGB and Blue waveforms. Return to the full mix, load another track and repeat.
3. Check theme switching against the loaded track, and search for an accented title without its accents.
4. Check sample playback, retriggering, volume, LEDs, shared pad hooks and teardown with audio callbacks active.
5. Check four-role fallback, rapid track replacement and repeated pitch direction changes. Verify both Utility and shortcut theme switches.

Stop a device run if transport freezes, audio drops or the guards reject the player. Record the build hash and observed failure before changing another feature.

Before preparing the migration pull request, run `make test`, `make preflight`, and read the complete diff. Use Summary, Changes, Testing and Legal. State every unverified behaviour.

## Theme transition result

The retained fix applies the pending theme at the beginning of a native render pass and invalidates the active windows once. Root traversal skips visible header groups beneath their hidden parent control, so the fix queues those groups through the native child-list iterator and renders them in a second pass. It does not change their visibility flags or write the framebuffer. Repeating root redraws for four seconds has been removed.

Automated dark/light/dark/light transitions on RX3 1.19 preserved the central background, header and eight hot-cue cells without screen navigation. The tests injected the existing queued request after checking the process, library hash, mapping, symbol and idle state; they did not inject physical button events. The test package enabled only core, theme, Telnet and logging, with both decks unloaded. Utility switching, loaded tracks, audio continuity and the other modules remain unverified. The core still exposes KEY/STEMS tabs in this theme-only configuration; that pre-existing module-gating issue is separate from the redraw fix.

The retained implementation passes 91 tests, publication preflight and 39 binary-address checks. Regression tests cover stable theme state within a render pass, window invalidation before root rendering, header rendering after the root, actual child-list iteration and a bounded exit for an unexpected cyclic iterator.
