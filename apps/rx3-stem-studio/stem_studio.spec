# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: MPL-2.0

import pathlib
import sys


repository = pathlib.Path(SPECPATH).parents[1]
# Demucs, PyTorch, and FFmpeg are provisioned into a per-user environment on
# first launch, so the application itself only carries its own notices.
resources = [
    (str(repository / "LICENSE"), "."),
    (str(repository / "THIRD_PARTY_NOTICES.md"), "."),
]

analysis = Analysis(
    [str(repository / "apps/rx3-stem-studio/main.py")],
    pathex=[str(repository)],
    binaries=[],
    datas=resources,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
        name="RX3 Stem Studio",
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
        name="RX3 Stem Studio",
    )
    application = BUNDLE(
        collected,
        name="RX3 Stem Studio.app",
        icon=None,
        bundle_identifier="org.xdjrx3.stem.studio",
    )
else:
    executable = EXE(
        archive,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="RX3 Stem Studio",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
    )
