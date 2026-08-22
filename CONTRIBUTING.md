<!-- SPDX-License-Identifier: MPL-2.0 -->
# Contributing

Contributions are limited to original source code, tests, and RX3 interoperability documentation.

By submitting a contribution you agree to license it under the Mozilla Public License 2.0. Submit only material you created or have sufficient rights to license under those terms.

## What must never be submitted

Firmware, manufacturer code, manufacturer binaries or GUI assets, credentials, encryption keys, dumps, mounted images, copyrighted audio, extracted proprietary assets, and generated artifacts.

`.gitignore` prevents the common accidents. It does not remove material already in Git history. Run `make preflight`, review `git status`, and inspect the staged diff before every public push.

Tagged GitHub Releases are the only exception for compiled artifacts: CI attaches the applications and the original ARM component they embed. Firmware, manufacturer code, keys, credentials and generated `autoexec.bin` files are never release assets.

## Repository layout

Everything under `mod/` executes on the RX3, as root. Everything above it runs on your computer.

| Path | Contents |
|---|---|
| `mod/autoexec.sh` | On-device orchestrator: indexed module loading, validation, guarded writes, rollback, logging |
| `mod/lib/module-api.sh` | Registration contract shared by every on-device module |
| `mod/<firmware>/compatibility.sh` | Accepted `rbp` SHA-1 values for that firmware |
| `mod/modules/<id>/<firmware>/` | One directory per module, named after its manifest `id`, versioned by firmware |
| `apps/rx3-toolbox/` | The one Tkinter application: a tab over the build engine, a tab over the stem pipeline |
| `tools/rx3_runtime/` | Build engine and its CLI |
| `tools/rx3_patcher/` | Offline counterparts to the on-device byte patches, for an extracted `rbp` |
| `tools/rx3_firmware/` | AES sector crypto and ISO 9660 authoring for `autoexec.bin` |
| `tools/rx3_stems/` | Rekordbox parsing, provisioning, separation, sidecar encoding |
| `scripts/` | Release packaging and the publication preflight |
| `tests/` | Unit tests |

