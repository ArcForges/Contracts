# SPDX-License-Identifier: Apache-2.0
"""AF-CTR-05 part C1: the Contracts follow-up window and the built-refusal annotations (D3).

The expected values below are written from the AF-CTR-05 plan (B.4, D.1), its coordinator decisions (Q12, Q13, Q14) and
ArcForges-Design errors.md at 611dda6 ("Built refusals the annotations do not name yet"), and from the receipted fleet rows
of the Cloud center's access table (center/internal/access/access.go, Receipt: true); they are not read back from the
protos or the generated code.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
FLEET = "public/proto/arcforges/fleet/v1/fleet.proto"
ACCOUNT = "public/proto/arcforges/node/v1/account.proto"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "eng" / (name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


scope = module("check_operation_scope")


def text(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def load(relative):
    return json.loads(text(relative))


def annotations():
    result = {}
    for relative in (FLEET, ACCOUNT):
        result.update(scope.flagship_annotations(text(relative), relative))
    return result


def codes(binding):
    return [code.strip() for code in annotations()[binding]["errors"].split(",")]


ENROLLMENT = "arcforges.fleet.v1.NodeEnrollmentService/"
# The fleet methods the center serves under a command receipt (access.go rows with Receipt: true).
RECEIPTED = ("ApproveDeviceCode", "ReportNodeInfo", "SignOutNode")


class BuiltRefusalAnnotations(unittest.TestCase):
    def test_the_enrollment_cap_is_named_where_the_node_is_enrolled(self):
        for method in ("CompleteNodeSignIn", "PollDeviceAuthorization"):
            with self.subTest(method):
                self.assertEqual(codes(ENROLLMENT + method)[-1], "RESOURCE/quota_exceeded")
        fleet = text(FLEET)
        self.assertIn("// RESOURCE/quota_exceeded: the account's enrollment cap (limit.limit_name max_nodes_per_account, "
                      "limit.maximum the cap) is\n  // reached when the node is enrolled", fleet)
        self.assertIn("RESOURCE/quota_exceeded (the enrollment cap, limit.limit_name\n  // max_nodes_per_account) mean what they "
                      "mean for CompleteNodeSignIn.", fleet)

    def test_sign_out_names_the_unreadable_credential_store(self):
        found = annotations()["arcforges.node.v1.AccountService/SignOut"]
        self.assertEqual(found["errors"], "STATE/not_signed_in, STATE/invalid_state")
        self.assertIn("// STATE/invalid_state (state.state signed_out, state.reason credential_store_unavailable): the node's "
                      "secret store or\n  // link file cannot be read; both sign-out forms then change nothing.", text(ACCOUNT))

    def test_every_receipted_fleet_method_names_command_id_reused(self):
        found = annotations()
        receipted = {binding for binding, value in found.items() if binding.startswith("arcforges.fleet.v1.")
                     and "CONFLICT/command_id_reused" in value["errors"]}
        # AF-CTR-05 (part C2) adds the two routed mutations, receipted per account and command_id (Plan CTR5-RTE-03).
        routed = {"arcforges.fleet.v1.FleetService/SubmitNodeTask", "arcforges.fleet.v1.FleetService/CancelNodeTask"}
        file_mutations = {"arcforges.fleet.v1.FleetService/" + name for name in ('WriteNodeFile', 'EditNodeFile', 'PlanNodeRemoval', 'ExecuteNodeRemoval', 'RegisterNodeWorkspace', 'UnregisterNodeWorkspace')}
        self.assertEqual(receipted, {ENROLLMENT + method for method in RECEIPTED} | routed | file_mutations)
        for method in RECEIPTED:
            with self.subTest(method):
                self.assertEqual(found[ENROLLMENT + method]["idempotency"], "command_id")
                self.assertEqual(codes(ENROLLMENT + method)[-1], "CONFLICT/command_id_reused")

    def test_a_reused_code_revokes_a_completed_sign_in(self):
        found = annotations()[ENROLLMENT + "CompleteNodeSignIn"]
        self.assertEqual(found["state"], "SM-SIGN-IN: APPROVED -> COMPLETED | REVOKED; COMPLETED -> REVOKED")
        self.assertIn("A correct code presented again revokes the flow, also after its completion (COMPLETED -> REVOKED).", text(FLEET))

    def test_the_denial_redirect_is_documented(self):
        value = re.search(r"^message NodeEnrollmentServiceApproveNodeSignInValue \{\n(.*?)^\}", text(FLEET), re.M | re.S).group(1)
        self.assertIn('optional string redirect_url = 10 [json_name = "redirectUrl"]; // loopback URI: on approval '
                      "<redirect_uri>?code=<code>&state=<state>; on a denial <redirect_uri>?error=access_denied&state=<state>", value)
        self.assertNotIn("loopback URI with code and state", text(FLEET))

    def test_approve_is_required_on_both_decisions_and_nowhere_else(self):
        fleet = text(FLEET)
        sidecar = load("public/proto/constraints/af-con-01-fleet.json")["messages"]
        for message in ("NodeEnrollmentServiceApproveNodeSignInRequest", "NodeEnrollmentServiceApproveDeviceCodeRequest"):
            with self.subTest(message):
                body = re.search(r"^message " + message + r" \{\n(.*?)^\}", fleet, re.M | re.S).group(1)
                self.assertIn('optional bool approve = 11 [json_name = "approve"]; // validate: required; true approves, false denies',
                              body)
                self.assertEqual(sidecar["arcforges.fleet.v1." + message]["fields"]["approve"], {"required": True})
        # The phone pairing decision is not a built refusal of errors.md: its approve stays optional.
        self.assertEqual(sidecar["arcforges.fleet.v1.NodeEnrollmentServiceConfirmPhonePairingRequest"]["fields"]["approve"], {})
        generated = text("src/public/dotnet/ArcForges.Contracts.Fleet/Generated/Shapes/ProtoValidation.g.cs")
        self.assertEqual(generated.count("if (!value.HasApprove) return false;"), 2)

    def test_the_annotated_codes_are_catalogued(self):
        catalogue = {row["category"] + "/" + row["code"] for row in load("fixtures/public/af-con-01-error-catalogue.json")["codes"]}
        for code in ("RESOURCE/quota_exceeded", "STATE/invalid_state", "CONFLICT/command_id_reused", "VALIDATION/invalid_argument",
                     "STATE/node_offline", "STATE/node_unreachable"):
            self.assertIn(code, catalogue)

    def test_no_other_proto_changes_than_comments_and_the_approve_rule(self):
        # The flagship record binds the two changed files; their descriptors keep the pinned flagship schema digest.
        record = load("eng/flagship-contracts.json")
        rows = {row["path"]: row["sha256"] for row in record["files"]}
        for relative in (FLEET, ACCOUNT):
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), rows[relative], relative)
        self.assertIn("AF-CTR-05 (part C1) adds comment-only annotation text to fleet.proto and account.proto", record["adoption"])


class EmailBound(unittest.TestCase):
    FIELDS = {
        "arcforges.publicapi.v1.AccountProfile": "primaryEmail",
        "arcforges.publicapi.v1.IdentityServiceBeginAuthenticationRequest": "loginHint",
        "arcforges.publicapi.v1.IdentityServiceRequestEmailCodeRequest": "email",
        "arcforges.publicapi.v1.IdentityServiceBeginRecoveryRequest": "email",
        "arcforges.publicapi.v1.IdentityServiceBeginEmailChangeRequest": "email",
    }

    def test_the_protobuf_validators_admit_254(self):
        for path in ("public/proto/constraints/con-07-identity.json", "public/proto/constraints.json"):
            messages = load(path)["messages"]
            for message, field in self.FIELDS.items():
                with self.subTest(path=path, message=message):
                    self.assertEqual(messages[message]["fields"][field]["maxLength"], 254)
            self.assertNotIn('"maxLength": 320', text(path))
        generated = text("src/public/dotnet/ArcForges.Contracts.Validation/Generated/Shapes/ProtoValidation.g.cs")
        self.assertEqual(len(re.findall(r"if \(ScalarLength\(value\.(?:PrimaryEmail|LoginHint|Email)\) > 254\) return false;", generated)), 5)
        self.assertNotRegex(generated, r"\(value\.(?:PrimaryEmail|LoginHint|Email)\) > 320")
        cases = {case["id"]: case for case in load("fixtures/public/con-07-identity.json")["cases"]}
        for message, field in self.FIELDS.items():
            name = message.rsplit(".", 1)[1]
            with self.subTest(message=message):
                self.assertEqual(cases[f"auto.{name}.{field}.max-length"]["value"][field]["$str"], ["a@", "a", 252])
                self.assertEqual(cases[f"auto.{name}.{field}.over-max-length"]["value"][field]["$str"], ["a@", "a", 253])
                self.assertEqual((cases[f"auto.{name}.{field}.max-length"]["valid"], cases[f"auto.{name}.{field}.over-max-length"]["valid"]),
                                 (True, False))

    def test_the_frozen_http_documents_stay_at_320_byte_identical(self):
        # Q12 (a): the stated divergence. The CON.17 window pins browser.schema.json; web-browser.schema.json is unchanged.
        sys.path.insert(0, str(ROOT / "eng"))
        from check_compatibility import schema_identity
        pins = {row["path"]: row["sha256"] for row in load("eng/compatibility/later-services-window.json")["schemas"]}
        self.assertEqual(schema_identity((ROOT / "public/http/v1/browser.schema.json").read_bytes())[0],
                         pins["public/http/v1/browser.schema.json"])
        # web-browser.schema.json is not in the CON.17 window: its bytes are pinned here (review N-4), equal to main 5873dc2.
        self.assertEqual(hashlib.sha256((ROOT / "public/http/v1/web-browser.schema.json").read_bytes()).hexdigest(),
                         "2e54a30f135c6b0fb372f68ffeea38647c58514f03317316ce492db442069078")
        for document in ("public/http/v1/browser.schema.json", "public/http/v1/web-browser.schema.json"):
            with self.subTest(document):
                self.assertEqual(text(document).count('"maxLength": 320'), 2)
        consuming = text("docs/consuming.md")
        for phrase in ("stay byte-identical with `maxLength` 320", "the center is stricter and refuses", "255 to 320 scalars",
                       "an HTTP client should apply 254 too"):
            self.assertIn(phrase, " ".join(consuming.split()))


class FollowUpDecisions(unittest.TestCase):
    def test_the_worker_reply_decision_is_recorded_without_a_contract_change(self):
        consuming = " ".join(text("docs/consuming.md").split())
        for phrase in ("Worker replies without `ResponseMeta` (Plan decision Q13)",
                       "the Worker adds a `ResponseMeta` with the correlation ID to its generated replies",
                       "The contracts and the generated validators are unchanged: they keep requiring `meta`."):
            self.assertIn(phrase, consuming)

    def test_additive_only_names_the_recorded_validator_tightenings(self):
        # Review N-3: within v1 the change is additive on the wire; the two validator tightenings are recorded decisions.
        consuming = " ".join(text("docs/consuming.md").split())
        self.assertIn("Within `v1`, changes are additive only on the wire, and a validator tightens only by a recorded decision "
                      "(AF-CTR-05 part C1: the e-mail bound of Plan decision Q12 and the `approve` rule, below)", consuming)
        self.assertIn("additive only on the wire and reviewed against the wire-compatibility baselines in "
                      "eng/compatibility/flagship-window.json; a validator tightens only by a recorded decision (AF-CTR-05 part C1: "
                      "the e-mail bound of Plan decision Q12 and the approve rule).", load("eng/flagship-contracts.json")["adoption"])

    def test_the_web_browser_session_document_keeps_no_error_body(self):
        web = load("public/http/v1/web-browser.schema.json")
        self.assertFalse([name for name in web["$defs"] if "Error" in name])
        self.assertEqual(load("public/http/v1/web-browser-error.schema.json")["title"], "WebBrowserSessionError")


if __name__ == "__main__":
    unittest.main()
