# SPDX-License-Identifier: MPL-2.0
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from app.stems import processes, provisioning
from app.ui.bridge import Bridge


class ProcessTests(unittest.TestCase):
    def test_silent_process_is_cancelled_and_reaped(self):
        control = processes.Control()
        with control.bind():
            process = processes.start([sys.executable, '-c', 'import time; time.sleep(60)'], stdout=subprocess.PIPE)
            started = time.monotonic()
            control.cancel()
            self.assertIsNotNone(process.poll())
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(process.stdout.read(), b'')
            process.stdout.close()
            with self.assertRaises(processes.Cancelled):
                processes.start([sys.executable, '-c', 'pass'])

    @unittest.skipIf(os.name == 'nt', 'POSIX process groups')
    def test_stubborn_worker_and_child_are_stopped(self):
        code = '''import signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], stdout=sys.stdout)
print('ready', flush=True)
time.sleep(60)
'''
        control = processes.Control()
        with control.bind():
            process = processes.start([sys.executable, '-c', code], stdout=subprocess.PIPE)
            self.assertEqual(process.stdout.readline(), b'ready\n')
            control.cancel()
            # The child inherited the pipe: EOF also proves it released it.
            output = []
            reader = threading.Thread(target=lambda: output.append(process.stdout.read()), daemon=True)
            reader.start(); reader.join(3)
            self.assertFalse(reader.is_alive())
            self.assertEqual(output, [b''])
            process.stdout.close()

    def test_installation_cancel_does_not_report_success(self):
        control = processes.Control()
        ready = threading.Event()
        errors = []
        def install():
            try:
                with control.bind():
                    provisioning._stream([sys.executable, '-u', '-c',
                        "import time; print('ready'); time.sleep(60)"],
                        lambda line: ready.set() if ': ready' in line else None, 'install')
            except processes.Cancelled:
                errors.append('cancelled')
        thread = threading.Thread(target=install, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(5))
        control.cancel(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ['cancelled'])

    def test_decode_cancellation_propagates(self):
        control = processes.Control()
        with control.bind():
            timer = threading.Timer(0.2, control.cancel)
            timer.start()
            try:
                with self.assertRaises(processes.Cancelled):
                    processes.run([sys.executable, '-c', 'import time; time.sleep(60)'], capture_output=True)
            finally:
                timer.join()

    def test_window_waits_for_cleanup_before_closing(self):
        bridge = Bridge()
        closed = threading.Event()
        window = Mock()
        window.destroy.side_effect = closed.set
        window.create_confirmation_dialog.return_value = True
        bridge._attach(window)
        bridge._claim('stems', 'working')
        stopped = threading.Event()
        bridge._watch(stopped.set)
        self.assertFalse(bridge._on_closing())
        self.assertTrue(stopped.wait(2))
        self.assertFalse(closed.is_set())
        bridge._settle('cancelled', 'stopped')
        self.assertTrue(closed.wait(2))
        self.assertTrue(bridge._on_closing())

    def test_declining_close_preserves_task_and_preview(self):
        bridge = Bridge()
        window = Mock()
        window.create_confirmation_dialog.return_value = False
        bridge._attach(window)
        bridge._locale = "fr"
        bridge._claim('stems', 'working')
        stop = Mock()
        bridge._watch(stop)
        preview = Mock()
        bridge._preview = preview
        self.assertFalse(bridge._on_closing())
        stop.assert_not_called()
        preview.close.assert_not_called()
        window.destroy.assert_not_called()
        self.assertFalse(bridge._closing)
        self.assertEqual(bridge._job["state"], "running")
        self.assertIn("interrompra", window.create_confirmation_dialog.call_args.args[1])
        bridge._settle('done', 'finished')
        self.assertTrue(bridge._on_closing())
        preview.close.assert_called_once()
        window.create_confirmation_dialog.assert_called_once()

    def test_cancel_before_registration_is_not_lost(self):
        bridge = Bridge(); bridge._claim('stems', 'working')
        bridge.job_cancel()
        stop = Mock(); bridge._watch(stop)
        stop.assert_called_once_with()

    def test_managed_separator_install_is_pinned_for_each_accelerator(self):
        for acceleration in provisioning.ACCELERATIONS.values():
            with patch.object(provisioning.sys, 'platform', 'linux'):
                commands = list(provisioning.install_packages(pathlib.Path('/runtime'), acceleration))
            command = commands[-1][1]
            self.assertIn(f'audio-separator[{acceleration.extra}]==0.44.5', command)
            self.assertIn('librosa==0.11.0', command)
            self.assertIn('imageio-ffmpeg==0.6.0', command)

    def test_interrupted_install_is_not_ready_until_completed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = provisioning.Runtime(root, root / 'models',
                provisioning._script(root, provisioning.SEPARATOR_COMMAND), root / 'ffmpeg')
            self.assertTrue(runtime.ready)
            (root / '.installing').touch()
            self.assertFalse(runtime.ready)
            (root / '.installing').unlink()
            self.assertTrue(runtime.ready)

    def test_mac_intel_installs_the_locked_set_for_the_current_separator(self):
        with patch.object(provisioning.sys, 'platform', 'darwin'), \
             patch.object(provisioning.platform, 'machine', return_value='x86_64'):
            command = list(provisioning.install_packages(pathlib.Path('/runtime'), provisioning.ACCELERATIONS['cpu']))[-1][1]
            self.assertEqual(provisioning.maximum_python(), (3, 12))
        self.assertEqual(command[-3:], ['--no-deps', '-r', str(provisioning.mac_intel_requirements())])
        # A separator bump that skips regenerating the set would leave Intel Macs
        # on another separator than every other platform.
        pins = set(provisioning.mac_intel_requirements().read_text().split())
        self.assertIn(f'audio-separator=={provisioning.SEPARATOR_VERSION}', pins)
        self.assertLessEqual(set(provisioning.SUPPORT_PACKAGES), pins)

    def test_mac_arm_installs_the_validated_inference_versions(self):
        with patch.object(provisioning.sys, 'platform', 'darwin'), \
             patch.object(provisioning.platform, 'machine', return_value='arm64'):
            command = list(provisioning.install_packages(pathlib.Path('/runtime'), provisioning.ACCELERATIONS['mps']))[-1][1]
        self.assertIn('torch==2.13.0', command)
        self.assertIn('onnxruntime==1.28.0', command)
