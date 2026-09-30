# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: MPL-2.0

import json
import os
import pathlib
import sys


repository = pathlib.Path(SPECPATH).parent
# The USB runtime half carries its module manifests and the ARM hook. The stems
# half provisions audio-separator, PyTorch, and FFmpeg into a per-user
# environment on first launch, so it contributes only its notices.
resources = [
    (str(repository / "app/stems/data/overcue-44100-96000.f32"), "stems"),
    (str(repository / "app/stems/data/mac-intel-requirements.txt"), "stems"),
    (str(repository / "app/stems/worker.py"), "."),
    (str(repository / "app/stems/wave_worker.py"), "."),
    (str(repository / "app/stems/wave_memory.py"), "."),
    (str(repository / "app/stems/wave_encoding.py"), "."),
    (str(repository / "LICENSE"), "."),
    (str(repository / "THIRD_PARTY_NOTICES.md"), "."),
    (str(repository / "mod/autoexec.sh"), "resources/mod"),
    (str(repository / "mod/categories.json"), "resources/mod"),
    (str(repository / "mod/lib/module-api.sh"), "resources/mod/lib"),
    (str(repository / "app/firmware/firmware_image.py"), "resources/app/firmware"),
]
for compatibility in (repository / "mod").glob("*/compatibility.sh"):
    destination = f"resources/{compatibility.parent.relative_to(repository).as_posix()}"
    resources.append((str(compatibility), destination))
for manifest in (repository / "mod/modules").glob("**/manifest.json"):
    destination = f"resources/{manifest.parent.relative_to(repository).as_posix()}"
    resources.append((str(manifest), destination))
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for item in data["files"]:
        source = manifest.parent / item["source"]
        source_destination = f"resources/{source.parent.relative_to(repository).as_posix()}"
        resources.append((str(source), source_destination))
    for source in data.get("build_files", []):
        source = manifest.parent / source
        source_destination = f"resources/{source.parent.relative_to(repository).as_posix()}"
        resources.append((str(source), source_destination))
    hook = data.get("arm_hook")
    if hook:
        source = manifest.parent / hook["source"]
        source_destination = f"resources/{source.parent.relative_to(repository).as_posix()}"
        resources.append((str(source), source_destination))

# The interface itself. shell.resources() looks for it under _MEIPASS, which
# inside a .app is Contents/Frameworks, and nothing put it there before, so the
# frozen application had no page to load.
for page in sorted((repository / "app/ui/web").iterdir()):
    if page.is_file():
        resources.append((str(page), "web"))

for catalog in sorted((repository / "app/localization").glob("*.json")):
    resources.append((str(catalog), "localization"))

# Where the manufacturer's source package is and what it must hash to;
# key_source.source_path() reads it from here when frozen.
resources.append((str(repository / "app/firmware/key_source.json"), "firmware"))

prebuilt_hook = pathlib.Path(os.environ["RX3_PREBUILT_HOOK"])
if not prebuilt_hook.is_absolute():
    prebuilt_hook = repository / prebuilt_hook
resources.append((str(prebuilt_hook), "resources/prebuilt"))

# Include the optional desktop helper when built for this platform. A build
# without it keeps native RX3 preparation and reports OverCue as unavailable.
native_name = "rx3-overcue-audio" + (".exe" if sys.platform == "win32" else "")
native_helper = pathlib.Path(os.environ.get("RX3_OVERCUE_HELPER", str(
    repository / "build/overcue-audio/release" / native_name)))
if "RX3_OVERCUE_HELPER" in os.environ and not native_helper.is_file():
    raise FileNotFoundError(native_helper)
native_binaries = [(str(native_helper), "overcue")] if native_helper.is_file() else []

analysis = Analysis(
    [str(repository / "app/ui/shell.py")],
    # Everything is imported as `app.*`, so the repository root is the one path.
    pathex=[str(repository)],
    binaries=native_binaries,
    datas=resources,
    hiddenimports=[
        "cryptography",
        "cryptography.hazmat.primitives.ciphers",
        "pycdlib",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Nothing is excluded. `ssl` used to be, to keep the interpreter's OpenSSL
    # out of a bundle that already carried cryptography's; the wheels now link
    # theirs statically, so there is only ever one. It could not stay in any
    # case: webview.http imports ssl when webview is imported, so excluding it
    # makes the window fail to open. scripts/check_macos_bundle.py is what
    # proves the bundle still carries one OpenSSL and not two.
    excludes=[],
    noarchive=False,
)
archive = PYZ(analysis.pure)
if sys.platform == "darwin":
    executable = EXE(
        archive,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="XDJ-RX3 Toolkit",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        codesign_identity=os.environ.get("RX3_CODESIGN_IDENTITY"),
    )
    collected = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name="XDJ-RX3 Toolkit",
    )
    application = BUNDLE(
        collected,
        name="XDJ-RX3 Toolkit.app",
        icon=None,
        bundle_identifier="fr.francois-brille.rx3-toolkit",
    )
else:
    executable = EXE(
        archive,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="XDJ-RX3 Toolkit",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
    )
