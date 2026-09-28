<!-- SPDX-License-Identifier: MPL-2.0 -->
# ADR-0001: Restructure the desktop application in place behind a verified application boundary

**Status:** Proposed, amended after independent review; not approved for implementation
**Date:** 2026-09-27
**Deciders:** François Brille
**Scope:** Desktop application, its public operations, workers and packaging. No redesign of the C runtime and no change to on-drive formats.

## Context

The desktop application is about 12,500 Python lines under `app/`, including a 1,169-line bridge exposing 57 public operations. It uses pywebview, Python services and engines, separately provisioned inference dependencies, and PyInstaller. At review time HEAD was `256596cbdb8b2fb59a1a52c342fa9de51918c4a8`, but extensive staged, unstaged and untracked changes mean HEAD alone does not identify the reviewed code. Capture the working-tree baseline before implementation.

The bridge contains application policy, engine calls, serialization and task scheduling. Four cancellation exception classes coexist. The stems import graph contains cycles across audition, importing, package, waveform and cache. The page loads nine global scripts. These are structural problems; changing the implementation language or the window shell does not resolve them by itself.

Existing tests remain useful but are not a complete behavioral oracle. At review time the suite ran 329 tests with one failure and two skips. The failure is `test_ui_setting_events_and_persistence`, in `tests/key_sync_settings.cjs`, reading `hidden` from an undefined element. The source self-test passes with 57 operations. Neither result validates the packaged UI, all supported operating systems, inference accelerators or playback on the RX3. The stems tests pin implementation internals with more than 50 `patch.object` calls (54 in `test_stems*.py` alone), which is a review signal, not a reason to delete them.

The existing exclusive task slot is valuable but narrower than first claimed. It is local to a Bridge instance. `mod_remove` (bridge.py:505), `samples_activate` (bridge.py:723) and `samples_remove` (bridge.py:728) reach mutating services while that slot is occupied, `drive_report` writes a probe file on the drive (services/drive.py:79), and `runtime/cli.py` invokes the build engine directly. Preserving `_claim` alone does not establish exclusion across all writers or application processes.

The desktop produces data consumed by the deck even when the C sources are unchanged. File structure, PCM properties, manifests, waveform interpretation and settings compatibility remain acceptance requirements. Local fixtures, real exports, packaged desktop workflows and hardware playback establish different parts of that evidence.

## Decision

Retain Python, pywebview and PyInstaller for this restructuring. Introduce a typed, explicit application boundary and migrate one feature at a time. Keep existing behavior unless a defect and its intended correction are explicitly recorded. Reconsider the shell in a separate ADR only after a representative prototype demonstrates a useful improvement.

Do not combine code relocation with automatic relocation of installed data. First centralize path resolution while retaining existing physical locations. A physical data migration requires its own recovery and compatibility design.

The intended layout is:

```text
contract/              standard request/result schemas and operation metadata
app/
  platform/            paths, packaged resources, cancellation, owned processes,
                       tool discovery, diagnostic logging and process locks
  jobs/                exclusive task runner, identity, state and progress
  services/            application use cases and shared GUI/CLI entry points
  stems/               engines and formats, with an acyclic dependency graph
  samples/ ...         other engines and formats
  localization/        Message, LocalizedError and catalogs
  ui/
    shell.py           window creation and lifecycle binding
    host.py            native dialogs and file-manager actions, if extraction helps
    bridge.py          explicit dispatch, request validation and one serialization point
    web/               modular source, one folder per screen, shared client
```

`platform` names OS-facing facilities explicitly and distinguishes them from the embedded `mod/modules/core`. It must not become a catch-all business layer. No dependency injection container, CQRS or generic plugin system is introduced. Explicit arguments or small protocols at filesystem, process and inference boundaries are allowed where they make behavior testable.

### Application boundary and contracts

- Use an explicit operation registry. Adding a public Python helper must not expose a new operation automatically. Separate application operations from host actions such as file selection and Reveal.
- Keep one authoritative contract definition. Prefer standard JSON Schema for transport requests and results, validated through an established Python validator and used to generate JS type declarations and a typed client. Validate this choice on two representative operations before applying it to all 57; do not build a custom schema language or general code generator.
- Pass one named request object through pywebview rather than long positional argument lists. Temporary adapters preserve existing callers while each feature migrates; remove them when its callers and tests have migrated.
- Define nullability, defaults, numeric bounds, allowed enum values, unknown-field behavior and stable error codes. Structural validation does not replace filesystem checks or application invariants in services. CLI callers must enforce the same invariants.
- Use a consistent success/error envelope. Keep `Message` and `LocalizedError` machine-readable until the existing localization serialization boundary. Unexpected errors return a neutral localized message and a diagnostic identifier; sanitized stack traces remain in local logs, never in the page.
- Results are typed per operation, including task results discriminated by operation. A common envelope must not flatten build results, sample exports and per-track stems outcomes into an untyped dictionary.
- Generate and actually check the frontend client types, for example with checked JavaScript and `tsc --noEmit`. Type declaration generation alone proves nothing about callers. CI verifies generated files are current and checks representative serialized responses against the schemas.
- Fixtures, defaults and UI mocks derive from, or are checked against, the same contract definitions, so a drifting mock fails in CI instead of hiding a mismatch.
- Backend validation stays authoritative. The UI may use the same constraints for immediate feedback; removing all frontend validation is not a goal.

