# SPDX-License-Identifier: MPL-2.0
"""Executable contract tests for the on-device POSIX shell module API."""

from __future__ import annotations

import subprocess
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


    def test_a_setting_the_running_player_lacks_asks_for_a_restart(self):
        # rbp reads its environment once, so exporting alone would leave a
        # player started without the setting running exactly as before.
        result = run_shell(
            r"""
module_begin feature-a feature_a || exit 10
rbp_environment_value() { printf ''; }
module_export RX3_THING yes Thing || exit 11
[ "$NEED_RBP_RESTART" = "1" ] || exit 12
[ "$RX3_THING" = "yes" ] || exit 13
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_setting_the_running_player_already_carries_asks_for_nothing(self):
        result = run_shell(
            r"""
module_begin feature-a feature_a || exit 10
rbp_environment_value() { printf 'yes'; }
module_export RX3_THING yes Thing && exit 11
[ "$NEED_RBP_RESTART" = "0" ] || exit 12
[ "$RX3_THING" = "yes" ] || exit 13
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reapplying_logging_succeeds_without_restarting_the_player(self):
        result = run_shell(
            r'''
USB=$(mktemp -d) || exit 10
trap 'rm -rf "$USB"' EXIT
. "${1%/lib/module-api.sh}/modules/logging/module.sh"
running_log=""
rbp_environment_value() { printf '%s' "$running_log"; }
run_hooks "$PREPARE_HOOKS" || exit 11
[ "$NEED_RBP_RESTART" = 1 ] || exit 12
[ "$RX3_LOG_FILE" = "$USB/RX3_RUNTIME/mod.txt" ] || exit 13
running_log=$RX3_LOG_FILE
NEED_RBP_RESTART=0
run_hooks "$PREPARE_HOOKS" || exit 14
[ "$NEED_RBP_RESTART" = 0 ] || exit 15
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stepping_aside_does_not_stop_the_session(self):
        # A prepare hook that returns non-zero stops the whole run and no
        # guarded word is written. So a module with nothing to do, or one the
        # operator has switched off, must return success: otherwise a switch
        # meant to take out one module takes out every one of them. This
        # shipped wrong once and cost a session on hardware.
        result = run_shell(
            r"""
module_begin feature-a feature_a || exit 10
switch=$(module_switch_path feature-a)
trap 'rm -f "$switch"' EXIT
: > "$switch"
feature_a_prepare() { module_disabled_by_switch feature-a && return 0; exit 11; }
register_prepare_hook feature_a_prepare || exit 12
run_hooks "$PREPARE_HOOKS" || exit 13
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_hook_that_really_failed_still_stops_the_session(self):
        # The other half. Stepping aside must not be so soft that a genuine
        # failure passes for it.
        result = run_shell(
            r"""
module_begin feature-a feature_a || exit 10
feature_a_prepare() { return 1; }
register_prepare_hook feature_a_prepare || exit 11
run_hooks "$PREPARE_HOOKS" && exit 12
exit 0
"""
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
