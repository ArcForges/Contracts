# SPDX-License-Identifier: Apache-2.0
"""Offline publication boundary checks; never download artifacts or invoke a toolchain."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
import central_publish
import snapshot_publish
from consumer_tools import consume
from packaging_tools import verify_artifacts
from publish_tools import existing_matches


class PublicationCompletion(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="publication-boundary-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "candidate"
        self.directory.mkdir()
        (self.directory / "maven.zip").write_bytes(b"retained-candidate")
        self.manifest = {"version": "1.0.0", "mavenVersion": "1.0.0", "commit": "a" * 40,
                         "files": [{"kind": "maven", "name": "maven.zip", "sha256": "b" * 64}]}
        self.deployment = "69143abb-d8f5-40d3-b9fe-bc030561be28"
        self.status = {"deploymentId": self.deployment, "deploymentName": "ArcForges-Contracts-1.0.0",
                       "deploymentState": "PUBLISHED", "purls": [
                           f"pkg:maven/io.github.arcforges/{name}@1.0.0" for name in central_publish.MAVEN_MODULES]}
        self.environment = {"MAVEN_CENTRAL_USERNAME": "fixture", "MAVEN_CENTRAL_TOKEN": "fixture-only",
                            "MAVEN_CENTRAL_DEPLOYMENT_ID": ""}

    def central(self, status):
        with patch("central_publish.ARTIFACTS", self.root), \
             patch("central_publish.zip_contents", return_value={}), \
             patch("central_publish.recover_receipt", return_value={"deploymentId": self.deployment, "phase": "PUBLISHING"}), \
             patch("central_publish.request", return_value=json.dumps(status).encode()) as request, \
             patch("central_publish.get", side_effect=AssertionError("Public artifact download prohibited")), \
             patch.dict(os.environ, self.environment):
            central_publish.publish(self.directory, self.manifest)
            self.assertEqual(request.call_count, 1)
            self.assertIn("/status?", request.call_args.args[0])

    def test_published_coordinates_complete_without_public_download(self):
        self.central(self.status)
        receipt = json.loads((self.root / "publication/deployment.json").read_text())
        self.assertEqual(receipt["phase"], "PUBLISHED")

    def test_other_deployment_or_package_cannot_complete(self):
        for key, value in (("deploymentId", "another"), ("deploymentName", "another"), ("purls", [])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.central(dict(self.status, **{key: value}))

    def test_network_error_is_not_retried(self):
        with patch("central_publish.zip_contents", return_value={}), \
             patch("central_publish.ARTIFACTS", self.root), \
             patch("central_publish.recover_receipt", return_value={"deploymentId": self.deployment, "phase": "PUBLISHING"}), \
             patch("central_publish.request", side_effect=ConnectionError("fixture network failure")) as request, \
             patch.dict(os.environ, self.environment), self.assertRaises(ConnectionError):
            central_publish.publish(self.directory, self.manifest)
        request.assert_called_once()

    def snapshot(self, current):
        self.manifest.update(version="1.0.0-ci.12.1", mavenVersion="1.0.0-SNAPSHOT")
        with patch("snapshot_publish.ARTIFACTS", self.root), \
             patch("snapshot_publish.run", return_value=json.dumps(current)), \
             patch("snapshot_publish.zip_contents", return_value={"candidate": b"bytes"}), \
             patch("snapshot_publish.transport") as transport, \
             patch("snapshot_publish.inspect", side_effect=AssertionError("Public byte inspection prohibited")), \
             patch("snapshot_publish.get", side_effect=AssertionError("Public artifact download prohibited")):
            snapshot_publish.publish(self.directory, self.manifest)
        return transport

    def test_latest_main_completes_at_upload(self):
        transport = self.snapshot({"ref": "refs/heads/main", "object": {"type": "commit", "sha": "a" * 40}})
        transport.assert_called_once_with({"candidate": b"bytes"}, "1.0.0-SNAPSHOT")
        self.assertEqual(json.loads((self.root / "publication/deployment.json").read_text())["phase"], "upload-completed")

    def test_superseded_main_does_not_upload(self):
        transport = self.snapshot({"ref": "refs/heads/main", "object": {"type": "commit", "sha": "c" * 40}})
        transport.assert_not_called()
        self.assertEqual(json.loads((self.root / "publication/deployment.json").read_text())["phase"], "superseded")

    def test_malformed_main_ref_does_not_upload(self):
        with self.assertRaisesRegex(ValueError, "invalid main"):
            self.snapshot({"ref": "refs/heads/main", "object": {"type": "tag", "sha": "a" * 40}})

    def test_existing_nuget_fails_from_metadata_without_downloading_archive(self):
        entry = {"kind": "nuget", "id": "ArcForges.Contracts.PublicApi"}
        with patch("publish_tools.get", return_value=b'{"versions":["1.0.0"]}') as get:
            with self.assertRaisesRegex(ValueError, "already exists"):
                existing_matches(self.directory / "absent.nupkg", entry, "1.0.0")
        self.assertEqual(get.call_count, 1)
        self.assertTrue(get.call_args.args[0].endswith("/index.json"))

    def test_absent_nuget_version_can_be_uploaded(self):
        with patch("publish_tools.get", return_value=b'{"versions":[]}'):
            self.assertFalse(existing_matches(self.directory / "absent.nupkg",
                                              {"kind": "nuget", "id": "ArcForges.Contracts.PublicApi"}, "1.0.0"))

    def test_consumer_rejects_ci_before_reading_candidate(self):
        with patch.dict(os.environ, {"CI": "true"}), self.assertRaisesRegex(ValueError, "CI execution is prohibited"):
            consume(self.directory / "missing", True)

    def test_publication_handoff_checks_bytes_without_rescanning_archives(self):
        entries = []
        for name, kind, identity in (("x.nupkg", "nuget", "ArcForges.Contracts.PublicApi"),
                                     ("proto.tgz", "npm", "@arcforges/proto"),
                                     ("client.tgz", "npm", "@arcforges/api-client"),
                                     ("maven.zip", "maven", "io.github.arcforges"),
                                     ("contracts.binpb", "descriptor", "arcforges.hello.v1")):
            data = name.encode()
            (self.directory / name).write_bytes(data)
            entries.append({"name": name, "kind": kind, "id": identity,
                            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        manifest = dict(self.manifest, format="arcforges.contracts.candidate.v1", dirty=False,
                        build={"sourceCommit": "a" * 40, "dirty": False}, files=entries)
        (self.directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with patch("build_identity.validate_source"), \
             patch("packaging_tools.archive_files", side_effect=AssertionError("Archive rescan prohibited")):
            self.assertEqual(verify_artifacts(self.directory, "a" * 40, contents=False), manifest)
            (self.directory / "x.nupkg").write_bytes(b"altered")
            with self.assertRaisesRegex(ValueError, "hash or size mismatch"):
                verify_artifacts(self.directory, "a" * 40, contents=False)


if __name__ == "__main__":
    unittest.main()
