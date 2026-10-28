# SPDX-License-Identifier: Apache-2.0
"""AF-CTR-01: offline negatives of the Go bindings tooling (no Go toolchain or network is used here).

The Go checks themselves (generation drift, gofmt, vet, staticcheck, tidy drift, tests, the C#/Go exchange, the module
identity against the go command, govulncheck) run through python eng/contracts.py go ...; these tests pin the rules of
the inventory row, the module identity, publication and admission that those checks and the publish job rely on.
"""

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
import go_bindings  # noqa: E402
from package_catalog import go_row as validate_go_row  # noqa: E402
import dependency_admission  # noqa: E402
import check_licences  # noqa: E402


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def repository(files: dict[str, bytes]) -> tuple[Path, str, tempfile.TemporaryDirectory]:
    holder = tempfile.TemporaryDirectory(prefix="go-module-")
    root = Path(holder.name)
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    git(root, "config", "core.autocrlf", "false")
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    git(root, "add", "-A")
    git(root, "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
    return root, git(root, "rev-parse", "HEAD"), holder


class GoModuleRow(unittest.TestCase):
    def setUp(self):
        self.row = copy.deepcopy(go_bindings.go_row())

    def test_registered_row(self):
        self.assertEqual(self.row["id"], "github.com/ArcForges/Contracts/go")
        self.assertEqual((self.row["kind"], self.row["channel"], self.row["access"], self.row["sourceRoot"]),
                         ("go", "go-module", "internal", "go"))
        packages = {item["protoPackage"]: item["contractAccess"] for item in self.row["goPackages"]}
        self.assertEqual(packages, {
            "arcforges.foundation.v1": "public", "arcforges.hello.v1": "public", "arcforges.publicapi.v1": "public",
            "arcforges.catalog.v1": "public", "arcforges.node.v1": "public", "arcforges.fleet.v1": "public",
            "arcforges.relay.v1": "internal", "arcforges.operator.v1": "internal"})
        # Every file of the eight proto packages, and nothing else (retired identities stay retired).
        expected = sorted(path for path in git(ROOT, "ls-files", "*.proto").split()
                          if path.split("/proto/")[0] in {"public", "internal"}
                          and path.split("/proto/")[1].split("/")[1] in {
                              "foundation", "hello", "publicapi", "catalog", "node", "fleet", "relay", "operator"})
        self.assertEqual(sorted(self.row["proto"]), expected)

    def test_row_negatives(self):
        def mutate(change):
            row = copy.deepcopy(self.row)
            change(row)
            return row
        cases = {
            "public access": lambda row: row.update(access="public"),
            "other root": lambda row: row.update(sourceRoot="src/internal/go"),
            "other channel": lambda row: row.update(channel="npm"),
            "dependency": lambda row: row.update(dependencies=["ArcForges.Contracts.Foundation"]),
            "json schema": lambda row: row.update(jsonSchemas=["public/http/v1/schema.json"]),
            "unmapped file": lambda row: row["proto"].append("public/proto/arcforges/events/v1/events.proto"),
            "duplicate file": lambda row: row["proto"].append(row["proto"][0]),
            "renamed package": lambda row: row["goPackages"][0].update(name="foundation"),
            "wrong import path": lambda row: row["goPackages"][0].update(
                importPath="github.com/ArcForges/Contracts/go/internal/foundation/v1"),
            "internal file in a public package": lambda row: row["goPackages"][-1].update(contractAccess="public"),
            "unused mapping": lambda row: row["goPackages"].append({
                "protoPackage": "arcforges.events.v1", "importPath": "github.com/ArcForges/Contracts/go/arcforges/events/v1",
                "name": "eventsv1", "contractAccess": "public"}),
        }
        for label, change in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_go_row(mutate(change))

    def test_mapping_options_use_virtual_paths(self):
        options = go_bindings.mapping_options(self.row)
        self.assertEqual(len(options), len(self.row["proto"]))
        self.assertIn("Marcforges/relay/v1/relay.proto=github.com/ArcForges/Contracts/go/arcforges/relay/v1;relayv1",
                      options)
        self.assertTrue(all("\\" not in option and option.count(";") == 1 for option in options))

    def test_package_doc_states_the_access_boundary(self):
        item = next(item for item in self.row["goPackages"] if item["contractAccess"] == "internal")
        text = go_bindings.package_doc(item["name"], item, connect=False)
        self.assertTrue(text.startswith("// SPDX-License-Identifier: Apache-2.0\n"))
        self.assertRegex(text, go_bindings.GENERATED_HEADER)
        self.assertIn("Contract access: internal.", text)
        self.assertTrue(text.endswith(f"package {item['name']}\n"))
        self.assertTrue(all(len(line) <= 120 for line in text.splitlines()))


class ModuleIdentity(unittest.TestCase):
    def test_hash1_is_the_dirhash_summary(self):
        files = [("m@v1.0.0/b.go", b"package b\n"), ("m@v1.0.0/a.go", b"package a\n")]
        summary = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files))
        self.assertEqual(go_bindings.hash1(files),
                         "h1:" + base64.b64encode(hashlib.sha256(summary.encode()).digest()).decode())
        self.assertNotEqual(go_bindings.hash1(files), go_bindings.hash1([files[0], ("m@v1.0.0/a.go", b"changed\n")]))

    def test_module_files_exclude_nested_modules_and_keep_the_committed_tree(self):
        root, commit, holder = repository({
            "go/go.mod": b"module github.com/ArcForges/Contracts/go\n\ngo 1.27.3\n",
            "go/LICENSE": b"licence\n",
            "go/arcforges/x/v1/x.pb.go": b"package xv1\n",
            "go/tools/go.mod": b"module github.com/ArcForges/Contracts/go/tools\n",
            "go/tools/go.sum": b"",
            "README.md": b"outside the module\n",
        })
        with holder:
            (root / "go/LICENSE").write_bytes(b"uncommitted change\n")
            files = dict(go_bindings.module_files(commit, root))
            self.assertEqual(sorted(files), ["LICENSE", "arcforges/x/v1/x.pb.go", "go.mod"])
            self.assertEqual(files["LICENSE"], b"licence\n")
            identity = go_bindings.module_identity(commit, "1.0.0-ci.7.2", root)
            self.assertEqual((identity["version"], identity["tag"], identity["files"]),
                             ("v1.0.0-ci.7.2", "go/v1.0.0-ci.7.2", 3))
            self.assertEqual(identity["goModHash"], go_bindings.hash1([("go.mod", files["go.mod"])]))
            # The zip names carry the module path and version, so another version has another hash.
            self.assertNotEqual(identity["zipHash"], go_bindings.module_identity(commit, "1.0.0-ci.7.3", root)["zipHash"])

    def test_module_files_refuse_links_and_export_attributes(self):
        for extra in ({".gitattributes": b"go/README.md export-ignore\n", "go/README.md": b"readme\n"},
                      {".gitattributes": b"go/*.go export-subst\n", "go/doc.go": b"package x\n"}):
            root, commit, holder = repository({"go/go.mod": b"module github.com/ArcForges/Contracts/go\n", **extra})
            with holder, self.subTest(extra=sorted(extra)), self.assertRaisesRegex(ValueError, "changes the Go module zip"):
                go_bindings.module_files(commit, root)
        if os.name != "nt":
            root, commit, holder = repository({"go/go.mod": b"module github.com/ArcForges/Contracts/go\n"})
            with holder:
                (root / "go/link").symlink_to("go.mod")
                git(root, "add", "-A")
                git(root, "-c", "commit.gpgsign=false", "commit", "-qm", "link")
                with self.assertRaisesRegex(ValueError, "Unsupported Git entry"):
                    go_bindings.module_files(git(root, "rev-parse", "HEAD"), root)

    def test_go_versions(self):
        self.assertEqual(go_bindings.go_version("1.0.0-ci.12.1"), "v1.0.0-ci.12.1")
        self.assertEqual(go_bindings.go_version("1.4.0"), "v1.4.0")
        with self.assertRaisesRegex(ValueError, "major version 2"):
            go_bindings.go_version("2.0.0")
        for value in ("v1.0.0", "1.0.0-rc.1", "1.0.0-ci.01.1"):
            with self.subTest(value), self.assertRaises(ValueError):
                go_bindings.go_version(value)

    def test_proxy_path_escaping(self):
        self.assertEqual(go_bindings.escape_path("github.com/ArcForges/Contracts/go"),
                         "github.com/!arc!forges/!contracts/go")

    def test_candidate_must_match_the_checkout(self):
        row = go_bindings.go_row()
        document = {"format": go_bindings.CANDIDATE_FORMAT, "zipHash": "h1:x"}
        with patch("go_bindings.candidate_document", return_value={"format": go_bindings.CANDIDATE_FORMAT,
                                                                   "zipHash": "h1:y"}):
            with self.assertRaisesRegex(ValueError, "differs from the checkout"):
                go_bindings.verify_candidate(document, row, "1.0.0-ci.1.1", {"commit": "a" * 40, "dirty": False})
        with self.assertRaisesRegex(ValueError, "Unknown Go module candidate format"):
            go_bindings.verify_candidate({"format": "other"}, row, "1.0.0-ci.1.1", {"commit": "a" * 40, "dirty": False})


