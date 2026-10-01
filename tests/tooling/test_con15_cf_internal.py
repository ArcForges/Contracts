# SPDX-License-Identifier: Apache-2.0
"""Offline conformance vectors for the private Cloudflare HTTP contract bundle (CON.15).

Everything here is an independent offline oracle: a small closed JSON-schema subset validator
and tiny reference models for the stateful rules (replay, lease epochs, R2 part receipts and
service-grant lifetime). None of it is a Worker handler, a live Cloudflare/R2 check or a
provider proof.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "internal/cf-http/v1/schema.json"
AI_SCHEMA_PATH = ROOT / "internal/ai-http/v1/schema.json"
FIXTURE_PATH = ROOT / "fixtures/internal/con-15-cf-internal.json"
EXTERNAL_PREFIX = "../../ai-http/v1/schema.json#/$defs/"
EXPECTED_SHARED_DEFS = {
    "ArcError",
    "ByteRange",
    "ExecutionOwner",
    "ModelUsage",
    "ResourceRef",
    "ResourceVersionRef",
    "SessionBinding",
}
UINT64_MAX = 2**64 - 1
INT64_MAX = 2**63 - 1
MAX_PART_BYTES = 8 * 1024 * 1024
GRANT_LIFETIME_SECONDS = 60
LEASE_SECONDS = 60
# Request/response roots of the 17 private routes; the last three roots are shared records.
ROUTE_ROOTS = {
    "cf.objects.authorize": ("ObjectAuthorizeRequest", "ObjectAuthorizeResponse"),
    "cf.objects.part-receipt": ("ObjectPartReceiptRequest", "ObjectPartReceiptResponse"),
    "cf.objects.verification": ("ObjectVerificationRequest", "ObjectVerificationResponse"),
    "cf.objects.job-grant": ("ObjectJobGrantRequest", "ObjectJobGrantResponse"),
    "cf.objects.job-authorize": ("ObjectJobAuthorizeRequest", "ObjectJobAuthorizeResponse"),
    "cf.objects.job-read": ("WorkerObjectJobRequest", "WorkerObjectJobResponse"),
    "cf.objects.job-write": ("WorkerObjectJobRequest", "WorkerObjectJobResponse"),
    "cf.ai.dispatch": ("WorkerDispatchRequest", "WorkerDispatchResponse"),
    "cf.ai.control": ("WorkerControlRequest", "WorkerControlResponse"),
    "cf.ai.delete": ("WorkerDeleteRequest", "WorkerDeleteResponse"),
    "cf.ai.web-search": ("WorkerWebSearchRequest", "WorkerWebSearchResponse"),
    "cf.ai.inference-job": ("InferenceJobRequest", "InferenceJobResponse"),
    "cf.ai.inference-lease": ("InferenceLeaseRequest", "InferenceLeaseResponse"),
    "cf.ai.inference-input": ("InferenceInputRequest", "InferenceInputResponse"),
    "cf.ai.inference-outcome": ("InferenceOutcomeRequest", "InferenceOutcomeResponse"),
    "cf.ai.inference-late-outcome": ("InferenceLateOutcomeRequest", "InferenceLateOutcomeResponse"),
    "cf.ai.inference-state": ("InferenceStateRequest", "InferenceStateResponse"),
}
SHARED_RECORD_ROOTS = {"CfDeletionTarget", "CfDeletionReceipt", "BackupManifest"}
FORBIDDEN_PROPERTY_NAMES = {
    "bearer", "accessToken", "refreshToken", "cookie", "accessKeyId", "secretAccessKey",
    "presignedUrl", "r2Key", "sql", "tableName", "operation", "workspaceKey",
}


def _type_matches(value, expected):
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: type(value) is int,
        "number": lambda: type(value) in (int, float),
        "boolean": lambda: type(value) is bool,
        "null": lambda: value is None,
    }[expected]()


def matches(value, node, owner_schema, ai_schema):
    """Closed JSON-schema subset used by the authored private bundles."""
    if "$ref" in node:
        reference = node["$ref"]
        if reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            target = owner_schema.get("$defs", {}).get(name)
            return target is not None and matches(value, target, owner_schema, ai_schema)
        if reference.startswith(EXTERNAL_PREFIX):
            name = reference.removeprefix(EXTERNAL_PREFIX)
            if name not in EXPECTED_SHARED_DEFS or name not in ai_schema.get("$defs", {}):
                return False
            return matches(value, ai_schema["$defs"][name], ai_schema, ai_schema)
        return False

    if "oneOf" in node:
        selected = sum(matches(value, branch, owner_schema, ai_schema) for branch in node["oneOf"]) == 1
        return selected and _within_byte_limit(value, node)

    kind = node.get("type")
    if kind is not None and not _type_matches(value, kind):
        return False
    if kind == "object":
        properties = node.get("properties", {})
        if not set(node.get("required", [])).issubset(value):
            return False
        if node.get("additionalProperties") is False and set(value) - set(properties):
            return False
        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            for name, child_value in value.items():
                if name not in properties and not matches(child_value, additional, owner_schema, ai_schema):
                    return False
        property_names = node.get("propertyNames")
        if property_names is not None and any(
            not matches(name, property_names, owner_schema, ai_schema) for name in value
        ):
            return False
        if len(value) < node.get("minProperties", 0) or len(value) > node.get("maxProperties", 10**9):
            return False
        for name, child in properties.items():
            if name in value and not matches(value[name], child, owner_schema, ai_schema):
                return False
    elif kind == "array":
        if len(value) < node.get("minItems", 0) or len(value) > node.get("maxItems", 10**9):
            return False
        if not all(matches(item, node["items"], owner_schema, ai_schema) for item in value):
            return False
    elif kind == "string":
        if len(value) < node.get("minLength", 0) or len(value) > node.get("maxLength", 10**9):
            return False
        if "pattern" in node and re.fullmatch(node["pattern"], value) is None:
            return False
    elif kind in {"integer", "number"}:
        if value < node.get("minimum", -float("inf")) or value > node.get("maximum", float("inf")):
            return False

    if "const" in node and value != node["const"]:
        return False
    if "enum" in node and value not in node["enum"]:
        return False
    if "not" in node and matches(value, node["not"], owner_schema, ai_schema):
        return False
    for rule in node.get("x-arcforges-rules", []):
        if rule == "nonzeroUuid" and value == "00000000-0000-0000-0000-000000000000":
            return False
        if rule == "uint64String" and (not value.isdecimal() or int(value) > UINT64_MAX):
            return False
        if rule == "positiveInt64String" and (not value.isdecimal() or not 0 < int(value) <= INT64_MAX):
            return False
    return _within_byte_limit(value, node)


def _within_byte_limit(value, node):
    limit = node.get("x-arcforges-max-bytes")
    return limit is None or len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= limit


def apply_operations(base, operations):
    candidate = copy.deepcopy(base)
    for operation in operations:
        tokens = operation["path"].split(".")
        parent = candidate
        for token in tokens[:-1]:
            parent = parent[int(token)] if isinstance(parent, list) else parent[token]
        leaf = tokens[-1]
        key = int(leaf) if isinstance(parent, list) else leaf
        if operation["op"] == "set":
            if isinstance(parent, list):
                parent[key] = copy.deepcopy(operation["value"])
            else:
                parent[key] = copy.deepcopy(operation["value"])
        elif operation["op"] == "remove":
            del parent[key]
        elif operation["op"] == "fill":
            parent[key] = [copy.deepcopy(operation["value"]) for _ in range(operation["count"])]
        else:
            raise AssertionError(f"unknown fixture operation {operation['op']}")
    return candidate


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ReplayLedger:
    """Reference model of exact retry, duplicate delivery and changed-body conflict."""

    def __init__(self, port):
        self.port = port
        self.commands = {}
        self.workflows = {}

    def workflow_id(self, body):
        prefix = "af" if self.port == "dispatch" else "afi"
        owner = body["runId"] if self.port == "dispatch" else body["jobId"]
        return f"{prefix}-{owner}-{body['recoveryGeneration']}"

    def submit(self, request_id, body):
        digest = canonical(body)
        if request_id in self.commands and self.commands[request_id] != digest:
            return {"result": "conflict"}
        self.commands[request_id] = digest
        workflow = self.workflow_id(body)
        if workflow in self.workflows:
            # The same durable workflow is returned only for the same identity payload.
            return ({"result": "existing", "workflowId": workflow}
                    if self.workflows[workflow] == digest else {"result": "conflict"})
        self.workflows[workflow] = digest
        return {"result": "created", "workflowId": workflow}


class LeaseTable:
    """Reference model of the 60-second epoch lease and its stale-fence rules."""

    def __init__(self):
        self.holder = None
        self.epoch = 0
        self.expires = None

    def live(self, at):
        return self.holder is not None and at < self.expires

    def claim(self, at, workflow, expected_epoch):
        if expected_epoch is None:
            if self.live(at):
                if workflow != self.holder:
                    return {"result": "refused"}
                self.expires = at + LEASE_SECONDS
                return {"result": "granted", "epoch": self.epoch}
            self.epoch += 1
            self.holder, self.expires = workflow, at + LEASE_SECONDS
            return {"result": "granted", "epoch": self.epoch}
        if expected_epoch != self.epoch or workflow != self.holder or not self.live(at):
            return {"result": "refused"}
        self.expires = at + LEASE_SECONDS
        return {"result": "granted", "epoch": self.epoch}

    def outcome(self, at, workflow, epoch):
        if epoch != self.epoch or workflow != self.holder or not self.live(at):
            return {"result": "staleEpoch"}
        return {"result": "accepted", "publishes": True}

    def late_outcome(self, original_epoch):
        # Stale-fence evidence may settle supplier liability but never publishes.
        if original_epoch > self.epoch:
            return {"result": "refused"}
        return {"result": "accepted", "publishes": False}


class PartLedger:
    """Reference model of immutable part receipts and pre-receipt verification."""

    def __init__(self):
        self.parts = {}

    def submit(self, step):
        if "bytes" in step:
            data = step["bytes"].encode("utf-8")
            length = len(data)
        else:
            data, length = None, step["declaredLength"]
        if length > MAX_PART_BYTES:
            return "refused-too-large"
        digest = hashlib.sha256(data).hexdigest() if data is not None else step["declaredSha256"]
        if digest != step["declaredSha256"]:
            return "refused-hash-mismatch"
        identity = (digest, length)
        number = step["partNumber"]
        if number in self.parts:
            return "same-receipt" if self.parts[number] == identity else "refused-duplicate-differs"
        self.parts[number] = identity
        return "recorded"


def grant_status(vector):
    if vector["grantEpoch"] != vector["currentEpoch"]:
        return "refused-stale-epoch"
    if vector["expiresAtSeconds"] - vector["issuedAtSeconds"] > GRANT_LIFETIME_SECONDS:
        return "refused-lifetime"
    if vector["expiresAtSeconds"] > vector["ownerLeaseExpiresAtSeconds"]:
        return "refused-lease"
    if vector.get("usedAtSeconds", vector["issuedAtSeconds"]) > vector["expiresAtSeconds"]:
        return "refused-expired"
    return "valid"


def worker_object_binding_is_consistent(path_grant_id, request):
    """Path-to-grant and method-to-direction rule; no Worker runtime handler is exercised."""
    expected_direction = {"GET": "read", "PUT": "write"}.get(request.get("method"))
    grant = request.get("grant")
    return (
        expected_direction is not None
        and request.get("grantId") == path_grant_id
        and isinstance(grant, dict)
        and grant.get("grantId") == path_grant_id
        and grant.get("direction") == expected_direction
    )


class Con15CfInternalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.ai_schema = json.loads(AI_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.roots = [row["$ref"].removeprefix("#/$defs/") for row in cls.schema["oneOf"]]
        cls.positive = {row["id"]: row for row in cls.fixture["positiveVectors"]}

    def check(self, value, root):
        return matches(value, self.schema["$defs"][root], self.schema, self.ai_schema)

    def test_root_bundle_has_unique_closed_titled_roots(self):
        self.assertEqual(self.schema.get("title"), "CloudflareInternalHttpContractBundle")
        self.assertEqual(self.schema.get("x-arcforges-schema-version"), "1")
        self.assertEqual(len(self.roots), len(set(self.roots)))
        for name in self.roots:
            node = self.schema["$defs"][name]
            self.assertEqual(node.get("title"), name)
            if node.get("type") == "object":
                self.assertIs(node.get("additionalProperties"), False)
                self.assertGreaterEqual(node["x-arcforges-max-bytes"], 1)
            else:
                self.assertEqual(set(node) - {"$comment"}, {"title", "oneOf", "x-arcforges-max-bytes"})
                self.assertTrue(all(branch["$ref"].startswith("#/$defs/") for branch in node["oneOf"]))
            self.assertLessEqual(node["x-arcforges-max-bytes"], 4194304)

    def test_every_object_in_the_bundle_is_closed(self):
        for name, node in self.schema["$defs"].items():
            if node.get("type") == "object" and "propertyNames" not in node:
                with self.subTest(definition=name):
                    self.assertIs(node.get("additionalProperties"), False)

    def test_routes_cover_exactly_the_bundle_roots(self):
        route_roots = {root for pair in ROUTE_ROOTS.values() for root in pair}
        self.assertEqual(len(ROUTE_ROOTS), 17)
        self.assertEqual(route_roots | SHARED_RECORD_ROOTS, set(self.roots))
        self.assertFalse(route_roots & SHARED_RECORD_ROOTS)

    def test_external_refs_are_exact_path_pinned_canonical_con10_models(self):
        found = set()

        def walk(node):
            if isinstance(node, dict):
                reference = node.get("$ref")
                if reference is not None:
                    if reference.startswith("#/$defs/"):
                        name = reference.removeprefix("#/$defs/")
                        self.assertTrue(name and "/" not in name, reference)
                        self.assertIn(name, self.schema["$defs"], reference)
                    else:
                        self.assertTrue(reference.startswith(EXTERNAL_PREFIX), reference)
                        name = reference.removeprefix(EXTERNAL_PREFIX)
                        self.assertIn(name, EXPECTED_SHARED_DEFS, reference)
                        self.assertIn(name, self.ai_schema["$defs"], reference)
                        found.add(reference)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(self.schema["$defs"])
        self.assertEqual(found, {EXTERNAL_PREFIX + name for name in EXPECTED_SHARED_DEFS})

    def test_no_credential_sql_or_raw_storage_field_is_representable(self):
        def names(node):
            if isinstance(node, dict):
                for key, child in node.get("properties", {}).items():
                    yield key
                    yield from names(child)
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        yield from names(value)
            elif isinstance(node, list):
                for value in node:
                    yield from names(value)

        self.assertFalse(set(names(self.schema["$defs"])) & FORBIDDEN_PROPERTY_NAMES)
        credential_owners = [
            name for name, node in self.schema["$defs"].items() if "credential" in node.get("properties", {})
        ]
        self.assertEqual(credential_owners, ["ObjectAuthorizeCredentialRequest"])

    def test_every_root_has_a_positive_vector_and_every_vector_is_accepted(self):
        self.assertEqual({row["schema"] for row in self.positive.values()}, set(self.roots))
        self.assertEqual(len(self.positive), len(self.fixture["positiveVectors"]))
        for vector in self.positive.values():
            with self.subTest(vector=vector["id"]):
                self.assertTrue(self.check(vector["input"], vector["schema"]))

    def test_union_branches_are_each_exercised(self):
        for root, branches in {
            "ObjectAuthorizeRequest": 2,
            "ObjectJobGrantRequest": 2,
            "ObjectJobGrantResponse": 2,
            "WorkerObjectJobRequest": 2,
            "WorkerObjectJobResponse": 2,
            "WorkerWebSearchResponse": 2,
            "InferenceOutcomeRequest": 2,
            "InferenceLateOutcomeRequest": 2,
        }.items():
            with self.subTest(root=root):
                accepted = [row for row in self.positive.values() if row["schema"] == root]
                self.assertGreaterEqual(len(accepted), branches)
                node = self.schema["$defs"][root]
                self.assertEqual(len(node["oneOf"]), branches)
                matched = set()
                for row in accepted:
                    for branch in node["oneOf"]:
                        if matches(row["input"], branch, self.schema, self.ai_schema):
                            matched.add(branch["$ref"])
                self.assertEqual(matched, {branch["$ref"] for branch in node["oneOf"]})

    def test_negative_vectors_fail_closed_after_a_single_mutation_of_a_valid_base(self):
        ids = [row["id"] for row in self.fixture["negativeVectors"]]
        self.assertEqual(len(ids), len(set(ids)))
        for vector in self.fixture["negativeVectors"]:
            with self.subTest(vector=vector["id"]):
                base = self.positive[vector["base"]]
                self.assertEqual(base["schema"], vector["schema"])
                self.assertTrue(self.check(base["input"], vector["schema"]))
                candidate = apply_operations(base["input"], vector["operations"])
                self.assertNotEqual(candidate, base["input"])
                self.assertFalse(self.check(candidate, vector["schema"]))

    def test_every_route_family_has_a_fail_closed_vector(self):
        covered = {row["schema"] for row in self.fixture["negativeVectors"]}
        for route, (request, response) in ROUTE_ROOTS.items():
            with self.subTest(route=route):
                self.assertTrue({request, response} & covered)

    def test_replay_and_duplicate_dispatch_vectors(self):
        for vector in self.fixture["replayVectors"]:
            with self.subTest(vector=vector["id"]):
                ledger = ReplayLedger(vector["port"])
                actual = [ledger.submit(step["requestId"], step["body"]) for step in vector["steps"]]
                self.assertEqual(actual, vector["expected"])
        ids = {row["id"] for row in self.fixture["replayVectors"]}
        self.assertIn("duplicate-dispatch-returns-same-workflow", ids)
        self.assertIn("duplicate-inference-job-returns-same-workflow", ids)

    def test_lease_takeover_and_stale_epoch_vectors(self):
        for vector in self.fixture["leaseVectors"]:
            with self.subTest(vector=vector["id"]):
                lease = LeaseTable()
                actual = []
                for step in vector["steps"]:
                    if step["action"] == "claim":
                        actual.append(lease.claim(step["at"], step["workflowId"], step["expectedEpoch"]))
                    elif step["action"] == "outcome":
                        actual.append(lease.outcome(step["at"], step["workflowId"], step["epoch"]))
                    else:
                        actual.append(lease.late_outcome(step["originalEpoch"]))
                self.assertEqual(actual, vector["expected"])
        takeover = next(row for row in self.fixture["leaseVectors"] if row["id"].startswith("takeover-after-expiry"))
        self.assertIn({"result": "staleEpoch"}, takeover["expected"])

    def test_r2_part_mismatch_and_bound_vectors(self):
        for vector in self.fixture["partVectors"]:
            with self.subTest(vector=vector["id"]):
                ledger = PartLedger()
                self.assertEqual([ledger.submit(step) for step in vector["steps"]], vector["expected"])
        ids = {row["id"] for row in self.fixture["partVectors"]}
        self.assertIn("r2-part-mismatch-different-bytes-for-same-part-is-refused", ids)

    def test_service_grant_lifetime_epoch_and_expiry_vectors(self):
        for vector in self.fixture["grantVectors"]:
            with self.subTest(vector=vector["id"]):
                self.assertEqual(grant_status(vector), vector["expected"])
        statuses = {row["expected"] for row in self.fixture["grantVectors"]}
        self.assertEqual(statuses, {
            "valid", "refused-lifetime", "refused-lease", "refused-stale-epoch", "refused-expired"})

    def test_worker_object_binding_vectors_cover_path_grant_and_direction_mismatches(self):
        self.assertIn("path-to-grant and method-to-direction enforcement", self.fixture["bindingValidationBoundary"])
        vectors = self.fixture["workerObjectJobBindingVectors"]
        self.assertEqual(len(vectors), 6)
        for vector in vectors:
            with self.subTest(vector=vector["id"]):
                request = copy.deepcopy(self.positive[vector["positiveVector"]]["input"])
                request["grantId"] = vector["requestGrantId"]
                request["grant"]["grantId"] = vector["signedGrantId"]
                request["method"] = vector["method"]
                request["grant"]["direction"] = vector["direction"]
                # JSON Schema checks each bounded DTO but cannot compare a URI path segment with
                # body values, so this separate rule is the specified binding contract.
                self.assertTrue(self.check(request, "WorkerObjectJobRequest"))
                self.assertEqual(
                    worker_object_binding_is_consistent(vector["pathGrantId"], request),
                    vector["expectedBinding"],
                )

    def test_fixture_is_offline_only_evidence(self):
        self.assertEqual(
            self.fixture["evidenceClass"],
            "offline contract vectors only; no Worker, Cloudflare, R2, provider, authorization or live-service proof",
        )
        self.assertEqual(self.fixture["transport"]["networkAccess"], "none")
        self.assertIs(self.fixture["transport"]["userBearerOrPatForwarding"], False)
        self.assertIs(self.fixture["transport"]["publicRouteAdmission"], False)


if __name__ == "__main__":
    unittest.main()