### Tasks, exclusion and cancellation

- Preserve one exclusive long-running task at a time. This restructuring introduces no queue, resume framework or concurrent preparation feature.
- Centralize all operations that can conflict with publication, including synchronous removal and activation. Admission and mutation must share a guard; checking an idle flag before a separate write is insufficient. Classify operations by actual side effects, since even `drive_report` writes a probe file.
- Add a shared interprocess exclusion mechanism for mutating GUI and CLI entry points, or explicitly enforce a single writer process. Internal service composition must not reacquire the guard recursively. Document the scope and its limits concerning external programs.
- Extract the generic cancellation primitive and owned-process control from `stems` to a neutral package. `jobs` must not depend on the stems engine. One cancellation exception and token do not imply that every operation owns subprocesses.
- Give each task a stable identity. Scope status, cancellation and progress updates to that identity so a delayed update cannot modify the next task.
- Specify transitions from running to cancelling and a terminal state. Cancellation is a request, not evidence of termination. Release the task slot only after workers, process trees and file handles are cleaned up, including on launch failure and window closure.
- Define progress as a localized stage, a fraction in `[0, 1]` or `null`, and typed detail. Distinguish per-stage from overall progress. Convert existing percentage callbacks through explicit adapters and permit returning to indeterminate progress.
- Preserve commit boundaries. Do not insert cancellation checkpoints into a publication sequence where interruption would make its reported outcome false. Per-track results must identify already committed outputs and remaining failures after cancellation or partial success.
- Scheduling threads belong to the task runner. Service use cases stay callable synchronously for tests and CLI execution; engine-managed worker pools and preview-server lifecycles remain explicitly owned resources.

### Stems dependency structure and tests

Separate low-level format readers and writers and shared audio primitives from orchestration. Readers must not import publication workflows, waveform generation or audition orchestration. Move multi-engine workflows into application services or clearly identified orchestration modules. Preserve the persistent inference worker, its framed protocol, model reuse and disposal after failure.

Add behavioral characterization before moving each responsibility. Keep the precise low-level tests for PCM, binary formats, hashes, cache provenance, timing, frame counts and publication failures. Replace implementation-coupled mocks only when equivalent observable behavior is covered. Do not rewrite the implementation and its expected test output together merely to restore a green suite, because that can erase regressions from the assertions.

Use deterministic byte comparisons where output is deterministic; normalize documented volatile metadata before comparisons elsewhere. Real inference comparisons need recorded model hashes, package versions, accelerator and appropriate numerical tolerances. Successful mocked service calls are not proof of inference or audio parity.

### Paths and installed data

Centralize path and resource discovery without changing storage on the first pass. Preserve explicit environment overrides, external runtime precedence, existing model caches, sample project asset references and saved webview preferences. Keep different lifecycles for configuration, persistent user data, caches, logs and managed runtimes, even if they share a product namespace.

