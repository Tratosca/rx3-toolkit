# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. It is untracked (see `.gitignore`) and never published.

## Working with the user

- Chat in French. Code, comments, commits and repo docs in English.
- Ask questions often (AskUserQuestion). Before a deep dive (a long Ghidra session, a large refactor, a multi-file investigation), propose a short plan and ask first. Keep answers short, conclusion first.
- Aim for a mod that works out of the box on the deck, but no sloppy code or shortcuts.
- Approval is scoped. "ARRÊT", "audit" or "AUCUNE modification de code" means read-only: report, then wait. "Vasy, intègre !" covers only the work just approved. "On bosse que sur le toolkit" excludes any emulator work. Codex overran these bounds twice; don't.
- At session start, read `WORKLOG.md` and give a 3-5 line recap: branch, uncommitted changes, open items, pending hardware tests. Update `WORKLOG.md` whenever work stops midway or a hardware test becomes pending.

## Audience rule (comes first)

The app and the mods are used live by performing DJs. Everything a DJ sees (UI strings, notices on the deck, README, release notes) is written in DJ language: controls named as printed on the unit (SLIP LOOP, BEAT FX, DECK 1, KEY, STEMS), no internal terms (hook, core, sidecar, rbp). French UI: vouvoiement, written natively rather than translated. Glossary: deck/unit = platine; USB drive = clé USB; power cycle = "éteignez puis rallumez la platine"; stems, pad, sample, hot cue (masculine) stay untranslated; "stem file" / "fichier de stems" in the UI.

## Commands

Always use the venv: system `python3` lacks `pycdlib`.

```sh
make hook test preflight PYTHON=.venv/bin/python     # what CI runs; must pass before proposing a commit
.venv/bin/python -m unittest tests.test_hook_symbols  # one test module
.venv/bin/python app/ui/shell.py --self-test          # CI's window check, opens no window
make app PYTHON=.venv/bin/python
make autoexec KEY=/abs/path/aes256.key FIRMWARE=1.19 MODULES="..."   # or export RX3_KEY
make new-module ID=<id> CATEGORY=<cat> [NAME="..."] [CORE=1]
```

CI runs Python 3.12 (this machine has 3.14). Some UI regression tests are Node `.cjs` files in `tests/`.

## Architecture

- Everything under `mod/` runs on the RX3 as root (except `mod/modules/core/build_labels.py`, which runs on the computer). `mod/autoexec.sh` is the on-device orchestrator. `mod/lib/module-api.sh` is the shell module contract. `mod/compatibility.sh` lists the accepted `rbp` SHA-1s. The deck reads `modules/index`, written by the build, and never reads `manifest.json`.
- A module is `mod/modules/<id>/` with `manifest.json`, `module.sh` and a README. Scaffold new ones with `make new-module`. Manifest `build_files` must list every header its headers include, because the frozen app bundles only what is listed.
- Performance core: `mod/modules/core/` builds one `librx3_core.so`, preloaded into `rbp`. It intercepts track load, audio, pads and drawing. `manifest.json` lists the compilation units (`arm_hook.sources`). New features use only `api/rx3_module_api.h` and register a descriptor in `runtime/rx3_composition.c`. `rx3_core_hook.c` is the legacy entry point.
- Core isolation is ongoing: framework first, then features. Codex's refactor left mod-specific content in the core. The goal is a core holding only generic services (hooks, notices, UI, images, DSP), with every feature (keyshift, stems, samples, titles...) in its own module as a separate compilation unit. Don't add feature code to `core/`. When touching core, move feature code out rather than extending it.
- The hook is `-nostdlib`. A libc name `rbp` doesn't export makes the `.so` fail to load silently, and every module goes stock. `-fno-builtin-memcmp/-bcmp` are load-bearing. A new libc call must be added to `ALLOWED` in `tests/test_hook_symbols.py` after confirming `rbp` exports it.
- Desktop side is `app/`, imported as `app.<package>`. Never import a sibling by bare name or add `app/` to `sys.path` (it creates duplicate module objects, and monkeypatches silently miss). `ui/bridge.py` is the only surface the webview may call. `localization/en.json` and `fr.json` hold the UI strings. The UI tabs drive the same engines as the CLI (`app/runtime/`, `app/firmware/`, `app/stems/`...).
- OverCue is a third-party mod for other Pioneer products that gives them stems. The toolbox's only job is to export OverCue-compatible stems (a different format from our `.rx3stem`), so that one USB drive can carry both mods. It is experimental: `OVERCUE=1`, `native/overcue-audio`, `mod/modules/stems/overcue/`.
- New firmware support: `scripts/check_addresses.py <rbp>` checks every hooked address and patch guard. Deep reference: `REFERENCES.md`, `docs/runtime-framework.md`, `docs/adr/`.

