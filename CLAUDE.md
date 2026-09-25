# CLAUDE.md

Working notes for anyone, human or agent, who edits this repository. Every line here has already cost a debugging round or would. REFERENCES.md says how the mod works; this file is only what you cannot guess from the tree.

## Commands

- Use the virtual environment: `make hook test preflight PYTHON=.venv/bin/python`. The system `python3` lacks `pycdlib`.
- The self-test the CI runs, which opens no window: `.venv/bin/python app/ui/shell.py --self-test`. It checks that every file the page pulls in shipped, so adding a script tag to `app/ui/web/index.html` needs no edit here.
- `make autoexec` refuses to run without `KEY=` or `RX3_KEY`. The key lives outside the repository and no file writes its location down. Keep it that way.
- CI runs Python 3.12; this machine has 3.14 only. What passes here is not exactly what the CI executes. Packaging can be checked locally on macOS: `RX3_PREBUILT_HOOK=build/librx3_core.so .venv/bin/pyinstaller --noconfirm --clean --distpath <elsewhere> --workpath <elsewhere> packaging/toolkit.spec`, then run the bundled executable with `--self-test`.

## Layout

- `app/` is everything that runs on the computer: the window (`shell.py`, `bridge.py`, `web/`) and the engine packages, imported as `app.<package>`. The window draws with the one the desktop already has; there is no second interface toolkit and nothing imports `tkinter`. Never import a sibling by bare name and never insert `app/` into `sys.path`: that makes a second module object for the same file, and a monkeypatch on the wrong one does nothing.
- A module is one directory under `mod/modules/`, with no level named after a firmware version: there is one set of addresses, so the tree does not pretend there are two. A manifest's `firmwares` list says which versions the module is built against, and `mod/compatibility.sh` holds every accepted player checksum in one list. 1.19 and 1.20 share everything, because their players differ by three bytes and none is at an address the mod touches.
- `scripts/check_addresses.py <rbp>` answers whether a player binary still holds what the mod expects, by reading the addresses and the eight-byte guards out of the core's own sources. That is how a new firmware is judged, and it is a minute rather than an afternoon.
- `mod/` is what the build copies to the stick and the deck runs as root. The one exception is `mod/modules/core/build_labels.py`, which draws the assets beside it on the computer and never ships.
- `.attic/` holds files waiting for the commit that deletes them (see CLEANUP.md). Do not import from it and do not add to it without a line there.
- `local/` is ignored and nothing in the code points at it. It is the only place that names the author of the reference build the five ported modules come from; attribution is deferred, so no committed file names them.

## The hook is `-nostdlib`

- A libc name that `rbp` does not export is neither a link error nor a warning: the shared object fails to load on the deck and every module goes silent. `-fno-builtin-memcmp` in the Makefile is load-bearing (clang rewrites `memcmp(a, b, n) == 0` into `bcmp`, which the deck lacks). `tests/test_hook_symbols.py` pins the allowed import set; add a name there when a feature needs it, and confirm `rbp` exports it.
- `rx3_core_hook.c` names every module header it compiles by hand. The Makefile's `mod/modules/*/*.h` wildcard is a rebuild trigger, not a compile input: a new module's headers compile only once the `.c` includes them, and `make new-module` prints that step.
- A module's `manifest.json` `build_files` must list every header its headers include. The frozen application bundles only what is listed.

## Names are conventions, not contracts

- One module has five names bound by convention only: manifest `id`, directory name, `runtime_directory`, shell namespace, C prefix. `search-latin` uses the C prefix `search_`, not what `make new-module` would mint. Grep before renaming.
- The `RX3_*` variables a module exports in `module.sh` are read by name in the C. There is no shared definition; a rename touches both.
- The file a deck reads beside a track is a stem, in code and in prose. The old word left in September 2026; do not bring it back.
- `tests/test_names.py` fails the build on a path or Python identifier that says where a file came from (extracted, decrypted, dumped, ripped, leaked, unpacked, cracked).
- `tests/test_docs_hygiene.py` fails the build if any `.md` outside `CHANGELOG.md` describes the update-container format again. Keep prose to what the code does.

## Tests

- `unittest`, discovered from `tests/` with the repository root as the working directory. Twelve files, sixty-one tests, under ten seconds.
- What deserves a test: something that fails when a deck would misbehave, a stick or a track would be damaged, the mod would load and silently do nothing, or a commitment in `LEGAL.md` would break. Nothing else, and no text assertions over the C source: those were cut in September 2026 because every edit of the C broke one without a deck behaving differently.

## The deck

- Nothing here reaches a deck. The acceptance sequence in `CONTRIBUTING.md` is the only verification of a runtime change, and a changelog entry for one says "not yet run on hardware" until someone has.
- The five ported modules (logo, samples, search-latin, stemwave, theme-white) have never run on hardware. The README says so beside each.

## Prose and commits

- Keyboard characters only: no em dash, no arrows, no curly quotes, no drawn boxes. One paragraph is one line.
- Conventional Commits, subject written as a sentence that says why. Every visible change gets a line under `## Unreleased` in `CHANGELOG.md`; the release job publishes that section.
- `.claude/settings.json` runs `scripts/preflight.sh` before any `git commit` an agent issues. A rejected file blocks the commit; that is the point.