class Publication(unittest.TestCase):
    COMMIT = "c" * 40

    def document(self, **change):
        value = {"format": go_bindings.CANDIDATE_FORMAT, "module": go_bindings.GO_MODULE, "version": "v1.0.0-ci.5.1",
                 "tag": "go/v1.0.0-ci.5.1", "commit": self.COMMIT, "dirty": False, "zipHash": "h1:zip",
                 "goModHash": "h1:mod"}
        value.update(change)
        return value

    def test_existing_tag_is_never_moved(self):
        responses = {"GET": (200, {"ref": "refs/tags/go/v1.0.0-ci.5.1", "object": {"type": "commit", "sha": "d" * 40}})}
        with patch("go_bindings.http_json", side_effect=lambda method, *args, **kwargs: responses[method]):
            with self.assertRaisesRegex(ValueError, "never moved"):
                go_bindings.create_tag("ArcForges/Contracts", "go/v1.0.0-ci.5.1", self.COMMIT, "token")

    def test_tag_is_created_once_and_accepted_at_the_same_commit(self):
        calls = []

        def respond(method, url, token=None, body=None):
            calls.append((method, url, body))
            if method == "POST":
                return 201, {}
            return 404, None
        with patch("go_bindings.http_json", side_effect=respond):
            self.assertEqual(go_bindings.create_tag("ArcForges/Contracts", "go/v1.0.0-ci.5.1", self.COMMIT, "t"), "created")
        self.assertEqual(calls[-1][2], {"ref": "refs/tags/go/v1.0.0-ci.5.1", "sha": self.COMMIT})
        annotated = {"ref": "refs/tags/go/v1.0.0-ci.5.1", "object": {"type": "tag", "sha": "e" * 40}}

        def peel(method, url, token=None, body=None):
            if url.endswith("/git/tags/" + "e" * 40):
                return 200, {"object": {"type": "commit", "sha": self.COMMIT}}
            return 200, annotated
        with patch("go_bindings.http_json", side_effect=peel):
            self.assertEqual(go_bindings.create_tag("ArcForges/Contracts", "go/v1.0.0-ci.5.1", self.COMMIT, "t"), "existing")

    def test_handoff_requires_the_commit_and_the_recorded_hashes(self):
        info = {"Version": "v1.0.0-ci.5.1", "Origin": {"Hash": self.COMMIT}}

        class Lookup:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        good = (f"{go_bindings.GO_MODULE} v1.0.0-ci.5.1 h1:zip\n{go_bindings.GO_MODULE} v1.0.0-ci.5.1/go.mod h1:mod\n\n"
                "go.sum database tree\n").encode()
        with patch("go_bindings.http_json", return_value=(200, info)), patch("go_bindings.urlopen",
                                                                            return_value=Lookup(good)), \
                patch("time.sleep"):
            self.assertEqual(go_bindings.resolve(self.document())["attempts"], 1)
            with self.assertRaisesRegex(ValueError, "checksum database records other hashes"):
                go_bindings.resolve(self.document(zipHash="h1:other"))
        moved = {"Version": "v1.0.0-ci.5.1", "Origin": {"Hash": "d" * 40}}
        with patch("go_bindings.http_json", return_value=(200, moved)), patch("time.sleep"):
            with self.assertRaisesRegex(ValueError, "not " + self.COMMIT):
                go_bindings.resolve(self.document())
        with patch("go_bindings.http_json", return_value=(410, None)), patch("time.sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "did not resolve"):
                go_bindings.resolve(self.document(), attempts=3)
            self.assertEqual(sleep.call_count, 3)

    def test_publish_refuses_another_commit_or_a_dirty_candidate(self):
        environment = {"GITHUB_REF": "refs/heads/main", "GITHUB_SHA": self.COMMIT, "GITHUB_TOKEN": "t",
                       "GITHUB_REPOSITORY": "ArcForges/Contracts"}
        for document in (self.document(commit="d" * 40), self.document(dirty=True), self.document(version="v1.0.0-ci.5.2")):
            with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, environment), \
                    patch("go_bindings.create_tag", side_effect=AssertionError("tagged")):
                directory = Path(temporary)
                (directory / "go-module.json").write_text(json.dumps(document), encoding="utf-8")
                manifest = {"version": "1.0.0-ci.5.1", "commit": self.COMMIT, "dirty": False}
                with self.assertRaisesRegex(ValueError, "does not describe this publishing commit"):
                    go_bindings.publish(directory, manifest, {"name": "go-module.json", "kind": "go"})


