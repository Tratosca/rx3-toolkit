# Contributing

Contributions are limited to original source code, tests, and RX3
interoperability documentation.

By submitting a contribution you agree to license it under the Mozilla Public
License 2.0. Submit only material you created or have sufficient rights to
license under those terms.

## What must never be submitted

Firmware, manufacturer code, manufacturer binaries or GUI assets, credentials,
encryption keys, dumps, mounted images, copyrighted audio, extracted proprietary
assets, and generated artifacts.

`.gitignore` prevents the common accidents. It does not remove material already
in Git history. Run `make preflight`, review `git status`, and inspect the
staged diff before every public push.

Tagged GitHub Releases are the only exception for compiled artifacts: CI attaches
the applications and the original ARM component they embed. Firmware,
manufacturer code, keys, credentials and generated `autoexec.bin` files are never
release assets.

## Repository layout

Everything under `runtime/` executes on the RX3, as root. Everything above it
runs on your computer.

| Path | Contents |
|---|---|
| `runtime/autoexec.sh` | On-device orchestrator: discovery, validation, guarded writes, rollback, logging |
| `runtime/<firmware>/compatibility.sh` | Accepted `rbp` SHA-1 values for that firmware |
| `runtime/modules/` | One directory per module, versioned by firmware |
| `apps/rx3-mod-generator/` | Tkinter interface over the build engine |
| `apps/rx3-stem-studio/` | Tkinter interface over the stem pipeline |
| `tools/rx3_runtime/` | Build engine and its CLI |
| `tools/rx3_firmware/` | AES sector crypto, CRC32 trailer, ISO 9660 authoring |
| `tools/rx3_stems/` | Rekordbox parsing, provisioning, separation, sidecar encoding |
| `scripts/` | Release packaging and the publication preflight |
| `tests/` | Unit tests |

Neither GUI holds build or separation logic. Both drive `tools/`.

## Building from source

Desktop releases already embed the compiled ARM component, so this is for
development only.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Clang and LLD are required to compile the ARM component. CI runs on Python 3.12.

Run either interface from the repository:

```sh
make gui
make stems-gui
```

Build `autoexec.bin` from the terminal. Without `MODULES`, the manifest defaults
are used:

```sh
make autoexec KEY=/absolute/path/to/aes256.key FIRMWARE=1.19
```

## Before submitting

```sh
make test
make preflight
```

```sh
make hook
```

`make hook` compiles the ARM component and asserts the resulting ELF is
`ELF 32-bit LSB shared object, ARM, EABI5`. `make test` runs the runtime
regression guards and the unit tests. `make preflight` inspects every publishable
tracked or untracked file.

## Hardware acceptance

Static tests do not cover the device. Run this sequence before claiming a
runtime change works:

1. insert the patch drive, confirm the interface freezes then restarts;
2. repeat ±32 Beat Jumps;
3. load a track with no corresponding sidecar, confirm stock Slip Loop;
4. load a prepared track, test all four component states;
5. load prepared tracks on both decks, confirm independent audio and LED state;
6. inspect `RX3_RUNTIME/session.txt` and `/tmp/rx3-stems.log` on failure;
7. power cycle, confirm stock behaviour is restored.

## Adding a module

Each runtime feature lives under a firmware version directory and provides a
valid `manifest.json`. The GUI, the CLI and the release packager must keep
discovering the same manifest rather than maintaining separate feature lists.
The schema is in [docs/reference.md](docs/reference.md#module-manifests).

## Supporting another firmware build

Similar-looking addresses are not evidence. A submission adding support for
another RX3 firmware build must identify:

- the exact target hash;
- the byte guards;
- the offsets;
- the static validation method;
- the result on hardware.

Every guarded word must have a stock value and a patched value, and the
orchestrator must be able to tell them apart.

## Security

Do not open an issue containing an encryption key, firmware image, dump,
credential, or personal data. Treat an exposed key as compromised; deleting it
from a commit does not remove it from Git history. See
[SECURITY.md](SECURITY.md).
