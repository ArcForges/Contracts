# SPDX-License-Identifier: Apache-2.0
"""Offline shape and guard-oracle tests for the private D1 ExecutePlan schema."""
import copy
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "internal/storage-http/v1/schema.json"
FIXTURE_PATH = ROOT / "fixtures/internal/con-15-d1-execute-plan.json"
FAILURES = {
    "invalidPlan", "staleGeneration", "precondition", "constraint",
    "overloaded", "unavailable", "unknownOutcome",
}


def matches(value, node, definitions):
    if "$ref" in node:
        reference = node["$ref"]
        if not reference.startswith("#/$defs/"):
            return False
        target = definitions.get(reference.removeprefix("#/$defs/"))
        return target is not None and matches(value, target, definitions)
    if "oneOf" in node:
        return sum(matches(value, branch, definitions) for branch in node["oneOf"]) == 1

    kind = node.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        properties = node.get("properties", {})
        if not set(node.get("required", [])).issubset(value):
            return False
        if node.get("additionalProperties") is False and set(value) - set(properties):
            return False
        for name, child in properties.items():
            if name in value and not matches(value[name], child, definitions):
                return False
    elif kind == "array":
        if not isinstance(value, list):
            return False
        if len(value) < node.get("minItems", 0) or len(value) > node.get("maxItems", 10**9):
            return False
        if not all(matches(item, node["items"], definitions) for item in value):
            return False
    elif kind == "string":
        if not isinstance(value, str):
            return False
        if len(value) < node.get("minLength", 0) or len(value) > node.get("maxLength", 10**9):
            return False
        if "pattern" in node and re.search(node["pattern"], value) is None:
            return False
    elif kind == "integer":
        if type(value) is not int:
            return False
        if value < node.get("minimum", -(10**100)) or value > node.get("maximum", 10**100):
            return False
    elif kind == "boolean":
        if type(value) is not bool:
            return False
    elif kind is not None:
        return False

    if "const" in node and value != node["const"]:
        return False
    if "enum" in node and value not in node["enum"]:
        return False
    if "not" in node and matches(value, node["not"], definitions):
        return False
    for rule in node.get("x-arcforges-rules", []):
        if rule == "nonzeroUuid" and value == "00000000-0000-0000-0000-000000000000":
            return False
        if rule == "uint64String" and (not value.isdecimal() or int(value) > 2**64 - 1):
            return False
        if rule == "int64" and (not re.fullmatch(r"-?(0|[1-9][0-9]*)", value) or not -(2**63) <= int(value) < 2**63):
            return False
        if rule == "canonicalDecimal":
            if not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]{1,9})?", value):
                return False
            if value == "-0" or ("." in value and value.endswith("0")):
                return False
            if len(value.replace("-", "").replace(".", "").lstrip("0")) > 28:
                return False
    return True


def encoded_within(value, node):
    limit = node.get("x-arcforges-max-bytes")
    return limit is None or len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= limit


