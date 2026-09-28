<!-- SPDX-License-Identifier: MPL-2.0 -->
# Interface implementation and acceptance

The approved Phase 2 redesign is implemented. All six destinations and all 41 previously reachable Python operations remain available. No commit or push was made. The existing dirty working tree was retained.

## Changed files

| Files | Change |
| --- | --- |
| PRODUCT.md, DESIGN.md | Approved product and design direction, created at the repository root |
| app/ui/web/app.css | One token region, deliberate light/dark palettes, compact sidebar/toolbars, grouped forms, responsive inspectors and accessible controls |
| app/ui/web/components.js | Presentation-only theme, focus, dialog and inline-state helpers; no dependency |
| app/ui/web/index.html | Six restructured screens, persistent primary actions, independent scrolling, job region, confirmations, appearance settings |
| app/ui/web/app.js | Transport recovery, inline status, scroll/focus continuity, modal deletion, progress semantics and consent-preserving startup |
| app/ui/web/samples.js | Pad keyboard access and labels, focus continuity, draft protection, save/delete feedback; audio math and payload unchanged |
| app/ui/web/logo.js | Tokenized guide colors, rendering status, keyboard focus after enabling module; placement math unchanged |
| app/ui/web/rx3-mock.js | Theme colors/system font from tokens; same schematic and artwork geometry |
| app/ui/web/stems.js | Preparation and Import & listen within one screen; runtime/cache disclosure, accessible role choices and explicit cache confirmation |
| app/ui/web/stems-listen.js | Translated accessible names update with language; theme-aware waveform; audio/ramp scheduling unchanged |
| app/localization/en.json, fr.json | 473 keys each, paired placeholders, concise new copy; all 11 terms entries unchanged |
| CHANGELOG.md | One added Unreleased entry |
| app/ui/web/design-audit/ | Audit, inventories, isolated native verification harness and results; none loaded by index.html |

No service, runtime, firmware, stems engine, sample engine, logo engine, session, preview engine, on-device module, packaging file, Makefile, bridge.py or shell.py was edited for this redesign. i18n.js is unchanged. The baseline SHA-256 of bridge.py still matches.

## Design decisions

- Keep the six destinations: preserve learned navigation and feature reachability.
- Reserve a toolbar per screen: primary actions stay reachable while content scrolls.
- Use inset groups and separators: reduce competing tile decoration without hiding module explanations.
- Put bank identity above pads and playback settings beside them: reduce the minimum-window distance to actual editing.
- Separate Preparation and Import & listen inside Stems: both workflows retain their controls and share source/output context.
- Keep preview appearance independent: changing the application theme cannot change exported artwork settings.
- Apply settings immediately: avoid a Save action with no underlying transaction.
- Confirm destructive actions in a dialog: expose the target and consequence before issuing the same bridge call.
- Preserve polling and serialized arguments: presentation changes do not move engine logic into JavaScript.

## Verification

```text
make test preflight PYTHON=.venv/bin/python
Ran 211 tests
OK (skipped=1)
Publication preflight: OK

.venv/bin/python app/ui/shell.py --self-test
self-test ok: 42 operations

.venv/bin/python -m unittest tests.test_localization
Ran 5 tests
OK

impeccable detect --json app/ui/web/index.html
[]
```

The full test run includes the unchanged sample/stem audio preview tests. Their first run exposed isolated-harness compatibility problems in the UI rewrite; these were fixed in the permitted frontend files, without altering the tests. The final run is green.

`make app PYTHON=.venv/bin/python` was executed. The sandbox initially refused pywebview's normal profile directory; the approved unsandboxed launch succeeded. The actual native file-page window and its legal dialog were inspected through computer-use tools. The legal dialog was cancelled; no key acquisition occurred.

The independent native pywebview fixture loads the actual production `index.html`, CSS and scripts from `file://`. It uses safe real module/geometry/localization metadata and explicit synthetic replies for all media, key, drive, job and download operations. It is never imported by the application. Re-run it with `.venv/bin/python app/ui/web/design-audit/verify_ui.py`; it leaves a clearly titled synthetic-data window open for inspection.

[verification.json](verification.json) records all 56 render configurations: the 48 requested combinations (six screens, EN/FR, light/dark, window 880x560 and 1440x900), plus eight Import & listen configurations. Native title bars leave client areas of 880x528 and 1440x868; tests record both requested window size and actual client size.

