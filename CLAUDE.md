# CLAUDE.md

Writing rules for all user-facing text, docs, comments and commits: @.claude/STYLE.md

## Commands

- Use the virtual environment: `make hook test preflight PYTHON=.venv/bin/python`. The system `python3` lacks `pycdlib`.
- One test file: `.venv/bin/python -m unittest tests.test_names` (replace the module name).
- The self-test the CI runs, which opens no window: `.venv/bin/python app/ui/shell.py --self-test`. It checks that every file the page pulls in shipped, so adding a script tag to `app/ui/web/index.html` needs no edit here.
- CI runs Python 3.12; this machine has 3.14 only, so what passes here is not exactly what the CI executes. `uv python install 3.12` gives a matching interpreter for a second run before pushing.
- Packaging can be checked locally on macOS: `RX3_PREBUILT_HOOK=build/librx3_core.so .venv/bin/pyinstaller --noconfirm --clean --distpath <elsewhere> --workpath <elsewhere> packaging/toolkit.spec`, then run the bundled executable with `--self-test`.

## The key

- `make autoexec` refuses to run without `KEY=` or `RX3_KEY`. The key lives outside the repository and no file writes its location on a developer's disk down. Keep it that way.
- If a task needs the key, stop and ask the operator to run that step. Never search the disk, the shell history or the environment of other processes for it.
- The app fetches the key on request, after terms the operator scrolls through and accepts, into the per-user folder `app/firmware/key_source.py` resolves. `key_source.json` holds the package links and SHA-256 fingerprints and nothing else. A moved link is an edit there, with new fingerprints, never a looser check.
- No file in the tree, fixture included, may hold the real key.

## Layout

- `app/` is everything that runs on the computer, imported as `app.<package>`: the window in `app/ui/` (`shell.py`, `bridge.py`, `web/`), the services it calls in `app/services/`, the engines in `app/runtime/`, `app/firmware/`, `app/stems/`, `app/samples/`, `app/logo/` and `app/session/`, the catalogs in `app/localization/`, and the pad row preview in `app/preview/`. Package names carry no `rx3_` prefix: `app.` already says whose they are. The PyInstaller spec is `packaging/toolkit.spec`. The window draws with the one the desktop already has; there is no second interface toolkit and nothing imports `tkinter`.
- Never import a sibling by bare name and never insert `app/` into `sys.path`. Either makes a second module object for the same file, and a monkeypatch on the wrong one does nothing.
- UI strings live in [TODO: path of the i18n files]. French and English are written separately from intent, per STYLE.md.
- A module is one directory under `mod/modules/`, with no level named after a firmware version: there is one set of addresses, so the tree does not pretend there are two. A manifest's `firmwares` list says which versions the module is built against, and `mod/compatibility.sh` holds every accepted player checksum in one list. 1.19 and 1.20 share everything, because their players differ by three bytes and none is at an address the mod touches.
- `scripts/check_addresses.py <rbp>` answers whether a player binary still holds what the mod expects, by reading the addresses and the eight-byte guards out of the core's own sources. That is how a new firmware is judged.
- `mod/` is what the build copies to the stick and the deck runs as root. The one exception is `mod/modules/core/build_labels.py`, which draws the assets beside it on the computer and never ships.
- Files removed by the September 2026 cleanup live only in the tag `snapshot/before-cleanup` (see CLEANUP.md). Nothing imports from it.
- `local/` is ignored and nothing in the code points at it. It is the only place that names the author of the reference build the five ported modules come from. Attribution is deferred, so no committed file names them.

## The hook is `-nostdlib`

- A libc name that `rbp` does not export is neither a link error nor a warning: the shared object fails to load on the deck and every module goes silent.
- `-fno-builtin-memcmp` in the Makefile is load-bearing. Clang rewrites `memcmp(a, b, n) == 0` into `bcmp`, which the deck lacks.
- `tests/test_hook_symbols.py` pins the allowed import set. Add a name there when a feature needs it, and confirm `rbp` exports it.
- New runtime modules compile separately through `arm_hook.sources` in the core manifest and register a descriptor in `rx3_composition.c`. Their only framework contract is `rx3_module_api.h`; never add their implementation headers to `rx3_core_hook.c`. The remaining legacy features still use includes while they migrate. See `docs/runtime-framework.md`.
- A module's `manifest.json` `build_files` must list every header its headers include. The frozen application bundles only what is listed.

## Names are conventions, not contracts

- One module has five names bound by convention only: manifest `id`, directory name, `runtime_directory`, shell namespace, C prefix. `search-latin` uses the C prefix `search_`, not what `make new-module` would mint. Grep before renaming.
- The `RX3_*` variables a module exports in `module.sh` are read by name in the C. There is no shared definition, so a rename touches both.
- The file a deck reads beside a track is a stem, in code and in prose. The old word left in September 2026; do not bring it back.
- `tests/test_names.py` fails the build on a path or Python identifier that says where a file came from (extracted, decrypted, dumped, ripped, leaked, unpacked, cracked). Name data by what it is, not by how it was obtained: [TODO: accepted replacements, for example plain, loaded, read].
- `tests/test_docs_hygiene.py` fails the build if any `.md` outside `CHANGELOG.md` describes the update-container format again. Keep prose to what the code does.

## Tests

- `unittest`, discovered from `tests/` with the repository root as the working directory. The whole suite runs in under ten seconds.
- What deserves a test: something that fails when a deck would misbehave, a stick or a track would be damaged, the mod would load and silently do nothing, or a commitment in `LEGAL.md` would break. Nothing else.
- No text assertions over the C source. They were cut in September 2026 because every edit of the C broke one without a deck behaving differently.

## The deck

- Nothing here reaches a deck. The acceptance sequence in `CONTRIBUTING.md` is the only verification of a runtime change, and a changelog entry for one says "not yet run on hardware" until someone has.
- The five ported modules (logo, samples, search-latin, stemwave, theme-white) have never run on hardware. The README says so beside each. Text describing their behaviour on the deck states intent, not fact.

## Prose and commits

- Repository prose, comments and commits use keyboard characters only: no em dash, no arrows, no curly quotes, no drawn boxes. One paragraph is one line. UI strings are exempt and follow STYLE.md (French typography in French strings).
- Conventional Commits, subject written as a sentence that says why. Every visible change gets a line under `## Unreleased` in `CHANGELOG.md`; the release job publishes that section.
- Run `make preflight PYTHON=.venv/bin/python` before committing. `.claude/settings.json` also runs `scripts/preflight.sh` before any `git commit` an agent issues, and a rejected file blocks the commit. Fix the file; never work around the check. [TODO: confirm preflight.sh excludes French i18n files from the keyboard-characters check.]