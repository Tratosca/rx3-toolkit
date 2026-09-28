<!-- SPDX-License-Identifier: MPL-2.0 -->
# Phase 1: interface audit and proposed direction

Date: 2026-09-26. Mode: Operate. Workflow: Impeccable shape, constrained by the user's brief. Status: proposed, awaiting approval. No implementation is authorized by this document.

## Decision

Keep all six screens and all current operations. Replace the current card-heavy composition with a stable sidebar, a persistent screen toolbar, inset grouped lists, and focused editors. Preserve Python contracts, product rules, audio behavior, acquisition consent, and local file operation. Use Apple's familiar desktop conventions within the existing webview, without claiming native AppKit controls, native vibrancy, a native menu bar, or native attached sheets.

The design target is preparation of an RX3 drive and its modules, sample banks, artwork and stems. The primary audience is a DJ or operator preparing media on a computer. This is a task interface, not a marketing surface or a hardware emulator.

## Evidence and boundaries

Read: CLAUDE.md, .claude/STYLE.md, CONTRIBUTING.md, relevant README sections, app/localization/README.md, all nine frontend files, bridge operation definitions and shell window dimensions. The working tree already contains substantial staged and unstaged work. This audit treats the current files as the baseline, not HEAD or historical checkouts.

This is a source audit, not a rendered visual acceptance test. Layout risks below are distinguished from directly established code defects. No app was launched, no key was sought, no drive was modified, and no network operation was initiated through the app. Browser and Windows behavior remain unverified. Two baseline checks passed: five localization tests and the shell resource self-test (42 exposed operations).

The only files created for Phase 1 are this report and [inventory.json](inventory.json), both inside the permitted web directory. Neither is loaded by the page. No PRODUCT.md, DESIGN.md, application code, catalog, changelog, bridge, shell, service, dependency, or commit was changed.

## Complete inventory

[inventory.json](inventory.json) records all 42 exposed operation signatures and definition locations, all 41 operations reachable from frontend code, all 53 static interactive/focusable HTML elements, all 429 catalog keys with their complete English and French values and placeholders, literal frontend references, dynamic key families, and source SHA-256 hashes. Literal string references are not a dead-code detector: names assembled at runtime and Python Message objects can reach the UI without a literal frontend reference.

The tables below also inventory dynamically generated controls, local interactions, and application states. `Local` means no direct Python call; a later save/build can serialize the change. All bridge replies keep the current `ok/value` or `ok/error/errorMessage` envelope. File-picker cancellation continues to be a no-op. Errors currently use the shared error strip unless otherwise noted.

### Shared shell and operations

| Screen | Element | Bridge call | Current states / behavior |
| --- | --- | --- | --- |
| All | Six sidebar destinations and Drive badge | Local | Selected/unselected, hidden panels, badge when mod installed; Up/Down/Home/End; scroll resets on every switch |
| All | Localization bootstrap | localization_catalogs() | Catalog success or thrown error; English fallback; saved locale or system locale |
| Settings / all | Language selection | localization_language(locale) | EN/FR, selected state, document language, redraw events, local persistence |
| All | Folder picker | pick_folder(start) | Native chooser, selected path, cancelled, error; shared by Drive, output and Stems |
| All | Single-file picker | pick_file(kind, start) | key/image/library filters; selected, cancelled, error |
| Samples / Stems | Multiple-file picker | pick_files(kind, start) | audio/stem filters; Samples accepts several; Stems slot requires exactly one |
| All | Job strip and progress | job_status() | idle/running/done/cancelled/failed; determinate or indeterminate; result/error text; polling every 200 ms |
| All | Cancel job | job_cancel() | Button shown while running; backend retains cancellation semantics |
| All | Error/success strip and dismiss | Local | Error persists; success auto-hides after 6 s; alert/status role; only one message at a time |
| All | Deletion arming | Local, then operation | First press changes label for 4 s; second press deletes; used for mod, retained key, stored bank |
| All | Schematic deck canvas | Local | Samples selection/playing and logo theme/artwork; no firmware screenshot; localized hardware labels |

`reveal(path)` is exposed by Python but is not called by the existing frontend. It is not a removed feature, and adding a new control for it is not required for parity. Preserve 41/41 currently reached operations; do not misreport the self-test's 42 as 42 existing UI controls.

### Drive

| Screen | Element | Bridge call | Current states / behavior |
| --- | --- | --- | --- |
| Drive | Choose/change USB folder | pick_folder(start), drive_report(path) | Empty, chosen, read error; also reachable from Samples prerequisite |
| Drive | Summary | drive_report(path) | Mod absent/present/unrecorded, firmware, installed modules, last loaded/refused modules, music absent or track/playlist counts, banks and active bank, read-only warning |
| Drive | Refresh | drive_report(path) | Re-reads selected drive; no dedicated pending state |
| Drive | Remove mod | mod_remove(path) | Disabled without installed mod; armed; success count; report refresh; failure |
| Drive / others | Propagate selected drive | Local event rx3drive | Initializes build output only if empty; loads Samples; opens Stems library if export exists and no library is open; initializes Stems output only if empty |

### Modules and key consent

