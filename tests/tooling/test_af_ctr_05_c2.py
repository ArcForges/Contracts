# SPDX-License-Identifier: Apache-2.0
"""AF-CTR-05 part C2: the node channel, the routed methods and the node additions.

The expected values below are written from the AF-CTR-05 plan (B.6, C.3, C.4, D.2), its coordinator decisions with the
Addendum (PB-1..PB-4, D0-B1, D0-B2, C-N1, C-N2, C-N6, Q7, Q9, Q15, Q17, Q25) and ArcForges-Design at 611dda6 (11 sections 1
and 3, errors.md, node-store.sql step 2); they are not read back from the protos or the generated code. The signatures and
the decoding of the golden vectors are checked in Go (go/internal/compat/relay_vectors_test.go) and C#
(tests/StructureTests/NodeChannelCases.cs).
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[2]
RELAY = "internal/proto/arcforges/relay/v1/relay.proto"
FLEET = "public/proto/arcforges/fleet/v1/fleet.proto"
COMMON = "public/proto/arcforges/node/v1/common.proto"
TASKS = "public/proto/arcforges/node/v1/tasks.proto"
POLICY = "public/proto/arcforges/node/v1/policy.proto"
VECTORS = "fixtures/internal/af-ctr-05-relay-vectors.json"
DOMAINS = {
    "call": "ArcForges relay-call v1\n",
    "result": "ArcForges relay-result v1\n",
    "hello": "ArcForges relay-hello v1\n",
    "origin": "ArcForges relay-origin v1\n",
}
ROUTED = ("SubmitNodeTask", "GetNodeTask", "ListNodeTasks", "WaitNodeTask", "ReadNodeTaskOutput", "CancelNodeTask")
BOUNDS = {"SubmitNodeTask": 253952, "GetNodeTask": 3072, "ListNodeTasks": 3072, "WaitNodeTask": 3072, "ReadNodeTaskOutput": 3072,
          "CancelNodeTask": 3072}

# The field-number table of the C2 additions (plan D.2, confirmed against the descriptors of main): every new field takes the
# next free number of its message, and a new message numbers from 1 (or, for a request, response or value, from 10 after
# meta = 1 and the reserved 2..9).
FIELDS = {
    (RELAY, "NodeHello"): {"node_id": 1, "version": 2, "generation": 3, "last_seq": 4, "contract_version": 5, "capabilities": 6,
                           "installation_id": 7, "hello_signature": 8},
    (RELAY, "RelayFrame"): {"frame_version": 1, "frame_seq": 2, "node_hello": 10, "summary": 11, "delta": 12, "snapshot": 13,
                            "demand": 14, "command": 15, "command_result": 16, "events": 17, "token_refresh": 18,
                            "entitlement_changed": 19, "close": 20, "ack": 21, "output_tail": 22, "call": 23, "call_result": 24,
                            "heartbeat": 25, "accepted": 26, "challenge": 27, "relay_nonce_request": 28, "relay_nonce": 29},
    (RELAY, "ChannelChallenge"): {"nonce": 1, "connection_id": 2, "hello_deadline": 3},
    (RELAY, "ChannelLimits"): {"max_frame_bytes": 1, "max_in_flight_calls": 2, "heartbeat_interval_ms": 3, "heartbeat_deadline_ms": 4,
                               "max_relay_nonces": 5},
    (RELAY, "ChannelAccepted"): {"connection_id": 1, "limits": 2, "signing_kids": 3, "node_name": 4},
    (RELAY, "ChannelHeartbeat"): {"sent_at": 1, "seq": 2},
    (RELAY, "SignedHeader"): {"header": 1, "signature": 2, "kid": 3, "algorithm": 4},
    (RELAY, "CallHeader"): {"call_id": 1, "kid": 2, "center_url_sha256": 3, "account_id": 4, "target_node_id": 5, "caller": 6,
                            "command_id": 7, "method": 8, "request_sha256": 9, "request_size": 10, "issued_at": 11, "expires_at": 12,
                            "deadline": 13, "relay_assertion_sha256": 14},
    (RELAY, "ChannelCall"): {"call_id": 1, "header": 2, "payload": 3},
    (RELAY, "ResultHeader"): {"call_id": 1, "command_id": 2, "node_id": 3, "method": 4, "request_sha256": 5, "response_sha256": 6,
                              "response_size": 7, "executed_at": 8, "outcome": 9, "error": 10},
    (RELAY, "ChannelResult"): {"call_id": 1, "header": 2, "payload": 3},
    (RELAY, "RelayNonceRequest"): {"request_id": 1},
    (RELAY, "RelayNonce"): {"request_id": 1, "nonce": 2, "expires_at": 3},
    (RELAY, "RelayAssertion"): {"relaying_node_id": 1, "relaying_installation_id": 2, "local_origin": 3, "local_session_id": 4,
                                "method": 5, "request_sha256": 6, "target_node_id": 7, "command_id": 8, "relay_nonce": 9,
                                "issued_at": 10, "expires_at": 11, "signature": 12},
    (FLEET, "FleetServiceListNodesRequest"): {"meta": 1, "caller": 10, "relay_assertion": 11},
    (FLEET, "FleetServiceGetNodeRequest"): {"meta": 1, "node_id": 10, "caller": 11, "relay_assertion": 12},
    (FLEET, "FleetNode"): {"credential_expires_at": 14, "reported_name": 15},
    (FLEET, "RoutedCaller"): {"kind": 1, "relaying_node_id": 2, "local_origin": 3},
    (COMMON, "ActorRef"): {"client_name": 8, "center_caller": 9},
    (COMMON, "CenterCaller"): {"kind": 1, "account_id": 2, "user_id": 3, "session_id": 4, "relaying_node_id": 5, "local_origin": 6,
                               "local_session_id": 7},
    (TASKS, "ManagedTask"): {"shared_keys": 26, "local_diagnostic": 27},
    (TASKS, "TaskServiceReadTaskOutputRequest"): {"attempt_id": 10, "max_bytes": 13, "wait_ms": 14},
    (POLICY, "PolicyDocument"): {"retry_safety": 17, "center_routed": 18},
    (POLICY, "CenterRoutedPolicy"): {"enabled": 1, "relayed_from": 2},
}
for name in ROUTED:
    FIELDS[(FLEET, f"FleetService{name}Request")] = {"meta": 1, "node_id": 10, "caller": 11, "request": 12, "relay_assertion": 13}
    FIELDS[(FLEET, f"FleetService{name}Response")] = {"meta": 1, "value": 2, "error": 3}
    FIELDS[(FLEET, f"FleetService{name}Value")] = {"response": 10, "node_id": 11}
ENUMS = {
    (RELAY, "RoutedMethod"): {"ROUTED_METHOD_UNSPECIFIED": 0, "ROUTED_METHOD_SUBMIT_NODE_TASK": 1, "ROUTED_METHOD_GET_NODE_TASK": 2,
                              "ROUTED_METHOD_LIST_NODE_TASKS": 3, "ROUTED_METHOD_WAIT_NODE_TASK": 4,
                              "ROUTED_METHOD_READ_NODE_TASK_OUTPUT": 5, "ROUTED_METHOD_CANCEL_NODE_TASK": 6,
                              "ROUTED_METHOD_LIST_NODES": 7, "ROUTED_METHOD_GET_NODE": 8},
    # routed_call_log.decision 1..4 (Design node-store.sql step 2).
    (RELAY, "RoutedOutcome"): {"ROUTED_OUTCOME_UNSPECIFIED": 0, "ROUTED_OUTCOME_EXECUTED": 1, "ROUTED_OUTCOME_REFUSED_BY_POLICY": 2,
                               "ROUTED_OUTCOME_REFUSED_VERIFICATION": 3, "ROUTED_OUTCOME_EXPIRED": 4},
    (FLEET, "CallerKind"): {"CALLER_KIND_UNSPECIFIED": 0, "CALLER_KIND_ACCOUNT_SESSION": 1, "CALLER_KIND_NODE_RELAY": 2,
                            "CALLER_KIND_AGENT_GRANT": 3},
    (COMMON, "CenterCallerKind"): {"CENTER_CALLER_KIND_UNSPECIFIED": 0, "CENTER_CALLER_KIND_ACCOUNT_SESSION": 1,
                                   "CENTER_CALLER_KIND_NODE_RELAY": 2, "CENTER_CALLER_KIND_AGENT_GRANT": 3},
    (POLICY, "RelayedFrom"): {"RELAYED_FROM_UNSPECIFIED": 0, "RELAYED_FROM_OWN_NODE": 1, "RELAYED_FROM_ACCOUNT": 2},
}


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


def comments(relative):
    """The file's text with the comment markers removed and the whitespace collapsed, so a phrase may cross a line break."""
    return " ".join(" ".join(line.strip().lstrip("/") for line in text(relative).splitlines()).split())


