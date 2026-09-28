<!-- SPDX-License-Identifier: MPL-2.0 -->
# Shared runtime framework

Decision: the core provides shared services. A module owns its behaviour and state and depends on the public service contract in full. Reading another module's globals or calling a private core helper is not a supported extension mechanism. Existing contracts may be replaced to establish this boundary.

## Source organization

Public contracts live in `mod/modules/core/api/`, lifecycle and composition in `runtime/`, shared implementations in `services/`, firmware adapters in `firmware/`, panel helpers and translations in `ui/`, and probe formats in `diagnostics/`. The root retains manifests, shell installation, asset generation and the legacy entry point. See [the directory guide](../mod/modules/core/README.md).

Native notification rendering belongs to rbp: the firmware adapter calls `ui::Caution::set` using B051. The queue coordinates toolkit requests only; it neither replaces Emergency Loop nor controls the priority of native player warnings.

## Implemented boundary

The library is still `librx3_core.so`. Separate compilation units establish ownership without adding a dynamic loader or assuming new symbols in the player's libc. This is source modularity, not independent binary delivery or crash isolation. The module descriptor is versioned and size-checked, but is not yet a stable dynamic ABI.

- `rx3_module_api.h` is the module entry contract. It exposes a service table, opaque hook handles and copied mix observations. It exposes no feature implementation or PCM context.
- `rx3_modules.c` handles configuration, descriptor validation, start, partial-failure cleanup, reverse-order stop and track notifications. It names no feature.
- `rx3_composition.c` lists the module descriptors. This is the only framework composition file that names individual modules.
- `rx3_hooks.c` owns detour records, trampolines and an exclusive address registry. A second owner cannot hook an overlapping range, including while the first owner is draining callbacks. Relocating a live handle is forbidden.
- `rx3_patch.c` is the ARM instruction-writing adapter. Firmware-specific patch primitives are not in the module service table.
- `rx3_log.c` owns the shared destination and log budget.
- `rx3_mix_state.c` owns one typed provider registration. Readers receive values, never the provider's buffers. Only the current provider can withdraw its registration. Missing providers and invalid decks produce an empty observation.

Keyshift, Search Latin, Now Playing and Stemwave are separate compilation units. Their only framework calls go through the service table. Their private headers are included by their own module source, not by the core. Native link tests build these units without the performance implementation. The Makefile and application compiler read the same additional compilation units from `arm_hook.sources`; every unit also belongs to its module's `build_files` for packaging.

Search Latin and Now Playing can start without performance UI when no performance feature is selected. If a selected performance feature fails, the bundle does not report ready. Stemwave receives selection, availability and readiness through the shared mix service; Stems supplies these values from its private state. It no longer exposes its readers or PCM pointers to the waveform renderer. The observation preserves the previous atomic field reads; it is not a new guarantee of a transactional, generation-consistent deck snapshot.

## Ownership and calling rules

Startup and hook mutation run serially. Descriptors, services and callback code live until process exit. There is no hot unloading. `start` returns success only after it has acquired its required resources; failure invokes that module's `stop`, without stopping unrelated modules. `stop` must accept a partial installation. Unselected modules are not started or stopped by the new lifecycle manager.

A hook handle starts at zero. `detach_hook` restores the native entry point while retaining the trampoline; after callbacks have drained, `release_hook` releases it. A failed restoration keeps the allocation and address reservation. Modules must not clear their original callback when removal fails. The simple `uninstall_hook` service combines both operations and is only suitable when its callbacks are quiescent. Audio modules must use the two-phase lifecycle. The low-level ARM writer still requires hardware acceptance; host tests cannot establish safe instruction replacement on the player.

`track_will_load` runs on the native loading thread before the original load, allowing metadata invalidation before new text can be observed. `track_did_load` runs after the original load and the existing providers' load callbacks. Mix observations may run on the waveform thread. A provider must return promptly without allocation, I/O or waiting, and its code must remain resident after withdrawal. Logging and hook installation are not audio-thread services. Workers remain owned and joined by their modules.

## Remaining migration

The old performance implementation remains in `rx3_core_hook.c`. It is not yet a pure framework: Stems, Samples, Logo and Theme still use legacy composition. Their use of the shared hook manager does not make them fully migrated modules. Do not use these legacy headers as templates for new modules.