| Screen | Element | Bridge call | Current states / behavior |
| --- | --- | --- | --- |
| Modules | Firmware segmented choice | mod_firmwares(), mod_modules(firmware) | Discovered firmware list; changing firmware rebuilds selection from defaults |
| Modules | Category groups | Local | performance, stems, screen, streaming, diagnostics; diagnostics disclosure opens if selected |
| Modules | Every selectable module switch | mod_selection(firmware, selected, toggled, on) | Off/on, defaults, dependencies, required-by explanations, conflicts; nonselectable internal dependencies remain implicit |
| Modules | Selected count and chips | Local | Empty/selected; firmware and dependency-resolved selection |
| Modules | KEY SYNC range and mode | Local, then mod_build | Range 1-12; identical/harmonic; disabled when keyshift off; persisted locally |
| Modules | Key-match rules | Local, then mod_build | Four checkboxes: diagonal/boostTwo/boostSeven/four; bitmask; disabled when module off; local persistence; external technique guide link |
| Modules | Browse column | Local, then mod_build | BPM/key/artist/time; IDs 13/15/7/11; disabled when module off; local persistence |
| Modules | Key status/path | mod_key_hint() | Absent, external selected key, retained key; retained-key deletion visibility; acquisition size note |
| Modules | Browse for key | pick_file("key", current) | Select existing key; cancel leaves current state |
| Modules / startup | Acquire key / terms | mod_key_fetch(true) | Terms automatically open at startup without key and idle job, or from fetch/build; must reach text end, explicitly check consent; Cancel/Escape; downloading, cancellation, error, retained success; false started refreshes hint |
| Modules | Forget retained key | mod_key_forget(), mod_key_hint() | Only for retained current key; armed confirmation; refresh; success/error |
| Modules | Output folder | pick_folder(current) | Empty/selected; independent of subsequent Drive selection |
| Modules | Build | mod_build(firmware, selected, key, output, logo, keySyncRange, keySyncMode, keyMatchRules, browseColumn) | No selection/output disables; missing key opens terms; accepted job; running/cancelled/failed/done; file size and path result; refresh selected drive on success |

Each selectable module is inventory-covered through `module.<id>.name/description` and the runtime module list, not a hardcoded replacement list. The current catalogs contain 17 module name/description pairs. Preserve compatibility and dependency decisions from Python.

### Samples

| Screen | Element | Bridge call | Current states / behavior |
| --- | --- | --- | --- |
| Samples | Limits/defaults bootstrap | samples_defaults() | Pad count, total max voices, duration/memory limits, gain/volume/name limits, colors/modes; do not substitute design constants |
| Samples | Drive prerequisite and schematic | Shared picker/report; Local | No drive -> actionable empty state; schematic stays visible; editor appears after drive event |
| Samples | Load bank list/active bank | samples_read(drive) | No banks -> new bank; active/existing bank; settings valid/bad; read error |
| Samples | Bank selector, new bank | Local; samples_read on switch | Existing/new; active marked with *; unsaved discard via native confirm; stop audio before loading |
| Samples | Bank name | Local | Editable, 64-character HTML maximum, backend naming validation on save |
| Samples | Pad grid | Local | Empty/filled/selected/playing; number, label, duration meter, duration, playback-mode badge |
| Samples | Add/change sound, batch import | pick_files("audio", ""), samples_analyse(paths) | Accepted/rejected sources; sequential assignment from selected pad; duration clamp from defaults; refusal message |
| Samples | Pad name | Local | Empty/default/file-derived/user name; limit from defaults |
| Samples | Pad color palette and custom picker | Local | Default/custom/selected; actual pad color is user content |
| Samples | Four playback modes | Local | Once/Hold/Loop/Latch, selected mode and explanatory hint; switching stops audition |
| Samples | Trim start and duration | Local | Numeric, bounded by source/default limits; change stops playback; kept audio becomes editable source |
| Samples | Audition / hold / stop | samples_audition(path, start, duration) | Pending conversion/decode, playback, release, stop, loop/latch toggle, no audio, error, voice ceiling; current JS audio math remains unchanged |
| Samples | Pad gain and reset | Local | Slider, readout, reset to backend unity; updates playing gain |
| Samples | Clear pad | Local | Disabled if empty/unnamed; clears draft pad; no immediate drive write |
| Samples | Simulation and Stop all | Local | Edit/simulate; pointer hold; number keys trigger pads, keyup releases hold; Escape stops; Shift stops if configured; blur stops audio |
| Samples | Bank volume | Local | 0-100 current HTML range; updates audio and readout; keep serialized meaning |
| Samples | Shift silence | Local | Off/on; capability ready/unknown displayed separately |
| Samples | Dirty/new/clean badge and bank memory | Local | Draft/new/saved, settings warning, byte usage/limit; beforeunload protection |
| Samples | Save | samples_save(drive, name, pads, options) | Queued job, progress, failure, cancellation, success -> reload; options retain volume, shiftSilence, activate rules |
| Samples | Activate bank | samples_activate(drive, name) | Disabled for new/dirty/already-active; activation -> reload; error |
| Samples | Delete bank | samples_remove(drive, name) | Stored banks only; armed confirmation; reload/error |

Pad payload stays `{source, keep, colour, name, mode, gain, start, duration}`. Saving remains separate from activation. Preserve the four playback modes and the backend's total voice ceiling. Do not add a loop timeout. The diagram's eight pad positions are not eight simultaneous voices.

### Logo

