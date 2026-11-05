# SPDX-License-Identifier: Apache-2.0
"""AF-CON-01: the adopted flagship design contracts, their packages, error catalogue and gates."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "eng" / (name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


scope = module("check_operation_scope")
compatibility = module("check_compatibility")
digests = module("flagship_schema_digest")


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


RECORD = load("eng/flagship-contracts.json")
CATALOGUE = load("fixtures/public/af-con-01-error-catalogue.json")
# Independent placement oracle (ArcForges-Design docs/contracts/README.md section 1): package, access, C# namespace.
PLACEMENT = {
    "node": ("ArcForges.Contracts.Node", "public", "ArcForges.Contracts.Node.V1"),
    "fleet": ("ArcForges.Contracts.Fleet", "public", "ArcForges.Contracts.Fleet.V1"),
    "peer": ("ArcForges.Contracts.Peer", "internal", "ArcForges.Contracts.Peer.V1"),
    "relay": ("ArcForges.Contracts.Relay", "internal", "ArcForges.Contracts.Relay.V1"),
    "publicapi": ("ArcForges.Contracts.PublicApi", "public", "ArcForges.Contracts.PublicApi.V1"),
    "operator": ("ArcForges.Contracts.CloudInternal", "internal", "ArcForges.Contracts.CloudInternal.Operator.V1"),
}
NEW_PACKAGES = {
    "ArcForges.Contracts.Node": ["ArcForges.Contracts.Foundation"],
    "ArcForges.Contracts.Fleet": ["ArcForges.Contracts.Foundation", "ArcForges.Contracts.Node"],
    "ArcForges.Contracts.Peer": ["ArcForges.Contracts.Foundation", "ArcForges.Contracts.Node"],
    "ArcForges.Contracts.Relay": ["ArcForges.Contracts.Foundation", "ArcForges.Contracts.Node", "ArcForges.Contracts.Fleet"],
}
SERVICE_COUNTS = {"node": 19, "fleet": 3, "peer": 6, "relay": 0, "publicapi": 1, "operator": 1}


def foundation_enum(name):
    text = (ROOT / "public/proto/arcforges/foundation/v1/foundation.proto").read_text(encoding="utf-8")
    body = re.search(r"^enum " + name + r" \{(.*?)^\}", text, re.M | re.S).group(1)
    return set(re.findall(r"^\s+([A-Z_]+) = \d+;", body, re.M))


class AdoptionRecord(unittest.TestCase):
    def test_every_adopted_file_is_byte_identical_and_placed_by_the_design(self):
        self.assertEqual(RECORD["schemaVersion"], "flagship-contracts.v1")
        self.assertEqual(RECORD["design"]["commit"], "78f0f5a4bb614c184e51da9a2d3030595f4f5976")
        self.assertEqual(len(RECORD["files"]), 25)
        for row in RECORD["files"]:
            area = row["design"].split("/")[1]
            package, access, namespace = PLACEMENT[area]
            self.assertEqual(row["path"], f"{access}/proto/{row['design']}")
            self.assertEqual(row["package"], package)
            data = (ROOT / row["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"], row["path"])
            text = data.decode("utf-8")
            self.assertIn(f'option csharp_namespace = "{namespace}";', text, row["path"])
            self.assertNotRegex(text, r'import "google/', row["path"])

    def test_the_record_lists_exactly_the_flagship_schema_files(self):
        actual = {path.relative_to(ROOT).as_posix() for base in ("public/proto/arcforges/node",
                  "public/proto/arcforges/fleet", "internal/proto/arcforges/peer", "internal/proto/arcforges/relay")
                  for path in (ROOT / base).rglob("*.proto")}
        actual |= {"public/proto/arcforges/publicapi/v1/support_access.proto",
                   "internal/proto/arcforges/operator/v1/operator_read.proto"}
        self.assertEqual({row["path"] for row in RECORD["files"]}, actual)
        self.assertEqual(sum(row["design"].startswith("arcforges/node/") for row in RECORD["files"]), 20)

    def test_packages_have_the_design_access_and_own_exactly_their_files(self):
        catalog = {row["id"]: row for row in load("eng/contract-packages.json")["packages"]}
        for package, dependencies in NEW_PACKAGES.items():
            row = catalog[package]
            owned = sorted(item["path"] for item in RECORD["files"] if item["package"] == package)
            self.assertEqual(sorted(row["proto"]), owned)
            self.assertEqual(row["dependencies"], dependencies)
            self.assertEqual(row["kind"], "nuget")
            self.assertNotIn("retired", row)
            self.assertEqual(row["access"], next(access for name, access, _ in PLACEMENT.values() if name == package))
            self.assertTrue(row["sourceRoot"].startswith("src/" + row["access"] + "/dotnet/"))
            self.assertEqual(row["jsonSchemas"], [])
        self.assertEqual(catalog["ArcForges.Contracts.PublicApi"]["proto"][-1], "public/proto/arcforges/publicapi/v1/support_access.proto")
        self.assertEqual(catalog["ArcForges.Contracts.CloudInternal"]["proto"][-1], "internal/proto/arcforges/operator/v1/operator_read.proto")
        # The reused packages keep their dependencies; Validation gains no flagship dependency.
        self.assertEqual(catalog["ArcForges.Contracts.PublicApi"]["dependencies"], ["ArcForges.Contracts.Foundation"])
        self.assertNotIn("ArcForges.Contracts.Node", catalog["ArcForges.Contracts.Validation"]["dependencies"])

    def test_service_counts_match_the_design_package_table(self):
        methods = scope.proto_methods(ROOT)
        for area, count in SERVICE_COUNTS.items():
            files = {row["path"] for row in RECORD["files"] if row["design"].split("/")[1] == area}
            services = {binding.split("/")[0] for binding, source in methods.items() if source in files}
            self.assertEqual(len(services), count, area)
        self.assertEqual(sum(source in {row["path"] for row in RECORD["files"]} for source in methods.values()), 226)

    def test_schema_digest_of_the_compiled_package_descriptors_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            descriptors = digests.repository_descriptors(ROOT, RECORD, Path(directory))
        self.assertEqual(digests.digest(descriptors), RECORD["schemaDigest"])


class ErrorCatalogue(unittest.TestCase):
    def test_codes_use_the_foundation_enumerations_and_message_key_form(self):
        categories = {name[len("ERROR_CATEGORY_"):] for name in foundation_enum("ErrorCategory")} - {"UNSPECIFIED"}
        modes = {name[len("RETRY_MODE_"):] for name in foundation_enum("RetryMode")} - {"UNSPECIFIED"}
        effects = {name[len("EFFECT_CERTAINTY_"):] for name in foundation_enum("EffectCertainty")} - {"UNSPECIFIED"}
        self.assertEqual(CATALOGUE["schemaVersion"], "af-con-01-error-catalogue.v2")
        self.assertEqual(CATALOGUE["source"]["path"], "docs/contracts/errors.md")
        # AF-CTR-05 (part C1): regenerated from errors.md at ArcForges-Design main 611dda6 (D0, Design #49).
        self.assertEqual(CATALOGUE["source"]["commit"], "611dda6b79c3f8aa854fbacad19e012f1759bd19")
        self.assertEqual(len(CATALOGUE["codes"]), 67)
        seen = set()
        for row in CATALOGUE["codes"]:
            key = row["category"] + "/" + row["code"]
            self.assertNotIn(key, seen)
            seen.add(key)
            self.assertIn(row["category"], categories, key)
            self.assertRegex(row["code"], r"^[a-z][a-z_]*$")
            self.assertEqual(row["messageKey"], f"error.{row['category'].lower()}.{row['code']}")
            self.assertTrue(row["pairs"], key)
            for pair in row["pairs"]:
                self.assertIn(pair["retry"], modes, key)
                self.assertIn(pair["effect"], effects, key)
        for codes in CATALOGUE["implicit"].values():
            self.assertTrue(set(codes) <= seen)
        self.assertEqual(CATALOGUE["implicit"]["receiptedMutations"], ["CONFLICT/command_id_reused"])

    def test_every_reply_is_an_explicit_effect_retry_pair(self):
        # errors.md "Delivered against target": AFTER_TIME pairs with DID_NOT_HAPPEN or HAPPENED; RECONCILE, SAME_COMMAND or NEVER
        # pair with UNKNOWN; a RECONCILE pair names its read operation (the foundation rules arcError and retryAdvice).
        for row in CATALOGUE["codes"]:
            key = row["category"] + "/" + row["code"]
            self.assertNotIn("retryModes", row, key)
            self.assertNotIn("effects", row, key)
            for pair in row["pairs"]:
                self.assertFalse(pair["effect"] == "UNKNOWN" and pair["retry"] == "AFTER_TIME", key)
                self.assertEqual(pair["retry"] == "RECONCILE", "reconciliationOperation" in pair, key)
        self.assertEqual(scope.error_catalogue_codes(CATALOGUE), {row["category"] + "/" + row["code"] for row in CATALOGUE["codes"]})
        pairs = {row["category"] + "/" + row["code"]: [(p["effect"], p["retry"], p.get("reconciliationOperation")) for p in row["pairs"]]
                 for row in CATALOGUE["codes"]}
        self.assertEqual(pairs["INTERNAL/internal"], [("UNKNOWN", "NEVER", None), ("DID_NOT_HAPPEN", "AFTER_TIME", None),
                                                      ("HAPPENED", "AFTER_TIME", None), ("HAPPENED", "SAME_COMMAND", None)])
        self.assertEqual(pairs["STATE/peer_unreachable"], [("DID_NOT_HAPPEN", "AFTER_TIME", None),
                                                           ("UNKNOWN", "RECONCILE", "arcforges.node.v1.PeerService/ListPeers"),
                                                           ("UNKNOWN", "SAME_COMMAND", None)])
        self.assertEqual(pairs["EXECUTION/provider_error"],
                         [("UNKNOWN", "RECONCILE", "arcforges.fleet.v1.StoreBillingService/GetBillingStatus")])
        # The D0 codes of center-routed calls (Plan decision Q2): STATE, never an UNAVAILABLE category.
        self.assertEqual(pairs["STATE/node_offline"], [("DID_NOT_HAPPEN", "AFTER_TIME", None)])
        self.assertEqual(pairs["STATE/node_unreachable"], [("DID_NOT_HAPPEN", "AFTER_TIME", None), ("UNKNOWN", "SAME_COMMAND", None),
                                                           ("UNKNOWN", "NEVER", None)])

    def test_independent_arrays_and_the_invalid_pair_are_refused(self):
        def mutated(change):
            catalogue = copy.deepcopy(CATALOGUE)
            change(next(row for row in catalogue["codes"] if row["code"] == "peer_unreachable"))
            return catalogue

        def arrays(row):
            row["retryModes"], row["effects"] = ["AFTER_TIME"], ["DID_NOT_HAPPEN", "UNKNOWN"]
            del row["pairs"]

        cases = {
            "independent arrays": (arrays, "exactly the pair form keys"),
            "arrays beside the pairs": (lambda row: row.update(retryModes=["AFTER_TIME"]), "exactly the pair form keys"),
            "AFTER_TIME with UNKNOWN": (lambda row: row["pairs"].append({"effect": "UNKNOWN", "retry": "AFTER_TIME"}),
                                        "UNKNOWN never pairs with AFTER_TIME"),
            "RECONCILE without its operation": (lambda row: row["pairs"][1].pop("reconciliationOperation"),
                                                "names its reconciliation operation"),
            "an operation without RECONCILE": (lambda row: row["pairs"][0].update(reconciliationOperation="arcforges.node.v1.PeerService/ListPeers"),
                                               "names its reconciliation operation"),
            "no pair": (lambda row: row.update(pairs=[]), "at least one effect/retry pair"),
            "a duplicate pair": (lambda row: row["pairs"].append(dict(row["pairs"][0])), "listed twice"),
            # Review N-1: the HAPPENED half of the pair form, and the cells and pair members are single values.
            "HAPPENED with NEVER": (lambda row: row["pairs"].append({"effect": "HAPPENED", "retry": "NEVER"}),
                                    "HAPPENED pairs only with AFTER_TIME or SAME_COMMAND"),
            "HAPPENED with RECONCILE": (lambda row: row["pairs"].append({"effect": "HAPPENED", "retry": "RECONCILE",
                                                                         "reconciliationOperation": "arcforges.node.v1.PeerService/ListPeers"}),
                                        "HAPPENED pairs only with AFTER_TIME or SAME_COMMAND"),
            "an effect cell as an array": (lambda row: row.update(effect=["DID_NOT_HAPPEN", "UNKNOWN"]), "the effect cell is a non-empty string"),
            "a retry advice cell as an array": (lambda row: row.update(retryAdvice=["AFTER_TIME"]), "the retryAdvice cell is a non-empty string"),
            "a pair effect as an array": (lambda row: row["pairs"][0].update(effect=["DID_NOT_HAPPEN", "UNKNOWN"]), "single values"),
            "a pair retry as an array": (lambda row: row["pairs"][0].update(retry=["AFTER_TIME"]), "single values"),
        }
        for label, (change, message) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(ValueError, message):
                scope.error_catalogue_codes(mutated(change))
        old = copy.deepcopy(CATALOGUE)
        old["schemaVersion"] = "af-con-01-error-catalogue.v1"
        with self.assertRaisesRegex(ValueError, "unsupported flagship error catalogue"):
            scope.error_catalogue_codes(old)

    def test_every_annotated_method_names_only_catalogued_codes(self):
        flagship = scope.flagship_methods(ROOT, scope.proto_methods(ROOT))
        self.assertEqual(len(flagship), 226)
        known = {row["category"] + "/" + row["code"] for row in CATALOGUE["codes"]}
        for method in flagship:
            named = method["annotations"]["errors"]
            if named != scope.FLAGSHIP_NO_ERRORS:
                self.assertTrue({code.strip() for code in named.split(",")} <= known, method["binding"])


class ConstraintSidecars(unittest.TestCase):
    """Sidecars hold the field inventory of every adopted message and exactly the unconditional
    `validate: required` annotations; every other validate comment stays specification text."""

    SHARDS = ["public/proto/constraints/af-con-01-node.json", "public/proto/constraints/af-con-01-fleet.json",
              "public/proto/constraints/af-con-01-support-access.json", "internal/proto/constraints/af-con-01-peer.json",
              "internal/proto/constraints/af-con-01-relay.json", "internal/proto/constraints/af-con-01-operator-read.json"]

    def test_required_flags_equal_the_unconditional_required_annotations(self):
        messages = {}
        for shard in self.SHARDS:
            messages.update(load(shard)["messages"])
        expected, declared = set(), set()
        for row in RECORD["files"]:
            text = (ROOT / row["path"]).read_text(encoding="utf-8")
            package = re.search(r"^package ([\w.]+);", text, re.M).group(1)
            for message in re.finditer(r"^message (\w+) \{\n(.*?)^\}", text, re.M | re.S):
                declared.add(package + "." + message.group(1))
                for line in message.group(2).splitlines():
                    field = re.search(r'json_name = "(\w+)"\];\s*// validate: (required(?:;.*)?)$', line)
                    if field:
                        expected.add((package + "." + message.group(1), field.group(1)))
        actual = {(name, field) for name, value in messages.items() for field, rules in value["fields"].items()
                  if rules.get("required")}
        self.assertEqual(set(messages), declared)
        self.assertEqual(actual, expected)
        # AF-CTR-05 (part C1) adds approve of ApproveNodeSignIn and ApproveDeviceCode (129 before).
        self.assertEqual(len(actual), 131)
        for value in messages.values():
            self.assertEqual({key for rules in value["fields"].values() for key in rules} - {"required"}, set())


class OperationScopeFlagshipRule(unittest.TestCase):
    PROTO = """syntax = "proto3";
