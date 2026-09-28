# SPDX-License-Identifier: MPL-2.0
import io
import contextlib
import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from app.stems import worker, separation, provisioning, engine


class EngineTests(unittest.TestCase):
    def test_worker_reuses_model_and_changes_output(self):
        calls = []
        class Separator:
            def __init__(self, **kw):
                calls.append(('init', kw))
                self.model_instance = SimpleNamespace(output_dir=kw['output_dir'])
            def load_model(self, **kw):
                calls.append(('load', kw))
            def separate(self, source):
                calls.append(('separate', source, self.output_dir, self.model_instance.output_dir))
                return ['stem.wav']
        config = {'model':'model', 'options':{}}
        commands = [{'configuration':config,'source':str(i),'output':f'/tmp/{i}'} for i in range(2)]
        output = io.StringIO()
        worker.serve(io.StringIO(''.join(json.dumps(x)+'\n' for x in commands)), output, Separator)
        self.assertEqual(sum(c[0]=='load' for c in calls),1)
        self.assertEqual([c[2:] for c in calls if c[0]=='separate'],[('/tmp/0','/tmp/0'),('/tmp/1','/tmp/1')])
        self.assertEqual(output.getvalue().count('"ok": true'),2)

    def test_worker_exits_after_failure(self):
        calls = []
        class Separator:
            def __init__(self, **kw): self.model_instance=SimpleNamespace()
            def load_model(self, **kw): pass
            def separate(self, source):
                calls.append(source)
                raise RuntimeError('GPU failed')
        command=json.dumps({'configuration':{'model':'m','options':{}},'source':'x','output':'out'})+'\n'
        output=io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()):
            worker.serve(io.StringIO(command*2),output,Separator)
        self.assertEqual(calls,['x'])
        self.assertIn('"ok": false',output.getvalue())

    def test_three_parts_resolve_on_cpu_and_gpu(self):
        models=separation.Catalogue(tuple(separation.Model('Demucs',n,n,('Vocals','Drums','Bass','Other'),None)
                                         for n in ('htdemucs.yaml','htdemucs_ft.yaml')))
        for accelerated in (False,True):
            resolved=[]
            for mode in ('quality','normal','quick'):
                s=separation.for_roles(separation.Settings(mode=mode),models,('vocals','drums'),accelerates_torch=accelerated)
                self.assertIn('drums',models.by_filename(s.model).roles)
                resolved.append((s.model,s.values['demucs_shifts']))
            self.assertEqual(resolved,[('htdemucs_ft.yaml',4),('htdemucs.yaml',2),('htdemucs.yaml',1)])

    def test_custom_model_is_not_replaced(self):
        s=separation.Settings().as_custom()
        self.assertEqual(separation.for_roles(s,separation.Catalogue(),('vocals','drums')),s)

    def test_identity_changes_with_weights_not_waveform(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            model=root/'model.ckpt';model.write_bytes(b'first')
            runtime=SimpleNamespace(models=root)
            settings=separation.Settings(model=model.name)
            before=engine.model_identity(runtime,settings)
            model.write_bytes(b'second')
            self.assertNotEqual(before,engine.model_identity(runtime,settings))

    def test_options_preserve_gain_and_architecture(self):
        runtime=SimpleNamespace(models=pathlib.Path('/tmp/models'))
        s=separation.Settings(values={'demucs_shifts':1,'mdxc_overlap':10})
        c=engine.configuration(s,'Demucs',('vocals','drums'),runtime,provisioning.ACCELERATIONS['cpu'])
        self.assertEqual(c['options']['normalization_threshold'],1)
        self.assertEqual(c['options']['demucs_params']['shifts'],1)
        self.assertNotIn('mdxc_params',c['options'])
        self.assertIsNone(c['options']['output_single_stem'])

    def test_process_restarts_after_failure_and_closes(self):
        import os
        import sys
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            module=root/'audio_separator';module.mkdir()
            (module/'__init__.py').write_text('')
            (module/'separator.py').write_text('''from types import SimpleNamespace
class Separator:
 def __init__(self, **kwargs): self.model_instance=SimpleNamespace()
 def load_model(self, **kwargs): pass
 def separate(self, source):
  if source == "bad": raise RuntimeError("failed")
  return ["stem.wav"]
''')
            env=dict(os.environ,PYTHONPATH=str(root))
            runtime=SimpleNamespace(subprocess_environment=lambda:env)
            current=engine.AudioSeparatorEngine(runtime,{'model':'test','options':{}})
            with patch.object(engine,'interpreter',return_value=pathlib.Path(sys.executable)):
                try:
                    first=current.submit('bad',root)
                    for line in first.stdout:
                        if line.startswith(engine.PREFIX):
                            self.assertFalse(json.loads(line[len(engine.PREFIX):])['ok']);break
                    first.wait(timeout=5)
                    second=current.submit('good',root)
                    self.assertNotEqual(first.pid,second.pid)
                    for line in second.stdout:
                        if line.startswith(engine.PREFIX):
                            self.assertTrue(json.loads(line[len(engine.PREFIX):])['ok']);break
                finally: current.close()
            self.assertIsNotNone(second.poll())

    def test_outputs_are_normalized_to_requested_roles(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp)
            for role in ("Vocals", "Drums", "Bass", "Other"):
                (root/f"track_({role})_model.wav").write_bytes(b"audio")
            current=engine.AudioSeparatorEngine(None,{})
            self.assertEqual(set(current.outputs(root,("vocals","drums"))),{"vocals","drums"})
            (root/'track_(Drums)_model.wav').unlink()
            with self.assertRaises(engine.OutputError):
                current.outputs(root,("vocals","drums"))
