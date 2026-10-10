# SPDX-License-Identifier: Apache-2.0
"""A reviewed retirement receipt may remove an artifact; nothing else may (CON.40, receipt-driven)."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_provenance as provenance
from check_provenance import ROOT, retirement_receipts
from test_provenance import Fixture

LEGACY = "eng/provenance/retirements/contracts-client-wp03-00.json"
MAVEN = ("io.github.arcforges:contracts-proto", "io.github.arcforges:contracts-connect-client",
         "io.github.arcforges:contract-fixtures")
NPM = ("@arcforges/proto", "@arcforges/api-client", "@arcforges/contract-fixtures", "@arcforges/operator-client")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def tracked():
    return subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
                                   text=True).splitlines()


class RepositoryRetirements(unittest.TestCase):
    """The committed CON.40 receipts retire exactly the seven catalog identities and the three javadoc targets."""

    def test_con40_receipts_cover_every_retired_identity_and_javadoc_target(self):
        files = tracked()
        history = {LEGACY: (ROOT / LEGACY).read_bytes()}
        covered = retirement_receipts(ROOT, "Contracts", files, history)
        self.assertEqual(sorted(covered), sorted([
            ("contracts-client", "io.github.arcforges:contracts-client", "maven-javadoc", "dokka-documentation-resources-r3"),
            *[(identity.split(":", 1)[1], identity, "maven-javadoc", "dokka-documentation-resources-r21") for identity in MAVEN]]))
        catalog = json.loads((ROOT / "eng/contract-packages.json").read_text(encoding="utf-8"))["packages"]
        self.assertEqual({row["id"] for row in catalog if "retired" in row}, set(MAVEN) | set(NPM))
        for name, packages in (("con-40-maven", MAVEN), ("con-40-npm", NPM)):
            receipt = json.loads((ROOT / f"eng/provenance/retirements/{name}.json").read_text(encoding="utf-8"))
            self.assertEqual(tuple(receipt["packages"]), packages)
            self.assertEqual(receipt["review"], {"owner": "Licensing and Provenance Owner",
                                                 "reviewer": "w-deku-20261008-rev-con-40",
                                                 "reviewedOn": "2026-10-10", "decision": "approved"})
            for source_root in receipt["sourceRoots"]:
                self.assertFalse((ROOT / source_root).exists(), source_root)
        inventory = json.loads((ROOT / provenance.INVENTORY).read_text(encoding="utf-8"))
        self.assertEqual(inventory["artifacts"], [])

    def test_legacy_receipt_format_is_accepted_only_as_committed_history(self):
        with self.assertRaisesRegex(ValueError, "Unreviewed retirement receipt format"):
            retirement_receipts(ROOT, "Contracts", tracked(), {})

    def test_every_retired_catalog_identity_needs_a_receipt(self):
        files = [p for p in tracked() if p != "eng/provenance/retirements/con-40-npm.json"]
        with self.assertRaisesRegex(ValueError, "no reviewed retirement receipt: @arcforges/proto"):
            retirement_receipts(ROOT, "Contracts", files, {LEGACY: b""})


class SyntheticRetirement(unittest.TestCase):
    """Synthetic history: one registered documentation artifact is retired, or silently removed."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="arcforges-retirement-test-")
        self.addCleanup(temp.cleanup)
        self.fixture = Fixture(Path(temp.name))
        self.root = self.fixture.root
        base = self.fixture.value
        origin = {"repository": base["sourceRepository"], "commit": base["sourceCommit"],
                  "paths": base["sourcePaths"], "spdx": "MIT", "evidence": base["licence"]["evidence"]}
        profile = "eng/provenance/artifact-profiles/docs-r1.json"
        self.fixture.write(profile, b"{}\n")
        self.docs = copy.deepcopy(base)
        self.docs.update(id="synthetic-docs-r1", kind="generated", targets=[],
                         generation={"generators": [origin], "inputs": [origin], "command": "Synthetic", "outputSpdx": "MIT"},
                         artifactTargets=[{"project": "fixture-docs", "package": "example:fixture-docs",
                                           "kind": "maven-javadoc", "profile": profile, "sha256": sha(b"{}\n")}])
        self.docs["notice"] = {**base["notice"], "distribution": "documentation"}
        self.docs_path = provenance.STORE + self.docs["id"] + ".json"
        self.fixture.put(self.docs_path, self.docs)
        self.catalog([{"id": "example:fixture-docs", "sourceRoot": "src/public/kotlin/fixture-docs"}])
        self.inventory(["synthetic-docs-r1"])
        self.previous = self.fixture.get(provenance.INVENTORY)
        self.history = {path: (self.root / path).read_bytes() for path in (self.fixture.record_path, self.docs_path)}
        self.fixture.validate(self.history, self.previous)
        # The retirement: the producer is marked retired and the artifact leaves the active inventory.
        self.catalog([{"id": "example:fixture-docs", "sourceRoot": "src/public/kotlin/fixture-docs",
                       "retired": {"task": "CON.40", "reason": "Synthetic retirement."}}])
        self.receipt = {
            "schemaVersion": 2, "id": "fixture-docs", "owner": "Contracts", "task": "CON.40",
            "packages": ["example:fixture-docs"], "sourceRoots": ["src/public/kotlin/fixture-docs"],
            "artifacts": [{"project": "fixture-docs", "package": "example:fixture-docs", "kind": "maven-javadoc"}],
            "previousRecord": "synthetic-docs-r1", "designCommit": "e" * 40, "reason": "Synthetic retirement.",
            "review": {"owner": "Licensing and Provenance Owner", "reviewer": "Synthetic reviewer",
                       "reviewedOn": "2026-10-10", "decision": "approved"}}

    def catalog(self, rows):
        self.fixture.put(provenance.CATALOG, {"schemaVersion": 1, "packages": rows})

    def inventory(self, artifacts):
        reused = {item["path"]: self.fixture.value["id"] for item in self.fixture.value["targets"]}
        records = {self.fixture.value["id"]: self.fixture.value, self.docs["id"]: self.docs}
        self.fixture.write(provenance.SUMMARY, provenance.render(records, set(reused.values()) | set(artifacts)))
        for _ in range(2):  # The inventory classifies itself.
            self.fixture.put(provenance.INVENTORY, {"schemaVersion": 1, "repository": "Contracts",
                                                    "firstParty": [p for p in self.fixture.files() if p not in reused],
                                                    "reused": reused, "artifacts": artifacts})

    def retire(self, receipt=None, name="fixture-docs"):
        if receipt is not None:
            self.fixture.put(provenance.RETIREMENTS + name + ".json", receipt)
        self.inventory([])
        return self.fixture.validate(self.history, self.previous)

    def test_reviewed_receipt_retires_the_artifact(self):
        result = self.retire(self.receipt)
        self.assertEqual(result["activeRecords"], ["synthetic-library-r1"])

    def test_artifact_removed_without_receipt_fails_closed(self):
        self.catalog([{"id": "example:fixture-docs", "sourceRoot": "src/public/kotlin/fixture-docs"}])
        with self.assertRaisesRegex(ValueError, "removed without a reviewed retirement receipt"):
            self.retire()

    def test_retired_catalog_identity_without_receipt_fails(self):
        with self.assertRaisesRegex(ValueError, "no reviewed retirement receipt: example:fixture-docs"):
            self.retire()

    def test_receipt_must_be_reviewed_and_approved(self):
        for key, value, message in (("decision", "pending", "Unapproved"), ("owner", "Someone", "Unapproved"),
                                    ("reviewer", " ", "Blank"), ("reviewedOn", "2026-13-01", "month")):
            with self.subTest(key=key):
                receipt = copy.deepcopy(self.receipt)
                receipt["review"][key] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.retire(receipt)
        receipt = copy.deepcopy(self.receipt)
        del receipt["review"]
        with self.assertRaisesRegex(ValueError, "Missing or unknown fields"):
            self.retire(receipt)

    def test_receipt_must_bind_the_exact_record_artifact_identity_and_roots(self):
        for mutate, message in (
                (lambda r: r.update(previousRecord="unrelated-r1"), "removed without a reviewed retirement receipt"),
                (lambda r: r["artifacts"][0].update(project="other"), "removed without a reviewed retirement receipt"),
                (lambda r: r["artifacts"][0].update(package="example:other"), "outside the retired packages"),
                (lambda r: r.update(packages=["example:other"]), "differs from publication catalog"),
                (lambda r: r.update(sourceRoots=["src/public/kotlin/other"]), "source roots differ"),
                (lambda r: r.update(task="CON.41"), "differs from publication catalog"),
                (lambda r: r.update(owner="Mobile"), "retirement identity"),
                (lambda r: r.update(designCommit="main"), "full immutable hash"),
                (lambda r: r.update(reason=""), "Blank"),
                (lambda r: r.update(id="other"), "path/ID mismatch"),
                (lambda r: r.update(schemaVersion=3), "Unknown retirement receipt schema")):
            with self.subTest(message=message):
                receipt = copy.deepcopy(self.receipt)
                mutate(receipt)
                with self.assertRaisesRegex(ValueError, message):
                    self.retire(receipt)

    def test_producer_sources_must_be_gone(self):
        self.fixture.write("src/public/kotlin/fixture-docs/Docs.kt", b"// still here\n")
        with self.assertRaisesRegex(ValueError, "still has producer sources"):
            self.retire(self.receipt)

    def test_retired_artifact_cannot_stay_registered_or_be_retired_twice(self):
        self.fixture.put(provenance.RETIREMENTS + "fixture-docs.json", self.receipt)
        self.inventory(["synthetic-docs-r1"])
        with self.assertRaisesRegex(ValueError, "Retired artifact is still registered"):
            self.fixture.validate(self.history, self.previous)
        twice = {**self.receipt, "id": "fixture-docs-again"}
        self.fixture.put(provenance.RETIREMENTS + "fixture-docs-again.json", twice)
        with self.assertRaisesRegex(ValueError, "more than one receipt"):
            self.retire()

    def test_legacy_format_needs_history_and_committed_receipts_are_immutable(self):
        legacy = json.loads((ROOT / LEGACY).read_text(encoding="utf-8"))
        legacy.update(project="fixture-docs", package="example:fixture-docs-old",
                      replacementPackage="example:fixture-docs", previousRecord="synthetic-docs-r1",
                      sourceRoot="src/public/kotlin/fixture-docs-old")
        with self.assertRaisesRegex(ValueError, "Unreviewed retirement receipt format"):
            self.retire(legacy, name="legacy")
        (self.root / provenance.RETIREMENTS / "legacy.json").unlink()
        path = provenance.RETIREMENTS + "fixture-docs.json"
        self.retire(self.receipt)
        self.history[path] = (self.root / path).read_bytes()
        changed = copy.deepcopy(self.receipt)
        changed["reason"] = "Rewritten history."
        with self.assertRaisesRegex(ValueError, "Used record changed or removed"):
            self.retire(changed)
        (self.root / path).unlink()
        with self.assertRaisesRegex(ValueError, "Used record changed or removed"):
            self.retire()


if __name__ == "__main__":
    unittest.main()
