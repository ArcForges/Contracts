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
    def inprocess_row(self, approval=False):
        owner, interface, method = (('Chat', 'IChatOperations', 'SubmitApproval') if approval
                                    else ('Platform', 'ICapabilityProvider', 'Invoke'))
        namespace = f'ArcForges.Contracts.LocalRpc.{owner}'
        row = {'operationId': f'{interface}.{method}', 'kind': 'in-process',
               'binding': f'{namespace}.Ports.{interface}.{method}Async',
               'source': f'src/internal/dotnet/{namespace}/Generated/InprocessPorts.g.cs',
               'scope': 'in-process', 'surface': 'in-process',
               'profile': 'human-approval-decision' if approval else 'in-process-invocation',
               'sourceRule': 'docs/architecture/contracts/02-local-rpc-operations.md#closed-in-process-authorization-profiles'}
        if approval:
            row['idempotency'] = 'IW'
            row['authorization'] = {'capability': None, 'risk': {'from': 'verifiedApprovalProposal.effectiveRisk'},
                'approval': 'foregroundProposal', 'stepUp': {'from': 'verifiedApprovalProposal.stepUp'},
                'localPresence': {'from': 'verifiedApprovalProposal.localPresence'},
                'egress': 'none', 'patEligible': False, 'actorKinds': ['human']}
        else:
            row['idempotency'] = {'from': 'admittedCapability.idempotency'}
            row['authorization'] = {field: {'from': 'admittedCapability.' +
                ('operationId' if field == 'capability' else field)} for field in gate.FIELDS - {'patEligible'}}
            row['authorization']['patEligible'] = False
            row['delegation'] = {'intersectOriginalActor': True, 'requireCurrentGrant': True,
                'denyHumanOnly': True, 'requireRegisteredProductHandler': True}
        return row

    def test_exact_inprocess_profiles_and_closed_bindings(self):
        for approval in (False, True):
            row = self.inprocess_row(approval)
            actors, derived = gate.authorization(row, set())
            self.assertEqual(actors, ['human'] if approval else [])
            self.assertEqual(set(derived), {'risk', 'stepUp', 'localPresence'} if approval else gate.FIELDS - {'patEligible'})
            for field, wrong in [('operationId', 'ICapabilityProvider.Describe'), ('surface', 'public'),
                                 ('scope', 'account'), ('kind', 'proto'), ('binding', 'Invented.InvokeAsync'),
                                 ('source', 'internal/proto/arcforges/local/platform/v1/inprocess.proto')]:
                hostile = copy.deepcopy(row); hostile[field] = wrong
                with self.subTest(approval=approval, field=field), self.assertRaises(ValueError):
                    gate.authorization(hostile, set())
            for field, wrong in [('patEligible', True), ('actorKinds', ['agent']), ('risk', {'from': 'caller.risk'})]:
                hostile = copy.deepcopy(row); hostile['authorization'][field] = wrong
                with self.subTest(approval=approval, field=field), self.assertRaises(ValueError):
                    gate.authorization(hostile, set())

    def test_inprocess_invocation_requires_current_registered_handler(self):
        row = self.inprocess_row()
        for guard in row['delegation']:
            for invalid in (False, 1, 1.0, None, 'true'):
                hostile = copy.deepcopy(row); hostile['delegation'][guard] = invalid
                with self.subTest(guard=guard, invalid=invalid), self.assertRaisesRegex(ValueError, 'incomplete delegated'):
                    gate.authorization(hostile, set())
        hostile = copy.deepcopy(row)
        hostile['delegation']['requireLaunchRole'] = hostile['delegation'].pop('requireRegisteredProductHandler')
        with self.assertRaisesRegex(ValueError, 'incomplete delegated'):
            gate.authorization(hostile, set())
        hostile = copy.deepcopy(row); hostile['profile'] = 'delegated-invocation'
        with self.assertRaises(ValueError):
            gate.authorization(hostile, set())

    def test_approval_proposal_cannot_be_fixed_or_caller_claimed(self):
        row = self.inprocess_row(True)
        for field, wrong in [('risk', 'R1'), ('risk', 'R3'), ('risk', {'from': 'verifiedApprovalProposal.risk'}),
                             ('stepUp', False), ('localPresence', False), ('approval', 'none'),
                             ('capability', row['operationId']), ('egress', 'ownedContent')]:
            hostile = copy.deepcopy(row); hostile['authorization'][field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(ValueError):
                gate.authorization(hostile, set())
        hostile = copy.deepcopy(row); hostile['delegation'] = self.inprocess_row()['delegation']
        with self.assertRaisesRegex(ValueError, 'metadata contradicts'):
            gate.authorization(hostile, set())

    def test_closed_operations_cannot_downgrade_to_generic_profiles(self):
        for approval in (False, True):
            row = self.inprocess_row(approval)
            row.pop('delegation', None)
            row['idempotency'] = 'IW'
            row['authorization'] = {'capability': None, 'risk': 'R1', 'approval': 'none',
                'stepUp': False, 'localPresence': False, 'egress': 'none',
                'patEligible': False, 'actorKinds': ['human']}
            for profile in ('product-handler', 'human-owner', 'tool-delegation'):
                row['profile'] = profile
                with self.subTest(approval=approval, profile=profile), self.assertRaisesRegex(ValueError, 'required closed'):
                    gate.authorization(row, set())

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
        oracle = gate.load(ROOT / "eng/operation-scope-manifest.json")
        self.assertEqual(len(result["operations"]), len(oracle["operations"]))
        self.assertEqual(result["registered"] + result["pending"] + result["reserved"], len(oracle["operations"]))
        methods = gate.proto_methods(ROOT)
        self.assertEqual(result["migrationExamples"], sorted(binding for binding, source in gate.EXAMPLES.items()
                         if methods.get(binding) == source))

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
        self.fails("profile surface mismatch")

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
        self.row["idempotency"] = {"from": "admittedCapability.idempotency"}
        self.row["authorization"]["risk"] = {"from": "admittedCapability.risk"}
        self.fails("partial delegated descriptor")

    def test_unknown_descriptor_expression(self):
        self.row["profile"] = "delegated-invocation"
        self.row["idempotency"] = {"from": "admittedCapability.idempotency"}
        self.row["authorization"]["risk"] = {"from": "caller.risk"}
        self.fails("unsupported derived risk")

    def test_fixed_lifecycle_cannot_silently_lower_risk(self):
        self.row["authorization"]["risk"] = "R0"
        self.fails("lifecycle metadata disagrees")

    def test_delegated_actor_and_grant_constraints_are_complete(self):
        row = copy.deepcopy(self.row)
        row.update(operationId="IExtensionHost.Invoke", profile="delegated-invocation")
        row["idempotency"] = {"from": "admittedCapability.idempotency"}
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

    def test_tool_profile_cannot_disguise_noncustomer_credentials(self):
        self.row.update(operationId="workspace.list", scope="account", surface="public", profile="tool-delegation")
        self.row["authorization"]["capability"] = "workspace.list"
        for actor in ("operator", "service", "provider", "preauth", "helper-parent"):
            self.row["authorization"]["actorKinds"] = [actor]
            with self.subTest(actor=actor), self.assertRaisesRegex(ValueError, "profile identity mismatch"):
                gate.authorization(self.row, {"workspace.list"})

    def test_operator_profile_cannot_disguise_account_surface(self):
        self.row.update(operationId="workspace.list", scope="account", surface="in-process", profile="operator")
        self.row["authorization"]["actorKinds"] = ["operator"]
        with self.assertRaisesRegex(ValueError, "profile surface mismatch"):
            gate.authorization(self.row, set())

    def test_duplicate_json_key_denied(self):
        path = self.root / "duplicate.json"
        path.write_text('{"risk":"R0","risk":"R3"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            gate.load(path)

    def test_bootstrap_exact_launch_profile(self):
        row = copy.deepcopy(self.row)
        row.update(operationId="ILocalBootstrap.Challenge", profile="launch-bootstrap-only", idempotency="NI",
                   launchRoles={"from": "verifiedLaunchProfile.callerRoles"}, requireLaunchRole=True)
        row["authorization"]["actorKinds"] = {"from": "verifiedLaunchProfile.actorKinds"}
        self.assertEqual(gate.authorization(row, set()), ([], ["actorKinds"]))
        hostile = copy.deepcopy(row)
        hostile["authorization"]["actorKinds"] = {"from": "caller.actorKinds"}
        with self.assertRaisesRegex(ValueError, "unsupported bootstrap"):
            gate.authorization(hostile, set())
        for mutation in ({"requireLaunchRole": False}, {"operationId": "identity.changePassword"},
                         {"launchRoles": ["helper-parent", "helper-child"]}, {"idempotency": "IW"}):
            hostile = {**row, **mutation}
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "incomplete bootstrap"):
                gate.authorization(hostile, set())

    def test_nonobject_export_denied(self):
        self.fails("row object required", [None])

    def test_export_cannot_spoof_generated_matrix_status(self):
        for field, value in (("status", "pending"), ("reachableActors", ["human"]),
                             ("metadataSource", "invented.json"), ("actorKind", "human")):
            row = {**self.row, field: value}
            with self.subTest(field=field):
                self.fails("unknown operation export fields", [row])

    def test_duplicate_oracle_denied(self):
        self.manifest["operations"].append(self.manifest["operations"][0])
        self.fails("ambiguous oracle row")

    def test_proto_options_and_streaming_discovery(self):
        (self.root / self.source).write_text('package p; service S { '
            'rpc Stream(stream Req) returns(stream Res) { option (x) = {a: "b"}; } '
            'rpc Next(Req) returns(Res); } // rpc Fake(Req) returns(Res);')
        self.assertEqual(set(gate.proto_methods(self.root)), {"p.S/Stream", "p.S/Next"})

    def test_option_strings_cannot_hide_actual_methods(self):
        (self.root / self.source).write_text('package p; service S { '
            'option (x) = "} // rpc Fake(Req) returns(Res);"; '
            'rpc Actual(Req) returns(Res); }')
        self.assertEqual(set(gate.proto_methods(self.root)), {"p.S/Actual"})

    def test_migration_exemption_is_not_wildcard(self):
        (self.root / self.source).write_text('package arcforges.hello.v1; service HelloService { '
                                            'rpc SayHello(Req) returns(Res); }')
        self.fails("unclassified registered method", [])


if __name__ == "__main__":
    unittest.main()
