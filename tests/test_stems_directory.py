# SPDX-License-Identifier: MPL-2.0
"""Reinserting a drive must not restart the player.

A drive pulled out as `sda` comes back as `sdb`, so its mount path moves and the
absolute path handed to rbp on the first insertion no longer resolves. rbp reads
the directory once at load time, so a moved path used to mean stopping and
relaunching it - which freezes the screen and empties the media list, the very
thing that makes the drive get pulled again.

These drive the real `stems_prepare` of the on-device module.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_API = ROOT / "mod/lib/module-api.sh"
STEMS_MODULE = ROOT / "mod/modules/stems/1.19/module.sh"

HARNESS = r"""
say() { echo "$@" >> "$SESSION_LOG"; }
PATCH_TABLE=""
PATCH_OFFSETS=""
PREPARE_HOOKS=""
AFTER_LAUNCH_HOOKS=""
POST_LAUNCH_HOOKS=""
REPORT_HOOKS=""
RBP_READY_FILES=""
RBP_DIAGNOSTIC_FILES=""
RUNTIME_PRELOAD_ENTRIES=""
LOADED_MODULES=""
CURRENT_MODULE=""
CURRENT_NAMESPACE=""
MODULE_LOAD_FAILED=0
NEED_RBP_RESTART=0
RESTART_REQUESTED_BY=""
RUNNING_HOOK=""
. "$MODULE_API"

# The packaged core lives on the mounted ISO on device; here it is a fixture.
CORE_OBJECT=$FAKE_CORE

# What the already-running player carries, as the orchestrator reads it out of
# /proc/<pid>/environ.
rbp_environment_value()
{
    [ "$1" = RX3_STEMS_DIR ] || return 1
    printf '%s' "$RUNNING_STEMS_DIR"
}

. "$STEMS_MODULE"
STEMS_LINK=$FIXED_PATH
run_hooks "$PREPARE_HOOKS"
echo "restart=$NEED_RBP_RESTART" >> "$SESSION_LOG"
echo "published=$RX3_STEMS_DIR" >> "$SESSION_LOG"
echo "requested-by:$RESTART_REQUESTED_BY" >> "$SESSION_LOG"
"""


class Deck:
    """One power cycle: a fixed path that survives, and what rbp carries."""

    def __init__(self, root: Path):
        self.root = root
        self.fixed_path = root / "tmp/rx3-stems"
        self.fixed_path.parent.mkdir(parents=True, exist_ok=True)
        self.core = root / "librx3_core.so"
        self.core.write_bytes(b"\x7fELF")
        self.running = ""

    def mount(self, device: str, sidecars: int = 2) -> Path:
        usb = self.root / "media/usb1" / device
        stems = usb / "RX3_STEMS"
        stems.mkdir(parents=True, exist_ok=True)
        for index in range(sidecars):
            (stems / f"Artist - {index}.rx3stem").write_bytes(b"x" * 128)
        return usb

    def insert(self, device: str, **kwargs) -> dict:
        """Run stems_prepare against the drive mounted at `device`."""
        usb = self.mount(device, **kwargs)
        log = self.root / "session.txt"
        log.write_text("")
        result = subprocess.run(
            ["sh", "-s"],
            input=HARNESS,
            text=True,
            capture_output=True,
            check=False,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "MODULE_API": str(MODULE_API),
                "STEMS_MODULE": str(STEMS_MODULE),
                "SESSION_LOG": str(log),
                "FAKE_CORE": str(self.core),
                "FIXED_PATH": str(self.fixed_path),
                "USB": str(usb),
                "RUNNING_STEMS_DIR": self.running,
            },
        )
        assert result.returncode == 0, result.stderr
        lines = log.read_text().splitlines()
        state = {
            "restart": next(l for l in lines if l.startswith("restart=")).split("=", 1)[1],
            "published": next(
                l for l in lines if l.startswith("published=")
            ).split("=", 1)[1],
            "lines": lines,
        }
        # A restart is what puts the published path into the running player.
        if state["restart"] == "1":
            self.running = state["published"]
        return state


class ReinsertionTests(unittest.TestCase):
    def test_a_drive_that_comes_back_as_another_device_does_not_restart_rbp(self):
        """The exact sequence from the field: inserted as sda2, pulled, back as
        sdb2. The mount path moves, the published one does not."""
        with tempfile.TemporaryDirectory() as directory:
            deck = Deck(Path(directory))

            first = deck.insert("sda2")
            self.assertEqual(first["restart"], "1", "the first insertion installs")

            second = deck.insert("sdb2")
            self.assertEqual(second["restart"], "0", second["lines"])
            self.assertEqual(second["published"], first["published"])

            # And the fixed path now resolves to the drive as it is mounted now.
            self.assertEqual(
                deck.fixed_path.resolve(),
                (Path(directory) / "media/usb1/sdb2/RX3_STEMS").resolve(),
            )

    def test_the_published_path_never_names_the_mount_point(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Deck(Path(directory))
            state = deck.insert("sda2")
            self.assertEqual(state["published"], str(deck.fixed_path))
            self.assertNotIn("sda2", state["published"])

    def test_reinsertion_is_free_however_many_times_the_node_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Deck(Path(directory))
            deck.insert("sda2")
            for device in ("sdb2", "sda2", "sdc2", "sdb2"):
                state = deck.insert(device)
                self.assertEqual(state["restart"], "0", f"{device}: {state['lines']}")


    def test_a_fixed_path_that_cannot_be_published_falls_back_to_the_mount(self):
        """A real directory in the way is not removed; the module degrades to
        the mount path rather than writing sidecar lookups inside it."""
        with tempfile.TemporaryDirectory() as directory:
            deck = Deck(Path(directory))
            deck.fixed_path.mkdir(parents=True)
            state = deck.insert("sda2")
            self.assertEqual(
                state["published"], str(Path(directory) / "media/usb1/sda2/RX3_STEMS")
            )
            self.assertTrue(
                any("falling back to the mount path" in line for line in state["lines"]),
                state["lines"],
            )


if __name__ == "__main__":
    unittest.main()
