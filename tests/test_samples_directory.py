# SPDX-License-Identifier: MPL-2.0
"""A repeated USB insertion must preserve a working sample-bank link."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_API = ROOT / "mod/lib/module-api.sh"
SAMPLES_MODULE = ROOT / "mod/modules/samples/module.sh"

HARNESS = r"""
say() { :; }
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
module_disabled_by_switch() { return 1; }
CORE_OBJECT=$FAKE_CORE
rbp_environment_value() {
    [ "$1" = RX3_SAMPLES_DIR ] || return 1
    printf '%s' "$RUNNING_SAMPLES_DIR"
}
. "$SAMPLES_MODULE"
SAMPLES_LINK=$FIXED_LINK
run_hooks "$PREPARE_HOOKS" || exit 10
printf '%s\n%s\n' "$NEED_RBP_RESTART" "$RX3_SAMPLES_DIR"
"""


class SampleDirectoryTests(unittest.TestCase):
    def test_mount_change_repoints_link_and_repeat_event_keeps_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "librx3_core.so"
            core.write_bytes(b"ELF")
            link = root / "rx3-samples"
            running = ""

            def insert(device):
                nonlocal running
                usb = root / "media" / device
                bank = usb / "RX3_RUNTIME/samples/banks/live"
                bank.mkdir(parents=True, exist_ok=True)
                (bank.parent.parent / "active").write_text("live\n")
                result = subprocess.run(
                    ["sh", "-s"], input=HARNESS, text=True,
                    capture_output=True, check=False,
                    env=dict(os.environ, MODULE_API=str(MODULE_API),
                             SAMPLES_MODULE=str(SAMPLES_MODULE),
                             FAKE_CORE=str(core), FIXED_LINK=str(link),
                             USB=str(usb), RUNNING_SAMPLES_DIR=running),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                restart, published = result.stdout.splitlines()
                if restart == "1":
                    running = published
                return restart, published, bank

            first_restart, first_path, _ = insert("sda2")
            self.assertEqual(first_restart, "1")
            second_restart, second_path, second_bank = insert("sdb2")
            self.assertEqual(second_restart, "0")
            self.assertEqual(second_path, first_path)
            self.assertEqual(link.resolve(), second_bank.resolve())
            link_inode = link.lstat().st_ino
            third_restart, _, _ = insert("sdb2")
            self.assertEqual(third_restart, "0")
            self.assertEqual(link.lstat().st_ino, link_inode)
