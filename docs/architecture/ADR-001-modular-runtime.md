# ADR-001: Modular runtime with one hook broker

**Status:** Accepted  
**Date:** 2026-08-13  
**Decider:** Project maintainer

## Context

Runtime modules were discovered from manifests, but `core`, `stems` and
`keyshift` were coupled implicitly:

- manifests could not declare dependencies or conflicts;
- the device sourced modules in filesystem glob order;
- lifecycle callbacks shared one unvalidated shell namespace;
- one readiness file represented the whole runtime;
- the performance core installed Stems hooks even when only Key Shift was
  selected;
- a rejected optional hook unwound every performance feature;
- Key Shift stored its mutable state in the Stems deck structure;
- rendering and touch routing contained separate feature-specific branches.

The target remains firmware 1.19. Guarded writes, RAM-only operation, rollback,
native rendering, targeted glyph refresh and the absence of framebuffer polling
are compatibility invariants.

## Decision

Use four explicit layers:

| Layer | Responsibility | Contract |
|---|---|---|
| Build engine | Discover, validate and resolve modules | Manifest DAG: `requires`, `conflicts`, `selectable` |
| Device orchestrator | Load and run selected modules | `lib/module-api.sh`; generated `modules/index`; namespaced lifecycle hooks; readiness collection |
| Performance core | Own executable writes, trampolines, deck identity, rendering and native touch | One owner per hook address; generic panel descriptor |
| Feature module | Own feature state and optional hook group | Depends on core services only, never on another feature |

`core` is an internal dependency and is therefore not directly selectable in
the desktop application. Selecting `stems` or `keyshift` adds it transitively.
Selecting a binary-only patch such as `decoder-sleep` does not.

The performance core deliberately remains the sole owner of inline patches.
Stems and Key Shift have disjoint hook groups, but both use `PcmReader::load`,
deck identity and the same native performance subtree. Independent preloaded
libraries would require hook chaining and constructor-order assumptions inside
a proprietary process. That increases failure modes without creating useful
feature isolation.

Feature isolation instead means:

1. dependencies are explicit and resolved before packaging;
2. module load order is deterministic;
3. lifecycle functions are scoped to their module namespace;
4. optional hooks are installed only when their feature is enabled;
5. rejecting one optional hook group disables only its feature;
6. per-deck state is private to its feature;
7. the core renders and dispatches a panel descriptor, not feature logic.

Names beginning with `_rx3_` are reserved for the module API. Module globals
use their declared namespace (uppercase is acceptable for configuration and
state); callbacks are enforced at load time as `<namespace>_*`.

## Options considered

### Separate `LD_PRELOAD` library per feature

**Advantages:** separate artifacts and superficially independent deployment.

**Rejected because:** two libraries cannot safely assume ownership of the same
function prologue. Hook order, rollback order and constructor order would become
part of an undocumented ABI. A failure could leave a trampoline targeting an
unloaded or partially initialized library.

### One monolithic feature hook

**Advantages:** simplest build and the previous known device behaviour.

**Rejected because:** selection was cosmetic. Feature state, hooks, UI and
failure handling were coupled, so changing one feature expanded the regression
surface of every other feature.

### One broker with independent feature contracts

**Advantages:** preserves single ownership of sensitive patches while making
dependencies, state, UI dispatch and failure domains explicit.

**Trade-off:** the performance features still share one deployed ELF and the
core remains a required platform component. This is deliberate platform
coupling, not feature-to-feature coupling.

## Consequences

- A manifest with a missing dependency, cycle, unsafe identifier or conflict is
  rejected before `autoexec.bin` is written.
- Build results report the effective selection, including transitive modules.
- New shell modules need no application changes and receive deterministic load
  order.
- New on-screen features implement the panel contract instead of adding draw
  and touch branches.
- Static and host-side tests verify architecture boundaries, but the resulting
  ELF still requires real-device acceptance before release.

## Follow-up

- Keep hardware addresses and byte guards in the firmware-specific layer.
- Add a new manifest version only when the schema itself changes.
- Do not split the broker into several preload libraries without a tested hook
  chaining ABI and device evidence that it improves fault containment.
