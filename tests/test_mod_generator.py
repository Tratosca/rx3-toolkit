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

    def test_compatibility_covers_every_binary_patch_combination(self):
        compatibility = (REPOSITORY / "runtime/1.19/compatibility.sh").read_text()
        self.assertEqual(compatibility.count("register_rbp_sha1 "), 4)

    def test_gui_discovers_manifests_instead_of_listing_patch_ids(self):
        gui = (REPOSITORY / "apps/rx3-toolbox/mod_generator.py").read_text()
        self.assertIn("discover_patches", gui)
        for patch in discover_patches(REPOSITORY, "1.19"):
            self.assertNotIn(f'"{patch.patch_id}"', gui)

    def test_release_matrix_covers_supported_desktop_hosts(self):
        workflow = (REPOSITORY / ".github/workflows/release.yml").read_text()
        for expected in (
            "ubuntu-24.04",
            "windows-2025",
            "macos-15-intel",
            "macos-latest",
        ):
            self.assertIn(f"runner: {expected}", workflow)

    def test_desktop_product_names_follow_project_name(self):
        workflow = (REPOSITORY / ".github/workflows/release.yml").read_text()
        gui = (REPOSITORY / "apps/rx3-toolbox/main.py").read_text()
        spec = (REPOSITORY / "apps/rx3-toolbox/rx3_toolbox.spec").read_text()
        self.assertIn('PRODUCT = "XDJ-RX3 Toolkit"', gui)
        self.assertIn("self.title(PRODUCT)", gui)
        self.assertIn('name="XDJ-RX3 Toolkit"', spec)
        self.assertIn("name: Release XDJ-RX3 Toolkit", workflow)
        self.assertIn("archive: XDJ-RX3-Toolkit-", workflow)
        self.assertIn('--title "XDJ-RX3 Toolkit ${GITHUB_REF_NAME}"', workflow)
        # The two applications this one replaces must not survive anywhere that
        # names a download, or the release page would offer both again.
        for obsolete in (
            "RX3 Runtime Builder", "RX3-Runtime-Builder", "Toolkit Builder",
            "RX3 Mod Generator", "RX3-Mod-Generator",
            "RX3 Stem Studio", "RX3-Stem-Studio",
        ):
            self.assertNotIn(obsolete, workflow + gui + spec)

    def test_both_panes_ship_in_one_application(self):
        application = REPOSITORY / "apps/rx3-toolbox"
        entry = (application / "main.py").read_text()
        spec = (application / "rx3_toolbox.spec").read_text()
        for pane in ("mod_generator", "stem_studio"):
            self.assertTrue((application / f"{pane}.py").is_file())
            self.assertIn(f"import {pane}", entry)
            self.assertIn(f"{pane}.self_test()", entry)
        self.assertFalse((REPOSITORY / "apps/rx3-mod-generator/main.py").exists())
        self.assertFalse((REPOSITORY / "apps/rx3-stem-studio/main.py").exists())
        self.assertIn("runtime/lib/module-api.sh", spec)
        self.assertIn('data.get("build_files", [])', spec)

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
            normalized = plain.replace(b"\r\n", b"\n")
            
            self.assertIn(b"compatibility\ncore\nkeyshift\n", normalized)
            self.assertNotIn(b"\nstems\n", normalized)

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
