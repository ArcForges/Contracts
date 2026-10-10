# SPDX-License-Identifier: Apache-2.0
"""Publication boundary negatives; the Maven snapshot and Central channels are retired (CON.40)."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
from contracts import ARTIFACTS, NPM_IDS, version
from release_channels import authorize, selected_version
from packaging_tools import verify_artifacts
from publish_tools import CHANNELS, npm_publish_tag, publish_verified

PUBLICATION_STOP = "eng/policy/publication-stops/con-40.json"
STOP_REVIEWER = "w-deku-20261008-rev-con-40"
SHA = re.compile(r"[0-9a-f]{40}")
CONSUMER_REPOSITORIES = ["Cloud", "Web", "Mobile"]
MIGRATION_TASKS = ["WEB.40", "AND.40", "CLOUD.84"]
PINS = {"AI": {"@arcforges/proto": "1.0.0-ci.287.1"},
        "DesktopPlatform": {"@arcforges/proto": "1.0.0-ci.113.1", "@arcforges/contract-fixtures": "1.0.0-ci.113.1"}}
RESIDUE_CLASSES = {"binding-history", "immutable-records", "documentation", "secret-scan-allowlist",
                   "policy-tooling-text"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("publication stop: " + message)


def ci_jobs(text: str) -> set[str]:
    jobs = text.split("\njobs:\n", 1)[1]
    return set(re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", jobs, re.M))


def check_publication_stop(record: dict, root: Path = ROOT) -> None:
    """CON.40 C8: the stop-publication record matches the retired catalog rows, the receipts and the head."""
    require(record.get("schemaVersion") == 1 and record.get("repository") == "Contracts"
            and record.get("task") == "CON.40" and record.get("unit") == "C8", "identity")
    catalog = json.loads((root / "eng/contract-packages.json").read_text(encoding="utf-8"))["packages"]
    retired = {row["id"]: row for row in catalog if row.get("retired", {}).get("task") == "CON.40"}
    receipts = {}
    for name in ("con-40-npm", "con-40-maven"):
        receipt = json.loads((root / f"eng/provenance/retirements/{name}.json").read_text(encoding="utf-8"))
        for package in receipt["packages"]:
            receipts[package] = f"eng/provenance/retirements/{name}.json"
    identities = record["identities"]
    ids = [row["id"] for row in identities]
    require(len(ids) == len(set(ids)), "duplicate identity")
    require(set(ids) == set(retired) == set(receipts), "identities differ from the retired catalog rows or receipts")
    require(not set(ids) & set(NPM_IDS) and "@arcforges/ai-internal" not in ids, "a retained identity is stopped")
    require(any(row["id"] == "@arcforges/ai-internal" for row in record["retained"]), "ai-internal not retained")
    runs = {row["run"]: row for row in record["publicationRuns"]}
    for row in record["publicationRuns"]:
        require(bool(SHA.fullmatch(row["sourceCommit"])) and set(row["publishers"]) == {"nuget", "npm", "maven"},
                "publication run shape")

    def published(entry: dict, channel: str, kind: str) -> None:
        if entry["run"] in runs:
            require(runs[entry["run"]]["sourceCommit"] == entry["sourceCommit"]
                    and runs[entry["run"]]["publishers"][channel] == "success", "run does not publish: " + kind)
        require(bool(SHA.fullmatch(entry["sourceCommit"])) and isinstance(entry["sourceOnMain"], bool), kind)
        if entry["version"] == "1.0.0-SNAPSHOT":
            require(channel == "maven", "a SNAPSHOT outside the Maven channel")
            return
        version(entry["version"])
        attempt = entry.get("candidateAttempt", entry["attempt"])
        require(entry["version"] == f"1.0.0-ci.{entry['runNumber']}.{attempt}", "version differs from its run: " + kind)

    for row in identities:
        identity = row["id"]
        catalog_row = retired[identity]
        require(row["kind"] == catalog_row["kind"] and row["access"] == catalog_row["access"]
                and row["sourceRoot"] == catalog_row["sourceRoot"], "catalog mismatch: " + identity)
        require(row["retirementReceipt"] == receipts[identity], "receipt mismatch: " + identity)
        channel = row["kind"]
        published(row["lastPublished"], channel, identity)
        published(row["lastPublishedFromMain"], channel, identity)
        require(row["lastPublishedFromMain"]["sourceOnMain"] is True, "main publication not on main: " + identity)
        if channel == "maven":
            published(row["lastRelease"], channel, identity)
            require(row["lastRelease"]["version"] != "1.0.0-SNAPSHOT", "Maven release is a snapshot: " + identity)
            require(row["lastPublished"]["version"] == "1.0.0-SNAPSHOT", "Maven snapshot channel: " + identity)
        require(row["firstPartyConsumersAtMain"] == [] and row["state"] == "stopped", "consumer left: " + identity)
    migrations = record["consumerMigration"]
    require([row["task"] for row in migrations] == MIGRATION_TASKS, "consumer-migration tasks")
    for row in migrations:
        require(bool(row["pullRequests"]) and all(SHA.fullmatch(pr["mergeCommit"]) for pr in row["pullRequests"]),
                "unmerged migration: " + row["task"])
    scans = record["consumerScans"]
    require([row["repository"] for row in scans] == CONSUMER_REPOSITORIES, "consumer scan set")
    for row in scans:
        require(bool(SHA.fullmatch(row["commit"])) and row["ref"] == "origin/main", "scan ref: " + row["repository"])
        require(row["consumerReferences"] == [], "first-party consumer left in " + row["repository"])
        require(set(row["matchingLinesByIdentity"]) == set(retired), "scan identity set: " + row["repository"])
        require({item["class"] for item in row["residue"]} <= RESIDUE_CLASSES, "unknown residue class")
        for item in row["residue"]:
            if isinstance(item["files"], list):
                require(not set(item["files"]) & set(row["dependencyFiles"]), "a dependency file is residue")
    pinned = {row["repository"]: row["pins"] for row in record["pinnedConsumers"]}
    require(pinned == PINS, "pinned consumers")
    for row in identities:
        for repository, pins in PINS.items():
            if row["id"] in pins:
                require(any(item.startswith(f"{repository} {pins[row['id']]}") for item in row["pinnedConsumers"]),
                        "pin not recorded on " + row["id"])
    require(record["registryActions"] == {"unpublish": [], "deprecate": [], "delete": [], "distTagChange": []},
            "registry action")
    require("Nothing is unpublished, deprecated or deleted" in record["statement"], "no-unpublish statement")
    review = record["review"]
    require(review["reviewer"] == STOP_REVIEWER and review["decision"] == "approved"
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", review["reviewedOn"]) is not None, "review fields")
    # The stop itself, at this head.
    require(tuple(CHANNELS) == ("nuget", "npm") and tuple(NPM_IDS) == ("@arcforges/ai-internal",), "channels")
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    require(ci_jobs(workflow) == {"candidate", "verify", "publish-nuget", "publish-npm"}, "workflow jobs")
    require(not re.search(r"setup-java|gradle|maven", workflow, re.I), "a Maven or Gradle step remains")
    require(sorted(record["stop"]["receipts"]) == sorted(set(receipts.values())), "stop receipts")
    inventory = json.loads((root / "eng/provenance/files.json").read_text(encoding="utf-8"))
    require(PUBLICATION_STOP in inventory["firstParty"], "record missing from the provenance inventory")


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
                self.assertEqual(npm_publish_tag("@arcforges/ai-internal", incoming), tag)

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


class PublicationStopRecord(unittest.TestCase):
    """CON.40 C8: eng/policy/publication-stops/con-40.json is the stop-publication evidence (S50(1))."""

    def setUp(self):
        self.record = json.loads((ROOT / PUBLICATION_STOP).read_text(encoding="utf-8"))

    def test_record_matches_catalog_receipts_and_head(self):
        check_publication_stop(self.record)
        self.assertEqual([row["id"] for row in self.record["identities"]], [
            "@arcforges/proto", "@arcforges/api-client", "@arcforges/contract-fixtures", "@arcforges/operator-client",
            "io.github.arcforges:contracts-proto", "io.github.arcforges:contracts-connect-client",
            "io.github.arcforges:contract-fixtures"])

    def test_record_refuses_mutations(self):
        def drop_identity(r):
            r["identities"].pop()

        def stop_retained(r):
            r["identities"].append(dict(r["identities"][0], id="@arcforges/ai-internal"))

        def consumer_left(r):
            r["consumerScans"][0]["consumerReferences"].append({"path": "package.json", "line": 1})

        def identity_consumer(r):
            r["identities"][1]["firstPartyConsumersAtMain"].append("Web")

        def unpublish(r):
            r["registryActions"]["unpublish"].append("@arcforges/proto@1.0.0-ci.350.1")

        def deprecate(r):
            r["registryActions"]["deprecate"].append("io.github.arcforges:contracts-proto")

        def statement(r):
            r["statement"] = r["statement"].replace("Nothing is unpublished", "Something is unpublished")

        def pending(r):
            r["review"]["decision"] = "pending"

        def reviewer(r):
            r["review"]["reviewer"] = "w-deku-20261010-con-40"

        def version_drift(r):
            r["identities"][0]["lastPublished"]["version"] = "1.0.0-ci.351.1"

        def snapshot_release(r):
            r["identities"][4]["lastRelease"]["version"] = "1.0.0-SNAPSHOT"

        def main_publication_off_main(r):
            r["identities"][2]["lastPublishedFromMain"]["sourceOnMain"] = False

        def skipped_publisher(r):
            r["publicationRuns"][0]["publishers"]["npm"] = "skipped"

        def missing_scan(r):
            r["consumerScans"].pop()

        def pin_changed(r):
            r["pinnedConsumers"][0]["pins"]["@arcforges/proto"] = "1.0.0-ci.324.1"

        def migration_dropped(r):
            r["consumerMigration"].pop()

        def receipt_swapped(r):
            r["identities"][0]["retirementReceipt"] = "eng/provenance/retirements/con-40-maven.json"

        def access_changed(r):
            r["identities"][3]["access"] = "public"

        def dependency_file_as_residue(r):
            r["consumerScans"][0]["residue"].append({"class": "documentation", "files": ["package.json"]})

        for mutate in (drop_identity, stop_retained, consumer_left, identity_consumer, unpublish, deprecate, statement,
                       pending, reviewer, version_drift, snapshot_release, main_publication_off_main,
                       skipped_publisher, missing_scan, pin_changed, migration_dropped, receipt_swapped,
                       access_changed, dependency_file_as_residue):
            with self.subTest(mutation=mutate.__name__):
                record = copy.deepcopy(self.record)
                mutate(record)
                with self.assertRaises(ValueError):
                    check_publication_stop(record)

    def test_record_refuses_a_head_that_still_publishes(self):
        with tempfile.TemporaryDirectory(prefix="publication-stop-") as temporary:
            root = Path(temporary)
            for path in ("eng/contract-packages.json", "eng/provenance/retirements/con-40-npm.json",
                         "eng/provenance/retirements/con-40-maven.json", "eng/provenance/files.json",
                         ".github/workflows/ci.yml"):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes((ROOT / path).read_bytes())
            check_publication_stop(self.record, root)
            workflow = root / ".github/workflows/ci.yml"
            original = workflow.read_text(encoding="utf-8")
            workflow.write_text(original + "\n  publish-maven:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "workflow jobs"):
                check_publication_stop(self.record, root)
            workflow.write_text(original, encoding="utf-8")
            catalog = root / "eng/contract-packages.json"
            document = json.loads(catalog.read_text(encoding="utf-8"))
            for row in document["packages"]:
                if row["id"] == "@arcforges/operator-client":
                    row.pop("retired")
            catalog.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "retired catalog rows"):
                check_publication_stop(self.record, root)
            catalog.write_bytes((ROOT / "eng/contract-packages.json").read_bytes())
            inventory = root / "eng/provenance/files.json"
            document = json.loads(inventory.read_text(encoding="utf-8"))
            document["firstParty"].remove(PUBLICATION_STOP)
            inventory.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provenance inventory"):
                check_publication_stop(self.record, root)


if __name__ == "__main__":
    unittest.main()
