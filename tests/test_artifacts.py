# SPDX-License-Identifier: MPL-2.0
"""The artifact resolver names roles, not origins."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "tools/rx3_artifacts.py"
SPEC = importlib.util.spec_from_file_location("rx3_artifacts", MODULE_PATH)
rx3_artifacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rx3_artifacts)


class ArtifactResolutionTests(unittest.TestCase):
    def setUp(self):
        # An operator's own artifacts.toml must not decide whether tests pass.
        patch = mock.patch.object(rx3_artifacts, "CONFIGURATION", Path("/nonexistent"))
        patch.start()
        self.addCleanup(patch.stop)

    def test_an_unconfigured_role_locates_nothing(self):
        """No invented default: a role nobody has configured has no path."""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(rx3_artifacts.locate("imagedata"))

    def test_environment_variable_wins(self):
        with mock.patch.dict(os.environ, {"RX3_IMAGE_DATA": "/tmp/somewhere"}):
            self.assertEqual(
                rx3_artifacts.locate("imagedata"), Path("/tmp/somewhere")
            )

    def test_configuration_is_read_when_no_variable_is_set(self):
        with tempfile.TemporaryDirectory() as directory:
            configuration = Path(directory) / "artifacts.toml"
            configuration.write_text('[artifacts]\nrbp = "/tmp/elsewhere"\n')
            with mock.patch.object(rx3_artifacts, "CONFIGURATION", configuration):
                with mock.patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(
                        rx3_artifacts.locate("rbp"), Path("/tmp/elsewhere")
                    )
                    # A role the file omits is simply not configured.
                    self.assertIsNone(rx3_artifacts.locate("imagedata"))

    def test_missing_artifact_explains_the_role_without_sourcing_it(self):
        with mock.patch.dict(os.environ, {"RX3_RBP": "/nonexistent/rbp"}):
            with self.assertRaises(rx3_artifacts.ArtifactMissing) as raised:
                rx3_artifacts.resolve("rbp")
        message = str(raised.exception)
        self.assertIn("rbp", message)
        self.assertIn(rx3_artifacts.ROLES["rbp"]["description"], message)
        self.assertIn(rx3_artifacts.DOCUMENTATION, message)

    def test_an_unconfigured_role_explains_itself_too(self):
        """The error has to work before anyone has configured anything."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(rx3_artifacts.ArtifactMissing) as raised:
                rx3_artifacts.resolve("rbp")
        message = str(raised.exception)
        self.assertIn("rbp", message)
        self.assertIn("RX3_RBP", message)
        self.assertIn(rx3_artifacts.DOCUMENTATION, message)

    def test_no_role_names_an_origin(self):
        """A role is what a file is for, never where it came from."""
        forbidden = ("extract", "decrypt", "firmware", "update", "dump", "iso")
        surface = " ".join(
            text for role in rx3_artifacts.ROLES for text in ROLE_TEXT(role)
        ).lower()
        for word in forbidden:
            self.assertNotIn(word, surface, f"{word!r} asserts an origin")

    def test_every_role_declares_its_variable_and_description(self):
        for role, record in rx3_artifacts.ROLES.items():
            with self.subTest(role=role):
                self.assertTrue(record["variable"].startswith("RX3_"))
                self.assertTrue(record["description"])


def ROLE_TEXT(role):
    record = rx3_artifacts.ROLES[role]
    return [role, record["variable"], record["description"]]


if __name__ == "__main__":
    unittest.main()
