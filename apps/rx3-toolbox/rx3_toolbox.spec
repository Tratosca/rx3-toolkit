# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: MPL-2.0

import json
import os
import pathlib
import sys


repository = pathlib.Path(SPECPATH).parents[1]
# The USB runtime half carries its module manifests and the ARM hook. The stems
# half provisions audio-separator, PyTorch, and FFmpeg into a per-user
# environment on first launch, so it contributes only its notices.
resources = [
    (str(repository / "LICENSE"), "."),
    (str(repository / "THIRD_PARTY_NOTICES.md"), "."),
    (str(repository / "mod/autoexec.sh"), "resources/mod"),
    (str(repository / "mod/lib/module-api.sh"), "resources/mod/lib"),
    (str(repository / "tools/rx3_firmware/firmware_image.py"), "resources/tools/rx3_firmware"),
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

prebuilt_hook = pathlib.Path(os.environ["RX3_PREBUILT_HOOK"])
resources.append((str(prebuilt_hook), "resources/prebuilt"))

application_directory = repository / "apps/rx3-toolbox"
analysis = Analysis(
    [str(application_directory / "main.py")],
    # The panes and the theme module are imported by bare name, so the
    # application directory has to be importable as well as the repository.
    pathex=[str(repository), str(application_directory)],
    binaries=[],
    datas=resources,
    hiddenimports=[
        "cryptography",
        "cryptography.hazmat.primitives.ciphers",
        "pycdlib",
        "mod_generator",
        "stem_studio",
        "theme",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Python.org's macOS _ssl and _hashlib extensions load the OpenSSL bundled
    # with the Python Framework. cryptography wheels load Homebrew OpenSSL.
    # Both use the same dylib names but may have incompatible ABIs, so retain
    # only cryptography's pair; hashlib falls back to the built-in SHA modules.
    # The stems half needs no in-process TLS: every download it triggers runs
    # inside the provisioned environment's own pip or audio-separator process.
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
        name="XDJ-RX3 Toolkit",
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
        name="XDJ-RX3 Toolkit",
    )
    application = BUNDLE(
        collected,
        name="XDJ-RX3 Toolkit.app",
        icon=None,
        bundle_identifier="org.xdjrx3.toolkit",
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