def contains(case, haystack, phrase):
    case.assertTrue(phrase in haystack, phrase)


def block(source, kind, name):
    match = re.search(rf"^{kind} {name} \{{\n(.*?)^\}}", text(source), re.M | re.S)
    if match is None:
        raise AssertionError(f"{kind} {name} not found in {source}")
    return match.group(1)


def declared(source, name):
    body = re.sub(r"//[^\n]*", "", block(source, "message", name))
    return {field: int(number) for field, number in re.findall(r"(\w+)\s*=\s*(\d+)\s*(?:\[[^]]*\])?;", body)}


def reserved(source, name):
    body = re.sub(r"//[^\n]*", "", block(source, "message", name))
    return re.findall(r"reserved\s+([^;]+);", body)


class FieldNumbers(unittest.TestCase):
    def test_every_added_field_has_its_decided_number(self):
        for (source, message), fields in FIELDS.items():
            with self.subTest(message=message):
                self.assertEqual({name: number for name, number in declared(source, message).items() if name in fields}, fields)

    def test_new_messages_declare_exactly_the_table(self):
        added = {"ChannelChallenge", "ChannelLimits", "ChannelAccepted", "ChannelHeartbeat", "SignedHeader", "CallHeader", "ChannelCall",
                 "ResultHeader", "ChannelResult", "RelayNonceRequest", "RelayNonce", "RelayAssertion", "RoutedCaller", "CenterCaller",
                 "CenterRoutedPolicy"} | {f"FleetService{n}{s}" for n in ROUTED for s in ("Request", "Response", "Value")}
        for (source, message), fields in FIELDS.items():
            if message in added:
                with self.subTest(message=message):
                    self.assertEqual(declared(source, message), fields)

    def test_requests_and_responses_keep_2_to_9_reserved(self):
        names = [f"FleetService{n}{s}" for n in ROUTED for s in ("Request", "Response")]
        names += ["FleetServiceListNodesRequest", "FleetServiceGetNodeRequest"]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(reserved(FLEET, name), ["2 to 9"] if name.endswith("Request") else ["4 to 9"])
                numbers = set(declared(FLEET, name).values())
                self.assertFalse(numbers & set(range(2 if name.endswith("Request") else 4, 10)))

    def test_enum_numbers(self):
        for (source, enum), values in ENUMS.items():
            with self.subTest(enum=enum):
                body = re.sub(r"//[^\n]*", "", block(source, "enum", enum))
                self.assertEqual({name: int(number) for name, number in re.findall(r"(\w+)\s*=\s*(\d+);", body)}, values)

    def test_the_six_routed_methods_follow_the_earlier_fleet_methods(self):
        service = block(FLEET, "service", "FleetService")
        self.assertEqual(len(re.findall(r"^  rpc \w+\(", service, re.M)), 19)
        methods = re.findall(r"^  rpc (\w+)\(FleetService(\w+)Request\) returns \(FleetService(\w+)Response\);", service, re.M)
        self.assertEqual([m[0] for m in methods][-6:], list(ROUTED))
        self.assertTrue(all(m[0] == m[1] == m[2] for m in methods[-6:]))


