# SPDX-License-Identifier: MPL-2.0
"""Collect runtime resources for the desktop application bundle."""

from __future__ import annotations

import pathlib

from app.runtime.build import discover_patches, runtime_file_source


def collect_bundle_resources(
    repository: pathlib.Path,
    artifact_root: pathlib.Path | None = None,
) -> list[tuple[str, str]]:
    """Return PyInstaller source and destination pairs for runtime resources."""
    repository = pathlib.Path(repository)
    artifact_root = pathlib.Path(artifact_root or repository / "build/artifacts")
    resources = [
        (str(repository / "LICENSE"), "."),
        (str(repository / "THIRD_PARTY_NOTICES.md"), "."),
        (str(repository / "mod/autoexec.sh"), "resources/mod"),
        (str(repository / "mod/categories.json"), "resources/mod"),
        (str(repository / "mod/compatibility.sh"), "resources/mod"),
        (str(repository / "mod/lib/module-api.sh"), "resources/mod/lib"),
        (
            str(repository / "app/firmware/firmware_image.py"),
            "resources/app/firmware",
        ),
    ]

    for patch in discover_patches(repository):
        manifest = patch.directory / "manifest.json"
        resources.append((str(manifest), _bundle_directory(repository, manifest)))

        for runtime_file in patch.files:
            if runtime_file.artifact:
                for firmware in patch.firmwares:
                    source = runtime_file_source(
                        repository,
                        firmware,
                        patch,
                        runtime_file,
                        artifact_root,
                    )
                    bundled = (
                        repository
                        / "build/artifacts"
                        / firmware
                        / patch.patch_id
                        / runtime_file.source
                    )
                    resources.append(
                        (str(source), _bundle_directory(repository, bundled))
                    )
                continue

            source = patch.directory / runtime_file.source
            resources.append(
                (str(source), _bundle_directory(repository, source))
            )

        for build_file in patch.build_files:
            source = patch.directory / build_file
            resources.append((str(source), _bundle_directory(repository, source)))

        if patch.arm_hook:
            source = patch.directory / patch.arm_hook.source
            resources.append((str(source), _bundle_directory(repository, source)))

    return resources


def _bundle_directory(repository: pathlib.Path, source: pathlib.Path) -> str:
    relative = source.parent.relative_to(repository).as_posix()
    return f"resources/{relative}"
