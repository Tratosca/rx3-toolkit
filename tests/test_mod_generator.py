# SPDX-License-Identifier: MPL-2.0
import importlib.util
import pathlib
import tempfile
import unittest
import unittest.mock
from dataclasses import replace
from pathlib import Path

from app.runtime import build as build_module
from app.runtime.build import (
    build_runtime,
    discover_patches,
    resolve_patches,
    runtime_file_source,
)


REPOSITORY = Path(__file__).parents[1]


def load_firmware_codec():
    path = REPOSITORY / "app/firmware/firmware_image.py"
    spec = importlib.util.spec_from_file_location("firmware_image_builder_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dependencies_met_late(patches):
    """Modules a caller would meet before the module they depend on."""
    offences = []
    seen = set()
    for patch in patches:
        offences += [
            f"{patch.patch_id} precedes {required}"
            for required in patch.requires
            if required not in seen
        ]
        seen.add(patch.patch_id)
    return offences


class DurableInstallTests(unittest.TestCase):
    def test_the_staged_image_lands_and_reports_what_the_drive_holds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            staged = root / ".autoexec.bin.tmp"
            staged.write_bytes(b"RX3" * 4096)
            final = root / "autoexec.bin"
            digest = build_module.install_durably(staged, final)
            self.assertFalse(staged.exists())
            self.assertEqual(digest, build_module._sha256(final))

    def test_the_flush_falls_back_rather_than_failing(self):
        # A filesystem that refuses the stronger call must still get the weaker
        # one, and a platform with neither must still produce a correct file.
        with tempfile.TemporaryDirectory() as directory:
            handle = (pathlib.Path(directory) / "f").open("wb+")
            try:
                handle.write(b"x")
                handle.flush()
                build_module._flush(handle.fileno())
                with unittest.mock.patch.object(
                    build_module, "fcntl", None
                ):
                    build_module._flush(handle.fileno())
                descriptor = handle.fileno()
            finally:
                handle.close()
            # A descriptor that has gone away exercises the last guard. A
            # negative one would not: that is a programming error, and the
            # helper is right to let it through rather than swallow it.
            build_module._flush(descriptor)

    def test_an_image_that_does_not_read_back_is_refused(self):
        # The drive is pulled rather than unmounted, so the case worth catching
        # is the one where the write returned and the medium holds something
        # else. Forced here, because a real one needs the drive to misbehave.
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            staged = root / ".autoexec.bin.tmp"
            staged.write_bytes(b"RX3" * 4096)
            final = root / "autoexec.bin"
            with unittest.mock.patch.object(
                build_module, "_sha256", side_effect=["expected", "different"]
            ):
                with self.assertRaises(ValueError) as raised:
                    build_module.install_durably(staged, final)
            self.assertIn("does not read back", str(raised.exception))


class ModGeneratorTests(unittest.TestCase):
    def test_the_discovered_order_is_dependency_first(self):
        """`resolve_patches` filters this order rather than sorting again, so a
        dependency landing after its dependent is also loaded after it."""
        self.assertEqual(
            dependencies_met_late(discover_patches(REPOSITORY, "1.19")), []
        )

    def test_dependency_cycles_and_conflicts_are_rejected(self):
        definitions = discover_patches(REPOSITORY, "1.19")
        core = next(patch for patch in definitions if patch.patch_id == "core")
        keyshift = next(
            patch for patch in definitions if patch.patch_id == "keyshift"
        )
        cycle = [replace(core, requires=("keyshift",)), keyshift]
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            resolve_patches(cycle, ["keyshift"])

        left = replace(
            core, patch_id="left", selectable=True, conflicts=("right",)
        )
        right = replace(core, patch_id="right", selectable=True)
        with self.assertRaisesRegex(ValueError, "incompatible modules"):
            resolve_patches([left, right], ["left", "right"])

    def test_generated_module_artifacts_stay_outside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "mod/modules/example"
            module.mkdir(parents=True)
            (module / "module.sh").write_text("module_begin example example\n")
            (module / "manifest.json").write_text(
                """{
  "id": "example",
  "name": "Example",
  "description": "Generated artifact fixture.",
  "firmwares": ["1.19"],
  "selectable": false,
  "runtime_directory": "example",
  "namespace": "example",
  "files": [
    {"source": "module.sh", "target": "module.sh"},
    {"source": "example.ko", "target": "example.ko", "artifact": true}
  ]
}
"""
            )

            patch = discover_patches(root, "1.19")[0]
            artifact = patch.files[1]
            artifacts = root / "local-artifacts"
            with self.assertRaisesRegex(
                ValueError,
                "local-artifacts/1.19/example/example.ko",
            ):
                runtime_file_source(root, "1.19", patch, artifact, artifacts)

            output = artifacts / "1.19/example/example.ko"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"built outside source")
            self.assertEqual(
                runtime_file_source(root, "1.19", patch, artifact, artifacts), output
            )

    def test_builds_selected_modules_without_external_iso_tool(self):
        codec = load_firmware_codec()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"0123456789012345678901234567890\n")
            result = build_runtime(
                "1.19",
                ["decoder-sleep"],
                key,
                directory,
                root=REPOSITORY,
            )
            self.assertEqual(result.output, directory / "autoexec.bin")
            plain = codec.read_autoexec(result.output, key)
            self.assertEqual(codec.autoexec_iso_metadata(plain), "UsbAuto")
            self.assertIn(b"/dev/subucom_spi1.0", plain)
            self.assertEqual(result.patches, ("decoder-sleep",))


    def test_the_module_index_is_written_with_unix_line_endings(self):
        """The index is read line by line by /bin/sh on the player, where a
        trailing CR is part of the directory name and fails the module-name
        check. Python translates \\n to os.linesep unless told not to, so a
        build made on Windows shipped an index no module could be loaded from.
        The source assertion carries the test on Linux and macOS, where that
        translation never happens and the built image cannot show the fault."""
        builder = (REPOSITORY / "app/runtime/build.py").read_text()
        self.assertRegex(
            builder, r'modules / "index"\)\.write_text\((?s:.*?)newline=""'
        )

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"0123456789012345678901234567890\n")
            result = build_runtime(
                "1.19", ["keyshift"], key, directory, root=REPOSITORY
            )
            plain = load_firmware_codec().read_autoexec(result.output, key)
            self.assertNotIn(b"compatibility\r", plain)


if __name__ == "__main__":
    unittest.main()