Do not treat renaming an existing virtual environment as a directory migration. Installed scripts can contain absolute interpreter paths, and Python documents virtual environments as generally non-portable. Reuse the old environment in place, or rebuild it at its final destination and validate it before switching the recorded location. Retain reusable models and the previous working environment until success. See the [Python venv documentation](https://docs.python.org/3/library/venv.html#how-venvs-work).

If consolidation is later justified, make it versioned, idempotent and recoverable after interruption. Define conflict precedence, free-space checks, verification before switching, rollback compatibility and treatment of absolute paths inside sample projects. Do not silently delete old data or trigger a multi-gigabyte download just to simplify the directory tree. Update user-facing folder-removal instructions if their scope changes.

### Frontend and packaging

Convert one screen at a time using a shared transport client and explicit imports. Preserve localization behavior, settings persistence, preview audio and UI outcomes. Native dialogs remain shell concerns; they do not become business services simply to make the bridge smaller.

The current shell loads a `file://` URL (shell.py:125), and native ES module loading has origin and CORS constraints there, so choose and validate the asset transport before converting all scripts. A small reproducible build that bundles modular source into local static assets is a reasonable initial option because it preserves the current origin and the saved browser state. A local HTTP asset server is another option, but requires explicit persistence and access-scope decisions. Neither option requires a frontend framework. See [JavaScript module loading constraints](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules) and the [pywebview API](https://pywebview.flowrl.com/api/).

Update packaging as part of this change: the PyInstaller spec copies only files directly under `web/` (packaging/toolkit.spec:50), so screen subdirectories would be silently omitted. Package generated schemas, client assets, worker scripts and transitive frontend resources deliberately, excluding audit tooling. Extend the self-test to verify the declared asset set and run a real packaged-webview startup test, because scanning HTML `src` and `href` attributes does not execute JS or discover its transitive imports.

## Options considered

| Option | Assessment | Decision |
|---|---|---|
| Python restructuring with current shell | Preserves working engines and permits incremental verification. Medium risk overall; publication, task control and data migration deserve separate gates. | Chosen |
| Full Rust rewrite | Reimplements orchestration and requires a proven strategy for the current models and inference runtimes. Structure could improve, but language choice provides no automatic parity. | Rejected for current scope |
| Tauri with Python sidecar now | Adds process lifecycle, IPC, crash handling and per-platform packaging while the existing structural problems remain. | Deferred |
| Electron | Provides a bundled browser runtime, which can improve rendering consistency, but adds distribution and maintenance costs while retaining Python inference needs. | No demonstrated requirement |

Earlier drafts promised a static 10 MB binary, instant startup and about a week of porting work. Those figures were not measured and are removed. Tauri uses system webviews and a process architecture, a Python sidecar may itself be packaged with PyInstaller, and signed Windows applications can still encounter reputation warnings. See [Tauri sidecars](https://v2.tauri.app/develop/sidecar/), the [process model](https://v2.tauri.app/concept/process-model/) and [Windows signing](https://v2.tauri.app/distribute/sign/windows/).

A shell change is assessed on measured startup time, installed application size separately from models and runtimes, memory use, installation success, update reliability, native integration and maintenance cost. Python-to-Rust performance gains require profiling of actual bottlenecks; compiled inference does not imply every Python processing stage has negligible cost.

## Implementation sequence and acceptance gates

These are dependent milestones with small reversible changes inside each one, not independent bulk edits. Every behavior change is identified separately from structural movement.

| Milestone | Work | Required evidence before continuing |
|---|---|---|
| 0. Baseline | Identify the working-tree snapshot; resolve or explicitly isolate the existing UI-test failure; inventory operations, writers, data roots, outputs and runtime versions. | Reproducible baseline, relevant behavioral fixtures, documented remaining validation gaps. |
| 1. Boundary pilot | Specify request, error, progress and result envelopes; migrate module selection and one long-running build use case through the service boundary with temporary adapters. | Existing callers remain compatible; valid and invalid requests and serialized responses are checked; JS callers are type-checked. |
| 2. Execution control | Extract generic cancellation and process ownership and the task runner; apply admission control to all conflicting mutations and GUI and CLI writers. | Concurrent launch, synchronous mutation, second-process exclusion, early cancellation, launch failure, cleanup and close tests. |
| 3. Application API | Move remaining business rules from the bridge into services one feature at a time; relocate sample draft orchestration; migrate contracts and remove adapters by feature. | Operation parity, service-level behavior and no engine-to-service or engine-to-UI imports. Host operations are separately identified. |
| 4. Stems internals | Extract pure format and audio primitives, break cycles, split settings, catalogue and provisioning responsibilities and remove proven unused code. | Characterization exists before each move; format, PCM, cache, worker and interruption checks pass. Profile representative workloads. |
| 5. Platform policy | Centralize data, resource and tool resolution while preserving existing locations and runtime precedence. | Legacy installs, overrides, managed and external runtime detection and packaged resource discovery behave as specified. No physical migration in this milestone. |
| 6. Modular frontend | Migrate shared infrastructure and screens; choose module delivery; update asset packaging and replace source-position tests with behavior tests. | Packaged startup, settings persistence, six-screen workflows, preview audio and localization on the supported webview and OS matrix. |

Physical data consolidation and a shell replacement are separate optional follow-up decisions. Neither is required for this ADR to be complete. Any shell prototype must cover dialogs, worker startup and failure, cancellation, window closure, preview streaming, persisted settings and signed distribution on the target platforms.

## Consequences

- New operations have an explicit contract and reuse existing services and task infrastructure.
- The shell boundary becomes narrower and easier to replace, but transport contracts do not eliminate OS integration, distribution or lifecycle work.
- Test coverage grows at behavior boundaries while the precise low-level tests remain. A green suite is evidence within its exercised scope, not a hardware guarantee.
- Installed data remains usable throughout the code restructuring. Migration complexity is paid only if a separate benefit justifies it.
- No change to the player-facing files or their semantics is implicit in this restructuring. Any intended format or DSP change requires its own decision and acceptance evidence.

## Action items

1. [ ] Review and accept this amended decision and its milestone gates.
2. [ ] Record a reproducible baseline and investigate the current UI-test failure.
3. [ ] Inventory all mutating entry points and specify their admission policy.
4. [ ] Implement and validate the boundary pilot before selecting contract-generation tooling for the whole surface.
5. [ ] Complete milestones 2 through 6 in independently reviewable changes.
6. [ ] Record packaged desktop results separately from fixture and hardware results.
7. [ ] Open a separate data-migration or shell ADR only when evidence justifies it.
