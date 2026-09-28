<!-- SPDX-License-Identifier: MPL-2.0 -->
# Sign and notarize the macOS app

Build separately on Apple Silicon and Intel. The certificate must be Developer ID Application, with its private key in the build machine's Keychain. Apple Development certificates do not sign an outside-App-Store distribution. No certificate, password or private key belongs in this repository.

Release bundles use `fr.francois-brille.rx3-toolkit` as their identifier; the display name remains XDJ-RX3 Toolkit.

From the repository root, using the build environment's Python:

```sh
make hook PYTHON=.venv/bin/python
RX3_PREBUILT_HOOK=build/librx3_core.so \
RX3_CODESIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)' \
  .venv/bin/python -m PyInstaller --noconfirm --clean packaging/toolkit.spec
.venv/bin/python scripts/check_macos_bundle.py 'dist/XDJ-RX3 Toolkit.app'
'dist/XDJ-RX3 Toolkit.app/Contents/MacOS/XDJ-RX3 Toolkit' --self-test
codesign --verify --deep --strict 'dist/XDJ-RX3 Toolkit.app'
```

PyInstaller signs the collected binaries with hardened runtime and an Apple timestamp when `RX3_CODESIGN_IDENTITY` is set. No hardened-runtime exception is enabled by default. Open the resulting application and exercise Modules, Samples, Logo, Stems and Settings before notarizing; the headless self-test does not execute the page's JavaScript.

Create a notarization profile interactively in your own terminal. Enter credentials only in Apple's prompts, not in scripts, command arguments or chat:

```sh
xcrun notarytool store-credentials RX3-Toolkit
```

After testing, submit the signed application to Apple:

```sh
.venv/bin/python scripts/notarize_macos.py 'dist/XDJ-RX3 Toolkit.app' \
  --profile RX3-Toolkit --output local/release/XDJ-RX3-Toolkit-macOS.zip
```

The script saves the submission result and Apple log beside the archive, requires an Accepted result, staples and validates the ticket, checks Gatekeeper, then archives the app and notices with `ditto`. A failed check produces no distribution archive. It neither tags nor publishes a release. Keep the signed app and submission ID when a request fails or is interrupted so its status can be queried without resubmitting.

# Separation runtime baseline

Managed installations request audio-separator 0.44.5, librosa 0.11.0 and imageio-ffmpeg 0.6.0. Apple Silicon also fixes PyTorch at 2.13.0 and ONNX Runtime at 1.28.0, the versions exercised by the signed app. Other platforms and accelerators still need their own validated pins; this is not a complete transitive lock. Capture their installed versions when validating each release platform. The PCM cache records actual inference package versions and model asset hashes, so changing an engine invalidates automatic separation reuse. Imported PCM retains its original provenance.

Before release, exercise a silent worker cancellation, window closure during work, interrupted installation, interrupted publication, a full destination and a missing destination. Already published packages must remain readable; the next run must reuse completed tracks and regenerate unfinished ones. Tests use temporary directories, never an operator's USB drive.
