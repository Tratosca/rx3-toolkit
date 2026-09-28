<!-- SPDX-License-Identifier: MPL-2.0 -->
# Contributing

Contributions are limited to original source code, tests, and RX3 interoperability documentation.

By submitting a contribution you agree to license it under the Mozilla Public License 2.0. Submit only material you created or have sufficient rights to license under those terms.

## What must never be submitted

Firmware, manufacturer code, manufacturer binaries or GUI assets, credentials, encryption keys, dumps, mounted images, copyrighted audio, extracted proprietary assets, and generated artifacts.

`.gitignore` prevents the common accidents. It does not remove material already in Git history. Run `make preflight`, review `git status`, and inspect the staged diff before every public push.

Tagged GitHub Releases are the only exception for compiled artifacts: CI attaches the applications and the original ARM component they embed. Firmware, manufacturer code, keys, credentials and generated `autoexec.bin` files are never release assets.

## Repository layout

Everything the build copies out of `mod/` executes on the RX3, as root. Everything else runs on your computer, including `build_labels.py` beside the core's assets, which draws them and never ships.

| Path | Contents |
|---|---|
| `mod/autoexec.sh` | On-device orchestrator: indexed module loading, validation, guarded writes, rollback, logging |
| `mod/lib/module-api.sh` | Registration contract shared by every on-device module |
| `mod/compatibility.sh` | Accepted `rbp` SHA-1 values, one list, commented by firmware |
| `mod/modules/<id>/` | One directory per module, named after its manifest `id`. Its manifest lists the firmware versions it is built against |
| `app/` | The desktop application and the engines it drives, imported as `app.<package>` |
| `app/ui/` | The window (`shell.py`), the one surface it may call (`bridge.py`), and the five screens (`web/`) |
| `app/localization/` | English and French UI catalogs, shared by Python and the page |
| `app/runtime/` | Build engine, its CLI, and `make new-module` |
| `app/firmware/` | AES sector crypto and ISO 9660 authoring for `autoexec.bin` |
| `app/stems/` | Rekordbox parsing, provisioning, separation, stem encoding |
| `app/session/`, `app/services/`, `app/logo/`, `app/samples/` | Session log, and the services the coming window drives: drive report, mod status, samples, logo artwork |
| `app/preview/` | Pad row images drawn on the computer, `python -m app.preview` |
| `packaging/` | The PyInstaller spec that freezes the application |
| `scripts/` | Release packaging and the publication preflight |
| `tests/` | Unit tests |

The tabs hold no build or separation logic. They drive the engine packages under `app/`, which the command line drives too, so both produce the same image.

## Building from source

Desktop releases already embed the compiled ARM component, so this is for development only.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Clang and LLD are required to compile the ARM component. CI runs on Python 3.12.

Run either interface from the repository:

```sh
make app
```

Build `autoexec.bin` from the terminal. Without `MODULES`, the manifest defaults are used:

```sh
make autoexec KEY=/absolute/path/to/aes256.key FIRMWARE=1.20
```

Export `RX3_KEY` instead and `KEY=` becomes optional, on the command line and in the application, which opens with that path already filled in. The key stays where you keep it; nothing here writes its location down.

## Before submitting

```sh
make hook test preflight
```

That is the line CI runs, so what passes here passes there. `make hook` compiles the ARM performance core and asserts the resulting ELF is `ELF 32-bit LSB shared object, ARM, EABI5`. `make test` runs the unit tests. `make preflight` inspects every publishable tracked or untracked file.

A pull request from a fork waits for a maintainer to approve its first CI run. If yours shows no checks at all, that is what happened: it does not mean the tests passed. Ask in a comment.

## Hardware acceptance

Static tests do not cover the device. Run this sequence before claiming a runtime change works:

1. insert the patch drive, confirm the interface freezes then restarts;
2. repeat ±32 Beat Jumps;
3. load a track with no corresponding stem, confirm stock Slip Loop;
4. load a prepared track, test all four component states;
5. load prepared tracks on both decks, confirm independent audio and LED state;
6. on the KEY and STEMS rows: press a control and confirm it lights under the finger; slide off it and release, and confirm nothing happened; slide back on and release, and confirm it acted; press the very top and the very bottom pixel row of a control, and confirm both reach it;
7. on the KEY row, confirm the two ends and the value between them are separately touchable, and that a press between them does nothing;
8. on the sample row, drag the level past the seam between the two halves and off the end of the screen, and confirm it tracks and stops at the ends;
9. switch the display mode mid-set and confirm the row's lettering and its ground move together;
10. confirm a hardware pad-mode key still returns the row to STATUS;
11. inspect `RX3_RUNTIME/session.txt` and `/tmp/rx3-stems.log` on failure, where the pad glyph atlas reports the artwork it loaded and the image ids it took;
12. insert a drive and confirm the loading notice appears once the player is back, and clears itself a few seconds later;
13. change the deck's language in Utility, reinsert, and confirm the notice follows it;
14. raise a notice while a track plays and confirm the audio does not stutter and the player does not freeze;
15. `touch /tmp/rx3-messages.off` and confirm no further notice appears;
16. power cycle, confirm stock behaviour is restored.

