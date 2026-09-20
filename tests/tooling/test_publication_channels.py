# SPDX-License-Identifier: Apache-2.0
"""Publication boundary negatives and real Gradle snapshot repository transport."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from contracts import ARTIFACTS, version
from release_channels import authorize, maven_version, selected_version
from snapshot_publish import inspect, resolve, transport
from maven_tools import verify_bundle
from publish_tools import npm_publish_tag


class PublicationChannels(unittest.TestCase):
    def test_versions_and_channel_mapping(self):
        for value in ("1.0.0", "2.31.4", "1.0.0-ci.12.1"):
            self.assertEqual(version(value), value)
        self.assertEqual(maven_version("1.0.0-ci.12.1"), "1.0.0-SNAPSHOT")
        self.assertEqual(maven_version("2.31.4"), "2.31.4")
        for value in ("v1.0.0", "01.0.0", "1.0", "1.0.0-SNAPSHOT", "1.0.0-ci.01.1", "1.0.0-rc.1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                version(value)

    def test_tag_requires_main_ancestry(self):
        with patch.dict(os.environ, {"GITHUB_REF": "refs/tags/v1.2.3", "GITHUB_SHA": "a" * 40}):
            with patch("release_channels.run") as git:
                self.assertEqual(selected_version(), "1.2.3")
                git.assert_called_once_with("git", "merge-base", "--is-ancestor", "a" * 40, "origin/main")
            with patch("release_channels.run", side_effect=subprocess.CalledProcessError(1, "git")):
                with self.assertRaises(subprocess.CalledProcessError):
                    selected_version()

    def test_mismatched_channels_and_noncanonical_tags_fail(self):
        for ref, build in (("refs/tags/v1.0.1", "1.0.0"), ("refs/heads/main", "1.0.0"),
                           ("refs/tags/v01.0.0", "01.0.0"), ("refs/tags/v1.0.0-ci.1.1", "1.0.0-ci.1.1")):
            with self.subTest(ref=ref), patch.dict(os.environ, {"GITHUB_REF": ref}), self.assertRaises(ValueError):
                authorize(build)

    def test_stable_npm_ordering(self):
        for current, incoming, tag in (("1.0.0-ci.99.1", "1.0.0", "latest"),
                                      ("2.0.0", "1.0.0", "release"), ("1.0.0", "1.1.0", "latest")):
            with patch("publish_tools.get", return_value=json.dumps({"latest": current}).encode()):
                self.assertEqual(npm_publish_tag("@arcforges/proto", incoming), tag)

    def test_snapshot_metadata_cannot_escape_repository(self):
        for value in ("../../evil", "1.0.0-ci.1.1", "1.0.0-20260920.123456-0"):
            xml = ("<metadata><groupId>io.github.arcforges</groupId><artifactId>contracts-proto</artifactId>"
                   "<version>1.0.0-SNAPSHOT</version><versioning><snapshotVersions><snapshotVersion>"
                   f"<extension>jar</extension><value>{value}</value></snapshotVersion>"
                   "</snapshotVersions></versioning></metadata>").encode()
            with patch("snapshot_publish.get", return_value=xml), self.assertRaisesRegex(ValueError, "timestamped"):
                resolve("contracts-proto", "1.0.0-SNAPSHOT")

    def test_real_snapshot_transport_preserves_all_twenty_files(self):
        directory = ARTIFACTS / "packages"
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest.get("mavenVersion") != "1.0.0-SNAPSHOT":
            self.skipTest("Formal release candidate uses the separately tested signing transport")
        entry = next(item for item in manifest["files"] if item["kind"] == "maven")
        files = verify_bundle(directory / entry["name"], manifest, (directory / "contracts.binpb").read_bytes())
        with tempfile.TemporaryDirectory(prefix="snapshot-repository-") as temporary:
            repository = Path(temporary)
            uri = repository.as_uri() + "/"
            transport(files, manifest["mavenVersion"], uri)

            def read(url):
                from urllib.request import url2pathname
                path = Path(url2pathname(unquote(urlparse(url).path)))
                return path.read_bytes() if path.is_file() else None

            with patch("snapshot_publish.get", side_effect=read):
                complete, records = inspect(files, manifest, uri)
                self.assertTrue(complete)
                self.assertEqual(len(records), 20)
                # The retry's public-byte check succeeds without another upload.
                self.assertTrue(inspect(files, manifest, uri)[0])
                altered = dict(files)
                jar = next(name for name in altered if name.endswith(".jar") and not name.endswith(("-sources.jar", "-javadoc.jar")))
                altered[jar] += b"changed"
                with self.assertRaisesRegex(ValueError, "different bytes"):
                    inspect(altered, manifest, uri)
                old = dict(manifest, version="1.0.0-ci.0.0")
                if old["version"] != manifest["version"]:
                    with self.assertRaisesRegex(ValueError, "newer snapshot"):
                        inspect(files, old, uri)
                target = repository / records[0]["remote"]
                target.unlink()
                self.assertFalse(inspect(files, manifest, uri)[0])


if __name__ == "__main__":
    unittest.main()
