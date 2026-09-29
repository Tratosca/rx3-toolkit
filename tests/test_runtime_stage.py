# SPDX-License-Identifier: MPL-2.0
"""Startup resources remain private until commit and survive failed launches."""

import shlex
import tempfile
import unittest
from pathlib import Path

from tests.test_module_api import run_shell


def quoted(path: Path) -> str:
    return shlex.quote(str(path))


class RuntimeStageTests(unittest.TestCase):
    def test_failed_first_rename_does_not_delete_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "new", root / "live"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            setup = f'RUNTIME_STAGE_DIR={quoted(root / "stage")}\n'
            stage = f'stage_runtime_file {quoted(source)} {quoted(target)} || exit 10\n'
            body = (
                setup + stage +
                'mv() { return 1; }\n'
                'commit_runtime_stage && exit 11\n'
                'restore_runtime_stage || exit 12\n'
                'discard_runtime_stage\n'
            )
            result = run_shell(body)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), b"old")

            # A later insertion must still see the uninstalled generation and
            # be able to apply it after the failed attempt was rolled back.
            result = run_shell(setup + stage +
                               'commit_runtime_stage || exit 16\n'
                               'discard_runtime_stage\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), b"new")

    def test_deferred_change_leaves_live_file_and_commit_can_be_undone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            setup = f'RUNTIME_STAGE_DIR={quoted(root / "stage")}\n'
            stage = f'stage_runtime_file {quoted(source)} {quoted(target)} || exit 10\n'
            result = run_shell(setup + stage +
                               f'[ "$(cat {quoted(target)})" = old ] || exit 11\n'
                               'discard_runtime_stage\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), b"old")
            self.assertFalse((root / "stage").exists())

            result = run_shell(setup + stage +
                               f'[ "$(cat {quoted(target)})" = old ] || exit 12\n'
                               'commit_runtime_stage || exit 13\n'
                               f'[ "$(cat {quoted(target)})" = new ] || exit 14\n'
                               'restore_runtime_stage || exit 15\n'
                               'discard_runtime_stage\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), b"old")

    def test_partial_commit_restores_all_previous_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            new_first, new_second = root / "new-first", root / "new-second"
            first.write_bytes(b"old first")
            second.write_bytes(b"old second")
            new_first.write_bytes(b"new first")
            new_second.write_bytes(b"new second")
            body = (
                f'RUNTIME_STAGE_DIR={quoted(root / "stage")}\n'
                f'stage_runtime_file {quoted(new_first)} {quoted(first)} || exit 10\n'
                f'stage_runtime_file {quoted(new_second)} {quoted(second)} || exit 11\n'
                'mv() {\n'
                '    [ "$2" = "$RUNTIME_STAGE_DIR/new2" ] && return 1\n'
                '    command mv "$@"\n'
                '}\n'
                'commit_runtime_stage && exit 12\n'
                'restore_runtime_stage || exit 13\n'
                'discard_runtime_stage\n'
            )
            result = run_shell(body)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(first.read_bytes(), b"old first")
            self.assertEqual(second.read_bytes(), b"old second")
            self.assertFalse((root / "stage").exists())

    def test_removed_optional_resource_returns_on_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "light-art"
            target.write_bytes(b"old optional art")
            body = (
                f'RUNTIME_STAGE_DIR={quoted(root / "stage")}\n'
                f'stage_runtime_removal {quoted(target)} || exit 10\n'
                f'[ -e {quoted(target)} ] || exit 11\n'
                'commit_runtime_stage || exit 12\n'
                f'[ ! -e {quoted(target)} ] || exit 13\n'
                'restore_runtime_stage || exit 14\n'
                'discard_runtime_stage\n'
            )
            result = run_shell(body)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), b"old optional art")

    def test_rollback_restores_existing_symlink_without_following_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, original, target = root / "new", root / "original", root / "live"
            source.write_bytes(b"new")
            original.write_bytes(b"old")
            target.symlink_to(original)
            body = (
                f'RUNTIME_STAGE_DIR={quoted(root / "stage")}\n'
                f'stage_runtime_file {quoted(source)} {quoted(target)} || exit 10\n'
                'commit_runtime_stage || exit 11\n'
                'restore_runtime_stage || exit 12\n'
                'discard_runtime_stage\n'
            )
            result = run_shell(body)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), original.resolve())
