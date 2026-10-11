# SPDX-License-Identifier: Apache-2.0
"""CON.41: the public operation-metadata.v1 rows packaged in ArcForges.Contracts.PublicApi."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from check_operation_scope import proto_methods
from contracts import ARTIFACTS, ROOT, sha256, write_json
import packaging_tools as tools

PUBLIC_API = "ArcForges.Contracts.PublicApi"
NEVER_STAGED_SURFACES = {"private-helper", "in-process", "cf-internal", "operator"}


def package_row(identity):
    return next(row for row in tools.packages() if row["id"] == identity)


def source_rows():
    """Independent read of every authored export: (posix path, row) in file order."""
    rows = []
    for path in sorted((ROOT / "eng/operations").glob("*.json"), key=lambda item: item.name):
        document = json.loads(path.read_text(encoding="utf-8"))
        rows.extend((path.relative_to(ROOT).as_posix(), row) for row in document["operations"])
    return rows


def closure_protos():
    """Independent closure: Foundation plus PublicApi protos from the package catalog."""
    catalog = json.loads((ROOT / "eng/contract-packages.json").read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in catalog["packages"]}
    return set(rows["ArcForges.Contracts.Foundation"]["proto"]) | set(rows[PUBLIC_API]["proto"])


def serialize(document):
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class SelectionTests(unittest.TestCase):
    """The packaged document equals the gated source rows filtered by the CON.41 rule."""

    @classmethod
    def setUpClass(cls):
        cls.data, cls.sources = tools.operation_metadata(package_row(PUBLIC_API))
        cls.document = json.loads(cls.data)
        cls.staged = {row["operationId"]: row for row in cls.document["operations"]}

    def test_staged_rows_equal_filtered_source_rows_with_key_order(self):
        protos = closure_protos()
        expected = sorted((row for _, row in source_rows()
                           if row["surface"] == "public" and row["kind"] == "proto" and row["source"] in protos),
                          key=lambda row: row["operationId"])
        self.assertEqual(list(self.document), ["schemaVersion", "operations"])
        self.assertEqual(self.document["schemaVersion"], "operation-metadata.v1")
        self.assertEqual(self.document["operations"], expected)
        self.assertEqual(len(self.document["operations"]), len(expected))
        for staged, source in zip(self.document["operations"], expected):
            self.assertEqual(list(staged), list(source), staged["operationId"])
        self.assertTrue(all(row["surface"] == "public" and row["kind"] == "proto"
                            for row in self.document["operations"]))

    def test_every_con07_identity_workspace_device_row_is_staged(self):
        con07 = [row for path, row in source_rows() if path == "eng/operations/con-07.json"]
        self.assertTrue(con07)
        for row in con07:
            self.assertEqual(self.staged.get(row["operationId"]), row)

    def test_private_helper_in_process_cf_internal_and_operator_rows_are_never_staged(self):
        excluded = [row for _, row in source_rows() if row["surface"] in NEVER_STAGED_SURFACES]
        self.assertEqual({row["surface"] for row in excluded}, NEVER_STAGED_SURFACES)
        for row in excluded:
            self.assertNotIn(row["operationId"], self.staged)

    def test_public_rows_outside_the_descriptor_closure_are_not_staged(self):
        events = [row for _, row in source_rows()
                  if row["surface"] == "public" and row["binding"].startswith("arcforges.events.v1.")]
        self.assertTrue(events, "the Events closure rows exist in the source exports")
        for row in events:
            self.assertNotIn(row["operationId"], self.staged)

    def test_source_digests_name_exactly_the_contributing_exports(self):
        contributing = sorted({path for path, row in source_rows() if row["operationId"] in self.staged})
        self.assertEqual(list(self.sources), contributing)
        for path, digest in self.sources.items():
            self.assertEqual(digest, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())

    def test_every_staged_binding_names_an_authored_closure_method(self):
        methods = proto_methods(ROOT)
        protos = closure_protos()
        for row in self.document["operations"]:
            self.assertIn(methods.get(row["binding"]), protos, row["operationId"])
            self.assertEqual(methods[row["binding"]], row["source"])

    def test_only_the_public_api_package_stages_operation_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            for row in tools.packages():
                target = Path(folder) / row["id"].replace("@", "").replace("/", "-")
                target.mkdir()
                staged = tools.stage_operation_metadata(target, row)
                written = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
                if row["id"] == PUBLIC_API:
                    self.assertEqual(staged, self.data)
                    self.assertEqual(written, [tools.OPERATION_METADATA_PATH])
                else:
                    self.assertIsNone(staged)
                    self.assertEqual(written, [])


class PureSelectionTests(unittest.TestCase):
    """Hostile inputs to the pure selection function."""
    A = "public/proto/arcforges/a/v1/a.proto"
    E = "public/proto/arcforges/e/v1/e.proto"
    METHODS = {"arcforges.a.v1.AService/Get": A, "arcforges.a.v1.AService/Put": A,
               "arcforges.e.v1.EService/Poll": E}

    def row(self, operation, binding, *, surface="public", kind="proto", source=None):
        return {"operationId": operation, "binding": binding, "kind": kind,
                "source": self.METHODS.get(binding, "x") if source is None else source,
                "scope": "account", "surface": surface, "authorization": {"risk": "R1"}}

    def select(self, *rows, path="eng/operations/a.json"):
        exports = [(path, "0" * 64, {"schemaVersion": "operation-metadata.v1", "operations": list(rows)})]
        return [row["operationId"] for _, row in tools.select_operation_rows(exports, self.METHODS, {self.A})]

    def test_public_closure_proto_row_is_staged_and_non_closure_row_is_not(self):
        self.assertEqual(self.select(self.row("a.get", "arcforges.a.v1.AService/Get"),
                                     self.row("e.poll", "arcforges.e.v1.EService/Poll")), ["a.get"])

    def test_non_public_surfaces_binding_closure_methods_are_not_staged(self):
        for surface in sorted(NEVER_STAGED_SURFACES):
            with self.subTest(surface=surface):
                self.assertEqual(self.select(self.row("a.get", "arcforges.a.v1.AService/Get", surface=surface)), [])
        self.assertEqual(self.select(self.row("h.get", "GET /v1/a", kind="http", surface="public")), [])
        self.assertEqual(self.select(self.row("i.get", "IA.Get", kind="in-process", surface="in-process")), [])
        self.assertEqual(self.select(self.row("c.get", "POST /internal/a", kind="http", surface="cf-internal")), [])

    def test_source_mismatch_and_unknown_binding_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "does not resolve to its authored source"):
            self.select(self.row("a.get", "arcforges.a.v1.AService/Get", source=self.E))
        with self.assertRaisesRegex(ValueError, "does not resolve to its authored source"):
            self.select(self.row("a.gone", "arcforges.a.v1.AService/Gone", source=self.A))

    def test_duplicate_operation_id_and_binding_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate operationId"):
            self.select(self.row("a.get", "arcforges.a.v1.AService/Get"),
                        self.row("a.get", "arcforges.a.v1.AService/Put"))
        with self.assertRaisesRegex(ValueError, "duplicate operation binding"):
            self.select(self.row("a.get", "arcforges.a.v1.AService/Get"),
                        self.row("a.put", "arcforges.a.v1.AService/Get"))
        # A duplicate is refused even when the second row would never be staged.
        with self.assertRaisesRegex(ValueError, "duplicate operationId"):
            self.select(self.row("a.get", "arcforges.a.v1.AService/Get"),
                        self.row("a.get", "POST /internal/a", kind="http", surface="cf-internal"))

    def test_malformed_documents_and_rows_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Unsupported operation export"):
            tools.select_operation_rows([("eng/operations/a.json", "", {"schemaVersion": "v0", "operations": []})],
                                        self.METHODS, {self.A})
        with self.assertRaisesRegex(ValueError, "Unsupported operation export"):
            tools.select_operation_rows([("eng/operations/a.json", "", {"schemaVersion": "operation-metadata.v1"})],
                                        self.METHODS, {self.A})
        with self.assertRaisesRegex(ValueError, "row object required"):
            self.select(["not", "a", "row"])
        with self.assertRaisesRegex(ValueError, "operationId"):
            self.select(self.row(None, "arcforges.a.v1.AService/Get"))
        with self.assertRaisesRegex(ValueError, "binding"):
            self.select(self.row("a.get", ""))

    def test_rows_are_returned_in_ordinal_operation_id_order_with_rows_verbatim(self):
        rows = [self.row("b.get", "arcforges.a.v1.AService/Get"), self.row("B.put", "arcforges.a.v1.AService/Put"),
                {**self.row("a.get2", "arcforges.a.v1.AService/Get2", source=self.A), "extra": [1, {"z": 1, "a": 2}]}]
        methods = {**self.METHODS, "arcforges.a.v1.AService/Get2": self.A}
        exports = [("eng/operations/a.json", "", {"schemaVersion": "operation-metadata.v1", "operations": rows})]
        selected = tools.select_operation_rows(exports, methods, {self.A})
        self.assertEqual([row["operationId"] for _, row in selected], ["B.put", "a.get2", "b.get"])
        self.assertIs(selected[1][1], rows[2])


class ExportReadTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "eng/operations").mkdir(parents=True)

    def write(self, name, text):
        (self.root / "eng/operations" / name).write_bytes(text.encode("utf-8"))

    def test_exports_are_enumerated_in_ordinal_posix_order_with_byte_digests(self):
        document = '{"schemaVersion": "operation-metadata.v1", "operations": []}\n'
        for name in ["b.json", "a.json", "Z.json", "_.json"]:
            self.write(name, document.replace("[]", "[]" + " " * len(name)))
        self.write("ignored.txt", "not an export")
        exports = tools.operation_exports(self.root)
        self.assertEqual([path for path, _, _ in exports],
                         ["eng/operations/Z.json", "eng/operations/_.json", "eng/operations/a.json", "eng/operations/b.json"])
        for path, digest, _ in exports:
            self.assertEqual(digest, hashlib.sha256((self.root / path).read_bytes()).hexdigest())

    def test_duplicate_json_keys_and_non_object_documents_are_refused(self):
        self.write("a.json", '{"schemaVersion": "operation-metadata.v1", "operations": [], "operations": []}')
        with self.assertRaisesRegex(ValueError, "ambiguous duplicate JSON key"):
            tools.operation_exports(self.root)
        self.write("a.json", '[]')
        with self.assertRaisesRegex(ValueError, "object required"):
            tools.operation_exports(self.root)


class DeterminismTests(unittest.TestCase):
    def test_staging_is_byte_identical_lf_only_and_ordinal(self):
        row = package_row(PUBLIC_API)
        first, sources = tools.operation_metadata(row)
        second, sources_again = tools.operation_metadata(row)
        self.assertEqual(first, second)
        self.assertEqual(sources, sources_again)
        self.assertNotIn(b"\r", first)
        self.assertTrue(first.endswith(b"}\n") and not first.endswith(b"\n\n"))
        operations = [item["operationId"] for item in json.loads(first)["operations"]]
        self.assertEqual(operations, sorted(operations))
        self.assertEqual(first, serialize(json.loads(first)))

    def test_reversed_filesystem_order_gives_identical_bytes(self):
        row = package_row(PUBLIC_API)
        expected = tools.operation_metadata(row)
        original = Path.glob

        def reversed_glob(self, pattern, *args, **kwargs):
            return iter(sorted(original(self, pattern, *args, **kwargs), key=str, reverse=True))

        with patch.object(Path, "glob", reversed_glob):
            self.assertEqual(tools.operation_metadata(row), expected)

    def test_written_file_equals_returned_bytes(self):
        row = package_row(PUBLIC_API)
        with tempfile.TemporaryDirectory() as folder:
            data = tools.stage_operation_metadata(Path(folder), row)
            self.assertEqual((Path(folder) / tools.OPERATION_METADATA_PATH).read_bytes(), data)
            self.assertEqual(data, tools.operation_metadata(row)[0])


class CandidateTests(unittest.TestCase):
    """verify_artifacts on a copy of the producer's candidate, with hashes rewritten so only content fails."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.candidate = Path(folder.name) / "candidate"
        shutil.copytree(ARTIFACTS / "packages", self.candidate)
        self.manifest = json.loads((self.candidate / "manifest.json").read_text(encoding="utf-8"))

    def entry(self, identity):
        return next(item for item in self.manifest["files"] if item["id"] == identity)

    def files(self, identity):
        with zipfile.ZipFile(self.candidate / self.entry(identity)["name"]) as archive:
            return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}

    def rewrite(self, identity, files):
        package = self.candidate / self.entry(identity)["name"]
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        self.entry(identity).update(sha256=sha256(package), size=package.stat().st_size)
        write_json(self.candidate / "manifest.json", self.manifest)

    def mutate_rows(self, change):
        files = self.files(PUBLIC_API)
        document = json.loads(files[tools.OPERATION_METADATA_PATH])
        change(document["operations"])
        files[tools.OPERATION_METADATA_PATH] = serialize(document)
        self.rewrite(PUBLIC_API, files)

    def refused(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            tools.verify_artifacts(self.candidate)

    def test_positive_control_rewritten_but_unchanged_candidate_verifies(self):
        files = self.files(PUBLIC_API)
        self.assertEqual(files[tools.OPERATION_METADATA_PATH], tools.operation_metadata(package_row(PUBLIC_API))[0])
        self.rewrite(PUBLIC_API, files)
        tools.verify_artifacts(self.candidate)

    def test_source_json_binds_contributing_digests_in_public_api_only(self):
        expected = tools.operation_metadata(package_row(PUBLIC_API))[1]
        for item in self.manifest["files"]:
            if item["kind"] != "nuget":
                continue
            source = json.loads(self.files(item["id"])["source.json"])
            if item["id"] == PUBLIC_API:
                self.assertEqual(source["operationSources"], expected)
            else:
                self.assertNotIn("operationSources", source, item["id"])
                self.assertFalse([name for name in self.files(item["id"]) if name.startswith("operations/")])

    def test_removed_row_is_refused_as_missing(self):
        removed = []
        self.mutate_rows(lambda rows: removed.append(rows.pop(3)["operationId"]))
        self.refused("rows missing: " + removed[0].replace(".", r"\."))

    def test_added_cf_internal_row_is_refused_as_extra(self):
        cf = next(row for _, row in source_rows() if row["surface"] == "cf-internal")

        def add(rows):
            rows.append(cf)
            rows.sort(key=lambda row: row["operationId"])
        self.mutate_rows(add)
        self.refused("rows extra: " + cf["operationId"].replace(".", r"\."))

    def test_altered_risk_is_refused_as_changed(self):
        changed = []

        def alter(rows):
            rows[0]["authorization"]["risk"] = "R1" if rows[0]["authorization"]["risk"] != "R1" else "R4"
            changed.append(rows[0]["operationId"])
        self.mutate_rows(alter)
        self.refused("rows changed: " + changed[0].replace(".", r"\."))

    def test_reordered_keys_are_refused_as_changed(self):
        changed = []

        def reorder(rows):
            rows[1] = dict(reversed(list(rows[1].items())))
            changed.append(rows[1]["operationId"])
        self.mutate_rows(reorder)
        self.refused("rows changed: " + changed[0].replace(".", r"\."))

    def test_reordered_rows_are_refused_as_non_deterministic(self):
        self.mutate_rows(lambda rows: rows.reverse())
        self.refused("deterministic staged byte layout")

    def test_crlf_layout_is_refused_as_non_deterministic(self):
        files = self.files(PUBLIC_API)
        files[tools.OPERATION_METADATA_PATH] = files[tools.OPERATION_METADATA_PATH].replace(b"\n", b"\r\n")
        self.rewrite(PUBLIC_API, files)
        self.refused("deterministic staged byte layout")

    def test_duplicated_row_is_refused(self):
        self.mutate_rows(lambda rows: rows.insert(1, rows[0]))
        self.refused("Duplicate packaged operation row")

    def test_deleted_operations_file_is_refused(self):
        files = self.files(PUBLIC_API)
        del files[tools.OPERATION_METADATA_PATH]
        self.rewrite(PUBLIC_API, files)
        self.refused("is missing operations/operation-metadata.v1.json")

    def test_extra_file_under_operations_is_refused(self):
        files = self.files(PUBLIC_API)
        files["operations/extra.json"] = b"{}\n"
        self.rewrite(PUBLIC_API, files)
        self.refused("Unexpected operation metadata entries")

    def test_wrong_document_shape_is_refused(self):
        files = self.files(PUBLIC_API)
        document = json.loads(files[tools.OPERATION_METADATA_PATH])
        document["schemaVersion"] = "operation-metadata.v2"
        files[tools.OPERATION_METADATA_PATH] = serialize(document)
        self.rewrite(PUBLIC_API, files)
        self.refused("not an operation-metadata.v1 document")

    def test_changed_missing_or_extra_source_digest_is_refused(self):
        expected = tools.operation_metadata(package_row(PUBLIC_API))[1]
        first = sorted(expected)[0]
        cases = [
            ("changed", lambda sources: sources.__setitem__(first, "0" * 64), "digest differs for " + first),
            ("missing", lambda sources: sources.pop(first), "missing contributing export: " + first),
            ("extra", lambda sources: sources.__setitem__("eng/operations/con-14.json", "0" * 64),
             "non-contributing export: eng/operations/con-14.json"),
        ]
        pristine = self.files(PUBLIC_API)
        for label, change, pattern in cases:
            with self.subTest(label):
                files = dict(pristine)
                source = json.loads(files["source.json"])
                change(source["operationSources"])
                files["source.json"] = json.dumps(source, indent=2).encode("utf-8")
                self.rewrite(PUBLIC_API, files)
                self.refused(pattern.replace(".", r"\."))
        files = dict(pristine)
        source = json.loads(files["source.json"])
        del source["operationSources"]
        files["source.json"] = json.dumps(source, indent=2).encode("utf-8")
        self.rewrite(PUBLIC_API, files)
        self.refused("source.json is missing operationSources")

    def test_operations_file_injected_into_another_package_is_refused(self):
        payload = self.files(PUBLIC_API)[tools.OPERATION_METADATA_PATH]
        files = self.files("ArcForges.Contracts.Foundation")
        files[tools.OPERATION_METADATA_PATH] = payload
        self.rewrite("ArcForges.Contracts.Foundation", files)
        self.refused("Operation metadata is packaged only in ArcForges.Contracts.PublicApi: ArcForges.Contracts.Foundation")

    def test_operation_sources_injected_into_another_package_is_refused(self):
        files = self.files("ArcForges.Contracts.Foundation")
        source = json.loads(files["source.json"])
        source["operationSources"] = {}
        files["source.json"] = json.dumps(source, indent=2).encode("utf-8")
        self.rewrite("ArcForges.Contracts.Foundation", files)
        self.refused("Operation metadata is packaged only in")


class StagedCSharpCaseTests(unittest.TestCase):
    """The StructureTests --con-41-staged case that pack runs on the staged file, run here on real and tampered bytes."""

    STRUCTURE_TESTS = ROOT / "tests/StructureTests/bin/Release/net10.0/StructureTests.dll"

    @classmethod
    def setUpClass(cls):
        if not cls.STRUCTURE_TESTS.is_file():
            raise AssertionError("Run eng/contracts.py pack first: StructureTests is not built")
        cls.data, _ = tools.operation_metadata(package_row(PUBLIC_API))

    def run_case(self, data):
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary) / "operation-metadata.v1.json"
            staged.write_bytes(data)
            return subprocess.run(["dotnet", str(self.STRUCTURE_TESTS), str(ROOT), "--con-41-staged", str(staged)],
                                  capture_output=True, text=True, encoding="utf-8", check=False)

    def test_pack_runs_the_case_on_the_staged_file_before_dotnet_pack(self):
        source = (ROOT / "eng/packaging_tools.py").read_text(encoding="utf-8")
        body = source[source.index("def pack(release: str)"):]
        self.assertLess(body.index('"--con-41-staged", nuget_metadata / OPERATION_METADATA_PATH'), body.index('run("dotnet", "pack"'))
        self.assertIn('args[1] == "--con-41-staged") return Con41OperationMetadataCases.Run(root, Path.GetFullPath(args[2]));',
                      (ROOT / "tests/StructureTests/Program.cs").read_text(encoding="utf-8"))

    def test_staged_rows_are_accepted_with_the_count_by_service(self):
        result = self.run_case(self.data)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = json.loads(self.data)["operations"]
        self.assertIn(f"{len(rows)} rows, one per generated PublicApi method", result.stdout)
        self.assertIn("sha256 " + hashlib.sha256(self.data).hexdigest(), result.stdout)

    def test_tampered_staged_files_are_refused(self):
        document = json.loads(self.data)
        rows = document["operations"]
        altered = json.loads(json.dumps(rows[0]))
        altered["idempotency"] = "Q" if altered["idempotency"] != "Q" else "I"
        cf_internal = next(row for _, row in source_rows() if row.get("surface") == "cf-internal")
        cases = {
            "has no row": rows[1:],
            "differs from its eng/operations source row": [altered, *rows[1:]],
            "duplicate operationId": [rows[0], *rows],
            "is not a public row": sorted([*rows, cf_internal], key=lambda row: row["operationId"]),
        }
        for reason, tampered in cases.items():
            with self.subTest(reason=reason):
                result = self.run_case(serialize({"schemaVersion": document["schemaVersion"], "operations": tampered}))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
        result = self.run_case(self.data.replace(b'"schemaVersion"', b'"schemaVersion": "operation-metadata.v1", "schemaVersion"', 1))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("staged: invalid JSON", result.stderr)