| Module | Target dependencies | Migration gate |
| --- | --- | --- |
| Search Latin | Hooks, logging | Implemented as a separate unit; no UI dependency. |
| Now Playing | Hooks, logging | Implemented as a separate unit; owns worker, sockets and player observations. |
| Stemwave | Hooks, logging, mix observations, track notifications | Implemented as a separate unit; no direct Stems state access. |
| Stems | Deck lifecycle, audio processing, pads/LEDs, panel, memory reservations | Remove PCM/path/loading logic from the core and use an input/audio owner before separate compilation. |
| Samples | Audio processing, input/SHIFT, mode ownership, panel, memory reservations | Remove calls to Stems and access to Theme's SHIFT state. |
| Key Shift | Hooks, deck lifecycle, audio format, panel/text observations | Separate compilation unit; owns pitch state, native pitch engine, configuration and panel. Core owns the common audio-start hook. |
| Logo | Image contributions and buffer lifetime | Remove the special lifecycle outside the module registry. |
| Theme | Render policy, image variants, input chords, Utility contributions | Stop owning SHIFT; coordinate image tables through one image service. |
| Beat Jump variants, Decoder Sleep, Telnet, Logging variants | Existing shell lifecycle and guarded patches | Keep independent of the in-process framework. |

The next extraction is the input service. It must own the native pad and SEND_KEY hooks, SHIFT state, deterministic input priority and mode handoff. Samples may consume an event while its mode owns the pads; otherwise dispatch continues to Stems and then the original player exactly once. Observers cannot consume events. Neither feature may install or remove the shared native hook.

The image service follows: one owner publishes native image tables and controls buffer lifetimes. Logo contributes an image and optional variants; Theme contributes conversion policy; panels contribute private IDs. Modules must not repoint a neighbour's table or free storage still referenced by a native image record.

Audio services must distinguish stream stages rather than expose a generic untyped bus. Registration fixes ordering, thread, block format and failure behaviour. Processing callbacks cannot allocate, read files or wait. Memory reservations account for Stems, Samples and image arenas together; they do not replace each module's own bounds checks.

## Alternatives

A single large translation unit preserves accidental access to every private global. Merely moving its includes does not solve that. One independent shared object per feature would introduce loading order and overlapping hook ownership before the contracts are ready. Separate compilation with one composition root is the chosen first step; splitting the binary can follow once each feature passes the same contract and lifecycle tests.

## Acceptance

A migrated module must compile and link against the public API and mock services without the performance core or sibling modules. Test partial installation, ownership conflicts, cleanup and the behaviour it changes. Build through both Makefile and the application's manifest path, and verify the resulting ARM imports against the known player symbols. Compile generated module templates too.

The runtime changes in this migration have not yet run on hardware. Before deployment, exercise each module alone, the combined configuration, guard refusal, track replacement and the existing pad/SHIFT/audio acceptance sequence in CONTRIBUTING.md. A successful host build is not hardware validation.

## Notification and DSP services (API version 2)

`services->notices` now exposes `post`, `cancel` and `available`. A request contains a stable owner token, an owner-local ID, deck, priority, duration and UTF-16 text. The service copies up to 95 UTF-16 units and rejects longer or empty strings. It holds eight requests; a full queue returns `RX3_NOTICE_FULL`, and contention returns `RX3_NOTICE_BUSY` immediately. Producers must handle these results; an audio callback must never retry in a waiting loop. Accepted means queued, not displayed.

Owner/ID replacement updates a message without consuming another slot. Equal priorities retain FIFO order; higher priorities preempt. Duration starts on first display; time spent preempted counts toward expiry. Replacement restarts duration on its next display. The renderer owns a separate persistent text buffer and hides the previous notice before replacing that buffer. Native UI calls never run on producer threads, and recursive drawing cannot re-enter the pump. The existing translated startup warning now uses this service. Its language is selected before posting, then its text is copied.

The native adapter still needs the existing performance draw hooks. `available()` remains false until a usable renderer has run, and the disable switch clears queued notices. Messages on decks 0 and 1 are supported by the current adapter; global routing is reserved and explicitly rejected pending firmware verification. A module must not claim a notice was displayed merely because posting succeeded. Sentinel polling runs in the existing background watcher, not once per rendered frame.

Example inside a module that retains the service table from `start`:

```c
static const unsigned char notice_owner;
static const uint16_t ready[] = {'R', 'E', 'A', 'D', 'Y', 0};
struct rx3_notice notice = {
    &notice_owner, 1u, 0u, RX3_NOTICE_INFO, 3000u, ready
};
enum rx3_notice_result result = services->notices->post(&notice);
/* Handle FULL/BUSY or fall back to the module's status. */
```

`services->dsp` supplies interleaved stereo PCM16-to-float conversion, gain ramps, additive mixing, peak/mean-square measurements and integer milliseconds-to-frames conversion (rounded down). Counts are stereo frames, buffers belong to callers and ramps carry caller-owned state. Ramps continue across block boundaries and apply one gain to both channels. These functions allocate nothing, perform no I/O and add no libc imports. Finite PCM values are expected; there is no hidden limiter, normalization or clipping.

The scalar kernels `rx3_dsp_lerp` and `rx3_dsp_loop_edge` are shared inline operations, already used by Stems transitions and Samples loop edges. Existing PCM reconstruction and sample playback regression tests preserve their behaviour. The loop edge kernel retains the existing 32-frame edge on loops of at least 128 frames.

This implements reusable calculations, not yet a shared audio processing graph. Stream-stage arbitration, resampling, public pitch adapters, memory reservations and removal of the remaining legacy module coupling are still pending. The notification adapter and DSP refactor have not yet run on hardware.

### Startup readiness

The constructor clears the previous ready marker before installation. Legacy providers and shared performance hooks start before standalone consumers. Every configured feature must install successfully before standalone modules start; any standalone failure then stops the consumers before removing the providers. The ready marker and success log are published only after the selected set succeeds. Standalone-only selections use the same failure check. Per-module configuration, activation and failure are written to the runtime log; readiness is an installation result, not proof of audio or rendering quality.

Logo is an explicit consumer of the performance image hooks even when no panel feature is selected. Its native position record is checked before changing it, and teardown restores the saved position only while the record still holds this module's value. The seven light tab images are shipped alongside their dark variants.

## Panels, buttons and sliders (API version 3)

`services->panels` accepts a static `rx3_pad_row` through `register_row`, releases it through `unregister_row`, and queues render-thread selection through `open(panel_id)`. IDs 1-3 belong to Keyshift, Stems and Samples; 4-16 are available to additional clients. Registration rejects duplicate owners, invalid counts and sliders without accessors. A module may register a panel without a legacy performance feature: the constructor then installs the shared rendering adapter before reporting readiness. Descriptors and callbacks must remain resident until runtime shutdown; arbitrary hot unload is not supported.

A client provides widget types, weights, captions, state/actions and slider accessors in its own units. Optional `kind` and RGB565 `colour` callbacks select presentation per deck, with slider accessors required when kind is dynamic. The framework owns layout, clipping, square button frames, selected/pressed states, slider tracks and caps, and touch capture. The same geometry drives rendering and touch. Leaving a button cancels it; sliders clamp at the track endpoints. Changing the panel during capture cancels the old gesture.

The Stems client declares one `RX3_PAD_TOGGLE_SLIDER` per available role. Tap toggles; holding for 350 ms then dragging changes volume relative to the initial gain. The core owns gesture recognition, geometry and RGB565-to-native-RGB888 accent conversion. API version 5 adds the optional `slider_visible` callback: Stems keeps partial volumes visible and hides a full-volume slider two seconds after release. Zero is off. The four percentages share one atomic word; enabling a muted role restores 100%. Changes use the existing 256-valid-frame interpolation before mixing the residual and prepared roles. Track loading resets the levels. Stemwave observes the nonzero role mask; it does not represent partial slider gain in its waveform amplitudes.

Samples declare one screen-wide slider plus a reset/readout button. Both deck halves access the same bank volume. No sample-specific drawing or coordinate calculation is part of the client.

The panel registry is compiled independently and exposed in the public service table. The native painter still uses rbp adapters in the legacy translation unit; the legacy audio features have not all become separate compilation units. Panel clients do not draw or inspect the renderer's private state. This is a shared panel contract, not a claim that the entire core migration is complete.


## Embedded waveforms (API version 4)

`services->waveform(deck, mask, destination, count)` copies the package's
amplitudes (0..31) on the native 150 Hz grid. Returns `count` on success, zero
when unavailable and `UINT32_MAX` when a package exists with an incompatible
axis. The destination belongs to the caller. The provider protects resident
package memory with its reader barrier; no provider pointers cross this API.

## Per-part semantic colours (API version 6)