class Con15D1ExecutePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.definitions = cls.schema["$defs"]
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.positive = cls.fixture["positiveVectors"]
        cls.negative = cls.fixture["negativeVectors"]

    def test_positive_schema_vectors_are_closed_and_bounded(self):
        for vector in self.positive:
            with self.subTest(vector=vector["id"]):
                root = self.definitions[vector["schema"]]
                self.assertTrue(matches(vector["input"], root, self.definitions))
                self.assertTrue(encoded_within(vector["input"], root))

    def test_negative_schema_vectors_fail_closed(self):
        request = copy.deepcopy(self.positive[0]["input"])
        success = copy.deepcopy(self.positive[1]["input"])
        bases = {"ExecutePlanRequest": request, "ExecutePlanResponse": success}
        for vector in self.negative:
            with self.subTest(vector=vector["id"]):
                candidate = copy.deepcopy(bases[vector["schema"]])
                patch = vector.get("patch", {})
                if vector["id"] == "request-rejects-101-statements":
                    patch = {"arguments": [[] for _ in range(101)]}
                elif vector["id"] == "request-rejects-101-parameters-per-statement":
                    patch = {"arguments": [[{"kind": "null"} for _ in range(101)]]}
                elif vector["id"] == "request-rejects-oversized-owner-scope":
                    patch = {"ownerScope": "x" * 257}
                for name in vector.get("remove", []):
                    candidate.pop(name, None)
                candidate.update(patch)
                root = self.definitions[vector["schema"]]
                self.assertFalse(matches(candidate, root, self.definitions))

    def test_private_protocol_has_only_the_named_plan_boundary(self):
        request = self.definitions["ExecutePlanRequest"]
        self.assertEqual(set(request["properties"]), {
            "planId", "planVersion", "manifestHash", "requestId", "recoveryGeneration",
            "ownerScope", "arguments", "deadlineUtc",
        })
        self.assertIs(request["additionalProperties"], False)
        scalar = self.definitions["D1Scalar"]
        kinds = {
            self.definitions[branch["$ref"].removeprefix("#/$defs/")]["properties"]["kind"]["const"]
            for branch in scalar["oneOf"]
        }
        self.assertEqual(kinds, {"null", "boolean", "int64", "uint64", "decimal", "text", "bytes"})
        self.assertNotIn("sql", request["properties"])
        self.assertNotIn("tableName", request["properties"])
        self.assertIn("server-side checks", self.fixture["encoding"]["ownerScope"])

    def test_d1_schema_compiles_with_the_pinned_shape_generator_without_writes(self):
        eng = str(ROOT / "eng")
        if eng not in sys.path:
            sys.path.insert(0, eng)
        from generate_shapes import bundle_external_models, compile_bundle_roots

        roots, compilers, owners = compile_bundle_roots(
            self.schema, "ArcForges.Contracts.CloudInternal.Storage.V1")
        self.assertEqual([root["title"] for root in roots], ["ExecutePlanRequest", "ExecutePlanResponse"])
        generated = [compiler.generate(bundle_external_models(index, compiler, owners))
                     for index, compiler in enumerate(compilers)]
        self.assertEqual(len(generated), 2)
        self.assertIn("ExecutePlanRequestJsonContext", generated[0][0])
        self.assertIn("ExecutePlanResponseJsonContext", generated[1][0])

    def test_failure_vocabulary_and_guard_vectors_are_bounded(self):
        failure = self.definitions["ExecutePlanFailure"]["properties"]["failure"]["enum"]
        self.assertEqual(set(failure), FAILURES)
        vectors = self.fixture["guardAndErrorVectors"]
        self.assertEqual(len({row["id"] for row in vectors}), len(vectors))
        for vector in vectors:
            with self.subTest(vector=vector["id"]):
                if vector["outcome"] in FAILURES:
                    self.assertIn(vector["outcome"], FAILURES)
                self.assertFalse(vector.get("effects", False))
        ambiguous = next(row for row in vectors if row["id"] == "ambiguous-timeout-remains-unknown")
        self.assertEqual(ambiguous["outcome"], "unknownOutcome")
        self.assertEqual(ambiguous["input"]["requestId"], ambiguous["retryRequestId"])
        self.assertFalse(ambiguous["newEffectPermitted"])
        public = next(row for row in vectors if row["id"] == "untrusted-container-or-public-ingress-refused")
        self.assertEqual(public["outcome"], "refuse-before-plan-execution")
        self.assertFalse(public["effects"])

    def test_maximum_width_values_and_text_encoding_are_exact(self):
        request = self.positive[0]["input"]
        values = request["arguments"]
        self.assertEqual(values[0][1], {"kind": "uint64", "value": "18446744073709551615"})
        self.assertEqual(values[1][0], {"kind": "bytes", "value": "AQID_w"})
        self.assertEqual(json.loads(values[1][1]["value"]), {"active": True, "count": 2})
        reply = self.positive[1]["input"]
        self.assertEqual(reply["rows"][0][0], {"kind": "int64", "value": "-9223372036854775808"})
        self.assertEqual(reply["rows"][0][1], {"kind": "decimal", "value": "12345678901234567890.125"})


if __name__ == "__main__":
    unittest.main()