## Adding a module

### The performance core

It is one shared object, `librx3_core.so`, built from `mod/modules/core/rx3_core_hook.c` and preloaded into the player's application. Its code runs inside that application, so it can intercept what the application does while it plays: a track being loaded, audio being pulled, a pad being pressed, the screen being drawn. It installs those interceptions once and hands them to whichever features are switched on.

A runtime module is compiled into that shared object through its own compilation unit and the public contract in `core/api/rx3_module_api.h`. Register its descriptor in `core/runtime/rx3_composition.c` and its source in the core manifest. Its shell module supplies configuration, while `requires` brings in the core automatically. Some older performance features still use the legacy panel/lifecycle contract while they migrate; do not copy their private includes into a new module. [The core README](mod/modules/core/README.md) describes the source layout.

### Saying something to the operator

Call `services->notices->post(...)` through the public API. The framework copies and queues the text, then its firmware adapter calls rbp's native `ui::Caution::set` on the render thread. This is the mechanism used by native notices such as EMERGENCY LOOP; the toolkit uses a separate existing caution object, B051. No custom notification renderer is needed.

Handle the returned queue status and check service availability; acceptance does not prove display. The [framework contract](docs/runtime-framework.md#notification-and-dsp-services-api-version-2) documents limits, priorities, cancellation and an example. `RX3_MESSAGES=0` or `/tmp/rx3-messages.off` disables toolkit messages, not rbp's own warnings.

### Which shape your idea has

The question is what your idea has to do, not what our internals are called.

| What it has to do | What that makes it |
| --- | --- |
| React to what the player does while it plays: a track loading, audio passing through, a pad pressed, something drawn on the screen | a feature inside the performance core, the way key shift and stems are |
| Run alongside the application, without ever seeing inside it | a plain module, the way session logging and the diagnostic shell are |
| Rewrite a few fixed bytes in the application, always on once applied | a byte patch, the way Beat Jump 32 is. It also has to clear the evidence bar under [Supporting another firmware build](#supporting-another-firmware-build) |

### Writing the files

The command produces the manifest, the shell contract and the README, correctly named and correctly namespaced:

```sh
make new-module ID=browse-lock CATEGORY=screen NAME="Browse lock"
make new-module ID=browse-lock CATEGORY=screen NAME="Browse lock" CORE=1
```

`CORE=1` is the first row above. It also writes a separate C module using the public framework API and the `module.sh` that declines when the core is not selected. The other two rows take the plain form.

It prints what to fill in and how to register the compilation unit and descriptor. New modules use the [shared framework contract](docs/runtime-framework.md), never private core state. It refuses to touch a module that already exists, so if you picked the wrong shape before filling anything in, delete the directory and run it again.

Nothing else needs editing. The application, the CLI and the release packager all discover the manifest; `make hook` treats the module's headers as prerequisites. No test names the modules, so no test has to be edited to admit a new one.

The generated files already follow the rules below. They are written down for when you change them.

- A module lives in `mod/modules/<id>/`, where `<id>` is the `id` its `manifest.json` declares. The schema is in [REFERENCES.md](REFERENCES.md#modules).
- Every `module.sh` starts with `module_begin <id> <namespace>`, and every lifecycle function name starts with that namespace. Sourcing a module may register contracts only; device mutation belongs in a registered lifecycle hook.
- Dependencies belong in `requires`, and a dependency must carry a lower `order`. Feature code must never probe for a sibling module to create an implicit dependency. The build rejects missing modules, cycles and conflicts, then writes the resolved order to `modules/index`.
- The performance core owns executable hook installation. Optional features own their state and hook group, depend only on core services, and must remove only their own hooks on failure. See [the orchestrator](REFERENCES.md#the-orchestrator).
- A core feature reaches libc through the names declared at the top of `rx3_core_hook.c`. Calling a new one means adding it to `ALLOWED` in `tests/test_hook_symbols.py`, and confirming `rbp` exports it. The hook is `-nostdlib`: a name `rbp` does not export is neither a link error nor a warning, the shared object simply fails to load, and every module goes silent, not just yours.

## Supporting another firmware build

A firmware version is not a set of addresses. Several versions can carry the same one, and when they do, supporting the new version is one checksum in `mod/compatibility.sh` and one entry in each module's `firmwares` list -- no new directory, no new hook. `scripts/check_addresses.py` answers which case you are in: point it at that version's own player binary and it checks every hooked address and every registered patch word against the sources. All of them holding means the existing target covers it.

Similar-looking addresses are not evidence, and neither is somebody else's claim. A submission adding support for a build whose addresses have moved must identify:

- the exact target hash;
- the byte guards;
- the offsets;
- the static validation method;
- the result on hardware.

Every guarded word must have a stock value and a patched value, and the orchestrator must be able to tell them apart.

## Security

Do not open an issue containing an encryption key, firmware image, dump, credential, or personal data. Treat an exposed key as compromised; deleting it from a commit does not remove it from Git history. See [SECURITY.md](SECURITY.md).
