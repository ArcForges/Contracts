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
from consumer_tools import NUGET_ID, consume, pin_candidate
from packaging_tools import verify_artifacts
from publish_tools import existing_matches, publish_verified


class PublicationCompletion(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="publication-boundary-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "candidate"
        self.directory.mkdir()
        self.manifest = {"version": "1.0.0", "commit": "a" * 40, "files": []}

    def test_maven_publication_modules_are_retired(self):
        # CON.40: the Central and snapshot completion paths no longer exist, so no credentialed Maven
        # publication can be reached; nothing already published is touched.
        import importlib.util
        for module in ("central_publish", "snapshot_publish", "maven_tools"):
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(module))
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": "ArcForges/Contracts",
                                     "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "a" * 40}), \
                patch("publish_tools.get", side_effect=AssertionError("Public artifact download prohibited")), \
                self.assertRaisesRegex(ValueError, "Retired or unknown publication channel"):
            publish_verified(self.directory, "maven")

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

    def test_candidate_pin_replaces_the_previous_client_pin_without_a_duplicate(self):
        import xml.etree.ElementTree as ET
        path = self.directory / "Directory.Packages.props"
        for before, expected in ((f'<PackageVersion Include="{NUGET_ID}" Version="1.0.0-ci.113.1" />', 1), ("", 1)):
            path.write_text("<Project><ItemGroup>" + before
                            + '<PackageVersion Include="Other.Package" Version="2.0.0" /></ItemGroup></Project>',
                            encoding="utf-8")
            pin_candidate(path, "1.0.0-ci.311.1")
            items = ET.parse(path).getroot().findall("ItemGroup/PackageVersion")
            ours = [item for item in items if item.get("Include") == NUGET_ID]
            self.assertEqual(len(ours), expected)
            self.assertEqual(ours[0].get("Version"), "1.0.0-ci.311.1")
            self.assertEqual([item.get("Version") for item in items if item.get("Include") == "Other.Package"], ["2.0.0"])
        path.write_text("<Project><ItemGroup>"
                        + f'<PackageVersion Include="{NUGET_ID}" Version="1" /><PackageVersion Include="{NUGET_ID}" Version="2" />'
                        + "</ItemGroup></Project>", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "more than once"):
            pin_candidate(path, "1.0.0-ci.311.1")

    def test_kotlin_consumer_is_retired(self):
        # CON.40: the Kotlin (Maven) package consumer and its sources are retired with the Maven channel.
        import importlib.util
        root = Path(__file__).resolve().parents[2]
        tool = (root / "eng/consumer_tools.py").read_text(encoding="utf-8")
        self.assertIsNone(importlib.util.find_spec("kotlin_consumer"))
        self.assertNotIn("kotlin_consumer", tool)
        self.assertNotIn("connect_client", tool)
        self.assertFalse((root / "tests/public/KotlinConnectClient").exists())

    def test_publication_handoff_checks_bytes_without_rescanning_archives(self):
        entries = []
        from package_catalog import packages
        inventory = [("package-" + str(index) + (".nupkg" if row["kind"] == "nuget" else ".tgz"), row["kind"], row["id"])
                     for index, row in enumerate(packages())]
        self.assertNotIn("maven", {kind for _, kind, _ in inventory})
        inventory += [(name, "descriptor", "descriptor:" + name)
                      for name in sorted({row["descriptor"] for row in packages()})]
        for name, kind, identity in inventory:
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
            # A retired Maven bundle can no longer enter the candidate inventory (CON.40).
            (self.directory / "maven.zip").write_bytes(b"retired-channel")
            retired = dict(manifest, files=[*entries, {"name": "maven.zip", "kind": "maven", "id": "io.github.arcforges",
                                                       "sha256": hashlib.sha256(b"retired-channel").hexdigest(), "size": 15}])
            (self.directory / "manifest.json").write_text(json.dumps(retired), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "complete registered package and descriptor inventory"):
                verify_artifacts(self.directory, "a" * 40, contents=False)
            (self.directory / "maven.zip").unlink()
            (self.directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (self.directory / inventory[0][0]).write_bytes(b"altered")
            with self.assertRaisesRegex(ValueError, "hash or size mismatch"):
                verify_artifacts(self.directory, "a" * 40, contents=False)


if __name__ == "__main__":
    unittest.main()