| Screen | Element | Bridge call | Current states / behavior |
| --- | --- | --- | --- |
| Logo | Geometry/defaults | logo_limits(), logo_canvases() | Available canvases and exact geometry/zoom limits come from Python |
| Logo | Choose/change image | pick_file("image", ""), logo_open(path) | Empty, opening, loaded, error; new image resets framing |
| Logo | Restore artwork | logo_open(remembered.path) | Local persistence restores canvas/frame/invertLight; failure uses common error |
| Logo | Canvas selector | Local, then logo_render | Dynamic named canvases and dimensions; selection updates framing preview |
| Logo | Fit/fill, zoom, recenter | Local, then logo_render | contain/cover; bounded zoom; recenter offsets; continuous local preview |
| Logo | Drag, wheel zoom, keyboard pan | Local, then logo_render | Pointer capture; wheel keeps point under pointer; arrows move 1, Shift+arrows 10; backend render debounced 200 ms |
| Logo | Deck preview light/dark | Local | Separate from application theme; uses existing artwork variants |
| Logo | Invert grays in light preview | Local, then logo_render | Toggle only when artwork is invertible; switches preview to light; noninvertible explanatory state |
| Logo | Exact preview / warnings | logo_render(path, pane, frame) | Local approximate preview then Python result; ignores stale result; faint warning, dimensions, same-in-light note; decoding error |
| Logo | Enable logo module | mod_selection via rx3.tick | Not selected warning and direct action; dependency rules remain in Python |
| Logo / Modules | Publish framing | Local rx3logo event | `{path, canvas, mode, zoom, offsetX, offsetY, invertLight}` feeds later build; no separate logo-save operation |

### Stems

| Screen | Element | Bridge call | Current states / behavior |
| --- | --- | --- | --- |
| Stems | Runtime status and accelerator options | stems_runtime(), stems_qualities() | Ready/missing; summary; accelerator list; actual quality summary |
| Stems | Accelerator / quality selectors | stems_choose(null, accelerator) / stems_choose(mode, null) | Selected choice; response updates quality; same current parameters |
| Stems | Install/reinstall | stems_install(accelerator) | Job running/done/failed; runtime refresh on success; existing backend network behavior retained |
| Stems | Cache limit and usage | stems_cache(), stems_cache(bytes, false) | 0-1024 GiB input in 0.25 steps, persisted bytes, error |
| Stems | Clear cache | stems_cache(null, true) | Disabled when empty; currently immediate; refresh usage |
| Stems | Library protection and recheck | stems_library_status() | Busy/free/error; busy warning with Recheck; blocks pickers/start/import |
| Stems | Open drive / XML | pick_folder("") / pick_file("library", ""), stems_library(path) | No library, loading, counts/path, read error; unlocks import/listening sections |
| Stems | Playlist | Local selection | Playlist labels with counts/missing tracks; changing refreshes estimates and track list |
| Stems | Estimate and per-track memory | stems_forecast(playlistId, roles) | Summary, per-role/total bytes, unknown size, threshold warning, failure |
| Stems | Parts | Local | Vocals always selected; drums optional; bass requires drums; deselecting drums deselects bass |
| Stems | Destination | pick_folder(output) | Empty/chosen; initialized from Drive only if empty |
| Stems | Prepare | stems_start(playlistId, output, roles) | Runtime/library/output prerequisites; protected by library check; shared job progress/current track/stage/errors/notices; cancel |
| Stems | Track selector for import/listening | stems_tracks(playlistId) | Empty/selected; stale responses guarded |
| Stems | Read assigned files | stems_import_assign(trackId, null) | Current mapping, no mapping, error |
| Stems | Assign/change/clear each of vocals/drums/bass | pick_files("stem", ""), stems_import_assign(trackId, values) | Exactly one file per slot; drop path when webview supports it, otherwise picker hint; clear unassigns, does not delete file |
| Stems | Import prepared files | stems_import_start(trackId, output) | Requires track/output/vocals and library closed; job result reports alignment trims/gain/residual/waveform notice |
| Stems | Listen source | Local | From drive/imported; imported disabled without vocals |
| Stems | Listen waveform, seek, play/stop | stems_audition(...) / stems_import_audition(...) | No track/no available audio, loading/decode failure, playing/stopped/end; seek via waveform or slider |
| Stems | Original / component listening buttons | Same audition calls | Original, drums, bass, rest/instrumental, vocal; selected masks; unavailable components hidden/disabled; rejected-role notice |
| Stems | Refresh listening | Same audition calls | Stops, clears local cache, resets mask/ramp state, reloads |

Both audition calls retain `(drive, trackId, {mask, state}, position, 30)`. The browser still schedules returned audio chunks and passes ramp state; no DSP, mask, cache, duration, gain, or chunk-scheduling redesign is proposed.

### Settings and legal text

| Screen | Element | Bridge call | Current states / behavior |
| --- | --- | --- | --- |
| Settings | Language EN/FR | localization_language(locale) | Immediate, stored locally, active choice |
| Settings | About | Local catalog text | Static heading/description; no invented version/update operation |
| Terms dialog | Seven legal paragraphs, title, scroll hint, acceptance, download, cancel | mod_key_fetch(true) after consent | All 11 terms keys retained with exact meaning; scroll gate and explicit acceptance retained |

Settings currently has no theme control. Add System/Light/Dark as the explicitly requested presentation setting, stored locally without extending Python.

## String coverage

