# SPDX-License-Identifier: Apache-2.0
"""AF-CTR-04 part C0: the additive fleet.v1 and node.v1 fields, SignOutNode and the frozen annotation delta.

The expected values below are written from the AF-CTR-04 plan, its review decisions and the C0 decisions (field
numbers, types, presence, the errors and idempotency annotations, the node key proof layout); they are not read
back from the protos or the generated code.
"""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
FLEET = "public/proto/arcforges/fleet/v1/fleet.proto"
NODE = "public/proto/arcforges/node/v1/node.proto"
ACCOUNT = "public/proto/arcforges/node/v1/account.proto"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "eng" / (name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


scope = module("check_operation_scope")


def text(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def message_fields(relative, message):
    """{number: (label, type, name, trailing comment)} of one top-level message, read from the proto text."""
    body = re.search(r"^message " + message + r" \{\n(.*?)^\}", text(relative), re.M | re.S)
    assert body is not None, message
    fields = {}
    for line in body.group(1).splitlines():
        field = re.match(r"\s*(optional |repeated )?([\w.]+) (\w+) = (\d+) \[json_name = \"\w+\"\];(.*)$", line)
        if field:
            fields[int(field.group(4))] = ((field.group(1) or "").strip(), field.group(2), field.group(3),
                                           field.group(5).strip())
    return fields


INSTANT = "arcforges.foundation.v1.Instant"
# (file, message, number) -> (label, type, name, required)
ADDED_FIELDS = {
    (FLEET, "NodeEnrollmentServiceBeginNodeSignInRequest", 13): ("optional", "string", "state", True),
    (FLEET, "NodeEnrollmentServiceBeginNodeSignInRequest", 14): ("optional", "bytes", "node_public_key", True),
    (FLEET, "NodeEnrollmentServiceCompleteNodeSignInRequest", 14): ("optional", "bytes", "node_key_proof", True),
    (FLEET, "NodeEnrollmentServiceStartDeviceAuthorizationRequest", 11): ("optional", "bytes", "node_public_key", True),
    (FLEET, "NodeEnrollmentServicePollDeviceAuthorizationRequest", 12): ("optional", "bytes", "node_key_proof", True),
    (FLEET, "NodeEnrollmentServiceRefreshNodeSessionValue", 13): ("repeated", "PublicKey", "command_keys", False),
    (FLEET, "NodeEnrollmentServiceRefreshNodeSessionValue", 14): ("repeated", "PublicKey", "entitlement_keys", False),
    (FLEET, "NodeEnrollmentServiceRefreshNodeSessionValue", 15): ("", INSTANT, "session_expires_at", False),
    (FLEET, "NodeEnrollmentServiceRefreshNodeSessionValue", 16): ("optional", "uint64", "access_lifetime_ms", False),
    (FLEET, "NodeCredentials", 10): ("", INSTANT, "session_expires_at", False),
    (FLEET, "NodeCredentials", 11): ("optional", "uint64", "access_lifetime_ms", False),
    (FLEET, "FleetNode", 14): ("", INSTANT, "credential_expires_at", False),
    (FLEET, "NodeEnrollmentServiceSignOutNodeValue", 10): ("", "arcforges.foundation.v1.Receipt", "receipt", False),
    (NODE, "NodeSettings", 6): ("optional", "string", "center_url", False),
    (NODE, "NodeServiceUpdateNodeSettingsRequest", 12): ("optional", "string", "center_url", False),
    (ACCOUNT, "AccountStatus", 14): ("optional", "string", "center_url", False),
    (ACCOUNT, "AccountStatus", 15): ("optional", "string", "node_key_fingerprint", False),
    (ACCOUNT, "AccountStatus", 16): ("", INSTANT, "credential_expires_at", False),
    (ACCOUNT, "SignInFlow", 13): ("optional", "string", "node_key_fingerprint", False),
}
# The highest field number each extended message had before C0: the additions are the next free numbers.
PREVIOUS_HIGHEST = {
    "NodeEnrollmentServiceBeginNodeSignInRequest": 12, "NodeEnrollmentServiceCompleteNodeSignInRequest": 13,
    "NodeEnrollmentServiceStartDeviceAuthorizationRequest": 10, "NodeEnrollmentServicePollDeviceAuthorizationRequest": 11,
    "NodeEnrollmentServiceRefreshNodeSessionValue": 12, "NodeCredentials": 9, "FleetNode": 13, "NodeSettings": 5,
    "NodeServiceUpdateNodeSettingsRequest": 11, "AccountStatus": 13, "SignInFlow": 12,
}

# The errors and idempotency annotations of every method C0 touches (CTR4-OPS-04 as amended).
ANNOTATIONS = {
    "arcforges.fleet.v1.NodeEnrollmentService/BeginNodeSignIn": (
        "VALIDATION/invalid_argument, RESOURCE/rate_limited, RESOURCE/kill_switch_active, CONFLICT/already_exists",
        "natural: every call starts a new flow; meta.command_id is correlation only"),
    "arcforges.fleet.v1.NodeEnrollmentService/GetNodeSignInFlow": (
        "STATE/not_found, STATE/expired, AUTHENTICATION/step_up_required, AUTHORIZATION/permission_denied",
        "natural: on a PENDING flow records the reviewing account and time"),
    "arcforges.fleet.v1.NodeEnrollmentService/ApproveNodeSignIn": (
        "STATE/not_found, STATE/expired, STATE/invalid_state, AUTHENTICATION/step_up_required, "
        "RESOURCE/quota_exceeded, AUTHORIZATION/permission_denied",
        "natural: the flow row; a repeat by the same account replaces the unredeemed one-use code"),
    "arcforges.fleet.v1.NodeEnrollmentService/CompleteNodeSignIn": (
        "STATE/not_found, STATE/expired, CONFLICT/code_reused, AUTHENTICATION/unauthenticated, "
        "VALIDATION/invalid_argument, CONFLICT/already_exists, AUTHENTICATION/credential_revoked",
        "natural: code single use; reuse revokes the flow"),
    "arcforges.fleet.v1.NodeEnrollmentService/StartDeviceAuthorization": (
        "VALIDATION/invalid_argument, RESOURCE/rate_limited, RESOURCE/kill_switch_active, CONFLICT/already_exists",
        "natural: every call starts a new flow; meta.command_id is correlation only"),
    "arcforges.fleet.v1.NodeEnrollmentService/PollDeviceAuthorization": (
        "STATE/not_found, RESOURCE/rate_limited, CONFLICT/already_exists, AUTHENTICATION/credential_revoked",
        "natural"),
    "arcforges.fleet.v1.NodeEnrollmentService/LookupDeviceCode": (
        "VALIDATION/code_invalid, STATE/expired, RESOURCE/rate_limited, STATE/invalid_state, "
        "AUTHENTICATION/step_up_required, AUTHORIZATION/permission_denied",
        "natural: counts one lookup of the live code and records the reviewing account"),
    "arcforges.fleet.v1.NodeEnrollmentService/ApproveDeviceCode": (
        "VALIDATION/code_invalid, STATE/expired, STATE/invalid_state, AUTHENTICATION/step_up_required, "
        "RESOURCE/quota_exceeded, AUTHORIZATION/permission_denied",
        "command_id"),
    "arcforges.fleet.v1.NodeEnrollmentService/RefreshNodeSession": (
        "AUTHENTICATION/token_expired, AUTHENTICATION/credential_revoked, AUTHORIZATION/permission_denied",
        "natural: rotation with reuse detection (reuse revokes the credential)"),
    "arcforges.fleet.v1.NodeEnrollmentService/ReportNodeInfo": (
        "AUTHENTICATION/unauthenticated, VALIDATION/invalid_argument, AUTHORIZATION/permission_denied", "command_id"),
    "arcforges.fleet.v1.NodeEnrollmentService/SignOutNode": (
        "AUTHENTICATION/unauthenticated, AUTHENTICATION/credential_revoked, AUTHORIZATION/permission_denied",
        "command_id"),
    "arcforges.node.v1.NodeService/UpdateNodeSettings": (
        "CONFLICT/revision_conflict, AUTHORIZATION/permission_denied, AUTHORIZATION/approval_required, "
        "STATE/invalid_state, VALIDATION/invalid_argument",
        "command_id; expected_rev"),
    "arcforges.node.v1.NodeService/StopNode": (
        "AUTHORIZATION/permission_denied, STATE/update_in_progress, STATE/invalid_state", "command_id"),
    "arcforges.node.v1.AccountService/BeginSignIn": (
        "STATE/invalid_state, STATE/cloud_unreachable, RESOURCE/rate_limited, AUTHORIZATION/permission_denied, "
        "STATE/not_activated",
        "command_id; one active flow at a time (returns it)"),
}
# AF-CTR-05 (part C1, D3) appends the built refusals of errors.md to five of these methods (tests/tooling/test_af_ctr_05_c1.py).
C1_APPENDED = {
    "arcforges.fleet.v1.NodeEnrollmentService/CompleteNodeSignIn": ", RESOURCE/quota_exceeded",
    "arcforges.fleet.v1.NodeEnrollmentService/PollDeviceAuthorization": ", RESOURCE/quota_exceeded",
    "arcforges.fleet.v1.NodeEnrollmentService/ApproveDeviceCode": ", CONFLICT/command_id_reused",
    "arcforges.fleet.v1.NodeEnrollmentService/ReportNodeInfo": ", CONFLICT/command_id_reused",
    "arcforges.fleet.v1.NodeEnrollmentService/SignOutNode": ", CONFLICT/command_id_reused",
}
ANNOTATIONS = {binding: (errors + C1_APPENDED.get(binding, ""), idempotency) for binding, (errors, idempotency) in ANNOTATIONS.items()}
STATES = {
    "arcforges.fleet.v1.NodeEnrollmentService/ApproveNodeSignIn": "SM-SIGN-IN: PENDING -> APPROVED | DENIED; APPROVED -> DENIED",
    "arcforges.fleet.v1.NodeEnrollmentService/ApproveDeviceCode": "SM-DEVICE-AUTH: PENDING -> APPROVED | DENIED; APPROVED -> DENIED",
}


def annotations():
    result = {}
    for relative in (FLEET, NODE, ACCOUNT):
        result.update(scope.flagship_annotations(text(relative), relative))
    return result


class AdditiveFields(unittest.TestCase):
    def test_each_added_field_has_its_number_type_presence_and_required_rule(self):
        for (relative, message, number), (label, kind, name, required) in ADDED_FIELDS.items():
            with self.subTest(message=message, number=number):
                field = message_fields(relative, message).get(number)
                self.assertIsNotNone(field)
                self.assertEqual(field[:3], (label, kind, name))
                self.assertEqual(field[3].startswith("// validate: required"), required)

    def test_additions_take_the_next_free_numbers_and_nothing_else_is_added(self):
        added = {}
        for (relative, message, number) in ADDED_FIELDS:
            added.setdefault((relative, message), set()).add(number)
        for (relative, message), numbers in added.items():
            if message not in PREVIOUS_HIGHEST:
                continue
            with self.subTest(message=message):
                present = set(message_fields(relative, message))
                self.assertEqual(present - set(range(1, PREVIOUS_HIGHEST[message] + 1)), numbers)
                self.assertEqual(numbers, set(range(PREVIOUS_HIGHEST[message] + 1,
                                                     PREVIOUS_HIGHEST[message] + 1 + len(numbers))))

    def test_withdrawn_proposals_stay_out(self):
        # Freeze item 6: no key_fingerprint in the shared EnrollingNodeInfo; freeze item 2 (Q7 (a)): no refresh proof.
        self.assertEqual(sorted(message_fields(FLEET, "EnrollingNodeInfo")), [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(sorted(message_fields(FLEET, "NodeEnrollmentServiceRefreshNodeSessionRequest")), [1, 10])
        self.assertNotIn("key_fingerprint", text(FLEET))

    def test_sign_out_node_messages_follow_the_unary_convention(self):
        self.assertEqual(message_fields(FLEET, "NodeEnrollmentServiceSignOutNodeRequest"),
                         {1: ("", "arcforges.foundation.v1.RequestMeta", "meta", "")})
        self.assertEqual(sorted(message_fields(FLEET, "NodeEnrollmentServiceSignOutNodeResponse")), [1, 2, 3])
        for message, reserved in (("NodeEnrollmentServiceSignOutNodeRequest", "reserved 2 to 9;"),
                                  ("NodeEnrollmentServiceSignOutNodeResponse", "reserved 4 to 9;")):
            body = re.search(r"^message " + message + r" \{\n(.*?)^\}", text(FLEET), re.M | re.S).group(1)
            self.assertIn(reserved, body)


class AnnotationDelta(unittest.TestCase):
    def test_errors_and_idempotency_of_the_methods_c0_touches(self):
        found = annotations()
        for binding, (errors, idempotency) in ANNOTATIONS.items():
            with self.subTest(binding):
                self.assertEqual(found[binding]["errors"], errors)
                self.assertEqual(found[binding]["idempotency"], idempotency)

    def test_sign_out_node_block_and_the_approval_state_lines(self):
        found = annotations()
        self.assertEqual(found["arcforges.fleet.v1.NodeEnrollmentService/SignOutNode"],
                         {"auth": "node credential", "idempotency": "command_id", "deadline": "10 s", "stream": "none",
                          "errors": ANNOTATIONS["arcforges.fleet.v1.NodeEnrollmentService/SignOutNode"][0],
                          "locality": "cloud"})
        for binding, state in STATES.items():
            self.assertEqual(found[binding]["state"], state)
        self.assertNotIn("plan_limit_reached", "".join(value["errors"] for key, value in found.items()
                                                       if key.startswith("arcforges.fleet.v1.NodeEnrollmentService/")))

    def test_frozen_specification_text(self):
        fleet = text(FLEET)
        for phrase in (
                '"ArcForges node-key-proof v1\\n" (28 bytes ASCII) || purpose (1 byte) || SHA-256(audience) (32 bytes)',
                "//   || node_id (16 bytes) || binding",
                "purpose 0x01 CompleteNodeSignIn, binding = flow_id (16 bytes) || code (UTF-8, 43 chars)",
                "PollDeviceAuthorization, binding = device_code (UTF-8, 43 chars)",
                "audience = the full canonical center URL",
                "low-S (s <= n/2)",
                "class fleet.approveNodeSignIn bound to the flow ID",
                "class fleet.approveDeviceCode bound to the normalized user code",
                "(state.state node_key, state.reason already_registered)",
                "<center>/connect#flow=<flow_id>",
                "<center>/activate#code=XXXX-XXXX",
                "authentication time is never evidence",
                "SemVer 2.0.0, <= 128 chars; the center stores the canonical form",
                # Fix round 1 of #125: protocol-1 (no wrong-code counter revokes a flow) and Q8 (entry budgets).
                "NODE_SIGN_IN_STATE_REVOKED = 6; // a correct code presented again (reuse), or a correct code with a "
                "wrong verifier or node key proof\n",
                "every entry (also a right one) is RESOURCE/rate_limited with retry_at until the window",
                "a right lookup gives both back",
                "The sixth and later lookups of one live code are refused with VALIDATION/code_invalid",
                "limit.available 0); the authorization stays PENDING.",
                "The audience is not sent: the center verifies the proof with SHA-256 of its own public",
                "node_id = the 16 bytes of EnrollingNodeInfo.node_id (Id.value) of the BeginNodeSignIn or "
                "StartDeviceAuthorization",
                "<flow_id> the lower-case 8-4-4-4-12 hex form of the 16 flow_id bytes in order (RFC 9562)"):
            with self.subTest(phrase):
                self.assertIn(phrase, fleet)
        self.assertEqual(len("ArcForges node-key-proof v1\n".encode("ascii")), 28)
        self.assertNotIn("passkey or recent authentication", fleet)
        self.assertNotIn("connect?flow=", fleet)
        for withdrawn in ("fifth wrong code", "denies it", "a wrong entry beyond", "compares it with its own"):
            self.assertNotIn(withdrawn, fleet)
        self.assertIn("STATE/invalid_state (state.state signed_in or signing_in, state.reason center_url).", text(NODE))
        self.assertIn("// validate: HUMAN only;", message_fields(NODE, "NodeServiceUpdateNodeSettingsRequest")[12][3])
        self.assertIn("XXXX-XXXX-XXXX-XXXX-XXXX: upper-case hex of the first 10 bytes of SHA-256",
                      message_fields(ACCOUNT, "SignInFlow")[13][3])


if __name__ == "__main__":
    unittest.main()