class DomainStrings(unittest.TestCase):
    def test_four_distinct_domain_strings_with_their_lengths(self):
        self.assertEqual(len(set(DOMAINS.values())), 4)
        self.assertEqual({k: len(v.encode("ascii")) for k, v in DOMAINS.items()}, {"call": 24, "result": 26, "hello": 25, "origin": 26})
        for name, value in DOMAINS.items():
            for other, second in DOMAINS.items():
                if name != other:
                    self.assertFalse(value.startswith(second), (name, other))
        fixture = load(VECTORS)
        self.assertEqual(fixture["domains"], DOMAINS)
        self.assertEqual(fixture["domainLengths"], {"call": 24, "result": 26, "hello": 25, "origin": 26})

    def test_the_proto_states_each_domain_string_and_layout(self):
        relay = comments(RELAY)
        for name, value in DOMAINS.items():
            literal = '"' + value.replace("\n", "\\n") + '"'
            self.assertEqual(relay.count(literal), 1, name)
            contains(self, relay, f"{literal} ({len(value)} bytes)")
        for phrase in ("|| SignedHeader.header (the exact CallHeader bytes)", "|| SignedHeader.header (the exact ResultHeader bytes)",
                       "|| nonce (32) || connection_id (16) || SHA-256(audience) (32) || node_id (16) || installation_id (16); 137 bytes",
                       "|| SHA-256(audience) (32) || relaying_node_id (16) || relaying_installation_id (16) || local_origin (1) "
                       "|| local_session_id (16) || method (1) || request_sha256 (32) || target_node_id (16) || command_id (16) "
                       "|| relay_nonce (32) || issued_at (12) || expires_at (12); 228 bytes",
                       "a signature over the signed bytes without their domain string is refused", "never re-encodes a decoded header",
                       "low-S: s <= n/2"):
            contains(self, relay, phrase)
        self.assertNotIn("ArcForges node-key-proof v1", relay)

    def test_the_vectors_start_with_their_own_domain_string(self):
        fixture = load(VECTORS)
        checks = [("call", fixture["routedCall"]["signingInput"], fixture["routedCall"]["callHeader"]),
                  ("result", fixture["routedResult"]["signingInput"], fixture["routedResult"]["resultHeader"])]
        for kind, signing, header in checks:
            with self.subTest(kind):
                self.assertEqual(bytes.fromhex(signing), DOMAINS[kind].encode() + bytes.fromhex(header))
        self.assertTrue(bytes.fromhex(fixture["hello"]["signingInput"]).startswith(DOMAINS["hello"].encode()))
        for vector in fixture["relayAssertions"]:
            self.assertTrue(bytes.fromhex(vector["signingInput"]).startswith(DOMAINS["origin"].encode()), vector["id"])
        signatures = [fixture["routedCall"]["signature"], fixture["routedResult"]["signature"], fixture["hello"]["signature"]]
        signatures += [vector["signature"] for vector in fixture["relayAssertions"]]
        self.assertEqual(len(set(signatures)), len(signatures))

    def test_the_canonical_bytes_hold_every_signed_field(self):
        # Rebuilt from the fixture's own field values: dropping or reordering a field of the relay-origin or hello layout
        # changes these bytes and fails the Go and C# signature checks.
        fixture = load(VECTORS)
        ids, audience = fixture["ids"], bytes.fromhex(fixture["audienceSha256"])
        self.assertEqual(hashlib.sha256(fixture["audience"].encode()).digest(), audience)
        for vector in fixture["relayAssertions"]:
            optional = lambda value: bytes(16) if value is None else bytes.fromhex(value)  # noqa: E731
            expected = (DOMAINS["origin"].encode() + audience + bytes.fromhex(ids["node"]) + bytes.fromhex(ids["installation"])
                        + bytes([vector["localOrigin"]]) + bytes.fromhex(ids["localSession"]) + bytes([vector["method"]])
                        + bytes.fromhex(vector["requestSha256"]) + optional(vector["targetNodeId"]) + optional(vector["commandId"])
                        + bytes.fromhex(vector["relayNonce"]) + struct.pack(">qI", *vector["issuedAt"]) + struct.pack(">qI", *vector["expiresAt"]))
            with self.subTest(vector["id"]):
                self.assertEqual(len(expected), 228)
                self.assertEqual(bytes.fromhex(vector["signingInput"]), expected)
                self.assertLessEqual(vector["expiresAt"][0] - vector["issuedAt"][0], 120)
        hello = fixture["hello"]
        expected = (DOMAINS["hello"].encode() + bytes.fromhex(hello["nonce"]) + bytes.fromhex(ids["connection"]) + audience
                    + bytes.fromhex(ids["node"]) + bytes.fromhex(ids["installation"]))
        self.assertEqual(bytes.fromhex(hello["signingInput"]), expected)
        call = fixture["routedCall"]
        self.assertLessEqual(call["expiresAt"][0] - call["issuedAt"][0], 300)
        self.assertEqual(hashlib.sha256(bytes.fromhex(call["payload"])).hexdigest(), call["payloadSha256"])
        self.assertEqual(fixture["relayAssertions"][0]["requestSha256"], call["payloadSha256"])
        self.assertEqual(call["relayAssertionSha256"], hashlib.sha256(bytes.fromhex(fixture["relayAssertions"][0]["assertion"])).hexdigest())

    def test_only_public_keys_are_recorded(self):
        raw = text(VECTORS)
        for word in ("PRIVATE", "private", "scalar", "seed"):
            self.assertNotIn(word, raw.replace("only their public halves are recorded", ""))
        for name in ("center", "node", "otherInstallation"):
            self.assertTrue(load(VECTORS)["keys"][name]["spki"].startswith("3059301306072a8648ce3d020106082a8648ce3d030107034200"))