| Families | Keys | Ownership |
| --- | ---: | --- |
| app, nav, common, preview, unit, locale | 29 | Shell, formatting, shared controls |
| drive | 23 | Drive report and removal |
| modules, module, keyshift, keyMatch, browseColumn | 90 | Module names, descriptions, configuration and key actions |
| samples | 63 | Bank/pad editor and listening |
| logo | 30 | Framing and preview |
| stems, quality, accelerator | 115 | Preparation, import, runtime, cache, audition and backend messages |
| settings | 5 | Language and About |
| job, error, dialog | 48 | Shared jobs, structured failures, native file filters |
| mock | 15 | Schematic hardware labels |
| terms | 11 | Consent and legal text |
| Total per language | 429 | Full values and placeholders in inventory.json |

EN/FR keys and placeholders pass the current localization tests. Neither catalog contains `[TODO]`. STYLE.md and CLAUDE.md still have documentation TODOs, including unknown hardware wording. Do not invent those facts to make the UI read more confidently. Preserve all terms values during the redesign; changing legal wording across README/NOTICE is outside scope. User metadata, paths, bank names and third-party diagnostic text remain data, not localization keys.

## Findings, with evidence

| Priority | Finding and evidence | Proposed resolution |
| --- | --- | --- |
| P1 | Destructive operations use a four-second arming state, not a dialog: app.js:92, app.js:468, app.js:618, samples.js:613. Two rapid presses can confirm without a separate decision surface. | Named confirmation dialog with exact target, explicit consequence, Cancel initially focused, destructive action; retain each original bridge call. |
| P1 | Samples field labels are not bound to their controls: samples.js:175, :189, :234; bank-pick has no dedicated label at index.html:166. | Stable IDs, labels, descriptions and group names; visible focus; screen reader verification. |
| P1 | Global progress is div/span only: index.html:361; updates at app.js:516 do not establish progressbar or a job live region. | Named progressbar with numeric value or indeterminate semantics and rate-limited status announcements. |
| P1 | ask() has no rejection handler and returns null silently without a bridge: app.js:61. Catalog bootstrap throws outside a recovery surface: i18n.js:43, app.js:701. | Explicit connecting/unavailable/retry states; preserve error envelope; catch transport failure without hiding backend diagnostics. |
| P1 | Focused controls are destroyed during ordinary updates: app.js:328 and :386; samples.js:92, :138 and :422; stems.js:88 and :105. | Update existing controls where possible; otherwise restore focus to stable logical ID and keep edit caret/selection. This is code-evidenced focus-loss risk, not a completed assistive-technology test. |
| P1 | Samples drive event reloads a bank without the discard guard used for bank changes: samples.js:597 versus :635. | Include a discard confirmation before a drive change replaces a dirty draft; preserve data/API semantics. This is a proposed UI safeguard requiring Phase 1 approval, not a backend repair. |
| P2 | Modules summary follows the entire list below 1040 px: app.css:571; primary Build sits in that summary, index.html:110. | Keep primary Build in persistent toolbar; move firmware/output/prerequisite summary before list at narrow widths. |
| P2 | Samples shows a 560 px-wide 8:5 diagram before the editor: index.html:128, app.css:553. It can consume much of a 560 px-high window. | Put bank/pads first, keep schematic available in a compact preview disclosure; no preview feature removed. |
| P2 | Stems begins with machine/cache controls and import/listening arrive far below: index.html:267, :326, :339. | Start with library/playlist/output and primary action; use in-screen Preparation and Import & Listen views, retaining runtime/cache controls in an explicit group. |
| P2 | No theme override: app.css:45; Settings has language/About only, index.html:342. | System/Light/Dark, with deliberate light and dark semantic palettes. |
| P2 | Many values bypass tokens: app.css:40, :435, :506, :658; inline margins throughout index.html and samples.js. Font stack differs from brief and paths use a separate monospace stack at app.css:240. | One tokens region; exact requested system stack for all UI; all component dimensions/colors/motion reference tokens. |
| P2 | Swatch targets are 26x26 and color input is 26 px high: app.css:435, :445. Other native controls need computed hit-area review. | Minimum 28x28, normal row/button target 32 px or larger; do not confuse 20 px switch graphic with its larger label hit area. |
| P2 | Navigation declares tablist but lacks vertical orientation: index.html:13; keyboard code is vertical at app.js:590. Pads put aria-selected on plain buttons at samples.js:107. | Complete vertical tab semantics; selected pad radio semantics in edit mode, ordinary pressed controls in simulation, no unsupported ARIA attributes. |
| P2 | Samples focused Hold pad in simulation has pointer listeners but no Space/Enter hold handlers: samples.js:109; click intentionally does nothing for Hold at :117. Numeric shortcuts do work at :574. | Preserve numeric shortcuts; implement Space/Enter down/up on focused pad and release on blur. |
| P2 | Listen canvas/seek accessible labels are created once at stems-listen.js:133 and :142; language listener calls draw() at :173 without updating those labels. | Reapply translated accessible names during locale changes. |
| P2 | App-wide failures replace one another, and most reads lack an inline pending/retry state: app.js:76, :181; stems.js:194. | Keep persistent errors beside the affected group; global toast for supplemental notification, result summaries remain readable. |
| P2 | Job cancel is shown for every running job: app.js:540; runtime installation does not register a cancellation watcher at bridge.py:813. | Preserve backend behavior; verify cancel response and explain whether cancellation was accepted. Do not promise immediate interruption or add backend cancellation. |
| P2 | Text/path overflow remains a risk: nonwrapping .spread at app.css:178, max-content dl at :267, four-column import slot at :702; no render matrix was run. | minmax(0,1fr), wrapping labels, stacked slot controls at narrow widths, full-path accessible disclosure; test FR longest strings. |
| P3 | All cards receive shadow and large radii, app.css:158; selected modules are tinted tiles at :628. | Flat inset groups, separators, smaller control radii, restrained selection. This is a design judgment from CSS, not a measured usability result. |
| P3 | Motion includes 50 ms button transform, app.css:194, and untokenized sweep at :314. Reduced-motion handling already exists at :368. | 160/200/240 ms state changes; static indeterminate treatment under reduced motion. |

