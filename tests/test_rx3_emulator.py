from __future__ import annotations

import json
import pathlib
import re
import struct
import tempfile
import unittest

from tools.rx3_emulator import cli, framebuffer, patches
from tools.rx3_emulator.framebuffer import (
    FramebufferError,
    encode_png,
    export_png,
    read_metadata,
)
from tools.rx3_emulator.cli import docker_command


class FramebufferTests(unittest.TestCase):
    def test_exports_little_endian_rgb565(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            raw = root / "framebuffer.raw"
            metadata = root / "framebuffer.json"
            output = root / "framebuffer.png"
            raw.write_bytes(struct.pack("<HHH", 0xF800, 0x07E0, 0x001F))
            metadata.write_text(json.dumps({
                "width": 3,
                "height": 1,
                "virtual_height": 1,
                "bpp": 16,
                "stride": 6,
                "yoffset": 0,
            }))
            result = export_png(raw, metadata, output)
            self.assertTrue(output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(result["non_black_pixels"], 3)

    def test_rejects_incomplete_framebuffer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "framebuffer.raw").write_bytes(b"\x00")
            (root / "framebuffer.json").write_text(json.dumps({
                "width": 1,
                "height": 1,
                "virtual_height": 1,
                "bpp": 16,
                "stride": 2,
                "yoffset": 0,
            }))
            with self.assertRaises(FramebufferError):
                export_png(
                    root / "framebuffer.raw",
                    root / "framebuffer.json",
                    root / "framebuffer.png",
                )

    def test_rejects_visible_page_outside_virtual_framebuffer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata = pathlib.Path(directory) / "framebuffer.json"
            metadata.write_text(json.dumps({
                "width": 1,
                "height": 2,
                "virtual_height": 2,
                "bpp": 16,
                "stride": 2,
                "yoffset": 1,
            }))
            with self.assertRaises(FramebufferError):
                read_metadata(metadata)

    def test_png_encoder_checks_payload_length(self) -> None:
        with self.assertRaises(FramebufferError):
            encode_png(b"\x00", 1, 1)


class AcceleratedDecoderTests(unittest.TestCase):
    """The Pillow path only ever accelerates; it must never change a pixel.

    Pillow widens 5- and 6-bit channels with its own rounding, so agreement is
    a property of the correction table rather than a coincidence. Exhausting
    all 65536 words is cheap and leaves nothing to sample.
    """

    def setUp(self) -> None:
        if framebuffer._Image is None:
            self.skipTest("Pillow is not installed; only the stdlib path exists")

    def test_every_rgb565_word_decodes_identically(self) -> None:
        words = struct.pack("<65536H", *range(65536))
        metadata = {
            "width": 65536,
            "height": 1,
            "virtual_height": 1,
            "bpp": 16,
            "stride": 131072,
            "yoffset": 0,
        }
        self.assertEqual(
            framebuffer._decode_slow(words, metadata),
            framebuffer._decode_fast(words, metadata).tobytes(),
        )

    def test_bgra_decodes_identically(self) -> None:
        metadata = {
            "width": 4,
            "height": 2,
            "virtual_height": 2,
            "bpp": 32,
            "stride": 16,
            "yoffset": 0,
        }
        page = bytes(range(32))
        self.assertEqual(
            framebuffer._decode_slow(page, metadata),
            framebuffer._decode_fast(page, metadata).tobytes(),
        )

    def test_non_black_count_agrees_with_the_stdlib_count(self) -> None:
        metadata = {
            "width": 3,
            "height": 1,
            "virtual_height": 1,
            "bpp": 16,
            "stride": 6,
            "yoffset": 0,
        }
        # Black, a colour that is dark in every channel, and pure blue: the
        # last one is the case a luminance test would wrongly call black.
        page = struct.pack("<HHH", 0x0000, 0x0841, 0x001F)
        image = framebuffer._decode_fast(page, metadata)
        rgb = framebuffer._decode_slow(page, metadata)
        self.assertEqual(framebuffer._count_non_black(rgb, None, 3), 2)
        self.assertEqual(framebuffer._count_non_black(rgb, image, 3), 2)


class FrontPanelGeometryTests(unittest.TestCase):
    """The window's buttons must aim where the hook actually listens.

    `emulator_apply_touch` in C and `panel_targets` in Python are two copies of
    one map, and nothing in the build makes them agree. A button that misses by
    a pixel does nothing at all, silently, so the agreement is asserted rather
    than assumed -- the same reason tests/test_module_consistency.py exists.
    """

    HOOK = (
        pathlib.Path(__file__).parents[1]
        / "mod/modules/core/1.19/rx3_core_hook.c"
    ).read_text()
    # Scope every match to the one function that reads window coordinates, so a
    # same-shaped comparison elsewhere in the hook cannot satisfy these guards.
    BODY = HOOK.split("static void emulator_apply_touch", 1)[1].split(
        "\nstatic void emulator_poll_touch", 1
    )[0]

    def hook_band(self, marker: str) -> tuple[int, int]:
        """The vertical band guarding the branch that reaches `marker`."""
        self.assertIn(marker, self.BODY, f"{marker} is not in emulator_apply_touch")
        position = self.BODY.index(marker)
        bands = [
            (int(match.group(1)), int(match.group(2)))
            for match in re.finditer(r"y >= (\d+) && y <= (\d+)", self.BODY)
            if match.start() < position
        ]
        self.assertTrue(bands, f"no touch band precedes {marker}")
        return bands[-1]

    def assert_inside(self, value: int, band: tuple[int, int], what: str) -> None:
        self.assertGreaterEqual(value, band[0], f"{what} is above the hook's band")
        self.assertLessEqual(value, band[1], f"{what} is below the hook's band")

    def test_tab_and_mode_rows_land_in_the_hook_bands(self) -> None:
        self.assert_inside(cli.TAB_ROW_Y, self.hook_band("panel_for_slot"), "tab row")
        self.assert_inside(
            cli.MODE_ROW_Y, self.hook_band("original_set_beatfx_selected"), "mode row"
        )
        self.assert_inside(
            cli.CONTROL_ROW_Y, self.hook_band("panel->control_count"), "control row"
        )

    def test_slot_columns_match_the_hook(self) -> None:
        for name, x in (("slot 0", cli.LEFT_SLOT_X), ("slot 1", cli.RIGHT_SLOT_X)):
            slot = 0 if name == "slot 0" else 1
            match = re.search(
                rf"x >= (\d+) && x <= (\d+)\)\s*\n\s*requested = panel_for_slot\({slot}u\)",
                self.BODY,
            )
            self.assertIsNotNone(match, f"no column in the hook for {name}")
            self.assertGreaterEqual(x, int(match.group(1)))
            self.assertLessEqual(x, int(match.group(2)))

    def test_deck_stride_matches_the_hook(self) -> None:
        self.assertIn(f"x >= {cli.DECK_STRIDE} ? 1u : 0u", self.BODY)

    def test_control_columns_match_the_feature_headers(self) -> None:
        headers = {
            1: pathlib.Path(__file__).parents[1]
            / "mod/modules/keyshift/1.19/rx3_keyshift_panel.h",
            2: pathlib.Path(__file__).parents[1]
            / "mod/modules/stems/1.19/rx3_stems_panel.h",
        }
        for panel, header in headers.items():
            source = header.read_text()
            lefts = [int(v) for v in re.search(r"_lefts\[\d\] = \{([^}]*)\}", source).group(1).split(",")]
            rights = [int(v) for v in re.search(r"_rights\[\d\] = \{([^}]*)\}", source).group(1).split(",")]
            self.assertEqual(
                [(left, right) for _, left, right in cli.PANEL_CONTROLS[panel]],
                list(zip(lefts, rights)),
                f"panel {panel} control columns drifted from {header.name}",
            )

    def test_every_button_lands_on_screen(self) -> None:
        for profile, panels in cli.PROFILE_PANELS.items():
            targets = [(x, y) for _, x, y, _ in cli.screen_targets(profile)]
            # STATUS and BEAT FX always, plus one tab per installed panel.
            self.assertEqual(len(targets), 2 + len(panels))
            for panel in panels:
                controls = cli.control_targets(panel)
                self.assertEqual(len(controls), 2 * len(cli.PANEL_CONTROLS[panel]))
                targets.extend((x, y) for _, _, x, y in controls)
            for x, y in targets:
                self.assertTrue(0 <= x < 1280 and 0 <= y < 720, f"{profile}: {x},{y}")

    def test_a_profile_only_offers_the_tabs_it_installs(self) -> None:
        self.assertEqual(
            [label for label, _, _, _ in cli.screen_targets("stems")],
            ["STATUS", "BEAT FX", "STEMS"],
        )
        self.assertEqual(cli.screen_targets("stock"), cli.screen_targets("stock")[:2])


class EmulatorPatchTests(unittest.TestCase):
    """Emulator-only rbp patches, and the line they must never cross.

    tools/rx3_patcher/ is the device's offline mirror and every member of it is
    required to have a matching register_patch in a module.sh. These patches are
    the opposite: valid only under QEMU, and a deck that applied one would be
    running a binary nobody validated. So the table lives outside that package
    and this asserts it stays out of the shipped modules too.
    """

    ROOT = pathlib.Path(__file__).parents[1]
    RUN_SH = (ROOT / "tools/rx3_emulator/container/run.sh").read_text()

    def test_shell_applies_exactly_the_python_table(self) -> None:
        applied = {
            (int(offset), stock, patched)
            for offset, stock, patched in re.findall(
                r"^\s*patch_word (\d+) ([0-9a-f]{8}) ([0-9a-f]{8})",
                self.RUN_SH,
                re.MULTILINE,
            )
        }
        for offset, stock, patched, _ in patches.PATCHES:
            self.assertIn(
                (offset, stock, patched),
                applied,
                "run.sh does not apply the word tools/rx3_emulator/patches.py declares",
            )

    def test_no_emulator_patch_is_registered_on_the_device(self) -> None:
        for module in self.ROOT.glob("mod/modules/*/*/module.sh"):
            source = module.read_text()
            for offset, _, _, _ in patches.PATCHES:
                self.assertNotIn(
                    f"register_patch {offset} ",
                    source,
                    f"{module} would apply an emulator-only patch on the deck",
                )

    def test_the_patch_is_a_branch_condition_flip(self) -> None:
        offset, stock, patched, _ = patches.UNBLOCK_STARTUP
        stock_word = int.from_bytes(bytes.fromhex(stock), "little")
        patched_word = int.from_bytes(bytes.fromhex(patched), "little")
        # Only the ARM condition field may move, NE (0b0001) to AL (0b1110):
        # same instruction, same target, so no offset is recomputed.
        self.assertEqual(stock_word & 0x0FFFFFFF, patched_word & 0x0FFFFFFF)
        self.assertEqual(stock_word >> 28, 0b0001)
        self.assertEqual(patched_word >> 28, 0b1110)

    def test_the_guard_words_match_the_shipped_rbp(self) -> None:
        rbp = self.ROOT / "local/research/rx3-lab/sysroot/root/pdj/rbp"
        if not rbp.is_file():
            self.skipTest("the private sysroot is not present")
        data = rbp.read_bytes()
        for offset, stock, _, label in patches.PATCHES:
            self.assertEqual(
                data[offset : offset + 4].hex(), stock, f"stock word moved for {label}"
            )


class StartupDiagnosisTests(unittest.TestCase):
    """A failed graphics start must say so in its own words.

    Without this the run reports five unrelated false checks and looks like a
    mod regression, when what actually happened is that DirectFB never opened
    /dev/fb0 -- an intermittent harness failure measured at roughly one run in
    three, and nothing to do with the code under test.
    """

    def test_directfb_start_is_reported_separately(self) -> None:
        source = (
            pathlib.Path(__file__).parents[1] / "tools/rx3_emulator/cli.py"
        ).read_text()
        self.assertIn('"directfb_started"', source)
        self.assertIn('framebuffer.json").is_file()', source)


class RunnerTests(unittest.TestCase):
    def test_container_is_named_for_touch_injection(self) -> None:
        command = docker_command(
            pathlib.Path("/private/sysroot"),
            pathlib.Path("/private/output"),
            "all",
            60,
            "rx3-test",
        )
        self.assertIn("rx3-test", command)
        self.assertEqual(command[command.index("--name") + 1], "rx3-test")


if __name__ == "__main__":
    unittest.main()
