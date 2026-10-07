"""Exercise an actual FLAC seek through the bounded deck-file/HTTP path."""
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
import json
from urllib.request import Request, urlopen
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from remote_metadata import audio_range, audio_stat  # noqa: E402
from td_gateway import Gateway, handler_for  # noqa: E402


@unittest.skipUnless(shutil.which("clang") and shutil.which("ffmpeg"),
                     "clang and ffmpeg are needed for the codec boundary test")
class AudioExcerptProxyTests(unittest.TestCase):
    def test_flac_interior_excerpt_uses_less_than_whole_file(self):
        root_source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            music = root / "Contents/fixture.flac"
            music.parent.mkdir()
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                            "-i", "anoisesrc=d=45:c=white", "-ar", "44100", "-ac", "2",
                            str(music)], check=True)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            binary = root / "server"
            subprocess.run(["clang", "-DLOCAL_TEST", f"-DMETADATA_PORT={port}",
                            "-O2", "-Wall", "-Wextra", "-Werror",
                            str(root_source / "mod/lib/metadata_server.c"),
                            "-o", str(binary)], check=True)

            class Catalog:
                manifest = {"export_pdb_sha256": "fixture"}
                tracks = {"1": {"metadata": {"title": "Fixture", "duration_s": 45},
                                "asset": None}}
                transferred = 0

                def audio_stat(self, _):
                    return audio_stat("127.0.0.1", "/Contents/fixture.flac", port)

                def audio_range(self, _, offset, count):
                    data, size = audio_range("127.0.0.1", "/Contents/fixture.flac",
                                             offset, count, port)
                    self.transferred += len(data)
                    return data, size

            process = subprocess.Popen([str(binary), str(root)])
            try:
                catalog = Catalog()
                for _ in range(50):
                    try:
                        catalog.audio_stat(1)
                        break
                    except OSError:
                        time.sleep(.02)
                else:
                    self.fail("file helper did not listen")
                gateway = Gateway(catalog, 1, "127.0.0.1", 4470)
                http = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(gateway))
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                try:
                    url = f"http://127.0.0.1:{http.server_port}/samples/1"
                    body = json.dumps({"start_s": 30, "duration_s": 4}).encode()
                    with urlopen(Request(url, data=body,
                                         headers={"Content-Type": "application/json"}),
                                 timeout=35) as response:
                        result = json.load(response)
                    self.assertEqual(result["source"], "sampled_source_file_pre_fader")
                    self.assertEqual(len(result["windows"]), 16)
                    self.assertGreater(catalog.transferred, 0)
                    self.assertLess(catalog.transferred, music.stat().st_size)
                    self.assertLessEqual(catalog.transferred, 8 * 1024 * 1024)
                finally:
                    http.shutdown(); http.server_close(); gateway.close()
                    thread.join(timeout=2)
            finally:
                process.terminate(); process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