package arcforges.node.v1;
service ProbeService {
  // Read the probe.
  // auth: HUMAN A, SCRIPT A, AGENT A; REMOTE=-
  // idempotency: read
  // deadline: 5 s
  // stream: none
  // errors: STATE/not_found
  // locality: node
  rpc Read(ProbeServiceReadRequest) returns (ProbeServiceReadResponse);
}
"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = "public/proto/arcforges/node/v1/probe.proto"
        (self.root / "eng/operations").mkdir(parents=True)
        (self.root / "fixtures/public").mkdir(parents=True)
        shutil.copyfile(ROOT / "fixtures/public/af-con-01-error-catalogue.json",
                        self.root / "fixtures/public/af-con-01-error-catalogue.json")
        self.manifest = {"schemaVersion": "operation-scope.v1", "operations": [{"operationId": "workspace.list", "scope": "account"}],
                         "idempotencyExamples": [], "toolAllowlist": []}
        self.write(self.PROTO)

    def write(self, text, digest=None):
        path = self.root / self.source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        record = copy.deepcopy(RECORD)
        record["files"] = [{"design": "arcforges/node/v1/probe.proto", "path": self.source,
                            "package": "ArcForges.Contracts.Node",
                            "sha256": digest or hashlib.sha256(text.encode("utf-8")).hexdigest()}]
        (self.root / "eng/flagship-contracts.json").write_text(json.dumps(record), encoding="utf-8")

    def test_annotated_method_is_reported_outside_the_manifest11_matrix(self):
        result = scope.audit(self.root, self.manifest)
        self.assertEqual([method["binding"] for method in result["flagshipMethods"]], ["arcforges.node.v1.ProbeService/Read"])
        self.assertEqual(result["flagshipMethods"][0]["annotations"]["locality"], "node")
        self.assertEqual(result["registered"], 0)

    def test_missing_annotation_is_refused(self):
        self.write(self.PROTO.replace("  // locality: node\n", ""))
        with self.assertRaisesRegex(ValueError, "lacks design annotations"):
            scope.audit(self.root, self.manifest)

    def test_uncatalogued_error_code_is_refused(self):
        self.write(self.PROTO.replace("STATE/not_found", "STATE/not_found, STATE/invented"))
        with self.assertRaisesRegex(ValueError, "missing from the catalogue"):
            scope.audit(self.root, self.manifest)

    def test_changed_bytes_without_a_reviewed_record_are_refused(self):
        self.write(self.PROTO, digest=hashlib.sha256(b"other").hexdigest())
        with self.assertRaisesRegex(ValueError, "differs from its reviewed record"):
            scope.audit(self.root, self.manifest)

    def test_unlisted_method_of_a_flagship_package_stays_unclassified(self):
        other = self.root / "public/proto/arcforges/node/v1/other.proto"
        other.write_text('syntax = "proto3"; package arcforges.node.v1; service OtherService { rpc Get(A) returns (B); }')
        with self.assertRaisesRegex(ValueError, "unclassified registered method"):
            scope.audit(self.root, self.manifest)

    def test_manifest11_export_cannot_claim_a_flagship_method(self):
        row = copy.deepcopy(scope.load(ROOT / "eng/operations/con-07.json")["operations"][0])
        row.update(operationId="workspace.list", binding="arcforges.node.v1.ProbeService/Read", source=self.source,
                   kind="proto", scope="account")
        (self.root / "eng/operations/example.json").write_text(json.dumps(
            {"schemaVersion": "operation-metadata.v1", "operations": [row]}))
        with self.assertRaisesRegex(ValueError, "flagship design method must not have a manifest11 operation export"):
            scope.audit(self.root, self.manifest)


