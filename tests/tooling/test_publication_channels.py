# SPDX-License-Identifier: Apache-2.0
"""Publication boundary negatives; the Maven snapshot and Central channels are retired (CON.40)."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from contracts import ARTIFACTS, version
from release_channels import authorize, selected_version
from packaging_tools import verify_artifacts
from publish_tools import npm_publish_tag, publish_verified


class PublicationChannels(unittest.TestCase):
    def test_versions_and_channel_mapping(self):
        for value in ("1.0.0", "2.31.4", "1.0.0-ci.12.1"):
            self.assertEqual(version(value), value)
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
            with patch("publish_tools.get", return_value=json.dumps({"dist-tags": {"latest": current}}).encode()):
                self.assertEqual(npm_publish_tag("@arcforges/proto", incoming), tag)

    def test_maven_channel_is_retired(self):
        # CON.40: the Maven channel stops. Nothing is unpublished; no new Maven version can be selected,
        # packed or published, and the Maven publication modules no longer exist.
        import release_channels
        self.assertFalse(hasattr(release_channels, "maven_version"))
        for module in ("maven_tools", "central_publish", "snapshot_publish", "kotlin_tools", "kotlin_consumer"):
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(module))
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": "ArcForges/Contracts",
                                     "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "a" * 40}), \
                patch("publish_tools.verify_artifacts", side_effect=AssertionError("Candidate read before channel check")), \
                patch("publish_tools.get", side_effect=AssertionError("Registry contacted for a retired channel")):
            with self.assertRaisesRegex(ValueError, "Retired or unknown publication channel"):
                publish_verified(ARTIFACTS / "packages", "maven")

    def test_maven_versioned_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="retired-maven-candidate-") as temporary:
            directory = Path(temporary)
            (directory / "manifest.json").write_text(json.dumps({
                "format": "arcforges.contracts.candidate.v1", "version": "1.0.0-ci.12.1",
                "mavenVersion": "1.0.0-SNAPSHOT", "commit": "a" * 40, "dirty": False,
                "build": {"sourceCommit": "a" * 40, "dirty": False}, "files": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Maven channel is retired"):
                verify_artifacts(directory, contents=False)


if __name__ == "__main__":
    unittest.main()
