# SPDX-License-Identifier: MPL-2.0
"""A restarted player gets a media notice without replaying block hotplug."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "mod/autoexec.sh").read_text()


def function(name: str) -> str:
    match = re.search(rf"(?m)^{name}\(\)\n\{{\n.*?^\}}\n", SOURCE, re.DOTALL)
    assert match, name
    return match.group(0)


SCRIPT = "say() { :; }\n" + "\n".join(function(name) for name in (
    "rbp_alive", "rbp_has_usb_channels", "announce_media"
))


class MediaAnnounceTests(unittest.TestCase):
    def run_announce(self, *, channels=True, mount=True, usb="/media/usb1/sda1"):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / "proc"
            slot = usb.split("/")[2][-1] if usb.startswith("/media/usb") else "1"
            fds = proc / "4242/fd"
            fds.mkdir(parents=True)
            (proc / "4242/exe").touch()
            (proc / "4242/stat").write_text("4242 (rbp) S 1 1 0\n")
            (proc / f"udev_usbctn{slot}").touch()
            (proc / f"udev_usb{slot}").touch()
            (proc / "mounts").write_text(
                f"/dev/sda1 {usb} vfat rw 0 0\n" if mount else ""
            )
            if channels:
                (fds / "39").symlink_to(f"/proc/udev_usbctn{slot}")
                (fds / "40").symlink_to(f"/proc/udev_usb{slot}")
            body = f'PROC_ROOT="{proc}"\nNEW=4242\nUSB="{usb}"\n' + SCRIPT
            body += "\nannounce_media\n"
            result = subprocess.run(
                ["sh", "-s"], input=body, text=True, capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return ((proc / f"udev_usbctn{slot}").read_text(),
                    (proc / f"udev_usb{slot}").read_text())

    def test_replays_only_the_players_connect_and_mount_messages(self):
        self.assertEqual(self.run_announce(),
                         ("connect", "mount /media/usb1/sda1"))
        self.assertEqual(self.run_announce(usb="/media/usb2/sdb1"),
                         ("connect", "mount /media/usb2/sdb1"))

    def test_missing_mount_or_invalid_path_does_not_announce(self):
        self.assertEqual(self.run_announce(mount=False), ("", ""))
        self.assertEqual(self.run_announce(usb="/media/usb1/../../x"), ("", ""))

    def test_does_not_reemit_block_add(self):
        self.assertNotIn("echo add >", SOURCE)
        self.assertNotIn("/sys/class/block/", SOURCE)

    def test_requires_both_channels_of_the_new_process(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            fds = proc / "4242/fd"
            fds.mkdir(parents=True)
            (fds / "39").symlink_to("/proc/udev_usb1")
            body = (f'PROC_ROOT="{proc}"\n' + SCRIPT +
                    '\nrbp_has_usb_channels 4242 1\n')
            result = subprocess.run(
                ["sh", "-s"], input=body, text=True, capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, result.stderr)


if __name__ == "__main__":
    unittest.main()