Neither GUI holds build or separation logic. Both drive `tools/`.

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
make autoexec KEY=/absolute/path/to/aes256.key FIRMWARE=1.19
```

Export `RX3_KEY` instead and `KEY=` becomes optional, on the command line and in the application, which opens with that path already filled in. The key stays where you keep it; nothing here writes its location down.

## Before submitting

```sh
make hook test preflight
```

That is the line CI runs, so what passes here passes there. `make hook` compiles the ARM performance core and asserts the resulting ELF is `ELF 32-bit LSB shared object, ARM, EABI5`. `make test` runs the runtime regression guards and the unit tests. `make preflight` inspects every publishable tracked or untracked file.

A pull request from a fork waits for a maintainer to approve its first CI run. If yours shows no checks at all, that is what happened: it does not mean the tests passed. Ask in a comment.

## Hardware acceptance

Static tests do not cover the device. Run this sequence before claiming a runtime change works:

1. insert the patch drive, confirm the interface freezes then restarts;
2. repeat ±32 Beat Jumps;
3. load a track with no corresponding sidecar, confirm stock Slip Loop;
4. load a prepared track, test all four component states;
5. load prepared tracks on both decks, confirm independent audio and LED state;
6. inspect `RX3_RUNTIME/session.txt` and `/tmp/rx3-stems.log` on failure;
7. power cycle, confirm stock behaviour is restored.

## Adding a module

Start with the performance core, because whether your idea needs it decides everything else.

It is one shared object, `librx3_core.so`, built from `mod/modules/core/<firmware>/rx3_core_hook.c` and preloaded into the player's application. Its code runs inside that application, so it can intercept what the application does while it plays: a track being loaded, audio being pulled, a pad being pressed, the screen being drawn. It installs those interceptions once and hands them to whichever features are switched on.

A feature is not a program of its own, and not a library of its own. It is C compiled into that same shared object, reached through the lifecycle contract in `rx3_feature_api.h`: `configured`, `install`, `remove`, and whichever callbacks it wants. Key shift and stems are the two that exist. So a core feature ships no code of its own to the deck. Its `module.sh` exports an environment flag, the core reads that flag and runs the feature, and the module declines when the core is not selected. The build pulls the core in through `requires`, which is why nobody picks it directly. [Its own README](mod/modules/core/1.19/README.md) covers the rest.

That gives three shapes. The question is what your idea has to do, not what our internals are called.

| What it has to do | What that makes it |
| --- | --- |
| React to what the player does while it plays: a track loading, audio passing through, a pad pressed, something drawn on the screen | a feature inside the performance core, the way key shift and stems are |
| Run alongside the application, without ever seeing inside it | a plain module, the way session logging and the diagnostic shell are |
| Rewrite a few fixed bytes in the application, always on once applied | a byte patch, the way Beat Jump 32 is. It also has to clear the evidence bar under [Supporting another firmware build](#supporting-another-firmware-build) |

Then write the files. The command produces the manifest, the shell contract, the guards and the README, correctly named and correctly namespaced:

```sh
make new-module ID=browse-lock NAME="Browse lock"
make new-module ID=browse-lock NAME="Browse lock" CORE=1
```

`CORE=1` is the first row. It also writes the feature header and the `module.sh` that declines when the core is not selected. The other two rows take the plain form.

It prints what to fill in, and for a core feature the edits `mod/modules/core/<firmware>/rx3_core_hook.c` needs. It refuses to touch a module that already exists, so if you picked the wrong shape before filling anything in, delete the directory and run it again.

Nothing else needs editing. The application, the CLI and the release packager all discover the manifest; `make test` runs the `test_regressions.py` sitting beside it; `make hook` treats the module's headers as prerequisites. No test names the modules, so no test has to be edited to admit a new one.

The generated files already follow the rules below. They are written down for when you change them.

- A module lives in `mod/modules/<id>/<firmware>/`, where `<id>` is the `id` its `manifest.json` declares. The schema is in [REFERENCES.md](REFERENCES.md#modules).
- Every `module.sh` starts with `module_begin <id> <namespace>`, and every lifecycle function name starts with that namespace. Sourcing a module may register contracts only; device mutation belongs in a registered lifecycle hook.
- Dependencies belong in `requires`, and a dependency must carry a lower `order`. Feature code must never probe for a sibling module to create an implicit dependency. The build rejects missing modules, cycles and conflicts, then writes the resolved order to `modules/index`.
- The performance core owns executable hook installation. Optional features own their state and hook group, depend only on core services, and must remove only their own hooks on failure. See [the orchestrator](REFERENCES.md#the-orchestrator).
- A core feature reaches libc through the names declared at the top of `rx3_core_hook.c`. Calling a new one means adding it to `ALLOWED` in `tests/test_hook_symbols.py`, and confirming `rbp` exports it. The hook is `-nostdlib`: a name `rbp` does not export is neither a link error nor a warning, the shared object simply fails to load, and every module goes silent, not just yours.
- A module that also ships an offline patcher puts it in `tools/rx3_patcher/`, not under `mod/`. Everything under `mod/` executes on the deck. The patcher declares `MODULE_ID` so `tests/test_module_consistency.py` can prove its table and the module's `register_patch` calls agree.

## Supporting another firmware build

Similar-looking addresses are not evidence. A submission adding support for another RX3 firmware build must identify:

- the exact target hash;
- the byte guards;
- the offsets;
- the static validation method;
- the result on hardware.

Every guarded word must have a stock value and a patched value, and the orchestrator must be able to tell them apart.

## Security

Do not open an issue containing an encryption key, firmware image, dump, credential, or personal data. Treat an exposed key as compromised; deleting it from a commit does not remove it from Git history. See [SECURITY.md](SECURITY.md).
