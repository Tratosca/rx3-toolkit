# SPDX-License-Identifier: MPL-2.0
"""A relaunched player whose audio output never starts is reported, not hidden."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "mod/autoexec.sh").read_text()


def function(name: str) -> str:
    match = re.search(rf"(?m)^{name}\(\)\n\{{\n.*?^\}}\n", SOURCE, re.DOTALL)
    assert match, name
    return match.group(0)


SCRIPT = "\n".join(function(name) for name in (
    "say", "rbp_alive", "running_playback_pcm", "check_audio_device"
))

STATUS = "state: {state}\ntrigger_time: 1.0\n-----\nhw_ptr      : {pointer}\nappl_ptr    : 0\n"


class RestartAudioCheckTests(unittest.TestCase):
    def run_check(self, *, state="RUNNING", moving=True):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / "proc"
            (proc / "4242/fd").mkdir(parents=True)
            (proc / "4242/exe").touch()
            (proc / "4242/stat").write_text("4242 (rbp) S 1 1 0\n")
            (proc / "4242/fd/7").symlink_to("/dev/snd/pcmC0D0p")
            status = proc / "asound/card0/pcm0p/sub0/status"
            status.parent.mkdir(parents=True)
            status.write_text(STATUS.format(state=state, pointer=100))
            log = Path(directory) / "log.txt"
            # The deck advances the pointer on its own; here each pause does.
            advance = (f'printf "{STATUS}" > "{status}"'.format(state=state, pointer=200)
                       if moving else ":")
            body = (f'PROC_ROOT="{proc}"\nNEW=4242\nLOGGING=1\nLOG="{log}"\n'
                    f"usleep() {{ {advance}; }}\n" + SCRIPT +
                    "\ncheck_audio_device\necho \"status=$?\" >> \"$LOG\"\n")
            result = subprocess.run(["sh", "-s"], input=body, text=True,
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return log.read_text()

    def test_moving_playback_pointer_is_reported_running(self):
        log = self.run_check()
        self.assertIn("audio output running: card0/pcm0p/sub0/status", log)
        self.assertIn("status=0", log)

    def test_stream_that_never_runs_is_a_failure_with_its_state(self):
        log = self.run_check(state="PREPARED")
        self.assertIn("FAILED: rbp pid 4242 has no running audio output", log)
        self.assertIn("card0/pcm0p/sub0/status: state: PREPARED", log)
        self.assertIn("rbp holds /dev/snd/pcmC0D0p", log)
        self.assertIn("status=1", log)

    def test_running_state_with_a_frozen_pointer_is_a_failure(self):
        self.assertIn("FAILED:", self.run_check(moving=False))

    def test_only_the_master_counts_when_the_players_card_is_present(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / "proc"
            (proc / "4242/fd").mkdir(parents=True)
            (proc / "4242/exe").touch()
            (proc / "4242/stat").write_text("4242 (rbp) S 1 1 0\n")
            card = proc / "asound/card1"
            for pcm, state in (("pcm0p", "PREPARED"), ("pcm1p", "RUNNING")):
                (card / pcm / "sub0").mkdir(parents=True)
                (card / pcm / "sub0/status").write_text(
                    STATUS.format(state=state, pointer=100))
            (card / "id").write_text("cs4344audiorev8\n")
            headphones = card / "pcm1p/sub0/status"
            log = Path(directory) / "log.txt"
            advance = f'printf "{STATUS}" > "{headphones}"'.format(state="RUNNING", pointer=200)
            body = (f'PROC_ROOT="{proc}"\nNEW=4242\nLOGGING=1\nLOG="{log}"\n'
                    f"usleep() {{ {advance}; }}\n" + SCRIPT + "\ncheck_audio_device\n")
            subprocess.run(["sh", "-s"], input=body, text=True, check=False)
            self.assertIn("FAILED:", log.read_text())

    def test_kernel_without_pcm_status_is_not_reported_as_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "log.txt"
            body = (f'PROC_ROOT="{directory}"\nNEW=4242\nLOGGING=1\nLOG="{log}"\n'
                    + SCRIPT + "\ncheck_audio_device\n")
            subprocess.run(["sh", "-s"], input=body, text=True, check=True)
            self.assertIn("audio check skipped", log.read_text())


if __name__ == "__main__":
    unittest.main()
