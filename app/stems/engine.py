# SPDX-License-Identifier: MPL-2.0
"""Lifecycle and configuration of the local separation engine."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from app.stems.separation import COMMON_OPTIONS, ARCHITECTURE_OPTIONS, ROLE_STEMS
from app.stems import processes

PREFIX = "\x1eRX3:"


def configuration(settings, architecture, roles, runtime, acceleration):
    settings.arguments(architecture)  # Apply the same validation as the CLI.
    options = {"model_file_dir": str(runtime.models), "output_format": "WAV",
               "sample_rate": 44100, "output_single_stem": "Vocals" if tuple(roles) == ("vocals",) else None,
               "use_directml": "--use_directml" in acceleration.separation_flags}
    names = {"normalization": "normalization_threshold", "amplification": "amplification_threshold",
             "invert_spect": "invert_using_spec"}
    for option in COMMON_OPTIONS:
        options[names.get(option.name, option.name)] = settings.value(option)
    for family, prefix in (("MDX", "mdx"), ("MDXC", "mdxc"), ("Demucs", "demucs"), ("VR", "vr")):
        if architecture == family:
            options[prefix + "_params"] = {o.name.removeprefix(prefix + "_"): settings.value(o)
                                            for o in ARCHITECTURE_OPTIONS[family]}
            if family == "Demucs":
                options["demucs_params"]["segments_enabled"] = True
    return {"model": settings.model, "options": options, "preserve_output_gain": True}


def interpreter(runtime):
    if runtime.separator is None:
        raise RuntimeError("Separation runtime is missing")
    scripts = runtime.separator.resolve().parent
    for candidate in (scripts / "python", scripts / "python.exe", scripts.parent / "python.exe"):
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Cannot locate Python beside {runtime.separator}")


class OutputError(RuntimeError):
    def __init__(self, role, count):
        self.role, self.count = role, count
        super().__init__(f"Expected one {role} output, found {count}")


class AudioSeparatorEngine:
    """One serial worker per preparation job, loaded lazily on a cache miss."""

    def __init__(self, runtime, config):
        self.runtime, self.config = runtime, config
        self.process = None

    def submit(self, source, output):
        if self.process is None or self.process.poll() is not None:
            self.close()
            worker = (pathlib.Path(sys._MEIPASS) / "worker.py" if getattr(sys, "frozen", False)
                      else pathlib.Path(__file__).with_name("worker.py"))
            self.process = processes.start(
                [str(interpreter(self.runtime)), "-u", str(worker)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                env=self.runtime.subprocess_environment())
        self.process.stdin.write(json.dumps({"source": str(source), "output": str(output),
                                           "configuration": self.config}) + "\n")
        self.process.stdin.flush()
        return self.process

    def outputs(self, workspace, roles):
        """Expose roles independently of audio-separator's naming convention."""
        candidates = sorted(workspace.rglob("*.wav"))
        result = {}
        for role in roles:
            matches = (candidates if tuple(roles) == ("vocals",) else
                       [p for p in candidates if f"({ROLE_STEMS[role]})".casefold() in p.name.casefold()])
            if len(matches) != 1:
                raise OutputError(role, len(matches))
            result[role] = matches[0]
        return result

    def close(self):
        process, self.process = self.process, None
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    process.stdin.write('{"action":"close"}\n')
                    process.stdin.flush()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    processes.stop(process)
        finally:
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()


def model_identity(runtime, settings):
    """Hash installed model assets, including Demucs submodels and YAML config."""
    import hashlib
    from app.stems.separation import parse_catalogue
    files = {runtime.models / pathlib.Path(settings.model).name}
    try:
        catalogue = parse_catalogue(json.loads((runtime.models.parent / "models.json").read_text()))
        model = catalogue.by_filename(settings.model)
        if model:
            files.update(model.local_files(runtime.models))
    except (OSError, ValueError, TypeError):
        pass
    result = {}
    for path in sorted(files):
        try:
            with path.open("rb") as source:
                result[path.name] = hashlib.file_digest(source, "sha256").hexdigest()
        except FileNotFoundError:
            result[path.name] = None
    return result


def runtime_identity(runtime):
    """Cache provenance includes the actual engine, including external installs."""
    if runtime.separator is None:
        return {"adapter": 2}
    query = '''import importlib.metadata as m, json
result = {}
for name in ('audio-separator', 'torch', 'onnxruntime', 'onnxruntime-gpu', 'onnxruntime-directml', 'librosa', 'imageio-ffmpeg'):
    try: result[name] = m.version(name)
    except m.PackageNotFoundError: pass
print(json.dumps(result))
'''
    answer = processes.run([str(interpreter(runtime)), '-c', query],
                           capture_output=True, text=True, timeout=10, check=True)
    return {"adapter": 2, "packages": json.loads(answer.stdout)}
