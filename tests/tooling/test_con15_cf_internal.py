# SPDX-License-Identifier: Apache-2.0
"""Offline conformance vectors for the private Cloudflare HTTP contract bundle."""
import copy
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


def matches(value, node, owner_schema, cf_schema, ai_schema):
    if "$ref" in node:
        reference = node["$ref"]
        if reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            target = owner_schema.get("$defs", {}).get(name)
            return target is not None and matches(value, target, owner_schema, cf_schema, ai_schema)
        if reference.startswith(EXTERNAL_PREFIX):
            name = reference.removeprefix(EXTERNAL_PREFIX)
            if name not in EXPECTED_SHARED_DEFS or name not in ai_schema.get("$defs", {}):
                return False
            return matches(value, ai_schema["$defs"][name], ai_schema, cf_schema, ai_schema)
        return False

    if "oneOf" in node:
        return sum(matches(value, branch, owner_schema, cf_schema, ai_schema) for branch in node["oneOf"]) == 1

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
                if name not in properties and not matches(child_value, additional, owner_schema, cf_schema, ai_schema):
                    return False
        property_names = node.get("propertyNames")
        if property_names is not None and any(
            not matches(name, property_names, owner_schema, cf_schema, ai_schema) for name in value
        ):
            return False
        if len(value) < node.get("minProperties", 0) or len(value) > node.get("maxProperties", 10**9):
            return False
        for name, child in properties.items():
            if name in value and not matches(value[name], child, owner_schema, cf_schema, ai_schema):
                return False
    elif kind == "array":
        if len(value) < node.get("minItems", 0) or len(value) > node.get("maxItems", 10**9):
            return False
        if not all(matches(item, node["items"], owner_schema, cf_schema, ai_schema) for item in value):
            return False
    elif kind == "string":
        if len(value) < node.get("minLength", 0) or len(value) > node.get("maxLength", 10**9):
            return False
        if "pattern" in node and re.search(node["pattern"], value) is None:
            return False
    elif kind in {"integer", "number"}:
        if value < node.get("minimum", -float("inf")) or value > node.get("maximum", float("inf")):
            return False

    if "const" in node and value != node["const"]:
        return False
    if "enum" in node and value not in node["enum"]:
        return False
    if "not" in node and matches(value, node["not"], owner_schema, cf_schema, ai_schema):
        return False
    for rule in node.get("x-arcforges-rules", []):
        if rule == "nonzeroUuid" and value == "00000000-0000-0000-0000-000000000000":
            return False
        if rule == "uint64String" and (not value.isdecimal() or int(value) > UINT64_MAX):
            return False
        if rule == "positiveInt64String" and (not value.isdecimal() or not 0 < int(value) <= INT64_MAX):
            return False
    byte_limit = node.get("x-arcforges-max-bytes")
    if byte_limit is not None and len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > byte_limit:
        return False
    return True


class Con15CfInternalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.ai_schema = json.loads(AI_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_root_bundle_has_unique_closed_records(self):
        roots = [row["$ref"].removeprefix("#/$defs/") for row in self.schema["oneOf"]]
        self.assertEqual(len(roots), len(set(roots)))
        for name in roots:
            node = self.schema["$defs"][name]
            self.assertEqual(node.get("title"), name)
            if node.get("type") == "object":
                self.assertIs(node.get("additionalProperties"), False)
            else:
                self.assertEqual(set(node), {"title", "oneOf", "x-arcforges-max-bytes"})
                self.assertGreaterEqual(node["x-arcforges-max-bytes"], 1)

    def test_external_refs_are_exact_path_pinned_canonical_con10_models(self):
        found = set()

        def walk(node):
            if isinstance(node, dict):
                reference = node.get("$ref")
                if reference is not None and reference.startswith("../../"):
                    self.assertTrue(reference.startswith(EXTERNAL_PREFIX), reference)
                    name = reference.removeprefix(EXTERNAL_PREFIX)
                    self.assertIn(name, self.ai_schema["$defs"])
                    found.add(name)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(self.schema["$defs"])
        self.assertEqual(found, EXPECTED_SHARED_DEFS)

    def test_positive_schema_vectors_are_closed_and_bounded(self):
        for vector in self.fixture["positiveVectors"]:
            with self.subTest(vector=vector["id"]):
                node = self.schema["$defs"][vector["schema"]]
                self.assertTrue(matches(vector["input"], node, self.schema, self.schema, self.ai_schema))

    def test_negative_schema_vectors_fail_closed(self):
        for vector in self.fixture["negativeVectors"]:
            with self.subTest(vector=vector["id"]):
                node = self.schema["$defs"][vector["schema"]]
                candidate = copy.deepcopy(vector["input"])
                if "repeatItems" in vector:
                    candidate["targets"] = [candidate["targets"][0] for _ in range(vector["repeatItems"])]
                if "repeatVectorItems" in vector:
                    candidate["items"][0]["vector"] = [0.25 for _ in range(vector["repeatVectorItems"])]
                self.assertFalse(matches(candidate, node, self.schema, self.schema, self.ai_schema))

    def test_required_idempotency_and_fence_vectors_are_offline_only(self):
        self.assertEqual(self.fixture["evidenceClass"], "offline-contract-vectors-not-runtime-or-provider-evidence")
        self.assertEqual(self.fixture["transport"]["networkAccess"], "none")
        vectors = self.fixture["stateVectors"]
        self.assertEqual(len({row["id"] for row in vectors}), len(vectors))
        for vector in vectors:
            with self.subTest(vector=vector["id"]):
                self.assertFalse(vector["newExternalEffectPermitted"])
        expected = {
            "duplicate-dispatch-same-command",
            "conflicting-dispatch-command",
            "inference-lease-takeover",
            "r2-part-mismatch",
            "stale-inference-result",
            "worker-delete-page-replay",
            "service-object-grant-binds-stable-owner-fence",
            "service-object-grant-expires-before-owner-lease",
            "worker-object-facade-streams-only-bounded-authorized-bytes",
        }
        self.assertEqual({row["id"] for row in vectors}, expected)
        expiry = next(row for row in vectors if row["id"] == "service-object-grant-expires-before-owner-lease")
        self.assertEqual(expiry["maximumLifetimeSeconds"], 60)
        facade = next(row for row in vectors if row["id"] == "worker-object-facade-streams-only-bounded-authorized-bytes")
        self.assertEqual(facade["maximumPartBytes"], 8388608)

    def test_worker_object_facade_binds_path_identity_to_the_owner_grant(self):
        requests = [row["input"] for row in self.fixture["positiveVectors"] if row["schema"] == "WorkerObjectJobRequest"]
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(request["grantId"], request["grant"]["grantId"])
            self.assertEqual(request["grant"]["direction"], {"GET": "read", "PUT": "write"}[request["method"]])
            if request["method"] == "PUT":
                self.assertLessEqual(request["declaredLength"], 8388608)


if __name__ == "__main__":
    unittest.main()