`rx3_pad_row.part_colour(deck, widget, part)` optionally supplies an RGB565
semantic accent independently of selection. Zero means unknown/unavailable.
KEY uses it for the Camelot key actually shown by each stepper part. The core
renders the rail and preserves theme adaptation and the selected-state frame.

## KEY SYNC configuration

The Toolkit supplies `keyshift/sync-range.txt` to the runtime builder as module
content (integer 1–12, default 1). The module exports `RX3_KEY_SYNC_RANGE` through
`module_export`, including its restart detection. The KEY client declares a
second standard button only while a valid sync offer exists; the core owns its
layout, rendering and touch dispatch. No KEY-specific drawing is added.

KEY SYNC additionally supplies `sync-mode.txt`. New Toolkit preferences use `harmonic`, a one-semitone limit and no optional Energy Boost rules. Stored preferences and legacy missing-file defaults are preserved. API version 12 adds a copied harmonic reference and deck-key publication to the BROWSE service. Both clients use the observed native key set, the local MASTER and its effective transposed key; the KEY client never changes the MASTER through KEY SYNC. The pure shared solver is checked against the Python preview implementation. See [Transposition](transposition.md) for evidence and unavailable-reference behavior.

## Passive panel statuses (API version 7)

`RX3_PAD_STATUS` declares a readable, non-actionable row element. The shared
painter omits button chrome and semantic accents; the shared touch machine
consumes the whole gesture without dispatching `fire` or a slider update. A
status becoming a button during the gesture remains passive until release.
Dynamic `kind` callbacks may now describe statuses without slider callbacks;
missing slider callbacks make a dynamically requested slider passive safely.
KEY uses the same slot for status and action to preserve touch geometry.

## Outlined actions (API version 8)

`RX3_PAD_OUTLINE_BUTTON` uses the regular release-action contract with a neutral
face, high-contrast caption and semantic outline (two pixels, three while held).
Shared steppers now keep their end actions neutral; only their value part may
use a full semantic fill. KEY supplies fixed −1/+1 labels and its target colours;
it does not own drawing or coordinates. Stem fills and status rendering remain
unchanged.

## Keyshift boundary (API version 9)

`keyshift/rx3_keyshift_module.c` owns the module descriptor, private state,
configuration, pitch hooks and panel. The core neither includes its private
headers nor calls its implementation. Only the composition root names it.
The native pitch effect adapter remains private to Keyshift; this is not a
shared audio processing graph or a firmware-independent DSP implementation.

The module descriptor now accepts audio-format, render-text and diagnostic
notifications. The core decodes the native glyph layout into a borrowed
`rx3_text_observation`; modules must not retain its text pointer. Keyshift
interprets the deck-key glyph and publishes its own refresh flag through the
existing `needs_refresh` panel callback. It cannot inspect renderer state.

The core installs the shared audio-start hook only when an active module
subscribes to audio-format notifications. Keyshift registers its panel and
pitch hook through the public service table. `detach_hook` and `release_hook`
are public services, preserving the two-phase audio hook teardown.

Shutdown closes notification admission and drains in-flight callbacks before
stopping modules. A module must not call runtime shutdown from a notification.
This drain covers lifecycle observations, not arbitrary native hook callbacks
or panel gestures; modules still own their hook quiescence. There is no hot
unload. Descriptor and panel storage remain resident.

Host tests link Keyshift without the performance core and exercise configuration,
manual pitch, track reset, harmonic sync, panel registration failure and hook
failure. A threaded test verifies notification draining before cleanup. These
checks do not establish audio fidelity or safe live patching on physical RX3.

## Native Browse extensions (API version 11)

`services->browse` shares the native row hook between Browse Columns and Key
Match. The core owns database requests on the native worker, record/string
allocator pairing, bounded UTF-16 transport with each queued row, and the extra
column's rendering. No database call runs on the paint thread. The feature
modules supply a field/caption or harmonic classification/image callbacks.
Registering another provider of the same kind fails without replacing it;
removing one provider preserves the other and its shared hook.

The first two columns keep their native sources. Browse Columns chooses only
the extra field. Registering a column hides the floating Browse LOAD images
and disables their list touch handlers, reclaiming the selected row for all
three values. Physical LOAD handlers and controls in other screens are unchanged.
The extra hooks are guarded, acquired only by the column provider and released
with it; Key Match alone retains the native LOAD controls.