Strengths to retain: centralized bridge access, server-owned limits and dependencies, semantic structured localization, native file pickers, existing keyboard navigation and logo panning, local fast logo feedback with stale-result protection, library guard, recoverable separation jobs, explicit sample-save model, and deliberately schematic hardware preview.

The README's advanced runtime uninstall/model-browser and long-run confirmation claims are not controls in the current frontend (README.md:178 and :194; stems.js:370). They are documentation/UI discrepancies, not features silently removed by this proposal. Adding those missing behaviors is outside this redesign. The existing external harmonic-mixing guide link remains explicit user navigation; no automatic network requests are added to the page. Existing Python key/runtime/model downloads remain unchanged.

## Information architecture and navigation

Keep this order: Drive / Modules / Samples / Logo / Stems / Settings. French labels: Cle USB / Modules / Samples / Logo / Stems / Reglages, with correct accents in the actual catalogs. No merged screens. The sidebar shows the chosen drive context and active job status concisely. Settings stays at the bottom. Original inline SVG icons use currentColor and a consistent 16 px line vocabulary; no downloaded fonts, raster assets, manufacturer graphics or SF Symbols package.

The native shell continues to own window chrome. Inside it: sidebar, screen toolbar, scrollable content, reserved job region. Primary task actions are persistent. Secondary commands remain labeled and discoverable. View state and draft data persist across screen switches; preserve current business defaults, firmware reset behavior, serialization and Python decisions. Restoring per-screen scroll is a proposed navigation improvement.

| Screen | Primary action | Secondary groups retained |
| --- | --- | --- |
| Drive | Choose/change drive | Refresh, report, explicit Remove mod action |
| Modules | Build | Firmware, output, all module settings, key actions and consent |
| Samples | Save bank | Bank selector/new/delete, activate, edit/simulate, Stop all, all pad/bank controls |
| Logo | Choose/change image | Framing, preview theme, invert grays, enable module, link to Modules; no invented Save button |
| Stems | Prepare; Import when Import & Listen is selected | Runtime/accelerator/cache, library/playlist/roles/quality/output, per-track import, audition |
| Settings | Direct setting selection, no artificial Save | Language, System/Light/Dark, About |

One primary means one emphasized task action where the screen has a task to commit. Settings changes apply immediately. An unmet prerequisite occupies an inline state with the action that resolves it, rather than a disabled primary button plus an unrelated explanation far away.

## Per-screen wireframes

These show hierarchy, not final pixel-perfect rendering. Text is abbreviated only in the diagrams; production labels must not be clipped. The sidebar is common to all six screens.

