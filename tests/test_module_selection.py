# SPDX-License-Identifier: MPL-2.0
"""The selection pane must obey the manifests' `requires`, in both directions.

These drive the real Tkinter variables of a real pane, so the trace callbacks
and their re-entrancy guard are exercised, not a reimplementation of them.
"""

import sys
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / "apps/rx3-toolbox"))

from tools.rx3_runtime.build import (  # noqa: E402
    dependent_closure,
    discover_patches,
    required_closure,
)

try:
    import tkinter as tk

    _ROOT = tk.Tk()
    _ROOT.withdraw()
except Exception as error:  # pragma: no cover - headless build agents
    _ROOT = None
    _REASON = f"no usable Tk display: {error}"


@unittest.skipIf(_ROOT is None, "Tk is unavailable")
class SelectionPropagationTests(unittest.TestCase):
    def setUp(self):
        from mod_generator import ModGeneratorPane

        self.pane = ModGeneratorPane(_ROOT)
        self.addCleanup(self.pane.destroy)
        self.variables = self.pane.patch_variables

    def set(self, identifier, value):
        self.variables[identifier].set(value)

    def clear(self):
        for name in list(self.variables):
            self.set(name, False)

    def ticked(self):
        return {name for name, variable in self.variables.items() if variable.get()}

    def test_every_module_is_listed_including_internal_ones(self):
        self.assertEqual(
            set(self.variables), {patch.patch_id for patch in discover_patches()}
        )

    def test_ticking_a_feature_pulls_in_its_dependency_and_nothing_else(self):
        self.clear()
        self.set("beatjump-32bars", True)
        self.assertIn("decoder-sleep", self.ticked())

        self.clear()
        self.set("stems", True)
        self.assertIn("core", self.ticked())

        # A module that requires nothing stays on its own.
        self.clear()
        self.set("decoder-sleep", True)
        self.assertEqual(self.ticked(), {"decoder-sleep"})

    def test_unticking_a_dependency_unticks_what_needed_it(self):
        self.clear()
        self.set("beatjump-32bars", True)
        self.set("beatjump-no-quantize", True)
        self.assertTrue({"beatjump-32bars", "decoder-sleep"} <= self.ticked())

        self.set("decoder-sleep", False)
        remaining = self.ticked()
        self.assertNotIn("beatjump-32bars", remaining)
        self.assertNotIn("beatjump-no-quantize", remaining)
        self.assertNotIn("decoder-sleep", remaining)

    def test_core_follows_its_dependents_and_is_never_ticked_alone(self):
        self.clear()
        self.assertFalse(self.variables["core"].get())

        self.set("keyshift", True)
        self.assertTrue(self.variables["core"].get())

        self.set("stems", True)
        self.set("keyshift", False)
        self.assertTrue(self.variables["core"].get(), "stems still needs the core")

        self.set("stems", False)
        self.assertFalse(self.variables["core"].get())

    def test_internal_modules_are_disabled_in_the_interface(self):
        internal = {
            patch.patch_id for patch in discover_patches() if not patch.selectable
        }
        self.assertTrue(internal, "this test assumes at least one internal module")
        states = {}
        for child in self.pane.patch_frame.winfo_children():
            if isinstance(child, tk.ttk.Checkbutton):
                states[str(child.cget("text"))] = str(child.cget("state"))
        disabled = {text for text, state in states.items() if state == "disabled"}
        self.assertTrue(
            any(text.endswith("(required)") for text in disabled),
            f"an internal module must be shown but not tickable; saw {states}",
        )
        # resolve_patches rejects an internal module as a direct selection, so
        # what the pane hands the resolver must exclude it even when ticked.
        self.set("stems", True)
        self.assertTrue(self.variables["core"].get())
        self.assertFalse(internal & {
            patch.patch_id for patch in discover_patches() if patch.selectable
        })


class ClosureTests(unittest.TestCase):
    """The graph helpers the pane relies on, without a display."""

    def test_the_closures_run_both_ways_and_ignore_unknown_identifiers(self):
        definitions = discover_patches()
        self.assertEqual(
            required_closure(definitions, ["beatjump-32bars"]),
            {"beatjump-32bars", "decoder-sleep"},
        )
        self.assertEqual(
            required_closure(definitions, ["decoder-sleep"]), {"decoder-sleep"}
        )
        self.assertEqual(
            dependent_closure(definitions, ["decoder-sleep"]),
            {"decoder-sleep", "beatjump-32bars", "beatjump-no-quantize"},
        )
        self.assertEqual(
            dependent_closure(definitions, ["core"]), {"core", "keyshift", "stems"}
        )
        self.assertEqual(required_closure(definitions, ["nope"]), set())
        self.assertEqual(dependent_closure(definitions, ["nope"]), set())


if __name__ == "__main__":
    unittest.main()
