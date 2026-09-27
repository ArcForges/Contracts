# SPDX-License-Identifier: Apache-2.0
"""Offline producer policy: hostile metadata must not create reachable authority."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("operation_scope", ROOT / "eng/check_operation_scope.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class OperationScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = "public/proto/arcforges/extensions/v1/extensions.proto"
        path = self.root / self.source
        path.parent.mkdir(parents=True)
        path.write_text('syntax = "proto3"; package arcforges.extensions.v1; '
                        'service ExtensionHostService { rpc RenewLease(Request) returns (Reply); }')
        self.row = copy.deepcopy(gate.load(ROOT / "eng/operations/extensions-baseline.json")["operations"][0])
        self.manifest = {"schemaVersion": "operation-scope.v1", "operations": [
            {"operationId": self.row["operationId"], "scope": "private-helper"},
            {"operationId": "workspace.list", "scope": "account"},
            {"operationId": "deviceSso.reserved", "scope": "future"}],
            "idempotencyExamples": [], "toolAllowlist": []}

    def write(self, rows=None):
        path = self.root / "eng/operations/example.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schemaVersion": "operation-metadata.v1", "operations":
                                   [self.row] if rows is None else rows}))

    def fails(self, phrase, rows=None):
        self.write(rows)
        with self.assertRaisesRegex(ValueError, phrase):
            gate.audit(self.root, self.manifest)

    def test_real_retained_methods_and_pending_inventory(self):
        result = gate.audit(ROOT)
        self.assertEqual(result["result"], "passed")
        self.assertGreater(result["pending"], 250)
        self.assertIn("arcforges.hello.v1.HelloService/SayHello", result["migrationExamples"])

    def test_deterministic_complete_matrix(self):
        self.write()
        result = gate.audit(self.root, self.manifest)
        self.assertEqual(result, gate.audit(self.root, self.manifest))
        self.assertEqual((result["registered"], result["pending"], result["reserved"]), (1, 1, 1))

    def test_all_eight_fields_are_mandatory(self):
        original = copy.deepcopy(self.row)
        for field in gate.FIELDS:
            with self.subTest(field=field):
                self.row = copy.deepcopy(original)
                del self.row["authorization"][field]
                self.fails("eight authorization fields")

    def test_unknown_registered_method(self):
        self.fails("unclassified registered method", [])

    def test_duplicate_export(self):
        self.fails("duplicate export", [self.row, self.row])

    def test_nonexistent_binding(self):
        self.row["binding"] += "Missing"
        self.fails("nonexistent service method")

    def test_source_escape(self):
        self.row["source"] = "../outside.proto"
        self.fails("invalid source path")

    def test_reserved_registration(self):
        self.row["operationId"] = "deviceSso.reserved"
        self.fails("reserved future operation")

    def test_unknown_operation(self):
        self.row["operationId"] = "invented.grant"
        self.fails("unclassified operation")

    def test_nonexistent_idempotency_example(self):
        self.manifest["idempotencyExamples"] = ["identity.revokeDevice"]
        self.fails("nonexistent idempotency example")

    def test_public_local_schema_import(self):
        with (self.root / self.source).open("a") as stream:
            stream.write('\nimport "arcforges/local/v1/bootstrap.proto";')
        self.fails("public import of local schema")

    def test_unknown_risk(self):
        self.row["authorization"]["risk"] = "R9"
        self.fails("unclassified risk")

    def test_boolean_is_not_string(self):
        self.row["authorization"]["stepUp"] = "false"
        self.fails("ambiguous stepUp")

    def test_helper_cannot_claim_public_human_profile(self):
        self.row["profile"] = "human-owner"
        self.row["authorization"]["actorKinds"] = ["human"]
        self.fails("helper boundary mismatch")

    def test_peer_cannot_claim_service_identity(self):
        self.row["authorization"]["actorKinds"] = ["service"]
        self.fails("profile identity mismatch")

    def test_helper_pat_denied(self):
        self.row["authorization"]["patEligible"] = True
        self.fails("forbidden PAT")

    def test_human_only_tool_denied_even_if_allowlisted(self):
        self.manifest["operations"].append({"operationId": "approval.decide", "scope": "account"})
        self.manifest["toolAllowlist"] = ["approval.decide"]
        self.fails("forbidden or unclassified tool")

    def test_scope_mismatch(self):
        self.row["scope"] = "account"
        self.fails("scope disagrees")

    def test_unclassified_profile(self):
        self.row["profile"] = "default"
        self.fails("unclassified source profile")

    def test_partial_derived_descriptor_denied(self):
        self.row["profile"] = "delegated-invocation"
        self.row["authorization"]["risk"] = {"from": "admittedCapability.risk"}
        self.fails("partial delegated descriptor")

    def test_unknown_descriptor_expression(self):
        self.row["profile"] = "delegated-invocation"
        self.row["authorization"]["risk"] = {"from": "caller.risk"}
        self.fails("unsupported derived risk")

    def test_fixed_lifecycle_cannot_silently_lower_risk(self):
        self.row["authorization"]["risk"] = "R0"
        self.fails("lifecycle metadata disagrees")

    def test_delegated_actor_and_grant_constraints_are_complete(self):
        row = copy.deepcopy(self.row)
        row.update(operationId="IExtensionHost.Invoke", profile="delegated-invocation")
        row["authorization"] = {field: {"from": "admittedCapability." +
            ("operationId" if field == "capability" else field)} for field in gate.FIELDS - {"patEligible"}}
        row["authorization"]["patEligible"] = False
        row["delegation"] = {"intersectOriginalActor": True, "requireCurrentGrant": True,
                             "denyHumanOnly": True, "requireLaunchRole": True}
        actors, derived = gate.authorization(row, set())
        self.assertEqual(actors, [])
        self.assertEqual(set(derived), gate.FIELDS - {"patEligible"})
        for constraint in row["delegation"]:
            hostile = copy.deepcopy(row)
            hostile["delegation"][constraint] = False
            with self.subTest(constraint=constraint), self.assertRaisesRegex(ValueError, "incomplete delegated"):
                gate.authorization(hostile, set())

    def test_operator_customer_credential_substitution(self):
        self.row.update(operationId="operator.suspend", scope="operator", surface="operator", profile="operator")
        self.row["authorization"]["actorKinds"] = ["human"]
        with self.assertRaisesRegex(ValueError, "profile identity mismatch"):
            gate.authorization(self.row, set())

    def test_cf_customer_credential_substitution(self):
        self.row.update(operationId="compute.dispatch", surface="cf-internal", profile="cf-service")
        self.row["authorization"]["actorKinds"] = ["human"]
        with self.assertRaisesRegex(ValueError, "profile identity mismatch"):
            gate.authorization(self.row, set())

    def test_public_local_presence_denied(self):
        self.row.update(operationId="workspace.list", scope="account", surface="public", profile="human-owner")
        self.row["authorization"]["actorKinds"] = ["human"]
        self.row["authorization"]["localPresence"] = True
        with self.assertRaisesRegex(ValueError, "public local-presence"):
            gate.authorization(self.row, set())

    def test_tool_requires_explicit_admission(self):
        self.row.update(operationId="workspace.list", scope="account", surface="public", profile="tool-delegation")
        self.row["authorization"].update(capability="workspace.list", actorKinds=["agent"])
        with self.assertRaisesRegex(ValueError, "tool is not explicitly admitted"):
            gate.authorization(self.row, set())
        self.assertEqual(gate.authorization(self.row, {"workspace.list"})[0], ["agent"])

    def test_duplicate_json_key_denied(self):
        path = self.root / "duplicate.json"
        path.write_text('{"risk":"R0","risk":"R3"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            gate.load(path)

    def test_nonobject_export_denied(self):
        self.fails("row object required", [None])

    def test_duplicate_oracle_denied(self):
        self.manifest["operations"].append(self.manifest["operations"][0])
        self.fails("ambiguous oracle row")

    def test_proto_options_and_streaming_discovery(self):
        (self.root / self.source).write_text('package p; service S { '
            'rpc Stream(stream Req) returns(stream Res) { option (x) = {a: "b"}; } '
            'rpc Next(Req) returns(Res); } // rpc Fake(Req) returns(Res);')
        self.assertEqual(set(gate.proto_methods(self.root)), {"p.S/Stream", "p.S/Next"})

    def test_migration_exemption_is_not_wildcard(self):
        (self.root / self.source).write_text('package arcforges.hello.v1; service HelloService { '
                                            'rpc SayHello(Req) returns(Res); }')
        self.fails("unclassified registered method", [])


if __name__ == "__main__":
    unittest.main()
