# SPDX-License-Identifier: MPL-2.0
"""Executable contract tests for the on-device POSIX shell module API."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_API = ROOT / "runtime/lib/module-api.sh"

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
LOADED_MODULES=""
CURRENT_MODULE=""
CURRENT_NAMESPACE=""
MODULE_LOAD_FAILED=0
NEED_RBP_RESTART=0
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

    def test_readiness_and_diagnostics_are_restricted_to_tmp(self):
        result = run_shell(
            r'''
module_begin feature-a feature_a || exit 10
register_ready_file /tmp/feature-a.ready || exit 11
register_diagnostic_file /tmp/feature-a.log || exit 12
register_ready_file /root/unsafe && exit 13
register_diagnostic_file /tmp/../etc/shadow && exit 16
[ "$RBP_READY_FILES" = ' /tmp/feature-a.ready' ] || exit 14
[ "$RBP_DIAGNOSTIC_FILES" = ' /tmp/feature-a.log' ] || exit 15
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