class Validators(unittest.TestCase):
    def sidecar(self, visibility):
        return load(f"{visibility}/proto/constraints.json")["messages"]

    def test_the_relationship_rules_are_declared_and_generated(self):
        relay, fleet, node = self.sidecar("internal"), self.sidecar("public"), self.sidecar("public")
        expected = {
            ("internal", "arcforges.relay.v1.CallHeader"): ["callHeader"],
            ("internal", "arcforges.relay.v1.ResultHeader"): ["resultHeader"],
            ("internal", "arcforges.relay.v1.ChannelCall"): ["channelCall"],
            ("internal", "arcforges.relay.v1.ChannelResult"): ["channelResult"],
            ("internal", "arcforges.relay.v1.ChannelLimits"): ["channelLimits"],
            ("internal", "arcforges.relay.v1.RelayAssertion"): ["relayAssertion"],
            ("public", "arcforges.node.v1.CenterCaller"): ["centerCaller"],
        }
        for name in [f"FleetService{n}Request" for n in ROUTED] + ["FleetServiceListNodesRequest", "FleetServiceGetNodeRequest"]:
            expected[("public", "arcforges.fleet.v1." + name)] = ["relayedCaller"]
        for (visibility, message), rules in expected.items():
            with self.subTest(message=message):
                self.assertEqual((relay if visibility == "internal" else fleet)[message].get("rules"), rules)
        self.assertEqual(node["arcforges.node.v1.CenterRoutedPolicy"]["fields"]["relayedFrom"], {"enumValues": [1, 2]})
        relay_cs = text("src/internal/dotnet/ArcForges.Contracts.Relay/Generated/Shapes/ProtoValidation.g.cs")
        # The two expiry bounds: 300 s for a call (AD-0021 section 10), 120 s for a relay assertion (Plan addendum D0-B1).
        self.assertEqual(relay_cs.count("if (!RelayWindow(value.IssuedAt, value.ExpiresAt, 300)) return false;"), 1)
        self.assertEqual(relay_cs.count("if (!RelayWindow(value.IssuedAt, value.ExpiresAt, 120)) return false;"), 1)
        self.assertNotRegex(relay_cs, r"RelayWindow\(value\.IssuedAt, value\.ExpiresAt, (?!300\)|120\))\d+\)")
        fleet_cs = text("src/public/dotnet/ArcForges.Contracts.Fleet/Generated/Shapes/ProtoValidation.g.cs")
        self.assertEqual(fleet_cs.count("if ((value.Caller is null) == value.HasRelayAssertion) return false;"), 8)

    def test_every_new_field_is_bounded(self):
        relay, public = self.sidecar("internal"), self.sidecar("public")
        call = relay["arcforges.relay.v1.CallHeader"]["fields"]
        self.assertEqual(call["requestSize"], {"required": True, "min": 1, "max": BOUNDS["SubmitNodeTask"]})
        self.assertEqual(call["kid"], {"required": True, "pattern": "^[A-Za-z0-9_-]{8,64}$"})
        for message, field in (("CallHeader", "centerUrlSha256"), ("CallHeader", "requestSha256"), ("ChannelChallenge", "nonce"),
                               ("RelayNonce", "nonce"), ("RelayAssertion", "requestSha256"), ("RelayAssertion", "relayNonce")):
            self.assertEqual(relay["arcforges.relay.v1." + message]["fields"][field], {"required": True, "bytesLength": 32}, (message, field))
        for message, field in (("SignedHeader", "signature"), ("RelayAssertion", "signature"), ("NodeHello", "helloSignature")):
            self.assertEqual(relay["arcforges.relay.v1." + message]["fields"][field], {"required": True, "bytesLength": 64}, (message, field))
        self.assertEqual(relay["arcforges.relay.v1.SignedHeader"]["fields"]["header"], {"required": True, "minLength": 1, "maxLength": 2048})
        self.assertEqual(relay["arcforges.relay.v1.ChannelLimits"]["fields"]["maxFrameBytes"], {"required": True, "min": 65536, "max": 1048576})
        for name, bound in BOUNDS.items():
            fields = public[f"arcforges.fleet.v1.FleetService{name}Request"]["fields"]
            self.assertEqual(fields["request"], {"required": True, "minLength": 1, "maxLength": bound}, name)
            self.assertEqual(fields["relayAssertion"], {"minLength": 1, "maxLength": 512}, name)
            self.assertEqual(fields["nodeId"], {"required": True}, name)
            self.assertEqual(public[f"arcforges.fleet.v1.FleetService{name}Value"]["fields"]["response"],
                             {"required": True, "minLength": 1, "maxLength": 1040384}, name)
        # The Submit envelope fits the center's AbsoluteMaxRequestBytes (262,144) with room for meta, caller and assertion (PN-9).
        self.assertLessEqual(BOUNDS["SubmitNodeTask"] + 512 + 4096, 262144)
        self.assertEqual(public["arcforges.node.v1.TaskServiceReadTaskOutputRequest"]["fields"]["waitMs"], {"min": 0, "max": 20000})


