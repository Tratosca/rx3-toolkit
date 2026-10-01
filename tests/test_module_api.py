# SPDX-License-Identifier: MPL-2.0
"""Executable contract tests for the on-device POSIX shell module API."""

from __future__ import annotations

import subprocess
import shlex
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
STOPPED_HOOKS=""
ROLLBACK_HOOKS=""
AFTER_LAUNCH_HOOKS=""
POST_LAUNCH_HOOKS=""
REPORT_HOOKS=""
RBP_READY_FILES=""
RBP_PID_READY_FILES=""
RBP_DIAGNOSTIC_FILES=""
RUNTIME_PRELOAD_ENTRIES=""
LOADED_MODULES=""
DISABLED_MODULES=""
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
    def test_removed_or_switched_off_module_requests_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            switch = Path(directory) / "stems.off"
            switch.write_text("")
            result = run_shell(
                'module_begin core core || exit 10\n'
                'module_begin stems stems || exit 11\n'
                'running="core stems|"\n'
                'rbp_environment_value() { printf %s "$running"; }\n'
                'reconcile_module_set\n'
                '[ "$NEED_RBP_RESTART" = 0 ] || exit 12\n'
                f'module_switch_path() {{ printf %s {shlex.quote(str(switch))}; }}\n'
                'module_disabled_by_switch stems || exit 13\n'
                'reconcile_module_set\n'
                '[ "$NEED_RBP_RESTART" = 1 ] || exit 14\n'
                '[ "$RX3_RUNTIME_MODULE_SET" = "core stems|stems" ] || exit 15\n'
                'NEED_RBP_RESTART=0\n'
                'DISABLED_MODULES=""\n'
                'LOADED_MODULES=" core"\n'
                'reconcile_module_set\n'
                '[ "$NEED_RBP_RESTART" = 1 ] || exit 16\n'
                '[ "$RX3_RUNTIME_MODULE_SET" = "core|" ] || exit 17\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_live_player_executable_must_be_the_guarded_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guarded = root / "rbp"
            guarded.write_bytes(b"player")
            old = root / "old-rbp"
            old.write_bytes(b"player")
            proc = root / "proc" / "4242"
            proc.mkdir(parents=True)
            exe = proc / "exe"
            exe.symlink_to(guarded)
            body = (
                f'PROC_ROOT={shlex.quote(str(root / "proc"))}\n'
                'PID=4242\n'
                f'RBP={shlex.quote(str(guarded))}\n'
                'rbp_executable_matches\n'
            )
            self.assertEqual(run_shell(body).returncode, 0)
            exe.unlink()
            exe.symlink_to(old)
            self.assertNotEqual(run_shell(body).returncode, 0)
            # /proc can retain the old inode while reporting the original
            # executable path after an atomic replacement.
            same_path = body.replace('rbp_executable_matches\n',
                                     f'readlink() {{ printf %s {shlex.quote(str(guarded))}; }}\n'
                                     'rbp_executable_matches\n')
            self.assertNotEqual(run_shell(same_path).returncode, 0)

    def test_pid_bound_readiness_rejects_an_earlier_player(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            marker = Path(directory) / "ready"
            marker.write_text("1234\n")
            body = (
                'module_begin core core\n'
                f'register_pid_ready_file {shlex.quote(str(marker))} || exit 10\n'
                f'ready_file_matches_pid {shlex.quote(str(marker))} 1234 || exit 11\n'
                f'ready_file_matches_pid {shlex.quote(str(marker))} 5678 && exit 12\n'
                'exit 0\n'
            )
            result = run_shell(body)
            self.assertEqual(result.returncode, 0, result.stderr)
            marker.write_text("5678\n")
            result = run_shell(body)
            self.assertEqual(result.returncode, 11, result.stderr)

    def test_resident_core_requires_pid_marker_and_matching_executable_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "librx3_core.so"
            core.write_bytes(b"first core")
            proc = root / "proc" / "4242"
            proc.mkdir(parents=True)
            marker = root / "performance.ready"
            marker.write_text("4242\n")
            maps = proc / "maps"
            maps.write_text(
                f"0000-1000 r-xp 00000000 00:00 {core.stat().st_ino} {core}\n"
            )
            body = (
                '. "${1%/lib/module-api.sh}/modules/core/module.sh"\n'
                'PID=4242\n'
                f'PROC_ROOT={shlex.quote(str(root / "proc"))}\n'
                f'CORE_LIB={shlex.quote(str(core))}\n'
                f'CORE_READY={shlex.quote(str(marker))}\n'
                'core_running_ready\n'
            )

            def check(expected):
                result = run_shell(body)
                self.assertEqual(result.returncode == 0, expected, result.stderr)

            check(True)
            marker.write_text("old marker\n")
            check(False)
            marker.write_text("4242\n")
            maps.write_text(f"0000-1000 r-xp 00000000 00:00 99999 {core}\n")
            check(False)
            maps.write_text(
                f"0000-1000 r-xp 00000000 00:00 {core.stat().st_ino} "
                f"{core} (deleted)\n"
            )
            check(False)

    def test_reinsertion_keeps_unchanged_core_and_logo_assets_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.rgb565"
            target = Path(directory) / "installed.rgb565"
            source.write_bytes(b"same artwork")
            target.write_bytes(source.read_bytes())

            for module, function in (("core", "core_install_asset"),
                                     ("logo", "logo_install_file")):
                with self.subTest(module=module):
                    before = target.stat()
                    call = (
                        f'RUNTIME_STAGE_DIR={shlex.quote(str(Path(directory) / "stage"))}\n'
                        f'. "${{1%/lib/module-api.sh}}/modules/{module}/module.sh" || exit 10\n'
                        f'{function} {shlex.quote(str(source))} {shlex.quote(str(target))} || exit 11\n'
                        'commit_runtime_stage || exit 12\n'
                        'discard_runtime_stage\n'
                        'printf "%s" "${LOGO_CHANGED:-0}"\n'
                    )
                    result = run_shell(call)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "0")
                    after = target.stat()
                    self.assertEqual((after.st_ino, after.st_mtime_ns),
                                     (before.st_ino, before.st_mtime_ns))

                    source.write_bytes(b"new artwork")
                    result = run_shell(call)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(target.read_bytes(), b"new artwork")
                    self.assertEqual(result.stdout, "1" if module == "logo" else "0")

                    # Matching bytes through a symlink must not preserve an
                    # unexpected link under the player's runtime directory.
                    target.unlink()
                    target.symlink_to(source)
                    result = run_shell(call)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(target.is_symlink())
                    self.assertEqual(target.read_bytes(), b"new artwork")
                    source.write_bytes(b"same artwork")
                    target.write_bytes(source.read_bytes())

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

    def test_stopped_and_rollback_hooks_are_separate_phases(self):
        result = run_shell(
            r'''
module_begin network network || exit 10
network_stopped() { printf 'stopped '; }
network_rollback() { printf 'rolled-back'; }
register_stopped_hook network_stopped || exit 11
register_rollback_hook network_rollback || exit 12
run_hooks "$STOPPED_HOOKS" || exit 13
run_hooks "$ROLLBACK_HOOKS" || exit 14
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "stopped rolled-back")

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

    def test_every_post_stop_failure_runs_rollback_hooks(self):
        autoexec = (ROOT / "mod/autoexec.sh").read_text(encoding="utf-8")

        self.assertEqual(autoexec.count('run_hooks "$ROLLBACK_HOOKS"'), 5)
        for failure in (
            "a stopped hook failed",
            "patch write(s)",
            "replacement rbp exited",
            "replacement rbp missed readiness",
        ):
            with self.subTest(failure=failure):
                self.assertIn(failure, autoexec)

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

    def test_preload_insertion_keeps_first_position_and_collapses_duplicates(self):
        result = run_shell(
            r'''
RBP_PRELOAD="/opt/vendor.so:/root/pdj/pcm.so:/root/pdj/core.so:/root/pdj/pcm.so"
ensure_preload_entry /root/pdj/core.so || exit 10
ensure_preload_entry /root/pdj/pcm.so || exit 11
[ "$RBP_PRELOAD" = "/opt/vendor.so:/root/pdj/pcm.so:/root/pdj/core.so" ] || exit 12
ensure_preload_entry /root/pdj/new.so || exit 13
[ "$RBP_PRELOAD" = "/opt/vendor.so:/root/pdj/pcm.so:/root/pdj/core.so:/root/pdj/new.so" ] || exit 14
ensure_preload_entry /root/pdj/new.so || exit 15
[ "$RBP_PRELOAD" = "/opt/vendor.so:/root/pdj/pcm.so:/root/pdj/core.so:/root/pdj/new.so" ] || exit 16
ensure_preload_entry "" && exit 17
exit 0
'''
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_core_preload_keeps_order_and_retires_legacy_library(self):
        result = run_shell(
            r'''
. "${1%/lib/module-api.sh}/modules/core/module.sh" || exit 9
RBP_PRELOAD="/opt/vendor.so:/root/pdj/librx3_core.so:/root/pdj/librx3_stems.so:/root/pdj/librx3_core.so"
core_normalize_preload || exit 10
[ "$RBP_PRELOAD" = "/opt/vendor.so:/root/pdj/librx3_core.so" ] || exit 11
RBP_PRELOAD="/opt/vendor.so:/root/pdj/librx3_stems.so"
core_normalize_preload || exit 12
[ "$RBP_PRELOAD" = "/opt/vendor.so:/root/pdj/librx3_core.so" ] || exit 13
RBP_PRELOAD=""
core_normalize_preload || exit 14
[ "$RBP_PRELOAD" = "/root/pdj/librx3_core.so" ] || exit 15
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

    def test_reapplying_browse_settings_succeeds_without_restart(self):
        for module in ("key-match", "browse-columns"):
            with self.subTest(module=module):
                result = run_shell(
                    'module=' + module + '\n' + r'''
CORE_OBJECT=$1
module_disabled_by_switch() { return 1; }
. "${1%/lib/module-api.sh}/modules/$module/module.sh"
already_running=0
rbp_environment_value() {
    [ "$already_running" = 1 ] || return 0
    case "$1" in
        RX3_KEY_MATCH) printf '%s' "$RX3_KEY_MATCH" ;;
        RX3_KEY_MATCH_RULES) printf '%s' "$RX3_KEY_MATCH_RULES" ;;
        RX3_BROWSE_COLUMNS) printf '%s' "$RX3_BROWSE_COLUMNS" ;;
        RX3_BROWSE_FIELD) printf '%s' "$RX3_BROWSE_FIELD" ;;
    esac
}
run_hooks "$PREPARE_HOOKS" || exit 10
[ "$NEED_RBP_RESTART" = 1 ] || exit 11
already_running=1
NEED_RBP_RESTART=0
run_hooks "$PREPARE_HOOKS" || exit 12
[ "$NEED_RBP_RESTART" = 0 ] || exit 13
CORE_OBJECT=/nonexistent/rx3-missing-core.so
run_hooks "$PREPARE_HOOKS" && exit 14
exit 0
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
