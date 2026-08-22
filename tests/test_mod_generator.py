# SPDX-License-Identifier: MPL-2.0
import importlib.util
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.rx3_runtime.build import build_runtime, discover_patches, resolve_patches


REPOSITORY = Path(__file__).parents[1]


def load_firmware_codec():
    path = REPOSITORY / "tools/rx3_firmware/firmware_image.py"
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


class ModGeneratorTests(unittest.TestCase):
    def test_every_module_directory_is_discovered(self):
        """Adding a module is adding its directory, and nothing else.

        Nothing here may name the modules. A list to edit is a step a
        contributor is not told about until a test they did not write fails on
        it, and CONTRIBUTING.md promises that step does not exist.
        """
        patches = discover_patches(REPOSITORY, "1.19")
        on_disk = sorted(
            path.parent
            for path in (REPOSITORY / "mod/modules").glob("*/1.19/manifest.json")
        )
        self.assertTrue(on_disk, "no module manifest was found to check")
        self.assertEqual(sorted(patch.directory for patch in patches), on_disk)
        for patch in patches:
            with self.subTest(module=patch.patch_id):
                self.assertEqual(patch.directory.name, patch.firmware)
                self.assertEqual(
                    patch.directory.parent.name, patch.patch_id,
                    "a module directory is named after the id its manifest declares",
                )

    def test_the_discovered_order_is_dependency_first(self):
        """`resolve_patches` filters this order rather than sorting again, so a
        dependency landing after its dependent is also loaded after it."""
        self.assertEqual(
            dependencies_met_late(discover_patches(REPOSITORY, "1.19")), []
        )

    def test_the_order_guard_would_actually_catch_a_regression(self):
        """A guard nobody has seen fail is a guard nobody knows works."""
        patches = discover_patches(REPOSITORY, "1.19")
        core = next(patch for patch in patches if patch.patch_id == "core")
        keyshift = next(patch for patch in patches if patch.patch_id == "keyshift")
        self.assertEqual(
            dependencies_met_late([keyshift, core]), ["keyshift precedes core"]
        )

    def test_what_the_application_offers_and_what_it_does_not(self):
        """Two decisions the manifests carry that a reader cannot infer."""
        patches = discover_patches(REPOSITORY, "1.19")
        core = next(patch for patch in patches if patch.patch_id == "core")
        self.assertFalse(core.selectable, "the core is a service, not a feature to pick")
        telnet = next(patch for patch in patches if patch.patch_id == "telnet")
        self.assertFalse(telnet.default, "a shell on the deck is never open unless asked for")

    def test_dependency_resolution_is_explicit_and_stable(self):
        patches = discover_patches(REPOSITORY, "1.19")
        self.assertEqual(
            [patch.patch_id for patch in resolve_patches(patches, ["stems", "keyshift"])],
            ["core", "keyshift", "stems"],
        )
        self.assertEqual(
            [patch.patch_id for patch in resolve_patches(patches, ["decoder-sleep"])],
            ["decoder-sleep"],
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
            self.assertEqual(result.patches, ("decoder-sleep",))


    def test_the_module_index_is_written_with_unix_line_endings(self):
        """The index is read line by line by /bin/sh on the player, where a
        trailing CR is part of the directory name and fails the module-name
        check. Python translates \\n to os.linesep unless told not to, so a
        build made on Windows shipped an index no module could be loaded from.
        The source assertion carries the test on Linux and macOS, where that
        translation never happens and the built image cannot show the fault."""
        builder = (REPOSITORY / "tools/rx3_runtime/build.py").read_text()
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


    def test_rejects_unknown_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"key\n")
            with self.assertRaisesRegex(ValueError, "unknown patch"):
                build_runtime("1.19", ["not-a-patch"], key, directory, root=REPOSITORY)


if __name__ == "__main__":
    unittest.main()
