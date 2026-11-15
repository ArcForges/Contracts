# SPDX-License-Identifier: Apache-2.0
"""Offline parsing/classification negatives and real Git/file drift controls; no Go process is substituted or run."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
import check_go_dependency_inventory as inventory


MAIN = "example.invalid/contracts"
EXPECT = "golang.org/x/tools/go/expect"
VERSION = "v0.1.1-deprecated"


def graph(extra=()):
    return inventory.module_graph([{"Path": MAIN, "Main": True}, *extra], MAIN)


class StrictGoOutputTests(unittest.TestCase):
    def test_concatenated_objects_and_test_variant_identities(self):
        records = inventory.json_stream(' {"ImportPath":"fmt","Standard":true}\n'
                                        '{"ImportPath":"example.invalid/contracts [example.invalid/contracts.test]",'
                                        '"ForTest":"example.invalid/contracts",'
                                        '"Module":{"Path":"example.invalid/contracts","Main":true}} ')
        packages = inventory.package_closure(records, graph())
        self.assertEqual(2, len(packages))
        self.assertEqual(MAIN, packages[0]["forTest"])

    def test_invalid_json_is_not_silently_partially_consumed(self):
        for text in ('', '[]', '{} trailing log', '{"Path":"one","Path":"two"}', '{"value":NaN}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                inventory.json_stream(text)

    def test_modules_reject_duplicates_errors_replacements_and_floating_versions(self):
        for extra in ([{"Path": "module", "Version": "latest"}],
                      [{"Path": "module", "Version": "v01.0.0"}],
                      [{"Path": "module", "Version": "v1.0.0-preview..1"}],
                      [{"Path": "module", "Version": "v1.0.0", "Error": "unresolved"}],
                      [{"Path": "module", "Version": "v1.0.0", "Replace": {"Path": "elsewhere"}}],
                      [{"Path": "module", "Version": "v1.0.0"}] * 2,
                      [{"Path": "unexpected", "Main": True}]):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                graph(extra)

    def test_partial_or_unmapped_package_results_fail(self):
        base = {"ImportPath": "module/pkg", "Module": {"Path": "module", "Version": "v1.0.0"}}
        selected = graph([{"Path": "module", "Version": "v1.0.0"}])
        cases = [{**base, "Incomplete": True}, {**base, "Error": {"Err": "failed"}},
                 {**base, "DepsErrors": [{"Err": "missing"}]}, {"ImportPath": "unclassified"},
                 {**base, "Module": {"Path": "module", "Version": "v2.0.0"}}]
        for package in cases:
            with self.subTest(package=package), self.assertRaises(ValueError):
                inventory.package_closure([package], selected)
        with self.assertRaises(ValueError):
            inventory.package_closure([base, base], selected)


class ClosureClassificationTests(unittest.TestCase):
    def test_difference_is_complete_but_an_unknown_name_gets_no_qualification(self):
        selected = graph([{"Path": EXPECT, "Version": VERSION}, {"Path": "unknown.invalid/module", "Version": "v1.0.0"}])
        result = inventory.classification({"tools": selected}, {"tool:staticcheck": []})
        self.assertEqual({EXPECT, "unknown.invalid/module"}, {row["path"] for row in result["metadataOnly"]})
        rows = {row["path"]: row for row in result["metadataOnly"]}
        self.assertTrue(rows[EXPECT]["eligibleForThisHostConfiguration"])
        self.assertFalse(rows["unknown.invalid/module"]["eligibleForThisHostConfiguration"])
        self.assertEqual(9, len(result["namedCandidates"]))

    def test_named_candidate_used_by_any_tool_or_owned_test_is_an_actual_dependency(self):
        selected = graph([{"Path": EXPECT, "Version": VERSION}])
        for context in ("tool:protoc-gen-go", "tool:protoc-gen-connect-go", "tool:staticcheck",
                        "tool:govulncheck", "owned-packages-and-tests"):
            closure = [{"importPath": EXPECT, "modulePath": EXPECT, "moduleVersion": VERSION}]
            result = inventory.classification({"main": selected, "tools": selected}, {context: closure})
            self.assertEqual([], result["metadataOnly"])
            self.assertEqual([context], result["actualDependencies"][0]["usedIn"])
            candidate = next(row for row in result["namedCandidates"] if row["path"] == EXPECT)
            self.assertFalse(candidate["eligibleForThisHostConfiguration"])
            self.assertEqual("actual-dependency", candidate["reason"])

    def test_use_of_a_different_version_also_revokes_the_named_metadata_qualification(self):
        main = graph([{"Path": EXPECT, "Version": "v0.1.0-deprecated"}])
        tools = graph([{"Path": EXPECT, "Version": VERSION}])
        packages = [{"modulePath": EXPECT, "moduleVersion": VERSION}]
        result = inventory.classification({"main": main, "tools": tools}, {"tool:staticcheck": packages})
        self.assertEqual("v0.1.0-deprecated", result["metadataOnly"][0]["version"])
        self.assertFalse(result["metadataOnly"][0]["eligibleForThisHostConfiguration"])


class SourceDriftTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="go-inventory-drift-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet")
        for name, value in {"source.go": "package fixture\n", ".gitignore": "artifacts/\n",
                            "go/go.sum": "public fixture checksum bytes\n"}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_unchanged_dirty_tree_is_recorded_without_claiming_a_clean_commit(self):
        (self.root / "source.go").write_text("package modified\n", encoding="utf-8")
        before = inventory.tree_snapshot(self.root)
        self.assertTrue(before["dirty"])
        inventory.unchanged(before, inventory.tree_snapshot(self.root))

    def test_lock_content_and_already_dirty_untracked_content_drift_are_detected(self):
        for name in ("go/go.sum", "untracked.go"):
            path = self.root / name
            path.write_text("before\n", encoding="utf-8")
            before = inventory.tree_snapshot(self.root)
            path.write_text("after\n", encoding="utf-8")
            after = inventory.tree_snapshot(self.root)
            self.assertEqual(before["statusSha256"], after["statusSha256"])
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, "drifted"):
                inventory.unchanged(before, after)

    def test_staging_or_head_change_is_drift_even_when_working_file_bytes_stay_equal(self):
        (self.root / "source.go").write_text("package modified\n", encoding="utf-8")
        before = inventory.tree_snapshot(self.root)
        self.git("add", "source.go")
        after = inventory.tree_snapshot(self.root)
        self.assertEqual(before["files"], after["files"])
        with self.assertRaises(ValueError):
            inventory.unchanged(before, after)
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "stage fixture")
        changed_head = inventory.tree_snapshot(self.root)
        self.assertEqual(after["files"], changed_head["files"])
        with self.assertRaises(ValueError):
            inventory.unchanged(after, changed_head)

    def test_output_cannot_overwrite_source_and_failed_evidence_replaces_stale_success(self):
        with self.assertRaises(ValueError):
            inventory.output_path(self.root / "go/go.sum", self.root)
        output = inventory.output_path(self.root / "artifacts/measurement.json", self.root)
        inventory.write_report(output, {"schema": inventory.SCHEMA, "result": "passed"})
        inventory.write_report(output, {"schema": inventory.SCHEMA, "result": "failed", "error": "query failed"})
        self.assertEqual("failed", json.loads(output.read_text(encoding="utf-8"))["result"])


if __name__ == "__main__":
    unittest.main()