Final matrix findings: zero horizontal overflow, zero measured control-text overflow, zero enabled hit targets below 28 px, zero visible unlabeled form controls and zero unresolved UI keys in the fixture content. Long French explanations and long synthetic paths are included. The final 30 designed text/surface contrast pairs all exceed 4.5:1; minimum measured ratio is 5.487:1. Twenty-six behavioral checks pass, including focus retention, cancel-first destructive dialogs, no calls before consent/confirmation, draft preservation, inline recovery, progress semantics and build/save/import argument shapes. No uncaught browser errors were recorded.

One finish review found native WebKit select controls constrained to 21 px and an over-tall bank header. They were corrected together with compact spacing, and one bounded native confirmation pass completed successfully. Screenshots were visually inspected through the native app tool; no raster assets were added to the app.

## Operation mapping

The table covers every operation the old UI reached. Each row has old and new source locations in [operation-parity.json](operation-parity.json). This is a reachability inventory; it does not claim every operation was executed against real services or hardware. `reveal` was exposed but unused before and remains outside the 41-operation parity count.

| Bridge operation | Retained destination / control |
| --- | --- |
| `localization_catalogs` | Shared startup |
| `localization_language` | Settings > Language |
| `job_status` | Shared job region; existing polling |
| `job_cancel` | Shared job region > Cancel |
| `pick_folder` | Drive / Modules output / Stems library and output |
| `pick_file` | Modules key / Logo image / Stems XML |
| `pick_files` | Samples sounds / Stems role assignment |
| `drive_report` | Drive > Choose or Refresh |
| `mod_modules` | Modules > Grouped module rows |
| `mod_firmwares` | Modules > Firmware |
| `mod_key_hint` | Modules > Key status |
| `mod_key_fetch` | Terms > Scroll > Explicit consent > Download |
| `mod_key_forget` | Modules > Forget > Confirm |
| `mod_selection` | Module switches / Logo > Enable module |
| `mod_remove` | Drive > Remove > Confirm |
| `mod_build` | Modules toolbar > Build |
| `samples_defaults` | Samples bootstrap |
| `samples_read` | Samples > Bank selector and refresh after save |
| `samples_save` | Samples toolbar > Save |
| `samples_analyse` | Samples > Add/change sound |
| `samples_audition` | Samples > Audition or simulate pads |
| `samples_activate` | Samples > Activate |
| `samples_remove` | Samples > Delete bank > Confirm |
| `logo_canvases` | Logo > Canvas choice |
| `logo_limits` | Logo bootstrap / Zoom |
| `logo_open` | Logo toolbar > Choose/change image or restored artwork |
| `logo_render` | Logo > Framing, zoom and invert setting |
| `stems_tracks` | Stems > Import & listen > Track |
| `stems_import_assign` | Stems > Import & listen > Role choose/change/clear |
| `stems_audition` | Stems > Listen > Drive source / seek / components |
| `stems_import_audition` | Stems > Listen > Imported source / seek / components |
| `stems_import_start` | Stems > Import & listen toolbar > Import |
| `stems_cache` | Stems > Engine and cache > Limit or Clear |
| `stems_library_status` | Stems > Library guard and Recheck |
| `stems_runtime` | Stems > Engine and cache |
| `stems_library` | Stems > USB drive or XML |
| `stems_qualities` | Stems > Preparation > Quality |
| `stems_choose` | Stems quality and accelerator choices |
| `stems_forecast` | Stems > Playlist and role estimate |
| `stems_install` | Stems > Engine > Install/reinstall |
| `stems_start` | Stems > Preparation toolbar > Prepare |

## Known limits

- Native rendering was verified on macOS/WebKit. Windows/WebView2 was not available and is not claimed as validated.
- The 56-configuration matrix measures native rendered DOM and control geometry; screenshots were inspected for representative screens, not archived individually for all configurations.
- The fixture validates frontend interaction and contracts, not firmware, real USB writes, encryption-key acquisition, dependency installation, separation quality or hardware playback. No such operations were performed on user data.
- Screen-reader output and arbitrary user-supplied artwork/pad colors were not exhaustively audited. Contrast measurements cover the UI's specified text/surface pairs, not an accessibility certification.
- Existing backend runtime-install cancellation capability is unchanged. The UI reports whether a cancellation request was accepted instead of claiming instant cancellation.
- Startup terms behavior is retained. This redesign does not supply missing uninstall/model-browser features described by older README text.

No additional design iteration or commit is planned.