class Annotations(unittest.TestCase):
    def methods(self):
        return {m["binding"]: m["annotations"] for m in scope.flagship_methods(ROOT, scope.proto_methods(ROOT))}

    def test_the_routed_methods_are_annotated(self):
        methods = self.methods()
        for name in ROUTED:
            annotations = methods["arcforges.fleet.v1.FleetService/" + name]
            errors = {code.strip() for code in annotations["errors"].split(",")}
            with self.subTest(name):
                self.assertEqual(annotations["locality"], "cloud -> node")
                self.assertEqual(annotations["stream"], "none")
                self.assertIn("node credential as the relay of its own node, with caller and relay_assertion", annotations["auth"])
                self.assertTrue({"STATE/node_offline", "STATE/node_unreachable", "STATE/not_found", "AUTHENTICATION/unauthenticated",
                                 "ENTITLEMENT/feature_not_entitled", "RESOURCE/rate_limited", "VALIDATION/invalid_argument",
                                 "AUTHORIZATION/permission_denied", "STATE/expired", "AUTHENTICATION/signature_invalid"} <= errors)
                mutation = name in ("SubmitNodeTask", "CancelNodeTask")
                # PB-1: step-up on Submit and Cancel; a mobile.limited session never reaches them; reads open to both.
                self.assertEqual("AUTHENTICATION/step_up_required" in errors, mutation)
                self.assertEqual("CONFLICT/command_id_reused" in errors, mutation)
                self.assertEqual("account session with step-up" in annotations["auth"], mutation)
                self.assertEqual("a mobile.limited session upgrades first" in annotations["auth"], mutation)
                self.assertEqual(annotations["idempotency"].startswith("command_id"), mutation)
                if not mutation:
                    self.assertEqual(annotations["idempotency"], "read")
                    self.assertIn("mobile.limited included", annotations["auth"])
        self.assertEqual(methods["arcforges.fleet.v1.FleetService/SubmitNodeTask"]["deadline"], "10 s")
        self.assertEqual(methods["arcforges.fleet.v1.FleetService/WaitNodeTask"]["deadline"], "wait_ms + 5 s, at most 55 s")
        self.assertEqual(methods["arcforges.fleet.v1.FleetService/ReadNodeTaskOutput"]["deadline"], "10 s; wait_ms + 10 s with wait_ms, at most 30 s")
        self.assertIn("class fleet.submitNodeTask", methods["arcforges.fleet.v1.FleetService/SubmitNodeTask"]["auth"])
        self.assertIn("class fleet.cancelNodeTask", methods["arcforges.fleet.v1.FleetService/CancelNodeTask"]["auth"])

    def test_list_and_get_node_take_the_assertion(self):
        methods = self.methods()
        for name in ("ListNodes", "GetNode"):
            annotations = methods["arcforges.fleet.v1.FleetService/" + name]
            with self.subTest(name):
                self.assertIn("or node credential as the relay of its own node, with caller and relay_assertion", annotations["auth"])
                self.assertIn("AUTHENTICATION/unauthenticated", annotations["errors"])
        for name in ("RenameNode", "RevokeNode"):
            self.assertNotIn("node credential", methods["arcforges.fleet.v1.FleetService/" + name]["auth"])

    def test_the_task_service_remote_cells_and_the_local_rule(self):
        methods = self.methods()
        cells = {"SubmitTask": "REMOTE=high (center-routed policy decides); local: HUMAN only (AD-0021 section 5)",
                 "GetTask": "REMOTE=low (center-routed policy decides)", "ListTasks": "REMOTE=low (center-routed policy decides)",
                 "WaitTask": "REMOTE=low (center-routed policy decides)",
                 "ReadTaskOutput": "REMOTE=low (center-routed policy decides; privacy policy for others' tasks)",
                 "CancelTask": "REMOTE=medium (center-routed policy decides; ADOPTED: process.terminate REMOTE=D)"}
        for name, cell in cells.items():
            with self.subTest(name):
                self.assertTrue(methods["arcforges.node.v1.TaskService/" + name]["auth"].endswith(cell))
                self.assertNotIn("REMOTE=-", methods["arcforges.node.v1.TaskService/" + name]["auth"])
        tasks = comments(TASKS)
        contains(self, tasks, "state.reason local_submission_human_only")
        contains(self, tasks, "ARCFORGES_TEST_ALLOW_LOCAL_SCRIPT_SUBMIT=1")

    def test_the_resend_pair_of_a_relay_assertion_refusal(self):
        # C1 review N-2, routed to C2: errors.md's AF-CTR-05 target advice for unauthenticated (C-N4).
        catalogue = {r["category"] + "/" + r["code"]: r for r in load("fixtures/public/af-con-01-error-catalogue.json")["codes"]}
        self.assertEqual(catalogue["AUTHENTICATION/unauthenticated"]["pairs"],
                         [{"effect": "DID_NOT_HAPPEN", "retry": "NEVER"}, {"effect": "DID_NOT_HAPPEN", "retry": "SAME_COMMAND"}])
        self.assertIn("resends with the same `command_id`", catalogue["AUTHENTICATION/unauthenticated"]["retryAdvice"])
        fleet = comments(FLEET)
        contains(self, fleet, "same command_id (DID_NOT_HAPPEN, SAME_COMMAND; no sign-in)")
        relay = comments(RELAY)
        contains(self, relay, "resends with the same command_id (DID_NOT_HAPPEN, SAME_COMMAND; no sign-in)")


