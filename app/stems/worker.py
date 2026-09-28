# SPDX-License-Identifier: MPL-2.0
"""Private audio-separator worker; run with the separation runtime's Python.

One model per process. JSON commands arrive on stdin; logs retain their native
progress output and framed JSON marks the completion of each request.
"""
import contextlib
import json
import sys
import traceback

PREFIX = "\x1eRX3:"


def preserve_output_gain(model):
    """Export the model's amplitude unchanged; the container carries headroom."""
    import pathlib
    import types
    def write_audio(self, stem_path, samples):
        import numpy as np
        import soundfile as sf
        if not np.isfinite(samples).all():
            raise ValueError("Non-finite separator output")
        path = pathlib.Path(self.output_dir) / stem_path
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), samples, self.sample_rate, subtype="FLOAT")
    model.write_audio = types.MethodType(write_audio, model)


def serve(stream=sys.stdin, output=sys.stdout, factory=None):
    separator = None
    configuration = None
    for line in stream:
        try:
            request = json.loads(line)
            if request.get("action") == "close":
                return
            config = request["configuration"]
            with contextlib.redirect_stdout(sys.stderr):
                if factory is None:
                    from audio_separator.separator import Separator
                    factory = Separator
                if separator is None:
                    separator = factory(**config["options"], output_dir=request["output"])
                    separator.load_model(model_filename=config["model"])
                    if config.get("preserve_output_gain"):
                        preserve_output_gain(separator.model_instance)
                    configuration = config
                elif configuration != config:
                    raise ValueError("A worker cannot change its separation configuration")
                separator.output_dir = request["output"]
                separator.model_instance.output_dir = request["output"]
                files = separator.separate(request["source"])
                if not files:
                    raise RuntimeError("The separator produced no audio files; inspect the preceding engine error")
            result = {"ok": True}
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            result = {"ok": False, "error": str(error)}
        print("\n" + PREFIX + json.dumps(result), file=output, flush=True)
        if not result["ok"]:
            return  # A failed model is never reused for the next track.


if __name__ == "__main__":
    serve()
