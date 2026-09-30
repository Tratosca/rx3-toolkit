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
# Directory lifecycle only; artwork staging has its own executable contract.
stage_panel_asset() { :; }
module_disabled_by_switch() { return 1; }
CORE_OBJECT=$FAKE_CORE
TMP=$FAKE_TMP
RUNTIME_STAGE_DIR=$FAKE_STAGE
rbp_environment_value() {
    case "$1" in
        RX3_SAMPLES_DIR) printf '%s' "$RUNNING_SAMPLES_DIR" ;;
        RX3_SAMPLES_GENERATION) printf '%s' "$RUNNING_GENERATION" ;;
    esac
}
. "$SAMPLES_MODULE"
SAMPLES_LINK=$FIXED_LINK
run_hooks "$PREPARE_HOOKS" || exit 10
before_target=$(readlink "$SAMPLES_LINK" 2>/dev/null)
[ "$NEED_RBP_RESTART" = 0 ] || commit_runtime_stage || exit 11
discard_runtime_stage
printf '%s\n%s\n%s\n%s\n' "$NEED_RBP_RESTART" "$RX3_SAMPLES_DIR" "$RX3_SAMPLES_GENERATION" "$before_target"
"""


class SampleDirectoryTests(unittest.TestCase):
    def test_mount_change_repoints_link_and_repeat_event_keeps_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "librx3_core.so"
            core.write_bytes(b"ELF")
            link = root / "rx3-samples"
            running = ""
            running_generation = ""
            temporary = root / "tmp"
            temporary.mkdir()

            def insert(device, active="live"):
                nonlocal running, running_generation
                usb = root / "media" / device
                samples = usb / "RX3_RUNTIME/samples"
                if active is None:
                    samples.mkdir(parents=True, exist_ok=True)
                    (samples / "active").unlink(missing_ok=True)
                    bank = samples
                else:
                    bank = samples / "banks" / active
                    bank.mkdir(parents=True, exist_ok=True)
                    (samples / "active").write_text(active + "\n")
                result = subprocess.run(
                    ["sh", "-s"], input=HARNESS, text=True,
                    capture_output=True, check=False,
                    env=dict(os.environ, MODULE_API=str(MODULE_API),
                             SAMPLES_MODULE=str(SAMPLES_MODULE),
                             FAKE_CORE=str(core), FIXED_LINK=str(link),
                             FAKE_TMP=str(temporary), FAKE_STAGE=str(root / "stage"),
                             USB=str(usb), RUNNING_SAMPLES_DIR=running,
                             RUNNING_GENERATION=running_generation),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                restart, published, generation, before_target = result.stdout.splitlines()
                if restart == "1":
                    running = published
                    running_generation = generation
                return restart, published, bank, before_target

            first_restart, first_path, _, _ = insert("sda2")
            self.assertEqual(first_restart, "1")
            second_restart, second_path, second_bank, _ = insert("sdb2")
            self.assertEqual(second_restart, "0")
            self.assertEqual(second_path, first_path)
            self.assertEqual(link.resolve(), second_bank.resolve())
            link_inode = link.lstat().st_ino
            third_restart, _, _, _ = insert("sdb2")
            self.assertEqual(third_restart, "0")
            self.assertEqual(link.lstat().st_ino, link_inode)

            other = root / "media" / "sdb2" / "RX3_RUNTIME/samples/banks/other"
            other.mkdir()
            (other.parent.parent / "active").write_text("other\n")
            changed_restart, _, _, before_target = insert("sdb2", "other")
            self.assertEqual(changed_restart, "1")
            self.assertEqual(before_target, str(second_bank))
            self.assertEqual(link.resolve(), other.resolve())

            (other / "1.wav").write_bytes(b"changed audio")
            audio_restart, _, _, before_target = insert("sdb2", "other")
            self.assertEqual(audio_restart, "1")
            self.assertEqual(before_target, str(other))
            stable_restart, _, _, _ = insert("sdb2", "other")
            self.assertEqual(stable_restart, "0")

            removed_restart, removed_path, _, before_target = insert("sdb2", None)
            self.assertEqual(removed_restart, "1")
            self.assertEqual(removed_path, "")
            self.assertEqual(before_target, str(other))
            self.assertFalse(link.exists())
            self.assertFalse(link.is_symlink())
            self.assertEqual(insert("sdb2", None)[0], "0")
