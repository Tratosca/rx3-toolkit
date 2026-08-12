# Third-party software

The Mozilla Public License 2.0 applies only to original source code identified
as MPL-covered in this repository. Dependencies remain under their own terms.

## Python dependencies

| Dependency | Declared version | License |
|---|---:|---|
| cryptography | `50.0.0` | Apache-2.0 OR BSD-3-Clause |
| pycdlib | `1.14.0` | LGPL-2.1-only |
| PyInstaller | `6.21.0` | GPL-2.0-or-later with the PyInstaller bootloader exception |

PyInstaller is a release build tool. Its exception permits applications built
with it to be distributed under the application's own license, subject to the
licenses of the bundled dependencies.

## Separation runtime

RX3 Stem Studio does not redistribute a separation runtime. On request it
installs audio-separator (MIT), PyTorch (BSD-3-Clause), librosa (ISC), soundfile
(BSD-3-Clause, binding the LGPL-2.1 libsndfile), and imageio-ffmpeg
(BSD-2-Clause, carrying an FFmpeg build under its own terms) from the Python
Package Index into a per-user environment outside the application. Those
packages, their transitive dependencies, and the pre-trained model weights
downloaded on first use of a model retain their own licenses and are not
covered by the project's MPL-2.0 license.

The separation models are third-party research artifacts published through the
Ultimate Vocal Remover project. Their individual terms govern their use; none
of them is redistributed here.

## Material not relicensed

This project does not grant rights to RX3 firmware, manufacturer executables,
product names, trademarks, user-provided encryption keys, music, Rekordbox
exports, or generated stem audio. None of that material is covered by the
project's MPL-2.0 license.
