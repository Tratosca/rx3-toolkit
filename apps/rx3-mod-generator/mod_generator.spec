# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: MPL-2.0

import json
import os
import pathlib
import sys


repository = pathlib.Path(SPECPATH).parents[1]
resources = [
    (str(repository / "LICENSE"), "."),
    (str(repository / "THIRD_PARTY_NOTICES.md"), "."),
    (str(repository / "runtime/autoexec.sh"), "resources/runtime"),
    (str(repository / "tools/rx3_firmware/firmware_image.py"), "resources/tools/rx3_firmware"),
]
for compatibility in (repository / "runtime").glob("*/compatibility.sh"):
    destination = f"resources/{compatibility.parent.relative_to(repository).as_posix()}"
    resources.append((str(compatibility), destination))
for manifest in (repository / "runtime/modules").glob("**/manifest.json"):
    destination = f"resources/{manifest.parent.relative_to(repository).as_posix()}"
    resources.append((str(manifest), destination))
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for item in data["files"]:
        resources.append((str(manifest.parent / item["source"]), destination))
    hook = data.get("arm_hook")
    if hook:
        resources.append((str(manifest.parent / hook["source"]), destination))

prebuilt_hook = pathlib.Path(os.environ["RX3_PREBUILT_HOOK"])
resources.append((str(prebuilt_hook), "resources/prebuilt"))

analysis = Analysis(
    [str(repository / "apps/rx3-mod-generator/main.py")],
    pathex=[str(repository)],
    binaries=[],
    datas=resources,
    hiddenimports=["cryptography", "cryptography.hazmat.primitives.ciphers", "pycdlib"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Python.org's macOS _ssl and _hashlib extensions load the OpenSSL bundled
    # with the Python Framework. cryptography wheels load Homebrew OpenSSL.
    # Both use the same dylib names but may have incompatible ABIs, so retain
    # only cryptography's pair; hashlib falls back to the built-in SHA modules.
    excludes=["ssl", "_ssl", "_hashlib"],
    noarchive=False,
)
archive = PYZ(analysis.pure)
if sys.platform == "darwin":
    executable = EXE(
        archive,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="RX3 Mod Generator",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
    )
    collected = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name="RX3 Mod Generator",
    )
    application = BUNDLE(
        collected,
        name="RX3 Mod Generator.app",
        icon=None,
        bundle_identifier="org.xdjrx3.mod.generator",
    )
else:
    executable = EXE(
        archive,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="RX3 Mod Generator",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
    )