class DocumentationTests(unittest.TestCase):
    """The packaged README and the release/consumer guides state the shipped path and its bindings."""

    README = ROOT / "src/public/dotnet/ArcForges.Contracts.PublicApi/README.md"

    def text(self, path):
        """Whitespace-normalised, so prose rewrapping does not change what is asserted."""
        return " ".join(path.read_text(encoding="utf-8").split())

    def test_package_readme_is_packed_and_states_the_path_rule_and_order(self):
        project = self.text(self.README.with_name(f"{PUBLIC_API}.csproj"))
        self.assertIn("<PackageReadmeFile>README.md</PackageReadmeFile>", project)
        readme = self.text(self.README)
        for fact in (f"`{tools.OPERATION_METADATA_PATH}`", f"`{tools.OPERATION_SCHEMA_VERSION}`",
                     "`surface` is `public`", "`kind` is `proto`", "descriptor closure", "value-identical",
                     "`eng/operations`", "ordinal", "arcforges.hello.v1.HelloService/SayHello"):
            self.assertIn(fact, readme)

    def test_packaged_readme_is_the_checked_in_readme(self):
        manifest = json.loads((ARTIFACTS / "packages/manifest.json").read_text(encoding="utf-8"))
        entry = next(item for item in manifest["files"] if item["id"] == PUBLIC_API)
        with zipfile.ZipFile(ARTIFACTS / "packages" / entry["name"]) as archive:
            packaged = archive.read("README.md")
        self.assertEqual(packaged.replace(b"\r\n", b"\n"), self.README.read_bytes().replace(b"\r\n", b"\n"))

    def test_releasing_guide_states_the_candidate_bindings_and_evidence(self):
        guide = self.text(ROOT / "docs/releasing.md")
        for fact in (f"`{tools.OPERATION_METADATA_PATH}`", "`source.json`", "`operationSources`", "SHA256",
                     "missing, extra or changed row", "count by service", "--con-41-staged"):
            self.assertIn(fact, guide)
        evidence = tools.operation_evidence(package_row(PUBLIC_API), b'{"operations": []}')
        self.assertIn(tools.OPERATION_METADATA_PATH, evidence)
        self.assertIn("by service", evidence)

    def test_consumer_guide_reads_the_restored_package_by_its_path_property(self):
        guide = self.text(ROOT / "docs/consuming.md")
        csharp = guide[guide.index("## C#"):guide.index("## Internal npm package")]
        self.assertIn(f'<PackageReference Include="{PUBLIC_API}" GeneratePathProperty="true" />', csharp)
        property_name = "Pkg" + PUBLIC_API.replace(".", "_")
        self.assertIn(f"$({property_name})/{tools.OPERATION_METADATA_PATH}", csharp)
        self.assertIn("Pin the exact version", csharp)
        self.assertIn("never read it from a Contracts checkout or source tree", csharp)


if __name__ == "__main__":
    unittest.main()
