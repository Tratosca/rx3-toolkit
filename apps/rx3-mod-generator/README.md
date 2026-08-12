# RX3 Mod Generator

Tkinter desktop interface that selects firmware-specific runtime modules and
writes `autoexec.bin` to a chosen output directory or mounted USB drive.

It uses `tools.rx3_runtime.build` and duplicates none of the module discovery,
compilation, ISO creation, encryption or verification logic. Release builds
embed the compiled ARM stems component. Running from source compiles that
component with Clang, and only when the stems module is selected.

Run from source:

```sh
python3 apps/rx3-mod-generator/main.py
```

User documentation is in [docs/quickstart.md](../../docs/quickstart.md) and
[docs/mod-rx3.md](../../docs/mod-rx3.md). Build and packaging details are in
[CONTRIBUTING.md](../../CONTRIBUTING.md).