class Policy(unittest.TestCase):
    def test_own_node_is_the_default(self):
        policy = text(POLICY)
        contains(self, policy, "RELAYED_FROM_UNSPECIFIED = 0; // read as OWN_NODE")
        contains(self, policy, "RELAYED_FROM_OWN_NODE = 1; // default:")
        contains(self, policy, "RELAYED_FROM_ACCOUNT = 2; // opt-in:")
        self.assertIn('optional RelayedFrom relayed_from = 2 [json_name = "relayedFrom"]; // default OWN_NODE; ACCOUNT is the cross-node opt-in', policy)
        section = policy.split("enum RelayedFrom")[1].split("message TimeWindow")[0]
        self.assertNotRegex(section, r"default:? ACCOUNT|ACCOUNT = 2; // default|OWN_NODE = 1; // opt-in")

    def test_the_center_routed_policy_has_its_own_human_only_switch(self):
        policy = comments(POLICY)
        contains(self, policy, "Only a local HUMAN changes it (operation policy.center_routed)")
        self.assertIn('optional bool enabled = 1 [json_name = "enabled"]; // default true while the node is signed in with its cloud link on', policy)
        contains(self, policy, "state.reason center_routed_disabled")
        contains(self, policy, "it neither enables nor disables center-routed calls")


if __name__ == "__main__":
    unittest.main()
