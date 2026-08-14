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


class ModGeneratorTests(unittest.TestCase):
    def test_manifests_are_versioned_and_unique(self):
        patches = discover_patches(REPOSITORY, "1.19")
        self.assertEqual(
            [patch.patch_id for patch in patches],
            [
                "core",
                # decoder-sleep precedes the beat jump modules that now require
                # it: the build engine enforces dependency-first manifest order.
                "decoder-sleep",
                "beatjump-32bars",
                "beatjump-no-quantize",
                "keyshift",
                "stems",
                "telnet",
                "logging",
            ],
        )
        self.assertTrue(all(patch.directory.name == patch.firmware for patch in patches))
        self.assertFalse(next(patch for patch in patches if patch.patch_id == "telnet").default)
        core = next(patch for patch in patches if patch.patch_id == "core")
        self.assertFalse(core.selectable)
        self.assertEqual(
            next(patch for patch in patches if patch.patch_id == "keyshift").requires,
            ("core",),
        )
        self.assertEqual(
            next(patch for patch in patches if patch.patch_id == "stems").requires,
            ("core",),
        )
        for identifier in ("beatjump-32bars", "beatjump-no-quantize"):
            self.assertEqual(
                next(patch for patch in patches if patch.patch_id == identifier).requires,
                ("decoder-sleep",),
            )

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

    def test_build_adds_required_core_without_adding_sibling_features(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"0123456789012345678901234567890\n")
            result = build_runtime(
                "1.19", ["keyshift"], key, directory, root=REPOSITORY
            )
            self.assertEqual(result.patches, ("core", "keyshift"))
            plain = load_firmware_codec().read_autoexec(result.output, key)

            self.assertIn(b"compatibility\ncore\nkeyshift\n", plain)
            self.assertNotIn(b"\nstems\n", plain)

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

    def test_the_session_log_ships_only_when_its_module_is_selected(self):
        """say() runs before any module is loaded, so the orchestrator reads
        the switch off the image rather than from a hook. Both halves of that
        arrangement have to agree on where it lives."""
        codec = load_firmware_codec()
        autoexec = (REPOSITORY / "mod/autoexec.sh").read_text()
        self.assertIn("[ -d /mnt/iso/modules/logging ]", autoexec)

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"0123456789012345678901234567890\n")

            quiet = build_runtime(
                "1.19", ["keyshift"], key, directory, root=REPOSITORY
            )
            self.assertNotIn("logging", quiet.patches)
            index = codec.read_autoexec(quiet.output, key)
            self.assertNotIn(b"\nlogging\n", index)

            verbose = build_runtime(
                "1.19", ["keyshift", "logging"], key, directory, root=REPOSITORY
            )
            self.assertIn("logging", verbose.patches)
            index = codec.read_autoexec(verbose.output, key)
            self.assertIn(b"\nlogging\n", index)

    def test_the_logging_module_warns_about_pulling_the_drive_out(self):
        """The warning is the reason the option exists at all, so it has to
        reach the operator where the box is ticked, not only in the log."""
        patch = next(
            item for item in discover_patches(REPOSITORY, "1.19")
            if item.patch_id == "logging"
        )
        self.assertFalse(patch.default)
        self.assertTrue(patch.selectable)
        self.assertIn("EJECT", patch.description)
        self.assertIn("NEVER PULL IT OUT", patch.description)

    def test_rejects_unknown_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"key\n")
            with self.assertRaisesRegex(ValueError, "unknown patch"):
                build_runtime("1.19", ["not-a-patch"], key, directory, root=REPOSITORY)

    def test_rejects_direct_selection_of_internal_core(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"key\n")
            with self.assertRaisesRegex(ValueError, "internal module"):
                build_runtime("1.19", ["core"], key, directory, root=REPOSITORY)


if __name__ == "__main__":
    unittest.main()
