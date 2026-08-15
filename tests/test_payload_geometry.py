"""The payload must aim where the hook actually listens.

`emulator_apply_touch` in C and the payload builder in Python are two copies of
one map, and nothing in the build makes them agree. A button that misses by a
pixel does nothing at all, silently, so the agreement is asserted rather than
assumed -- the same reason tests/test_module_consistency.py exists.

This guard lives in the toolkit because both halves it compares are the
toolkit's: the hook is ours and so is the payload we emit. A bench that runs
the payload has no business knowing either.
"""

from __future__ import annotations

import pathlib
import re
import tomllib
import unittest

from tools.rx3_payload import cli as builder


ROOT = pathlib.Path(__file__).parents[1]
HOOK = (ROOT / "mod/modules/core/1.19/rx3_core_hook.c").read_text()
# Scope every match to the one function that reads window coordinates, so a
# same-shaped comparison elsewhere in the hook cannot satisfy these guards.
BODY = HOOK.split("static void emulator_apply_touch", 1)[1].split(
    "\nstatic void emulator_poll_touch", 1
)[0]


class HookAgreementTests(unittest.TestCase):
    def hook_band(self, marker: str) -> tuple[int, int]:
        """The vertical band guarding the branch that reaches `marker`."""
        self.assertIn(marker, BODY, f"{marker} is not in emulator_apply_touch")
        position = BODY.index(marker)
        bands = [
            (int(match.group(1)), int(match.group(2)))
            for match in re.finditer(r"y >= (\d+) && y <= (\d+)", BODY)
            if match.start() < position
        ]
        self.assertTrue(bands, f"no touch band precedes {marker}")
        return bands[-1]

    def assert_inside(self, value: int, band: tuple[int, int], what: str) -> None:
        self.assertGreaterEqual(value, band[0], f"{what} is above the hook's band")
        self.assertLessEqual(value, band[1], f"{what} is below the hook's band")

    def test_rows_land_in_the_hook_bands(self) -> None:
        self.assert_inside(builder.TAB_ROW, self.hook_band("panel_for_slot"), "tab row")
        self.assert_inside(
            builder.MODE_ROW,
            self.hook_band("original_set_beatfx_selected"),
            "mode row",
        )
        self.assert_inside(
            builder.CONTROL_ROW, self.hook_band("panel->control_count"), "control row"
        )

    def test_slot_columns_match_the_hook(self) -> None:
        for slot, x in enumerate(builder.SLOTS):
            match = re.search(
                rf"x >= (\d+) && x <= (\d+)\)\s*\n\s*requested = panel_for_slot\({slot}u\)",
                BODY,
            )
            self.assertIsNotNone(match, f"no column in the hook for slot {slot}")
            self.assertGreaterEqual(x, int(match.group(1)))
            self.assertLessEqual(x, int(match.group(2)))

    def test_deck_stride_matches_the_hook(self) -> None:
        self.assertIn(f"x >= {builder.DECK_STRIDE} ? 1u : 0u", BODY)

    def test_log_and_ready_paths_match_the_hook(self) -> None:
        for constant, declared in (
            ("LOG_FILE", builder.LOG_FILE),
            ("READY_FILE", builder.READY_FILE),
        ):
            match = re.search(rf'#define {constant}\s+"([^"]+)"', HOOK)
            self.assertIsNotNone(match, f"the hook defines no {constant}")
            # The hook writes an absolute guest path; a payload declares the
            # same path relative to the guest root.
            self.assertEqual(match.group(1).lstrip("/"), declared)


class GeneratedManifestTests(unittest.TestCase):
    """What the builder emits has to be a manifest a bench would accept."""

    def manifest(self, variant: str) -> dict:
        return tomllib.loads(builder.manifest(variant, "0.0.0-test"))

    def test_every_variant_produces_a_parseable_manifest(self) -> None:
        for variant in builder.VARIANTS:
            document = self.manifest(variant)
            self.assertEqual(document["payload"]["name"], f"rx3-toolkit-{variant}")
            self.assertTrue(document["preload"])

    def test_control_columns_come_from_the_module_headers(self) -> None:
        document = self.manifest("all")
        for panel in document["panel"]:
            module = {1: "keyshift", 2: "stems"}[panel["id"]]
            self.assertEqual(
                [(control["left"], control["right"]) for control in panel["controls"]],
                builder.panel_columns(module),
                f"panel {panel['name']} drifted from its module header",
            )

    def test_a_variant_only_declares_the_panels_it_turns_on(self) -> None:
        self.assertEqual(
            [panel["name"] for panel in self.manifest("stems")["panel"]], ["STEMS"]
        )
        self.assertEqual(
            [panel["name"] for panel in self.manifest("keyshift")["panel"]], ["KEY"]
        )

    def test_every_declared_button_lands_on_screen(self) -> None:
        for variant in builder.VARIANTS:
            document = self.manifest(variant)
            screen = document["screen"]
            for entry in document["mode"] + document["panel"]:
                self.assertLess(entry["slot"], len(screen["slots"]))
            for panel in document["panel"]:
                for control in panel["controls"]:
                    for deck in range(screen["decks"]):
                        x = deck * screen["deck_stride"] + (
                            control["left"] + control["right"]
                        ) // 2
                        self.assertTrue(
                            0 <= x < 1280, f"{variant}: {control['label']} at x={x}"
                        )

    def test_the_image_table_patch_is_registered_on_the_device_too(self) -> None:
        """The payload's rewrite must be the one a device applies.

        A payload that patched something no module.sh registers would be
        exercising a binary nobody validated on hardware.
        """
        offset = builder.IMAGE_TABLE_PATCH[0]
        registered = any(
            f"register_patch {offset} " in module.read_text()
            for module in ROOT.glob("mod/modules/*/*/module.sh")
        )
        self.assertTrue(
            registered, f"no module.sh registers the payload's patch at {offset}"
        )


if __name__ == "__main__":
    unittest.main()
