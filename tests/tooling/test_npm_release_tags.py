# SPDX-License-Identifier: Apache-2.0
"""Release ordering checks; registry reads and uploads stay mocked.

CON.40: @arcforges/ai-internal is the one npm channel. The retired npm identities (@arcforges/proto,
@arcforges/api-client, @arcforges/contract-fixtures, @arcforges/operator-client) are never published again;
already published versions stay immutable and resolvable.
"""

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from publish_tools import npm_publish_tag, publish_verified


class NpmReleaseTags(unittest.TestCase):
    def test_first_publish_creates_latest(self):
        for metadata in [None, b'{}', b'{"dist-tags":{"next":"1.0.0-ci.6.1"}}']:
            with self.subTest(metadata=metadata), patch("publish_tools.get", return_value=metadata):
                self.assertEqual(npm_publish_tag("@arcforges/ai-internal", "1.0.0-ci.10.1"), "latest")

    def test_unpublished_packages_use_public_metadata_and_accept_only_404(self):
        for name in ("ai-internal",):
            url = f"https://registry.npmjs.org/%40arcforges%2F{name}"
            with self.subTest(name=name):
                with patch("publish_tools.urlopen", side_effect=HTTPError(url, 404, "Not Found", {}, None)) as request:
                    self.assertEqual(npm_publish_tag(f"@arcforges/{name}", "1.0.0-ci.83.1"), "latest")
                    self.assertEqual(request.call_args.args[0].full_url, url)
                for status in (401, 403, 429, 500):
                    with patch("publish_tools.urlopen", side_effect=HTTPError(url, status, "Failure", {}, None)):
                        with self.assertRaises(HTTPError) as caught:
                            npm_publish_tag(f"@arcforges/{name}", "1.0.0-ci.83.1")
                        caught.exception.close()

    def test_newer_run_or_attempt_advances_latest_numerically(self):
        for latest, incoming in [
            ("1.0.0-ci.9.9", "1.0.0-ci.10.1"),
            ("1.0.0-ci.10.9", "1.0.0-ci.10.10"),
        ]:
            with self.subTest(latest=latest, incoming=incoming):
                with patch("publish_tools.get", return_value=json.dumps({"dist-tags": {"latest": latest}}).encode()):
                    self.assertEqual(npm_publish_tag("@arcforges/ai-internal", incoming), "latest")

    def test_delayed_run_or_retry_preserves_newer_latest(self):
        for incoming in ["1.0.0-ci.9.99", "1.0.0-ci.10.1", "1.0.0-ci.10.2"]:
            with self.subTest(incoming=incoming):
                with patch("publish_tools.get", return_value=b'{"dist-tags":{"latest":"1.0.0-ci.10.2"}}'):
                    self.assertEqual(npm_publish_tag("@arcforges/ai-internal", incoming), "ci")

    def test_stable_latest_is_preserved_for_development(self):
        with patch("publish_tools.get", return_value=b'{"dist-tags":{"latest":"1.0.0"}}'):
            self.assertEqual(npm_publish_tag("@arcforges/ai-internal", "1.0.0-ci.10.1"), "ci")

    def test_oidc_publishes_the_ai_internal_archive_to_latest_without_bootstrap_token(self):
        env = {"GITHUB_REPOSITORY": "ArcForges/Contracts", "GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "a" * 40, "NPM_PUBLISH_MODE": "oidc"}
        entries = [{"id": "@arcforges/ai-internal", "name": "ai-internal.tgz", "kind": "npm"}]
        manifest = {"dirty": False, "version": "1.0.0-ci.10.1", "files": entries}
        with patch.dict(os.environ, env, clear=True), patch("publish_tools.verify_artifacts", return_value=manifest):
            with patch("publish_tools.existing_matches", return_value=False):
                with patch("publish_tools.get", return_value=b'{"dist-tags":{"latest":"1.0.0-ci.6.1"}}'):
                    with patch("publish_tools.run") as upload:
                        publish_verified(Path("candidate"), "npm")
        self.assertEqual(upload.call_count, 1)
        for call, entry in zip(upload.call_args_list, entries, strict=True):
            self.assertEqual(call.args[1], "publish")
            self.assertEqual(call.args[2], Path("candidate") / entry["name"])
            self.assertEqual(call.args[call.args.index("--tag") + 1], "latest")
            self.assertNotIn("env", call.kwargs)

    def test_retired_npm_identities_fail_closed_before_registry_access(self):
        # CON.40: a candidate naming a retired npm identity is refused before any registry read or upload,
        # alone or beside the retained package, in both publication modes.
        retired = ["@arcforges/proto", "@arcforges/api-client", "@arcforges/contract-fixtures",
                   "@arcforges/operator-client", "@arcforges/unknown"]
        kept = {"id": "@arcforges/ai-internal", "name": "ai-internal.tgz", "kind": "npm"}
        for mode in ("oidc", "bootstrap"):
            env = {"GITHUB_REPOSITORY": "ArcForges/Contracts", "GITHUB_REF": "refs/heads/main",
                   "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "a" * 40, "NPM_PUBLISH_MODE": mode,
                   "NPM_BOOTSTRAP_TOKEN": "unused"}
            for identity in retired:
                for entries in ([{"id": identity, "name": "retired.tgz", "kind": "npm"}],
                                [kept, {"id": identity, "name": "retired.tgz", "kind": "npm"}]):
                    manifest = {"dirty": False, "version": "1.0.0-ci.10.1", "files": entries}
                    with self.subTest(mode=mode, identity=identity, count=len(entries)),                             patch.dict(os.environ, env, clear=True),                             patch("publish_tools.verify_artifacts", return_value=manifest),                             patch("publish_tools.get", side_effect=AssertionError("Registry read before identity check")),                             patch("publish_tools.existing_matches", side_effect=AssertionError("Registry read before identity check")),                             patch("publish_tools.run", side_effect=AssertionError("Upload of a retired identity")):
                        with self.assertRaisesRegex(ValueError, "Retired or unregistered npm identity: " + identity):
                            publish_verified(Path("candidate"), "npm")

    def test_npm_channel_is_closed_to_ai_internal(self):
        from contracts import NPM_IDS
        from package_catalog import packages
        self.assertEqual(NPM_IDS, ("@arcforges/ai-internal",))
        self.assertEqual([row["id"] for row in packages("npm")], list(NPM_IDS))
        retired = {row["id"]: row["retired"] for row in packages("npm", include_retired=True) if "retired" in row}
        self.assertEqual(set(retired), {"@arcforges/proto", "@arcforges/api-client", "@arcforges/contract-fixtures",
                                        "@arcforges/operator-client"})
        self.assertTrue(all(marker["task"] == "CON.40" for marker in retired.values()))


if __name__ == "__main__":
    unittest.main()
