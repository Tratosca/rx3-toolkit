# RX3 Stem Studio

Tkinter desktop application that generates `.rx3stem` vocal sidecars from a
playlist in a Rekordbox XML export. Audio files, separation and encoding stay on
the computer.

It holds no separation code: `tools/rx3_stems/` carries the export parser, the
runtime resolver, the model catalogue, the job pipeline and the container
encoder.

Run from source:

```sh
python3 apps/rx3-stem-studio/main.py
```

User documentation is in [docs/stem-studio.md](../../docs/stem-studio.md).
Internals, including the gain-correction rationale, are in
[docs/reference.md](../../docs/reference.md#stems-internals).