## Reverse engineering rbp

Tools: the Ghidra MCP server, scripts and exports in `local/ghidra/`, emulator traces, on-device logs, strace, objdump and other binutils. Pin the firmware version and the binary's SHA before drawing any conclusion. `local/` is private, gitignored lab material. Never copy firmware, Pioneer binaries, extracted assets, dumps or keys into tracked paths. `~/Desktop/rx3-toolbox` is an old historical checkout: never mix its evidence with this one.

## UI and mocks

Mocks and UI changes rest on the mod's real layout, controls, states, geometry and contracts (C panel geometry, native object IDs, `bridge.py` operations), not illustrative guesses. Stay in the existing graphical spirit (`DESIGN.md`). A PostToolUse hook in `.claude/settings.local.json` runs Impeccable's check after edits under `app/ui/web/`.

## Validation order

Proof levels are separate, and reports name the one reached: host tests, packaged app, emulator, hardware. Emulator proof requires an active core, a painted framebuffer and a real response to input; building and booting alone prove nothing.

1. `make hook test preflight`.
2. The emulator, for new mods and UI changes, before anything goes to hardware: `../rx3-emulator` (see its CLAUDE.md). The deck is not near the user's desk, so use the emulator wherever possible. The native `computer-use` MCP (CLI sessions only) can drive the emulator window and the desktop app.
3. Deck over telnet. The deck exposes an APIPA (169.254.x.x) Ethernet interface on its rear USB-B port. Find its address with `arp -a` or similar on the Mac. Login is `root`, password `&ep139`. The password is publicly known, but never write it in tracked files, commits, docs or logs. Telnet also needs a drive carrying the diagnostic telnet payload. If there is no answer, ask the user whether the deck is connected.
   - Allowed without asking: anything non-destructive (read logs, `ps`, strace, push test binaries to `/tmp`, restart `rbp`). Ask before touching persistent storage.
   - Useful logs: `RX3_RUNTIME/session.txt` on the drive, `/tmp/rx3-*.log`.
4. Anything that needs a human at the deck (touch, pads, listening, `CONTRIBUTING.md` acceptance sequence): write a short checklist and add it to `WORKLOG.md` as pending. Never claim hardware validation that didn't happen.

## Tests

Test only what would make a deck misbehave, damage a stick or a track, make the mod load and silently do nothing, or break a `LEGAL.md` commitment. No text assertions over C source. The suite runs from the repo root in seconds.

## Git

- Claude manages branches (never work on `main`; only `main` produces releases). Ask before every commit, and never push, merge to `main` or tag unless asked.
- Commit message: one Conventional Commit subject line (`fix(runtime): ...`), straight to the point, no body unless essential, no `Co-Authored-By` or "Generated with" lines.
- Every visible change adds a line under `## Unreleased` in `CHANGELOG.md`. Runtime changes say "not yet run on hardware" until tested.
- Repo prose, comments and commits use keyboard characters only (no em dash, arrows or curly quotes). UI strings are exempt.