class ExchangeSamples(unittest.TestCase):
    def test_map_entries_get_distinct_ordered_keys_and_no_unknowns(self):
        model = {"messages": {
            ".p.M": {1: {"name": "labels", "type": 11, "label": 3, "typeName": ".p.M.LabelsEntry", "oneof": None}},
            ".p.M.LabelsEntry": {1: {"name": "key", "type": 9, "label": 1, "typeName": "", "oneof": None},
                                 2: {"name": "value", "type": 9, "label": 1, "typeName": "", "oneof": None}}},
            "enums": {}}
        entries = go_bindings.map_entries(model)
        self.assertEqual(entries, {".p.M.LabelsEntry"})
        tree = {1: [{1: "k", 2: "v", "?": [b"x"]}, {1: "k", 2: "w", "?": [b"x"]}], "?": [b"y"]}
        sample = go_bindings.map_sample(model, entries, ".p.M", tree)
        self.assertEqual(sample, {1: [{1: "A-k", 2: "v"}, {1: "B-k", 2: "w"}], "?": [b"y"]})


class DependencyAdmission(unittest.TestCase):
    def test_go_sum_rows_and_tool_only_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "go/tools").mkdir(parents=True)
            (root / "go/go.sum").write_text("a.example/m v1.2.3 h1:aaa=\na.example/m v1.2.3/go.mod h1:bbb=\n")
            (root / "go/tools/go.sum").write_text(
                "a.example/m v1.2.3 h1:aaa=\nb.example/t v0.0.0-20240101000000-abcdefabcdef h1:ccc=\n")
            self.assertEqual(dependency_admission.go_sum_rows(root, "go/go.sum"), [("a.example/m", "v1.2.3", "h1:aaa=")])
            self.assertEqual(dependency_admission.go_tool_only(root),
                             {"go:b.example/t@v0.0.0-20240101000000-abcdefabcdef"})
            for line in ("a.example/m latest h1:aaa=", "a.example/m v1.2.3 sha256:aaa", "a.example/m v1.2.3"):
                (root / "go/go.sum").write_text(line + "\n")
                with self.subTest(line), self.assertRaises(ValueError):
                    dependency_admission.go_sum_rows(root, "go/go.sum")

    def test_stable_closure_exempts_only_tool_modules(self):
        policy = json.loads((ROOT / dependency_admission.POLICY).read_text())
        actual = dependency_admission.inventory(ROOT)
        tool_only = dependency_admission.go_tool_only(ROOT)
        self.assertTrue(any("-" in key.rsplit("@", 1)[1] for key in tool_only))
        dependency_admission.validate(policy, actual, stable=True, tool_only=tool_only)
        runtime_prerelease = next(key for key in tool_only if "-" in key.rsplit("@", 1)[1])
        with self.assertRaisesRegex(ValueError, "Stable closure contains prerelease"):
            dependency_admission.validate(policy, actual, stable=True, tool_only=tool_only - {runtime_prerelease})


