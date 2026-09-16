# SPDX-License-Identifier: Apache-2.0
"""Exercise Maven failure boundaries and real detached signing without accounts."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from contracts import ARTIFACTS, sha256, write_json
from packaging_tools import verify_artifacts
from maven_tools import verify_bundle, zip_contents
from central_publish import registry_matches, signed_bundle, publish
from publish_tools import publish_verified


class MavenReleaseGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ARTIFACTS / "packages"
        cls.manifest = json.loads((cls.directory / "manifest.json").read_text())
        cls.entry = next(item for item in cls.manifest["files"] if item["kind"] == "maven")
        cls.files = verify_bundle(cls.directory / cls.entry["name"], cls.manifest,
                                 (cls.directory / "contracts.binpb").read_bytes())

    def test_missing_maven_publication_fails_even_after_outer_rehash(self):
        with tempfile.TemporaryDirectory(prefix="contracts-maven-guard-") as temporary:
            candidate = Path(temporary) / "candidate"
            shutil.copytree(self.directory, candidate)
            bundle = candidate / self.entry["name"]
            with zipfile.ZipFile(bundle, "w") as archive:
                for name, data in self.files.items():
                    if not name.endswith("-sources.jar"):
                        archive.writestr(name, data)
            manifest = json.loads((candidate / "manifest.json").read_text())
            entry = next(item for item in manifest["files"] if item["kind"] == "maven")
            entry.update(sha256=sha256(bundle), size=bundle.stat().st_size)
            write_json(candidate / "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "complete publications"):
                verify_artifacts(candidate)

    def test_maven_client_cannot_pin_another_candidate(self):
        for module in ("contracts-client", "contracts-connect-client"):
            with self.subTest(module=module), tempfile.TemporaryDirectory(prefix="contracts-maven-guard-") as temporary:
                files = dict(self.files)
                pom = next(name for name in files if f"/{module}/" in name and name.endswith(".pom"))
                old = self.manifest["version"].encode()
                # Keep the POM's own identity, alter only its internal dependency version.
                before, dependencies = files[pom].split(b"<dependencies>", 1)
                files[pom] = before + b"<dependencies>" + dependencies.replace(old, b"1.0.0-ci.999999.1")
                bundle = Path(temporary) / "wrong-client.zip"
                with zipfile.ZipFile(bundle, "w") as archive:
                    for name, data in files.items():
                        archive.writestr(name, data)
                with self.assertRaisesRegex(ValueError, "pin this candidate"):
                    verify_bundle(bundle, self.manifest, (self.directory / "contracts.binpb").read_bytes())

    def test_public_registry_conflict_is_not_overwritten(self):
        with patch("central_publish.get", return_value=b"different"):
            with self.assertRaisesRegex(ValueError, "different bytes"):
                registry_matches(self.files)

    def test_partial_registry_visibility_does_not_trigger_upload(self):
        values = iter([next(iter(self.files.values())), *([None] * (len(self.files) - 1))])
        with patch("central_publish.get", side_effect=lambda _: next(values)), patch("central_publish.request") as network:
            with self.assertRaisesRegex(ValueError, "partly visible"):
                publish(self.directory, self.manifest)
            network.assert_not_called()

    def test_pr_event_cannot_reach_maven_credentials(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "pull_request"}), patch("central_publish.publish") as publisher:
            with self.assertRaisesRegex(ValueError, "restricted"):
                publish_verified(self.directory, "maven")
            publisher.assert_not_called()

    def test_uncertain_upload_is_not_repeated(self):
        with patch("central_publish.registry_matches", return_value=False), \
             patch("central_publish.recover_receipt", return_value={"phase": "upload-started", "deploymentId": None}), \
             patch("central_publish.request") as network, \
             patch.dict(os.environ, {"MAVEN_CENTRAL_USERNAME": "test-user", "MAVEN_CENTRAL_TOKEN": "test-only", "MAVEN_CENTRAL_DEPLOYMENT_ID": ""}):
            with self.assertRaisesRegex(ValueError, "uncertain outcome"):
                publish(self.directory, self.manifest)
            network.assert_not_called()

    def test_real_signatures_cover_unchanged_candidate_files(self):
        # This throwaway test key is created locally and never printed, committed,
        # retained or used with a registry. No account credentials are required.
        gpg = shutil.which("gpg")
        self.assertIsNotNone(gpg, "Install GnuPG to verify the Central signing path")
        with tempfile.TemporaryDirectory(prefix="contracts-signing-test-") as temporary:
            stage = Path(temporary)
            keyring = stage / "keyring"
            keyring.mkdir(mode=0o700)
            command = [gpg, "--homedir", "keyring", "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
            def gnupg(*args, **kwargs):
                result = subprocess.run([*command, *args], cwd=stage, capture_output=True, **kwargs)
                if result.returncode:
                    raise RuntimeError("GnuPG test failed: " + result.stderr.decode(errors="replace"))
                return result
            try:
                gnupg("--quick-generate-key", "ArcForges ephemeral CI signing test", "rsa2048", "sign", "0")
                private = gnupg("--armor", "--export-secret-keys").stdout.decode()
                with patch.dict(os.environ, {"MAVEN_SIGNING_KEY": private, "MAVEN_SIGNING_PASSWORD": ""}):
                    bundle = signed_bundle(self.files, stage)
                contents = zip_contents(bundle.read_bytes())
                self.assertEqual(len(contents), len(self.files) * 6)
                for name, original in self.files.items():
                    self.assertEqual(original, contents[name])
                    self.assertEqual(hashlib.sha256(original).hexdigest().encode(), contents[name + ".sha256"])
                    path = "repository/" + name
                    gnupg("--verify", path + ".asc", path)
            finally:
                subprocess.run([str(Path(gpg).with_name("gpgconf.exe" if os.name == "nt" else "gpgconf")),
                                "--homedir", "keyring", "--kill", "all"], cwd=stage, capture_output=True)


if __name__ == "__main__":
    unittest.main()
