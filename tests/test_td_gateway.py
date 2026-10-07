import json
from pathlib import Path
import socket
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.request import Request
from urllib.error import HTTPError
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from td_gateway import Gateway, handler_for, osc_frames, td_values  # noqa: E402
from tests.test_prodjlink_bridge import BridgeTests, now_message, pos_message  # noqa: E402


class Catalog:
    manifest = {"export_pdb_sha256": "test-export"}
    tracks = {"7": {"metadata": {"title": "Test", "duration_s": 100},
                    "asset": {"grid": []}}}

    def audio_stat(self, track_id):
        if track_id != 7:
            raise KeyError(track_id)
        return 4096

    def audio_range(self, track_id, offset, count):
        if track_id != 7:
            raise KeyError(track_id)
        return bytes((offset + i) % 256 for i in range(count)), 4096


class GatewayTests(unittest.TestCase):
    def snapshot(self):
        state = BridgeTests().make_state()
        state.ingest("now-playing", now_message(), "169.254.1.2", 10.0)
        state.ingest("position-diagnostic", pos_message(), "169.254.1.2", 10.0)
        return state.snapshot(1, 10.1)

    def test_td_values_preserve_availability_and_manual_selection(self):
        snapshot = self.snapshot()
        values = td_values(snapshot, 1)
        prefix = "/vj/deck0/"
        self.assertEqual(values[prefix + "title"], "Test")
        self.assertEqual(values[prefix + "analysis/ready"], 1)
        self.assertEqual(values[prefix + "phrase/valid"], 1)
        self.assertEqual(values[prefix + "preview/weight"], 1)
        self.assertEqual(values[prefix + "audio/valid"], 0)
        self.assertEqual(values[prefix + "fader/valid"], 0)
        self.assertEqual(values[prefix + "audibility/valid"], 0)
        self.assertEqual(td_values(snapshot, 2)[prefix + "preview/weight"], 0)
        snapshot["timing"]["valid"] = False
        self.assertEqual(td_values(snapshot, 1)[prefix + "preview/weight"], 0)

    def test_osc_packets_are_bounded_coherent_frames(self):
        packets = osc_frames(self.snapshot(), 1, 42)
        self.assertGreater(len(packets), 1)
        self.assertTrue(all(len(packet) <= 1350 for packet in packets))
        self.assertTrue(all(packet.startswith(b"#bundle\0") for packet in packets))
        self.assertTrue(all(b"/vj/frame/parts" in packet for packet in packets))
        self.assertTrue(all(b"/vj/replay/session" in packet for packet in packets))

    def test_local_http_state_and_asset(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as osc:
            osc.bind(("127.0.0.1", 0))
            gateway = Gateway(Catalog(), 1, "127.0.0.1", osc.getsockname()[1])
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(gateway))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                gateway.publish(self.snapshot())
                osc.settimeout(2)
                self.assertTrue(osc.recv(1500).startswith(b"#bundle\0"))
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/state") as response:
                    state = json.load(response)
                self.assertEqual(state["decks"][0]["track"]["title"], "Test")
                with urlopen(base + "/assets/7") as response:
                    asset = json.load(response)
                self.assertEqual(asset["metadata"]["title"], "Test")
                with urlopen(Request(base + "/audio/7", method="HEAD")) as response:
                    self.assertEqual(response.headers["Content-Length"], "4096")
                with urlopen(Request(base + "/audio/7",
                                     headers={"Range": "bytes=250-260"})) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.headers["Content-Range"],
                                     "bytes 250-260/4096")
                    self.assertEqual(response.read(), bytes(range(250, 256)) +
                                     bytes(range(5)))
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/audio/7")
                self.assertEqual(error.exception.code, 416)
                error.exception.close()
                excerpt = {"source": "sampled_source_file_pre_fader",
                           "windows": [{"start_s": 0.25, "end_s": 0.75,
                                        "rms_dbfs": -12.0, "peak_dbfs": -3.0,
                                        "low": 0.4, "mid": 0.2, "high": 0.1,
                                        "onset": 0.3, "centroid_hz": 700}]}
                with patch("td_gateway.decode_url", return_value=excerpt):
                    body = json.dumps({"start_s": 0.25, "duration_s": 0.5}).encode()
                    with urlopen(Request(base + "/samples/7", data=body,
                                         headers={"Content-Type": "application/json"})) as response:
                        self.assertEqual(json.load(response)["windows"][0]["low"], 0.4)
                gateway.publish(self.snapshot())
                with urlopen(base + "/state") as response:
                    sampled = json.load(response)
                self.assertEqual(sampled["decks"][0]["audio"]["source"],
                                 "sampled_source_file_pre_fader")
                self.assertTrue(sampled["decks"][0]["audio"]["valid"])
                gateway.stale()
                with urlopen(base + "/state") as response:
                    stale = json.load(response)
                self.assertFalse(stale["decks"][0]["timing"]["valid"])
            finally:
                server.shutdown(); server.server_close(); gateway.close()
                thread.join(timeout=2)

    def test_concurrent_excerpt_jobs_do_not_compete_for_deck_reads(self):
        gateway = Gateway(Catalog(), 1, "127.0.0.1", 4470)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(gateway))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        entered = threading.Event()
        release = threading.Event()
        first_result = []
        body = json.dumps({"start_s": 1, "duration_s": 1}).encode()
        url = f"http://127.0.0.1:{server.server_port}/samples/7"

        def slow_decode(*_):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("test release never arrived")
            return {"windows": [], "source": "sampled_source_file_pre_fader"}

        def first_request():
            try:
                with urlopen(Request(url, data=body), timeout=4) as response:
                    first_result.append(response.status)
            except Exception as exc:
                first_result.append(exc)

        worker = threading.Thread(target=first_request)
        try:
            with patch("td_gateway.decode_url", side_effect=slow_decode):
                worker.start()
                self.assertTrue(entered.wait(2))
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(url, data=body), timeout=2)
                self.assertEqual(error.exception.code, 429)
                error.exception.close()
                release.set()
                worker.join(timeout=4)
                self.assertEqual(first_result, [200])
        finally:
            release.set()
            worker.join(timeout=4)
            server.shutdown(); server.server_close(); gateway.close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
