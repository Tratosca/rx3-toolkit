# SPDX-License-Identifier: MPL-2.0
"""Executable contract tests for the on-device POSIX shell module API."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_API = ROOT / "mod/lib/module-api.sh"

HARNESS = r'''
say() { :; }
PATCH_TABLE=""
PATCH_OFFSETS=""
SUPPORTED_SHA1=""
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
. "$1"
'''


def run_shell(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-s", "--", str(MODULE_API)],
        input=HARNESS + body,
        text=True,
        capture_output=True,
        check=False,
    )


class ModuleApiTests(unittest.TestCase):
    def test_namespaced_lifecycle_hook_is_registered_and_run(self):
        result = run_shell(
            r'''
module_begin feature-a feature_a || exit 10
feature_a_prepare() { printf 'prepared'; }
register_prepare_hook feature_a_prepare || exit 11
run_hooks "$PREPARE_HOOKS" || exit 12
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "prepared")

    def test_module_cannot_register_a_sibling_namespace(self):
        result = run_shell(
            r'''
module_begin feature-a feature_a || exit 10
feature_b_prepare() { :; }
register_prepare_hook feature_b_prepare && exit 11
[ "$MODULE_LOAD_FAILED" = 1 ] || exit 12
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_two_modules_cannot_own_the_same_patch_address(self):
        result = run_shell(
            r'''
module_begin feature-a feature_a || exit 10
register_patch 42 '\001\002\003\004' '\005\006\007\010' first || exit 11
module_begin feature-b feature_b || exit 12
register_patch 42 '\001\002\003\004' '\011\012\013\014' second && exit 13
[ "$MODULE_LOAD_FAILED" = 1 ] || exit 14
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)


    def test_a_rollback_takes_every_injected_object_out_of_the_preload(self):
        """Stock bytes under our own hook is neither state, so restoring the
        binary has to unload what this runtime put in front of it."""
        result = run_shell(
            r'''
module_begin feature-a feature_a || exit 10
register_runtime_preload /root/pdj/librx3_core.so || exit 11
register_runtime_preload /root/pdj/librx3_stems.so || exit 12
register_runtime_preload /root/pdj/librx3_core.so || exit 13
[ "$RUNTIME_PRELOAD_ENTRIES" = " /root/pdj/librx3_core.so /root/pdj/librx3_stems.so" ] || exit 14

kept=$(preload_without_runtime \
  "/root/pdj/librx3_core.so:/opt/vendor/libfoo.so:/root/pdj/librx3_stems.so")
[ "$kept" = "/opt/vendor/libfoo.so" ] || exit 15
[ -z "$(preload_without_runtime /root/pdj/librx3_core.so)" ] || exit 16
[ -z "$(preload_without_runtime "")" ] || exit 17
[ "$(preload_without_runtime /opt/a.so:/opt/b.so)" = "/opt/a.so:/opt/b.so" ] || exit 18
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)


    def test_the_launch_wait_ends_as_soon_as_every_module_is_ready(self):
        """The drive stays missing from the player until the launch is declared
        good, so the wait must not outlast the evidence it is waiting for."""
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / "core.ready"
            result = run_shell(
                f'''
rbp_is_running() {{ return 0; }}
RBP_LAUNCH_TIMEOUT=9
RBP_READY_FILES="{ready}"
( sleep 1; echo up > "{ready}" ) &
wait_for_rbp 4242 || exit 10
[ "$RBP_SETTLED_AFTER" -ge 1 ] || exit 11
[ "$RBP_SETTLED_AFTER" -le 3 ] || exit 12
'''
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_process_that_died_ends_the_wait_at_once(self):
        result = run_shell(
            r'''
rbp_is_running() { return 1; }
RBP_LAUNCH_TIMEOUT=9
RBP_READY_FILES="/nonexistent/never.ready"
wait_for_rbp 4242 || exit 10
[ "$RBP_SETTLED_AFTER" = 0 ] || exit 11
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
