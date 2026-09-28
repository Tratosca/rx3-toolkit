# SPDX-License-Identifier: MPL-2.0
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.services import keyshift
from app.ui.bridge import Bridge
from app.runtime import build
from app.localization import LocalizedError

class KeySyncSettingsTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node runs the UI event tests')
    def test_ui_setting_events_and_persistence(self):
        result = subprocess.run(['node', 'tests/key_sync_settings.cjs'],
                                capture_output=True, text=True, timeout=15,
                                env={**os.environ, 'RX3_TEST_PYTHON': sys.executable})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_default_range_and_validation(self):
        self.assertEqual(keyshift.files(), {"sync-range.txt": b"1\n", "sync-mode.txt": b"harmonic\n"})
        for value in (1, 2, 12):
            self.assertEqual(keyshift.files(value)["sync-range.txt"], f"{value}\n".encode())
        for value in (None, True, 0, 13, 1.5, "2", "$(id)"):
            with self.assertRaises(LocalizedError): keyshift.files(value)

    def test_mode_validation(self):
        self.assertEqual(keyshift.files(1, 'harmonic')['sync-mode.txt'], b'harmonic\n')
        for value in (None, True, 1, 'bogus', '$(id)'):
            with self.assertRaises(LocalizedError): keyshift.files(1, value)

    def test_toolkit_setting_reaches_the_runtime_build(self):
        bridge=Bridge()
        result=SimpleNamespace(output="autoexec.bin", size=1, sha256="x", patches=("keyshift",))
        with patch('app.ui.bridge.build_module.build_runtime', return_value=result) as writer, patch.object(bridge, '_settle'):
            bridge._build('1.19',['key-sync'],pathlib.Path('key'),pathlib.Path('.'),None,build.Cancellation(),3,'harmonic')
        self.assertEqual(writer.call_args.kwargs['supplied_files'], {'key-sync': {'sync-range.txt': b'3\n', 'sync-mode.txt': b'harmonic\n'}, 'key-match': {'rules.txt': b'0\n'}})
        selected=build.resolve_patches(build.discover_patches(None,'1.19'),['key-sync'])
        self.assertEqual(build._validate_supplied_files(writer.call_args.kwargs['supplied_files'],selected),
                         {'key-sync': {'sync-range.txt': b'3\n', 'sync-mode.txt': b'harmonic\n'}, 'key-match': {'rules.txt': b'0\n'}})

    def test_manual_shift_enables_sync_only_for_selected_dependencies(self):
        script=pathlib.Path('mod/modules/keyshift/module.sh').read_text()
        with tempfile.TemporaryDirectory() as temp:
            core=pathlib.Path(temp)/'core';core.write_bytes(b'x')
            for loaded, disabled, expected in [('core keyshift', '', '0'),
                    ('core key-match keyshift key-sync', '', '1'),
                    ('core key-match keyshift key-sync', 'key-sync', '0'),
                    ('core key-match keyshift key-sync', 'key-match', '0')]:
                prefix=f'CORE_OBJECT="{core}"\nLOADED_MODULES="{loaded}"\nDISABLED="{disabled}"\n' + r'''
module_begin(){ :; }
register_prepare_hook(){ :; }
register_after_launch_hook(){ :; }
module_disabled_by_switch(){ [ "$1" = "$DISABLED" ]; }
say(){ :; }
module_export(){ printf '%s=%s\n' "$1" "$2"; }
'''
                result=subprocess.run(['sh'],input=prefix+script+'\nkeyshift_prepare\n',text=True,capture_output=True,check=True)
                self.assertIn('RX3_KEY_SYNC='+expected+'\n',result.stdout)

    def test_module_exports_setting_and_defaults_without_executing_data(self):
        import subprocess
        script=pathlib.Path('mod/modules/key-sync/module.sh').read_text()
        with tempfile.TemporaryDirectory() as temp:
            config=pathlib.Path(temp)/'range'
            core=pathlib.Path(temp)/'core';core.write_bytes(b'x')
            script=script.replace('/mnt/iso/modules/key-sync/sync-range.txt',str(config))
            mode=pathlib.Path(temp)/'mode'
            script=script.replace('/mnt/iso/modules/key-sync/sync-mode.txt',str(mode))
            prefix=f'CORE_OBJECT="{core}"\n' + '''module_begin(){ :; }
register_prepare_hook(){ :; }
register_after_launch_hook(){ :; }
module_disabled_by_switch(){ return 1; }
say(){ :; }
module_export(){ printf '%s=%s\\n' "$1" "$2"; }
'''
            for raw,expected in ((None,1),('4\n',4),('12\n',12),('0\n',1),('$(touch injected)\n',1)):
                if raw is not None: config.write_text(raw)
                result=subprocess.run(['sh'],input=prefix+script+'\nkey_sync_prepare\n',text=True,capture_output=True,check=True,cwd=temp)
                self.assertIn(f'RX3_KEY_SYNC_RANGE={expected}\n',result.stdout)
                self.assertFalse((pathlib.Path(temp)/'injected').exists())
            for raw,expected in ((None,'identical'),('harmonic','harmonic'),('identical','identical'),('$(touch injected)','identical')):
                if raw is not None: mode.write_text(raw+'\n')
                result=subprocess.run(['sh'],input=prefix+script+'\nkey_sync_prepare\n',text=True,capture_output=True,check=True,cwd=temp)
                self.assertIn(f'RX3_KEY_SYNC_MODE={expected}\n',result.stdout)
                self.assertFalse((pathlib.Path(temp)/'injected').exists())