class LicenceBoundary(unittest.TestCase):
    def test_go_modules_are_registered_and_checked(self):
        result = check_licences.audit(ROOT)
        self.assertEqual(sorted(project["path"] for project in result["projects"] if project["kind"] == "go"),
                         ["go/go.mod", "go/tools/go.mod"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--cached", "--others",
                                                 "--exclude-standard"], text=True).splitlines():
                if path.endswith(("go.mod", ".csproj", "package.json", "LICENSE")) or path in {
                        "eng/policy/licence-boundary.json", "Directory.Build.props", "Directory.Build.targets",
                        "Directory.Packages.props"} or path.endswith("packages.lock.json") or path == "package-lock.json":
                    (root / path).parent.mkdir(parents=True, exist_ok=True)
                    (root / path).write_bytes((ROOT / path).read_bytes())
            git(root, "init", "-q")
            git(root, "add", "-A")
            check_licences.audit(root)
            for label, path, data in (
                    ("replace", "go/go.mod", (ROOT / "go/go.mod").read_text() + "\nreplace a.example/m => ../m\n"),
                    ("first-party requirement", "go/tools/go.mod",
                     (ROOT / "go/tools/go.mod").read_text() + "\nrequire github.com/ArcForges/Cloud v1.0.0\n"),
                    ("other module", "go/go.mod", "module github.com/ArcForges/Other\n"),
                    ("licence", "go/LICENSE", "MIT\n")):
                original = (root / path).read_bytes()
                (root / path).write_text(data)
                with self.subTest(label), self.assertRaises(ValueError):
                    check_licences.audit(root)
                (root / path).write_bytes(original)


if __name__ == "__main__":
    unittest.main()
