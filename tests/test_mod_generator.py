# SPDX-License-Identifier: MPL-2.0
import importlib.util
import tempfile
import unittest
from pathlib import Path

from tools.rx3_runtime.build import build_runtime, discover_patches


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
                "beatjump-32bars",
                "beatjump-no-quantize",
                "decoder-sleep",
                "stems",
                "telnet",
            ],
        )
        self.assertTrue(all(patch.directory.name == patch.firmware for patch in patches))
        self.assertFalse(next(patch for patch in patches if patch.patch_id == "telnet").default)

    def test_compatibility_covers_every_binary_patch_combination(self):
        compatibility = (REPOSITORY / "runtime/1.19/compatibility.sh").read_text()
        self.assertEqual(compatibility.count("register_rbp_sha1 "), 4)

    def test_gui_discovers_manifests_instead_of_listing_patch_ids(self):
        gui = (REPOSITORY / "apps/rx3-mod-generator/main.py").read_text()
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
        gui = (REPOSITORY / "apps/rx3-mod-generator/main.py").read_text()
        spec = (REPOSITORY / "apps/rx3-mod-generator/mod_generator.spec").read_text()
        self.assertIn('self.title("RX3 Mod Generator")', gui)
        self.assertIn('name="RX3 Mod Generator"', spec)
        self.assertIn("name: Release XDJ-RX3 Toolkit", workflow)
        self.assertIn("archive: XDJ-RX3-Mod-Generator-", workflow)
        self.assertIn('--title "XDJ-RX3 Toolkit ${GITHUB_REF_NAME}"', workflow)
        for obsolete in ("RX3 Runtime Builder", "RX3-Runtime-Builder", "Toolkit Builder"):
            self.assertNotIn(obsolete, workflow + gui + spec)

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

    def test_rejects_unknown_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "aes256.key"
            key.write_bytes(b"key\n")
            with self.assertRaisesRegex(ValueError, "unknown patch"):
                build_runtime("1.19", ["not-a-patch"], key, directory, root=REPOSITORY)


if __name__ == "__main__":
    unittest.main()
