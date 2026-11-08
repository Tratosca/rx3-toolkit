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
AFTER_LAUNCH_HOOKS=""
POST_LAUNCH_HOOKS=""
REPORT_HOOKS=""
RBP_READY_FILES=""
RBP_PID_READY_FILES=""
RBP_DIAGNOSTIC_FILES=""
RUNTIME_PRELOAD_ENTRIES=""
LOADED_MODULES=""
DISABLED_MODULES=""
INACTIVE_MODULES=""
CURRENT_MODULE=""
CURRENT_NAMESPACE=""
MODULE_LOAD_FAILED=0
NEED_RBP_RESTART=0
RESTART_REQUESTED_BY=""
RUNNING_HOOK=""
. "$1"
'''


def settings_reader() -> str:
    """module_setting from module-api.sh, for module scripts tested alone."""
    import re
    text = MODULE_API.read_text(encoding="utf-8")
    return re.search(r"^module_setting\(\)\n\{.*?^\}\n", text, re.S | re.M).group(0)


def write_settings(usb, key, raw) -> None:
    """A drive whose settings file sets `key` to `raw`, or none when raw is None."""
    path = Path(usb) / "RX3_RUNTIME" / "settings.cfg"
    if raw is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"version = 1\n{key} = {raw.strip()}\n", encoding="utf-8")


def run_shell(body: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-s", "--", str(MODULE_API)],
        input=HARNESS + body,
        text=True,
        capture_output=True,
        check=False,
    )


class ModuleApiTests(unittest.TestCase):
    def setting(self, content, key, fallback="d"):
        """What module_setting prints for `key` on a drive holding `content`."""
        with tempfile.TemporaryDirectory() as usb:
            if content is not None:
                runtime = Path(usb) / "RX3_RUNTIME"
                runtime.mkdir()
                data = content if isinstance(content, bytes) else content.encode()
                (runtime / "settings.cfg").write_bytes(data)
            result = run_shell(f"USB={shlex.quote(usb)}\n"
                               f"module_setting {shlex.quote(key)} {shlex.quote(fallback)}\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_settings_file_is_read_as_data_with_its_rules(self):
        self.assertEqual(self.setting(None, "a.b"), "d")
        self.assertEqual(self.setting("version = 1\na.b = 4\n", "a.b"), "4")
        self.assertEqual(self.setting("version = 1\r\n  a.b=4  \r\n", "a.b"), "4")
        self.assertEqual(self.setting("version = 1\na.b = 4\na.b = 7\n", "a.b"), "7")
        self.assertEqual(self.setting("version = 1\n# a.b = 4\n", "a.b"), "d")
        self.assertEqual(self.setting("version = 1\na.bc = 4\n", "a.b"), "d")
        # Not a settings file: no version, another version, or too large.
        self.assertEqual(self.setting("a.b = 4\n", "a.b"), "d")
        self.assertEqual(self.setting("version = 2\na.b = 4\n", "a.b"), "d")
        self.assertEqual(self.setting("version = 1\na.b = 4\n" + "#" * 65536, "a.b"), "d")
        # A value is text for the module to validate, never shell code.
        self.assertEqual(self.setting("version = 1\na.b = $(touch injected) x\n", "a.b"),
                         "$(touch injected) x")

    def test_summary_exports_selected_module_count_and_image_version(self):
        with tempfile.TemporaryDirectory() as directory:
            version = Path(directory) / "toolkit-version"
            version.write_text("0.5.2-90-gb730f95\n", encoding="ascii")
            result = run_shell(
                f'RX3_ISO_ROOT={shlex.quote(directory)}\n'
                'module_begin compatibility compatibility || exit 10\n'
                'module_begin core core || exit 11\n'
                'module_begin stems stems || exit 12\n'
                'module_begin logging logging || exit 13\n'
                'DISABLED_MODULES=" stems"\n'
                'rbp_environment_value() { :; }\n'
                'reconcile_module_set || exit 14\n'
                '[ "$RX3_ACTIVE_MODULES" = 1 ] || exit 15\n'
                '[ "$RX3_TOOLKIT_VERSION" = 0.5.2-90-gb730f95 ] || exit 16\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_summary_exports_utility_rows_for_loaded_modules_only(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "modules").mkdir()
            (Path(directory) / "modules/utility").write_text(
                "stems|STEMS|8351ffc\n"
                "logging|TROUBLESHOOTING REPORT|1d824ea+\n"
                "keyshift|KEY SHIFT|3f2a9c1\n"
                "telnet|BAD;ROW|1234567\n",
                encoding="ascii",
            )
            result = run_shell(
                f'RX3_ISO_ROOT={shlex.quote(directory)}\n'
                'module_begin core core || exit 10\n'
                'module_begin stems stems || exit 11\n'
                'module_begin logging logging || exit 12\n'
                'module_begin telnet telnet || exit 13\n'
                'DISABLED_MODULES=" stems"\n'
                'module_inactive logging\n'
                'rbp_environment_value() { :; }\n'
                'reconcile_module_set || exit 14\n'
                'printf "%s" "$RX3_UTILITY_ROWS"\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            # Switched off and loaded-but-idle both read OFF.
            self.assertEqual(
                result.stdout.splitlines()[-1],
                "STEMS|OFF 8351ffc;TROUBLESHOOTING REPORT|OFF 1d824ea+",
            )

    def test_utility_rows_carry_switches_and_declared_options(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "modules").mkdir()
            (Path(directory) / "modules/utility").write_text(
                "key-sync|KEY SYNC|abc1234|1\n"
                "logo|LOGO|0123456|0\n"
                "samples|SAMPLES|1111111|1\n"
                "browse-columns|THIRD BROWSE COLUMN|2222222|1\n",
                encoding="ascii",
            )
            (Path(directory) / "modules/settings").write_text(
                "key-sync|range|SYNC RANGE|1|RX3_KEY_SYNC_RANGE|1=1 SEMITONE,2=2 SEMITONES\n"
                "key-sync|mode|SYNC MODE|1|PATH|harmonic=NEAREST MATCH\n"
                "key-sync|gone|GONE|1|RX3_NOT_EXPORTED|1=ONE,2=TWO\n"
                "key-sync|odd|ODD|2|RX3_KEY_SYNC_RANGE|1=ONE,2=TWO\n"
                "browse-columns|column|THIRD COLUMN|0|RX3_BROWSE_FIELD|13=BPM,7=ARTIST\n",
                encoding="ascii",
            )
            result = run_shell(
                f'RX3_ISO_ROOT={shlex.quote(directory)}\n'
                'for m in core key-sync logo samples browse-columns; do module_begin $m x || exit 10; done\n'
                'DISABLED_MODULES=" browse-columns"\n'
                'module_inactive samples\n'
                'export RX3_KEY_SYNC_RANGE=2 RX3_BROWSE_FIELD=13\n'
                'rbp_environment_value() { :; }\n'
                'reconcile_module_set || exit 14\n'
                'printf "%s" "$RX3_UTILITY_ROWS"\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            # An option follows its module only while the module runs; a name
            # outside RX3_, an unset value or an odd field drops the option.
            self.assertEqual(result.stdout.splitlines()[-1].split(";"), [
                "KEY SYNC|abc1234|key-sync.enabled|0|on|on=ON,off=OFF",
                "  SYNC RANGE||key-sync.range|1|2|1=1 SEMITONE,2=2 SEMITONES",
                "LOGO|ON 0123456",
                "SAMPLES|OFF 1111111",
                "THIRD BROWSE COLUMN|2222222|browse-columns.enabled|0|off|on=ON,off=OFF",
            ])

    def test_the_drive_can_switch_a_module_off(self):
        for value, disabled in (("off", True), ("on", False), ("OFF", False)):
            with tempfile.TemporaryDirectory() as usb:
                write_settings(usb, "stems.enabled", value)
                result = run_shell(
                    f"USB={shlex.quote(usb)}\n"
                    "module_switch_path() { printf '%s/none' \"$USB\"; }\n"
                    "module_disabled_by_switch stems; echo \"rc=$? [$DISABLED_MODULES]\"\n"
                )
                self.assertEqual(result.stdout.strip(),
                                 "rc=0 [ stems]" if disabled else "rc=1 []", value)

    def merge(self, existing, pending):
        """settings.cfg after the deck merges `pending` into `existing` bytes."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "settings.cfg"
            if existing is not None:
                target.write_bytes(existing)
            (Path(directory) / "pending").write_bytes(pending)
            result = run_shell(f"settings_merge {shlex.quote(directory)}/pending "
                               f"{shlex.quote(str(target))}; echo \"rc=$?\"\n")
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),
                             sorted({"pending"} | ({"settings.cfg"} if target.exists() else set())))
            return result.stdout.strip(), target.read_bytes() if target.exists() else None

    def test_utility_changes_merge_into_the_settings_file(self):
        rc, data = self.merge(
            b"# mine\r\nversion = 1\r\ntheme-white.mode = dark\r\nkey-sync.range = 2\r\n"
            b"guard.stems = off\r\nkey-sync.range = 5\r\n",
            b"key-sync.range = 7\nnot a setting\nKEY.x = 1\nstems.enabled = off\nx.y = a b\n")
        self.assertEqual(rc, "rc=0")
        self.assertEqual(data, b"# mine\nversion = 1\ntheme-white.mode = dark\n"
                               b"key-sync.range = 7\nguard.stems = off\nstems.enabled = off\n")
        self.assertEqual(self.merge(None, b"key-sync.mode = identical\n"),
                         ("rc=0", b"version = 1\nkey-sync.mode = identical\n"))
        # Nothing to merge leaves even a missing file missing.
        self.assertEqual(self.merge(None, b""), ("rc=0", None))
        # A file the deck would not read is never rewritten.
        for content in (b"key-sync.range = 2\n", b"version = 2\n", b"",
                        b"version = 1\n" + b"#" * 65536):
            self.assertEqual(self.merge(content, b"key-sync.range = 3\n"), ("rc=1", content))

    def test_the_writer_saves_pending_changes_until_a_newer_one_takes_over(self):
        with tempfile.TemporaryDirectory() as directory:
            usb = Path(directory) / "usb"
            (usb / "RX3_RUNTIME").mkdir(parents=True)
            pending, token = Path(directory) / "pending", Path(directory) / "token"
            script = (
                f"USB={shlex.quote(str(usb))}\n"
                f"SETTINGS_PENDING={shlex.quote(str(pending))}\n"
                f"SESSION_WATCHER={shlex.quote(str(token))}\n"
                "start_session_watcher '' || exit 10\n"
                "until [ -s \"$SESSION_WATCHER\" ]; do :; done\n"
                "printf 'key-sync.range = 4\\n' > \"$SETTINGS_PENDING\"\n"
                "for i in 1 2 3 4 5 6 7 8 9 10; do\n"
                "  [ -e \"$USB/RX3_RUNTIME/settings.cfg\" ] && [ ! -e \"$SETTINGS_PENDING\" ] && break\n"
                "  sleep 0.5\n"
                "done\n"
                "cat \"$USB/RX3_RUNTIME/settings.cfg\"\n"
                "echo other > \"$SESSION_WATCHER\"; sleep 1.5\n"
                "printf 'key-sync.range = 9\\n' > \"$SETTINGS_PENDING\"; sleep 1.5\n"
                "cat \"$USB/RX3_RUNTIME/settings.cfg\"; ls \"$SETTINGS_PENDING\"\n"
            )
            result = run_shell(script)
            self.assertEqual(result.stdout.splitlines(),
                             ["version = 1", "key-sync.range = 4",
                              "version = 1", "key-sync.range = 4", str(pending)],
                             result.stderr)

    CRASH_HARNESS = (
        'P=$(mktemp -d); PROC_ROOT=$P; echo "100.00 1.00" > $P/uptime\n'
        'RUNTIME_PRELOAD_ENTRIES=" /root/pdj/librx3_core.so"\n'
        'RBP_PRELOAD=/root/pdj/librx3_core.so; RBP_RESTORE_OUTPUT=/dev/null; NEW=10\n'
        'say() { echo "say: $*"; }\n'
        'rbp_alive() { [ -e "$P/alive.$1" ]; }\n'
        'launch_rbp() { NEW=$((NEW + 1)); : > "$P/alive.$NEW"; echo "launch $NEW ${RBP_PRELOAD:-none}"; }\n'
        'announce_media() { echo "announce $NEW"; }\n'
        'at() { echo "$1.00 1.00" > $P/uptime; }\n'
    )

    def test_a_dead_player_is_relaunched_then_relaunched_without_the_mods(self):
        result = run_shell(self.CRASH_HARNESS + (
            '_rx3_rbp=10; _rx3_crashed_at=; _rx3_without_mods=0\n'
            'rbp_relaunch_after_crash; echo "watching ${_rx3_rbp:-none}"\n'
            'at 800; rbp_relaunch_after_crash\n'      # long after: as it was
            'at 900; rbp_relaunch_after_crash\n'      # again soon: no mods
            'at 950; rbp_relaunch_after_crash; echo "watching ${_rx3_rbp:-none}"\n'
        ))
        lines = [line for line in result.stdout.splitlines() if not line.startswith("say: ")]
        self.assertEqual(lines, [
            "launch 11 /root/pdj/librx3_core.so", "announce 11", "watching 11",
            "launch 12 /root/pdj/librx3_core.so", "announce 12",
            "launch 13 none", "announce 13",
            "watching none",
        ], result.stderr)
        self.assertIn("say: STOP: rbp pid 13 died again without the mods; not relaunched",
                      result.stdout)

    def test_the_watcher_leaves_the_player_alone_while_an_insertion_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            usb = Path(directory) / "usb"
            (usb / "RX3_RUNTIME").mkdir(parents=True)
            result = run_shell(self.CRASH_HARNESS + (
                f"USB={shlex.quote(str(usb))}\n"
                f"LOCK={shlex.quote(directory)}/lock; mkdir $LOCK\n"
                f"SESSION_WATCHER={shlex.quote(directory)}/token\n"
                f"SETTINGS_PENDING={shlex.quote(directory)}/pending\n"
                f"OUT={shlex.quote(directory)}/out\n"
                'echo me > $SESSION_WATCHER\n'
                'session_watcher me 10 > $OUT 2>&1 &\n'
                'sleep 2.5; echo "locked: $(grep -c ^launch $OUT)"\n'
                'rmdir $LOCK; sleep 2.5; echo "unlocked: $(grep -c ^launch $OUT)"\n'
                'echo other > $SESSION_WATCHER; wait\n'
            ))
            self.assertEqual(result.stdout.splitlines(), ["locked: 0", "unlocked: 1"],
                             result.stderr)

    def test_logo_without_artwork_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory) / "librx3_core.so"
            core.write_bytes(b"")
            (Path(directory) / "modules/logo").mkdir(parents=True)
            result = run_shell(
                f'RX3_ISO_ROOT={shlex.quote(directory)}\n'
                f'CORE_OBJECT={shlex.quote(str(core))}\n'
                '. "${1%/lib/module-api.sh}/modules/logo/module.sh" || exit 10\n'
                'logo_prepare || exit 11\n'
                '[ "$LOGO_READY" = 0 ] || exit 12\n'
                '[ -z "${RX3_LOGO:-}" ] || exit 13\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_image_without_a_version_still_loads_and_exports_the_count(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_shell(
                f'RX3_ISO_ROOT={shlex.quote(directory)}\n'
                'module_begin core core || exit 10\n'
                'module_begin logging logging || exit 11\n'
                'rbp_environment_value() { :; }\n'
                'reconcile_module_set || exit 12\n'
                '[ "$RX3_ACTIVE_MODULES" = 1 ] || exit 13\n'
                '[ -z "$RX3_TOOLKIT_VERSION" ] || exit 14\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_removed_or_switched_off_module_requests_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            switch = Path(directory) / "stems.off"
            switch.write_text("")
            result = run_shell(
                'module_begin core core || exit 10\n'
                'module_begin stems stems || exit 11\n'
                'running="core stems|"\n'
                # The running player already carries this summary.
                'rbp_environment_value() { case $1 in\n'
                '  RX3_RUNTIME_MODULE_SET) printf %s "$running" ;;\n'
                '  RX3_ACTIVE_MODULES) printf 1 ;; esac; }\n'
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

    def test_core_preload_keeps_order_and_preserves_other_libraries(self):
        result = run_shell(
            r'''
. "${1%/lib/module-api.sh}/modules/core/module.sh" || exit 9
RBP_PRELOAD="/opt/vendor.so:/root/pdj/librx3_core.so:/root/pdj/librx3_stems.so:/root/pdj/librx3_core.so"
core_normalize_preload || exit 10
[ "$RBP_PRELOAD" = "/opt/vendor.so:/root/pdj/librx3_core.so:/root/pdj/librx3_stems.so" ] || exit 11
RBP_PRELOAD="/opt/vendor.so:/root/pdj/librx3_stems.so"
core_normalize_preload || exit 12
[ "$RBP_PRELOAD" = "/opt/vendor.so:/root/pdj/librx3_stems.so:/root/pdj/librx3_core.so" ] || exit 13
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