class FlagshipCompatibilityWindow(unittest.TestCase):
    def test_every_adopted_file_has_exactly_one_baseline(self):
        window = compatibility.flagship_window(ROOT)
        adopted = sorted(name for baseline in window["baselines"] for name in baseline["adopted"])
        self.assertEqual(adopted, sorted(row["design"] for row in RECORD["files"]))
        for baseline in window["baselines"]:
            data = (ROOT / baseline["baseline"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), baseline["sha256"])

    def test_uncovered_adopted_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eng/compatibility").mkdir(parents=True)
            window = load("eng/compatibility/flagship-window.json")
            window["baselines"] = window["baselines"][:-1]
            (root / "eng/compatibility/flagship-window.json").write_text(json.dumps(window), encoding="utf-8")
            shutil.copyfile(ROOT / "eng/flagship-contracts.json", root / "eng/flagship-contracts.json")
            with self.assertRaisesRegex(ValueError, "covered by exactly one baseline"):
                compatibility.flagship_window(root)

    def test_breaking_changes_against_a_baseline_are_reported(self):
        window = compatibility.flagship_window(ROOT)
        node = next(item for item in window["baselines"] if item["package"] == "ArcForges.Contracts.Node")
        pinned = compatibility.descriptor((ROOT / node["baseline"]).read_bytes())
        message = ".arcforges.node.v1.TaskSpec"
        tag = min(pinned["messages"][message])
        for label, mutate in {
            "deleted member": lambda model: model["messages"][message].pop(tag),
            "changed member": lambda model: model["messages"][message][tag].update(type=12),
            "deleted definition": lambda model: model["services"].pop(".arcforges.node.v1.TaskService"),
        }.items():
            current = copy.deepcopy(pinned)
            mutate(current)
            with self.subTest(label):
                self.assertTrue(any(label.split()[0] in error for error in compatibility.compare(pinned, current)))
        self.assertEqual(compatibility.compare(pinned, copy.deepcopy(pinned)), [])


if __name__ == "__main__":
    unittest.main()
