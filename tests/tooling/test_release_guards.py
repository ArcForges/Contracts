# SPDX-License-Identifier: Apache-2.0
"""Negative checks for the release boundary; never contact a registry."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from contracts import ARTIFACTS, sha256, write_json
from packaging_tools import verify_artifacts
from publish_tools import existing_matches, publish_verified


class ReleaseGuards(unittest.TestCase):
    def test_changed_archive_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="contracts-guard-") as directory:
            candidate = Path(directory) / "candidate"
            shutil.copytree(ARTIFACTS / "packages", candidate)
            package = next(candidate.glob("*.nupkg"))
            with package.open("ab") as stream:
                stream.write(b"unexpected mutation")
            with self.assertRaisesRegex(ValueError, "hash or size mismatch"):
                verify_artifacts(candidate)

    def test_hashes_alone_cannot_hide_missing_schema(self):
        with tempfile.TemporaryDirectory(prefix="contracts-guard-") as directory:
            candidate = Path(directory) / "candidate"
            shutil.copytree(ARTIFACTS / "packages", candidate)
            package = next(candidate.glob("*.nupkg"))
            with zipfile.ZipFile(package) as original:
                entries = {name: original.read(name) for name in original.namelist()
                           if not name.startswith("proto/")}
            with zipfile.ZipFile(package, "w") as altered:
                for name, contents in entries.items():
                    altered.writestr(name, contents)
            manifest = json.loads((candidate / "manifest.json").read_text())
            entry = next(entry for entry in manifest["files"] if entry["kind"] == "nuget")
            entry.update(sha256=sha256(package), size=package.stat().st_size)
            write_json(candidate / "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "Proto or descriptor"):
                verify_artifacts(candidate)

    def test_other_source_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source commit"):
            verify_artifacts(ARTIFACTS / "packages", "0" * 40)

    def test_rehashed_nuget_cannot_drop_generator_attribution(self):
        with tempfile.TemporaryDirectory(prefix="contracts-notice-guard-") as directory:
            candidate = Path(directory) / "candidate"
            shutil.copytree(ARTIFACTS / "packages", candidate)
            package = next(candidate.glob("*.nupkg"))
            with zipfile.ZipFile(package) as original:
                entries = {name: original.read(name) for name in original.namelist()}
            entries["NOTICE"] = b"ArcForges Contracts\nRuntime dependency inventory only.\n"
            with zipfile.ZipFile(package, "w") as altered:
                for name, contents in entries.items():
                    altered.writestr(name, contents)
            manifest = json.loads((candidate / "manifest.json").read_text())
            entry = next(item for item in manifest["files"] if item["kind"] == "nuget")
            entry.update(sha256=sha256(package), size=package.stat().st_size)
            write_json(candidate / "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "Package lost recorded source/generator notices"):
                verify_artifacts(candidate)

    def test_pr_manual_and_fork_events_cannot_publish(self):
        for event, repo, ref in [
            ("pull_request", "ArcForges/Contracts", "refs/heads/main"),
            ("workflow_dispatch", "ArcForges/Contracts", "refs/heads/main"),
            ("push", "someone/Contracts", "refs/heads/main"),
            ("push", "ArcForges/Contracts", "refs/heads/feature"),
        ]:
            with self.subTest(event=event, repo=repo, ref=ref):
                env = {"GITHUB_EVENT_NAME": event, "GITHUB_REPOSITORY": repo, "GITHUB_REF": ref}
                with patch.dict(os.environ, env), patch("publish_tools.get") as network:
                    with self.assertRaisesRegex(ValueError, "restricted"):
                        publish_verified(ARTIFACTS / "packages", "npm")
                    network.assert_not_called()

    def test_duplicate_npm_version_with_different_bytes_fails(self):
        manifest = json.loads((ARTIFACTS / "packages/manifest.json").read_text())
        entry = next(entry for entry in manifest["files"] if entry["kind"] == "npm")
        with patch("publish_tools.get", return_value=b'{"dist":{"integrity":"sha512-different"}}'):
            with self.assertRaisesRegex(ValueError, "different bytes"):
                existing_matches(ARTIFACTS / "packages" / entry["name"], entry, manifest["version"])


if __name__ == "__main__":
    unittest.main()