```text
+------------------+--------------------------------------------------+
| XDJ-RX3 Toolkit  | Drive                     [Choose / Change drive] |
|                  +--------------------------------------------------+
| Drive            | Selected drive name                              |
| Modules          | Full path available                              |
| Samples          | +----------------------------------------------+ |
| Logo             | | Mod status                 Firmware / status | |
| Stems            | | Modules                    Names             | |
|                  | | Last run / refused         Details           | |
|                  | | Music                      Tracks/playlists  | |
|                  | | Sample banks               Active bank       | |
|                  | +----------------------------------------------+ |
|                  | [Refresh]              [Remove mod...]           |
| Settings         | Inline warning / result / actionable empty state |
+------------------+--------------------------------------------------+
|                  | Job: task / progress / stage       [Cancel]      |
+------------------+--------------------------------------------------+

+------------------+--------------------------------------------------+
| Sidebar          | Modules                                  [Build] |
|                  +--------------------------------------------------+
|                  | Firmware [1.xx | 1.yy]    Output [Choose...]      |
|                  | Key: absent/selected/retained [Fetch] [Browse]    |
|                  |                              [Forget...]         |
|                  | +---------------------------+------------------+ |
|                  | | Performance               | Build summary    | |
|                  | | Name / explanation [on]   | Selected names   | |
|                  | |   KEY SYNC range / mode   | Dependencies     | |
|                  | |   Key-match rules / guide | Prerequisite     | |
|                  | | Stems                     | Result path      | |
|                  | | Screen / browse column    |                  | |
|                  | | Streaming                 |                  | |
|                  | | > Diagnostics             |                  | |
|                  | +---------------------------+------------------+ |
+------------------+--------------------------------------------------+

+------------------+--------------------------------------------------+
| Sidebar          | Samples                              [Save bank] |
|                  +--------------------------------------------------+
|                  | Bank [selector] [New] [Delete...]  Active/Draft   |
|                  | Name [...........]                 [Activate]    |
|                  | [Edit | Simulate]                     [Stop all] |
|                  | +----------------------+-----------------------+ |
|                  | | [1] [2] [3] [4]      | Pad / Add-change sound| |
|                  | | [5] [6] [7] [8]      | Name / color          | |
|                  | | Memory usage / limit | Once/Hold/Loop/Latch  | |
|                  | | Volume [-----]       | Start / duration      | |
|                  | | Shift silence [on]   | Audition / gain/reset | |
|                  | | Capability status    | Clear pad             | |
|                  | +----------------------+-----------------------+ |
|                  | > Schematic preview and on-deck instructions     |
+------------------+--------------------------------------------------+

+------------------+--------------------------------------------------+
| Sidebar          | Logo                     [Choose / Change image] |
|                  +--------------------------------------------------+
|                  | +----------------------------+-----------------+ |
|                  | |                            | Canvas choice   | |
|                  | | Schematic deck preview     | Fit / Fill      | |
|                  | | Drag / keyboard framing    | Zoom [------]   | |
|                  | |                            | [Recenter]      | |
|                  | |                            | Deck light/dark | |
|                  | +----------------------------+-----------------+ |
|                  | Invert grays [on] / availability explanation     |
|                  | Dimensions / rendering status / faint warning    |
|                  | Included in build / [Enable logo module]         |
|                  | Build includes this framing       [Go to Modules]|
+------------------+--------------------------------------------------+

+------------------+--------------------------------------------------+
| Sidebar          | Stems                         [Prepare / Import] |
|                  +--------------------------------------------------+
|                  | Library [USB drive] [XML]   path / counts         |
|                  | Playlist [..............]  Output [Choose...]     |
|                  | Busy library -> Close Rekordbox [Check again]    |
|                  | [Preparation | Import & Listen]                  |
|                  | Preparation:                                     |
|                  |   Quality [High | Normal | Fast] + actual summary|
|                  |   Vocals required / Drums [ ] / Bass [ ]          |
|                  |   Duration / size estimate; per-track details    |
|                  | Import & Listen:                                 |
|                  |   Track [.............]                          |
|                  |   Vocals / Drums / Bass [Choose] [Clear]          |
|                  |   Import report; source and component buttons    |
|                  |   Waveform / seek / [Play] [Refresh]              |
|                  | > Runtime, accelerator, Install/reinstall, cache |
+------------------+--------------------------------------------------+

+------------------+--------------------------------------------------+
| Sidebar          | Settings                                         |
|                  +--------------------------------------------------+
|                  | Appearance                                       |
|                  | +----------------------------------------------+ |
|                  | | Theme              [System | Light | Dark]   | |
|                  | +----------------------------------------------+ |
|                  | Language                                         |
|                  | +----------------------------------------------+ |
|                  | | Language           [English | Francais]      | |
|                  | +----------------------------------------------+ |
|                  | About                                            |
|                  | Existing product description                     |
|                  | Settings apply immediately                       |
+------------------+--------------------------------------------------+
```

At 880x560, sidebar becomes 180 px and content insets 16 px, leaving approximately 668 px before a vertical scrollbar. Toolbar can wrap into two rows; no icon-only collapse. Modules configuration precedes the list and the Build action stays in the toolbar. Samples uses one column: bank controls, grid, selected-pad inspector, remaining bank settings and preview. Logo uses preview then framing. Stems slot buttons wrap below their path. At wider sizes, Samples/Logo gain side-by-side inspectors and Modules gains its summary column. At 1440x900, content is capped and aligned, not stretched into oversized fields. All column transitions depend on available content width, tested with French labels.

The job region reserves its own layout row instead of covering controls. At short heights it shows task, percent and Cancel on one line with expandable details. Error/results wrap without introducing horizontal scroll. Full user paths remain accessible without relying solely on a hover title.

## State designs

| Screen | Empty / prerequisite | Loading | Progress | Error | Success |
| --- | --- | --- | --- | --- | --- |
| Drive | Select a USB drive + picker | Named reading state in report group | Removal pending state; no invented percentage | Inline failure + choose/refresh; read-only warning | Fresh report; removal result persists near action |
| Modules | No selection / missing key / output + relevant action | Firmware/module list busy; keep focus | Shared job with build context and cancellation response | Local build/key error, retained selection, retry action | Output path/size and refreshed report |
| Samples | No drive -> choose; empty bank/pad -> add sound | Bank read / analysis / audio loading near affected element | Save job; bank actions protected against duplicate submit | Failed save/import/audition with draft retained; dirty-discard sheet | Saved versus active remain distinct visible states |
| Logo | Choose image | Opening/rendering indicator, stable preview area | Exact-render pending, no fabricated percentage | Image/render failure with Change image or retry | Artwork ready/included, dimensions; no false claim of drive write |
| Stems | Missing runtime/library/output/track with Install/Open/Choose action | Runtime check/library parse/estimate/audition state | Current backend job kind, track, stage, percent and cancel response | Inline library guard/import report/job failures, retry path | Batch result/errors/notices or import report; audition available |
| Settings | No empty data state required; valid defaults | Initial catalog load shared with app | Immediate local changes; no fake job | Shared catalog failure with retry; storage-unavailable note if persistence fails | Current theme/language shown and announced |

Global startup distinguishes connecting, ready and unavailable. Do not infer backend readiness from a timer. Job states remain exactly idle/running/done/cancelled/failed; keep polling, never add push transport. Inactive screen navigation remains available while a job runs. Prevent duplicate starts without changing what Python accepts, and only show completion after backend confirmation. An error must not destroy the user's draft.

The startup terms prompt is retained to respect existing product behavior. Within Modules the same terms dialog remains reachable from Fetch and from Build when the key is absent. Text, scrolling gate, explicit checkbox and server-side acceptance stay intact.

## Proposed token set

