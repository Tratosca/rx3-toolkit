# SPDX-License-Identifier: MPL-2.0
"""Executable tests for the guards that decide whether to stop the player.

Stopping rbp cuts whatever is playing. These decide when not to. They are run
here against a mount table and a process tree written by the test, which is
what PROC_ROOT in the orchestrator exists for.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTOEXEC = ROOT / "mod/autoexec.sh"


def function(name: str) -> str:
    """Lift one function out of the orchestrator.

    The file runs work at the top level, so it cannot be sourced. Reading the
    function out of it keeps the test against the shipped text rather than a
    copy that can drift away from it.
    """
    source = AUTOEXEC.read_text()
    match = re.search(rf"(?m)^{name}\(\)\n\{{\n.*?^\}}\n", source, re.DOTALL)
    assert match, f"{name} is not defined in {AUTOEXEC.name}"
    return match.group(0)


PREAMBLE = "say() { :; }\n" + function("media_topology_is_unsafe") + function("rbp_alive")


def run_shell(body: str, proc_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-s"],
        input=f'PROC_ROOT="{proc_root}"\n' + PREAMBLE + body,
        text=True, capture_output=True, check=False,
    )


class MediaTopologyTests(unittest.TestCase):
    def guard(self, mounts: str, ours: str = "/media/usb1/RX3") -> int:
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "mounts"
            table.write_text(mounts)
            result = run_shell(
                f'media_topology_is_unsafe "{ours}" "{table}"\n'
                'echo "verdict=$?"\necho "reason=$MEDIA_GUARD_REASON"\n',
                Path(directory),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.verdict_reason = result.stdout
            return int(re.search(r"verdict=(\d+)", result.stdout).group(1))

    def test_our_drive_alone_is_safe(self):
        self.assertEqual(self.guard(
            "/dev/root / squashfs ro 0 0\n"
            "/dev/sda1 /media/usb1/RX3 vfat rw 0 0\n"), 1)

    def test_a_second_drive_defers(self):
        """The B2B case. Their stick is mounted and playing; ours must not stop rbp."""
        self.assertEqual(self.guard(
            "/dev/sda1 /media/usb1/RX3 vfat rw 0 0\n"
            "/dev/sdb1 /media/usb2/THEIRS vfat rw 0 0\n"), 0)
        self.assertIn("/media/usb2/THEIRS", self.verdict_reason)
        self.assertIn("/dev/sdb1", self.verdict_reason)

    def test_an_unreadable_table_defers(self):
        """Not knowing is treated as unsafe, not as an empty table."""
        with tempfile.TemporaryDirectory() as directory:
            result = run_shell(
                'media_topology_is_unsafe "/media/usb1/RX3" "/nonexistent/mounts"\n'
                'echo "verdict=$?"\necho "reason=$MEDIA_GUARD_REASON"\n',
                Path(directory),
            )
            self.assertIn("verdict=0", result.stdout)
            self.assertIn("mount table unavailable", result.stdout)

    def test_our_drive_missing_defers(self):
        """A mount that moved is a mount we cannot reason about."""
        self.assertEqual(self.guard("/dev/root / squashfs ro 0 0\n"), 0)
        self.assertIn("expected 1", self.verdict_reason)

    def test_a_trailing_slash_is_the_same_drive(self):
        self.assertEqual(self.guard(
            "/dev/sda1 /media/usb1/RX3 vfat rw 0 0\n",
            ours="/media/usb1/RX3/"), 1)


class ZombieTests(unittest.TestCase):
    def alive(self, pid: str, exe: bool, state: str) -> int:
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / pid
            proc.mkdir()
            if exe:
                (proc / "exe").write_text("")
            (proc / "stat").write_text(f"{pid} (rbp) {state} 1 1 0\n")
            result = run_shell(
                f'rbp_alive "{pid}"\necho "verdict=$?"\n', Path(directory))
            self.assertEqual(result.returncode, 0, result.stderr)
            return int(re.search(r"verdict=(\d+)", result.stdout).group(1))

    def test_a_running_player_is_alive(self):
        self.assertEqual(self.alive("101", exe=True, state="S"), 0)

    def test_a_zombie_is_not_alive(self):
        """It keeps its directory and loses its mapping, and the mapping is the
        only thing that makes writing rbp dangerous. Testing for the directory
        alone waits ten seconds for a process that has already gone."""
        self.assertEqual(self.alive("102", exe=False, state="Z"), 1)

    def test_the_guard_would_actually_catch_a_regression(self):
        """A directory test passes the zombie the real one rejects."""
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / "103"
            proc.mkdir()
            (proc / "stat").write_text("103 (rbp) Z 1 1 0\n")
            weakened = run_shell(
                f'[ -d "$PROC_ROOT/103" ]\necho "verdict=$?"\n', Path(directory))
            self.assertIn("verdict=0", weakened.stdout)
            self.assertEqual(self.alive("103", exe=False, state="Z"), 1)


if __name__ == "__main__":
    unittest.main()


class PlayerLoggingTests(unittest.TestCase):
    def test_continuous_output_is_only_on_usb_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = root / "modules"
            modules.mkdir()
            for verbose in (False, True):
                if verbose:
                    (modules / "logging-verbose").mkdir()
                result = subprocess.run(["sh", "-s"], input=(
                    f'OUT="{root}/USB"\n' + function("configure_player_logs") +
                    f'configure_player_logs "{modules}"\n' +
                    'printf "%s\n%s\n" "$RBP_OUTPUT" "$RBP_RESTORE_OUTPUT"\n'
                ), text=True, capture_output=True, check=True)
                paths = result.stdout.splitlines()
                expected = str(root / "USB") if verbose else "/tmp"
                self.assertTrue(all(str(Path(path).parent) == expected for path in paths))

    def test_ram_logs_rotate_in_ram_without_writing_usb(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ram = root / "ram"
            ram.mkdir()
            output = ram / "stdout.txt"
            output.write_text("previous session")
            result = subprocess.run(["sh", "-s"], input=(
                f'OUT="{root}/USB"\nRBP_OUTPUT="{output}"\n'
                f'RBP_RESTORE_OUTPUT="{ram}/restore.txt"\n'
                'LOGGING=1\nPLAYER_LOGS_ROTATED=0\n' + function("rotate_player_logs") +
                'rotate_player_logs\n'
            ), text=True, capture_output=True, check=True)
            self.assertFalse((root / "USB").exists())
            self.assertEqual((ram / "stdout-previous.txt").read_text(), "previous session")
