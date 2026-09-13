# SPDX-License-Identifier: Apache-2.0
"""Release ordering checks; registry reads and uploads stay mocked."""

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from publish_tools import npm_publish_tag, publish_verified


class NpmReleaseTags(unittest.TestCase):
    def test_first_publish_creates_latest(self):
        for metadata in [None, b'{}', b'{"next":"1.0.0-ci.6.1"}']:
            with self.subTest(metadata=metadata), patch("publish_tools.get", return_value=metadata):
                self.assertEqual(npm_publish_tag("@arcforges/proto", "1.0.0-ci.10.1"), "latest")

    def test_newer_run_or_attempt_advances_latest_numerically(self):
        for latest, incoming in [
            ("1.0.0-ci.9.9", "1.0.0-ci.10.1"),
            ("1.0.0-ci.10.9", "1.0.0-ci.10.10"),
        ]:
            with self.subTest(latest=latest, incoming=incoming):
                with patch("publish_tools.get", return_value=json.dumps({"latest": latest}).encode()):
                    self.assertEqual(npm_publish_tag("@arcforges/proto", incoming), "latest")

    def test_delayed_run_or_retry_preserves_newer_latest(self):
        for incoming in ["1.0.0-ci.9.99", "1.0.0-ci.10.1", "1.0.0-ci.10.2"]:
            with self.subTest(incoming=incoming):
                with patch("publish_tools.get", return_value=b'{"latest":"1.0.0-ci.10.2"}'):
                    self.assertEqual(npm_publish_tag("@arcforges/proto", incoming), "ci")

    def test_unrecognized_latest_requires_policy_review(self):
        with patch("publish_tools.get", return_value=b'{"latest":"1.0.0"}'):
            with self.assertRaisesRegex(ValueError, "Review the npm release policy"):
                npm_publish_tag("@arcforges/proto", "1.0.0-ci.10.1")

    def test_oidc_publishes_both_archives_to_latest_without_bootstrap_token(self):
        env = {"GITHUB_REPOSITORY": "ArcForges/Contracts", "GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "a" * 40, "NPM_PUBLISH_MODE": "oidc"}
        entries = [{"id": "@arcforges/proto", "name": "proto.tgz", "kind": "npm"},
                   {"id": "@arcforges/api-client", "name": "api-client.tgz", "kind": "npm"}]
        manifest = {"dirty": False, "version": "1.0.0-ci.10.1", "files": entries}
        with patch.dict(os.environ, env, clear=True), patch("publish_tools.verify_artifacts", return_value=manifest):
            with patch("publish_tools.existing_matches", return_value=False):
                with patch("publish_tools.get", return_value=b'{"latest":"1.0.0-ci.6.1"}'):
                    with patch("publish_tools.run") as upload:
                        publish_verified(Path("candidate"), "npm")
        self.assertEqual(upload.call_count, 2)
        for call, entry in zip(upload.call_args_list, entries, strict=True):
            self.assertEqual(call.args[1], "publish")
            self.assertEqual(call.args[2], Path("candidate") / entry["name"])
            self.assertEqual(call.args[call.args.index("--tag") + 1], "latest")
            self.assertNotIn("env", call.kwargs)


if __name__ == "__main__":
    unittest.main()