One contiguous design-token region at the top of app.css contains base values, light and dark palettes, explicit theme overrides, automatic system-theme rules and responsive token overrides. Components below it contain no raw color, spacing, radius, shadow, type or duration values. Runtime quantities such as progress percentage, pad color, artwork dimensions and waveform peaks are data, not new design constants.

| Token family | Proposed values / semantics |
| --- | --- |
| Font | `--font-ui: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable", "Segoe UI", system-ui`; use it throughout, including paths and canvas text; no font files |
| Type | caption 12 px; body/control 13 px; body-prominent 14 px; section 16 px; title 22 px; weights 400/500/600; line-height compact 1.25, body 1.45, prose 1.5; tabular numbers |
| Space | `--space-0` 0; 1/2/3/4/5/6/8/10/12 correspond to 4/8/12/16/20/24/32/40/48 px |
| Geometry | sidebar 208 px, compact 180 px; toolbar min 56 px; controls min 32 px; absolute hit minimum 28 px; grouped row min 44 px; inspector 288 px; content max 1120 px; compact/full insets 16/24 px |
| Radii | small 4 px, control 6 px, group 10 px, dialog 12 px, pill 999 px; pills only for compact status, not every button |
| Borders/focus | border 1 px; focus 2 px + 2 px offset; selected state includes shape/checkmark/text, not color alone |
| Motion | fast 160 ms, normal 200 ms, sheet 240 ms; ease-out `cubic-bezier(.2,.8,.2,1)`; reduced motion sets motion tokens to zero and replaces moving indeterminate stripe with static status |
| Materials | opaque canvas, sidebar and inset surface; optional translucent toolbar only with solid fallback; no native-vibrancy claim |
| Shadows | controls none or restrained 0 1px 2px; dialog 0 12px 36px; all compound shadow values defined as tokens |

| Semantic color | Light | Dark |
| --- | --- | --- |
| canvas | #F5F5F7 | #1C1C1E |
| sidebar | #ECECEF | #242426 |
| inset surface | #FFFFFF | #2C2C2E |
| raised surface | #FFFFFF | #363638 |
| text | #1D1D1F | #F5F5F7 |
| secondary text | #5C5C63 | #B8B8BE |
| separator | #D2D2D7 | #49494F |
| control edge | #85858C | #898990 |
| accent / primary fill | #005FCC | #0A64D8 |
| accent text / focus | #005FCC | #80B5FF |
| on-accent text | #FFFFFF | #FFFFFF |
| selection fill | #E6EFFC | #243A58 |
| success text | #24663B | #8BD9A0 |
| warning text | #805500 | #F5C16C |
| destructive text | #B42318 | #FFAAA3 |
| destructive fill / text | #B42318 / #FFFFFF | #A9231B / #FFFFFF |

Status surface, hover, active, disabled, focus-gap, scrim, toolbar-material and preview palette tokens complete these semantic roles in implementation. Exact token proposals must be checked against every actual surface pairing, including hover, disabled explanatory text and focus boundaries; this audit is not an AA certification. Do not derive dark colors through inversion. User-selected pad colors never determine body-text contrast; keep labels on a neutral surface and use color as an accessory. The schematic gets separate preview tokens for its independent light/dark setting. Canvas renderers read resolved CSS properties; backend artwork pixels and signal data remain untouched.

## Component contract

| Component | Required behavior |
| --- | --- |
| Sidebar item | SVG + label + optional status; vertical tablist, orientation, roving focus, Up/Down/Home/End; all six screens visible |
| Toolbar | Named heading, one primary task action, labeled secondary commands; wraps before clipping; persists while content scrolls |
| Grouped list row | Label, value/control, supporting text; separator, wrapping, accessible description; nested settings outside switch label |
| Toggle | Native checkbox with switch semantics, visible label, 28 px minimum label hit region, focus and disabled reason |
| Segmented control | Named single-choice group with radio keyboard behavior; selection distinct from action buttons; multi-select listening components stay pressed buttons |
| Buttons | Primary, secondary, quiet, destructive; pending/disabled; stable labels; minimum target; no duplicate submit |
| Progress | Named progressbar, current value only when known; bounded status announcements; cancel request and terminal response distinct |
| Sheet/dialog | HTML dialog styled as a document-modal surface; title, consequence, cancel/confirm; focus contained and restored, Escape cancels; destructive default focus on Cancel |
| Toast | Nonmodal status or alert; dismissible; supplemental, never sole durable record of failure or completed work |
| Empty state | Short specific explanation with direct remedy; errors and missing prerequisites do not masquerade as empty content |
| Pad cell | Empty/filled/selected/playing states; neutral readable label, actual color accent, index, mode, duration; keyboard edit selection and simulation trigger/release |
| Inspector/form field | Explicit label, control and help association, grouped choices, validation close to field; stable focus after updates |
| Disclosure | Visible descriptive summary and status; details remain keyboard reachable; use for diagram, diagnostics and advanced runtime controls |
| Listening transport | Accessible seek slider, play/stop, source and component choices, track position; translated labels refresh with locale |
| Inline state | Loading/prerequisite/error/success within affected group; retains content and offers appropriate recovery |

The dialog interaction follows W3C APG: focus stays inside, Escape closes, focus returns to the invoking control, and least-destructive initial focus is appropriate for irreversible actions. [W3C modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).

Apple's sidebar and toolbar guidance anchors the navigation/action distinction; the specific dimensions and composition above are proposed application choices, not quoted Apple requirements. [Apple Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars), [Apple Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars), [Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/). The direct documentation pages require JavaScript in the research reader; official indexed extracts were available. No assets or dependencies were downloaded for the app.

## Proposed PRODUCT.md content (not written)

```markdown
# Product

XDJ-RX3 Toolkit is a desktop preparation tool for DJs and operators who manage RX3 drive modifications, sample banks, logo artwork and stems on macOS and Windows.

Mode: Operate. Success means the operator understands the selected drive and output, can complete each preparation task, can see progress and recover from failure, and retains access to every existing operation.

The six destinations are Drive, Modules, Samples, Logo, Stems and Settings. The local vanilla-JavaScript page runs inside pywebview without a build step or a network dependency. Python is the authority for capabilities, limits, dependencies, validation and long-running work. Jobs are polled.

The UI is bilingual EN/FR. French uses professional vouvoiement and the project glossary. Hardware labels and legal meaning are preserved. Artwork previews are schematic, never firmware screenshots or claims of hardware validation.

Product behavior, audio behavior, bridge arguments/results and service implementation are outside the UI redesign. Minimum window is 880x560; default is 1180x820. Approval is required before implementation, dependency changes, feature removal, out-of-scope writes or commits.
```

## Proposed DESIGN.md content (not written)

```markdown
# Design

Pinned direction: Apple HIG with native macOS conventions, interpreted within the existing cross-platform webview. Mode: Operate. Calm hierarchy, compact controls, stable navigation, readable state and one emphasized task action per screen.

Use a persistent labeled sidebar, a screen toolbar, flat inset groups, separators and focused inspectors. Keep all six screens and every existing control. At compact widths, stack inspectors and summaries without hiding primary actions or introducing horizontal scroll.

Use only the specified system font stack. Draw original line icons with inline SVG or CSS. No raster assets, bundled Apple fonts, CDN, framework or build tooling.

Keep all design tokens in one top-of-file CSS region. Use separate semantic light/dark palettes, System/Light/Dark override, blue accent and restrained success/warning/destructive roles. Preview theme is independent of application theme. Runtime pad colors and artwork are content.

Use 4 px spacing increments, 32 px normal control targets, 28 px absolute minimum targets, deliberate focus rings and 160-240 ms state-change motion. Respect reduced motion. No decorative animation.

Every applicable asynchronous task has empty/prerequisite, loading, progress, error and success states. Destructive actions use a named modal confirmation. Legal acquisition retains scrolling and explicit consent. Preserve keyboard navigation, editing focus, accessible names, drafts and all Python contracts.

Validate both languages and themes at 880x560 and 1440x900 in the actual app. Run one finish review, fix its findings, and stop after a bounded confirmation. Record untested environments and unresolved issues without claiming certification.
```

## Phase 2 plan and acceptance evidence

After explicit approval: read the craft floor; implement tokens and shared components, then Drive, Modules, Samples, Logo, Stems, Settings in that order. Do not touch Python or services. Emit `done, [screen], [files changed], [checks run]` after each screen. Add one Unreleased changelog entry for the finished visible change.

Suggested frontend boundaries: retain i18n.js, samples.js, logo.js, stems.js, stems-listen.js and rx3-mock.js responsibilities. A plain components.js may own UI-only dialogs, focus restoration, status, theme and reusable controls; no framework or dependency. Keep all existing argument positions, payloads, return handling, audio calculations, and bridge-driven limits. Do not rewrite DSP behavior under the name of UI cleanup.

Required regression gate is the inventory mapping: every reachable operation listed in inventory.json must have a new control/flow and recorded verification. Particularly pin mod_build's nine positional arguments, samples_save options and pad shape, logo rendering/build framing, both stems_choose null-position forms, all stems_cache forms, import assignment read/write/clear, audition mask/ramp/30-second arguments, consent and cancellation. No existing operation can disappear behind a redesigned screen.

Run the requested checks, retaining exact exit/output evidence:

```sh
make test preflight PYTHON=.venv/bin/python
.venv/bin/python app/ui/shell.py --self-test
.venv/bin/python -m unittest tests.test_localization
make app PYTHON=.venv/bin/python
```

Then one finish review covering six screens x two sizes x two themes x two languages (48 screen configurations), plus key modal/dialog states, keyboard-only operation, focus restoration, long paths, long French strings and empty/error/job states. Group the checks into one review pass; fix collected defects as one batch, with only bounded confirmation afterward. Do not loop on cosmetic refinements. Use actual app screenshots/interaction for available flows; if controlled bridge fixtures are used for destructive or unavailable states, label them as fixtures and keep them unreachable in production. No real key or destructive drive operation is needed to validate the design; hardware/media write acceptance is reported separately if not exercised.

The app must retain its existing backend acquisition/install operations, while the frontend itself loads only local scripts/styles/resources. No new requests, fonts, CDN or runtime dependencies. Verify local file loading rather than treating a localhost browser run as packaged-app proof.

Baseline in this Phase 1: localization `Ran 5 tests ... OK`; shell `self-test ok: 42 operations`. Full make test/preflight, app launch, 48 visual configurations, Windows, screen-reader runs, contrast measurements and all real job paths have not been run. They remain acceptance work, not implied successes.

## Approval boundary

Approve this direction and the proposed navigation/UI safeguards before Phase 2. No screen, feature or control is proposed for deletion. PRODUCT.md and DESIGN.md remain proposed content; writing them at the repository root needs explicit approval in addition to ordinary in-scope UI implementation. No commit or push is requested or planned.
