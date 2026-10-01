# SPDX-License-Identifier: Apache-2.0
"""Offline shape and guard-oracle tests for the private D1 ExecutePlan schema (CON.15).

The guard oracle below is an independent reference model of the data-model/04 section 3
admission order. It is not the Cloud.Storage.D1 implementation, a Worker handler or a D1 run.
"""
import copy
from datetime import datetime, timezone
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
D1_OUTCOMES = {
    "constraintViolation": "constraint",
    "overloaded": "overloaded",
    "timeout": "unknownOutcome",
}


def matches(value, node, definitions):
    if "$ref" in node:
        reference = node["$ref"]
        if not reference.startswith("#/$defs/"):
            return False
        target = definitions.get(reference.removeprefix("#/$defs/"))
        return target is not None and matches(value, target, definitions)
    if "oneOf" in node:
        return sum(matches(value, branch, definitions) for branch in node["oneOf"]) == 1 and encoded_within(value, node)

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
        if "pattern" in node and re.fullmatch(node["pattern"], value) is None:
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
    return encoded_within(value, node)


def encoded_within(value, node):
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
            parent[key] = copy.deepcopy(operation["value"])
        elif operation["op"] == "remove":
            del parent[key]
        elif operation["op"] == "fill":
            parent[key] = [copy.deepcopy(operation["value"]) for _ in range(operation["count"])]
        else:
            raise AssertionError(f"unknown fixture operation {operation['op']}")
    return candidate


def instant(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def classify(request, registry, context, d1_outcome=None):
    """Admission order of the private named-plan bridge; every refusal precedes any D1 effect."""
    refused = {"outcome": "refuse-before-plan-execution", "effects": False}
    if not context["trustedContainer"] or context["publicRoute"]:
        return refused
    plan = registry.get((request["planId"], request["planVersion"]))
    if plan is None or not plan["workerSupported"] or plan["manifestHash"] != request["manifestHash"]:
        return {"outcome": "invalidPlan", "effects": False}
    if [len(statement) for statement in request["arguments"]] != plan["statementParameterCounts"]:
        return {"outcome": "invalidPlan", "effects": False}
    if request["recoveryGeneration"] != context["activeRecoveryGeneration"]:
        return {"outcome": "staleGeneration", "effects": False}
    if instant(request["deadlineUtc"]) <= instant(context["nowUtc"]):
        return {"outcome": "unavailable", "effects": False}
    if request["ownerScope"] != context["currentOwnerScope"]:
        return {"outcome": "precondition", "effects": False}
    if d1_outcome is None:
        return {"outcome": "admitted", "effects": False}
    outcome = D1_OUTCOMES[d1_outcome]
    if outcome == "unknownOutcome":
        # A timeout after submission can never be treated as safe to repeat with a new command.
        return {"outcome": outcome, "effects": "unknown", "retryWithSameRequestId": True}
    return {"outcome": outcome, "effects": False}


class Con15D1ExecutePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.definitions = cls.schema["$defs"]
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.positive = {row["id"]: row for row in cls.fixture["positiveVectors"]}

    def check(self, value, root):
        return matches(value, self.definitions[root], self.definitions)

    def test_positive_schema_vectors_are_closed_and_bounded(self):
        self.assertEqual({row["schema"] for row in self.positive.values()}, {"ExecutePlanRequest", "ExecutePlanResponse"})
        for vector in self.positive.values():
            with self.subTest(vector=vector["id"]):
                self.assertTrue(self.check(vector["input"], vector["schema"]))

    def test_negative_schema_vectors_fail_closed_after_a_single_mutation_of_a_valid_base(self):
        ids = [row["id"] for row in self.fixture["negativeVectors"]]
        self.assertEqual(len(ids), len(set(ids)))
        for vector in self.fixture["negativeVectors"]:
            with self.subTest(vector=vector["id"]):
                base = self.positive[vector["base"]]
                self.assertEqual(base["schema"], vector["schema"])
                candidate = apply_operations(base["input"], vector["operations"])
                self.assertNotEqual(candidate, base["input"])
                self.assertFalse(self.check(candidate, vector["schema"]))

    def test_private_protocol_has_only_the_named_plan_boundary(self):
        request = self.definitions["ExecutePlanRequest"]
        self.assertEqual(set(request["properties"]), {
            "planId", "planVersion", "manifestHash", "requestId", "recoveryGeneration",
            "ownerScope", "arguments", "deadlineUtc",
        })
        self.assertIs(request["additionalProperties"], False)
        self.assertEqual(request["x-arcforges-max-bytes"], 262144)
        self.assertEqual(self.definitions["ExecutePlanResponse"]["x-arcforges-max-bytes"], 262144)
        self.assertEqual(request["properties"]["arguments"], {"$ref": "#/$defs/PlanArguments"})
        self.assertEqual(self.definitions["PlanArguments"]["maxItems"], 100)
        self.assertEqual(self.definitions["PlanArguments"]["items"]["maxItems"], 100)
        scalar = self.definitions["D1Scalar"]
        kinds = {
            self.definitions[branch["$ref"].removeprefix("#/$defs/")]["properties"]["kind"]["const"]
            for branch in scalar["oneOf"]
        }
        self.assertEqual(kinds, {"null", "boolean", "int64", "uint64", "decimal", "text", "bytes"})
        for forbidden in ("sql", "statement", "tableName", "table", "query", "operation"):
            self.assertNotIn(forbidden, request["properties"])
        self.assertIn("server-side checks", self.fixture["encoding"]["ownerScope"])

    def test_every_schema_object_is_closed_and_has_no_remote_reference(self):
        for name, node in self.definitions.items():
            if node.get("type") == "object":
                with self.subTest(definition=name):
                    self.assertIs(node.get("additionalProperties"), False)
        self.assertNotIn('"$ref": "http', json.dumps(self.schema))
        self.assertTrue(all(ref.startswith("#/$defs/") for ref in re.findall(r'"\$ref": "([^"]+)"', json.dumps(self.schema))))

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

    def test_failure_vocabulary_matches_the_guard_oracle(self):
        failure = self.definitions["ExecutePlanFailure"]["properties"]["failure"]["enum"]
        self.assertEqual(set(failure), FAILURES)
        registry = {
            (row["planId"], row["planVersion"]): row for row in self.fixture["planRegistry"]
        }
        context = self.fixture["guardContext"]
        base = self.positive["execute-plan-typed-parameters"]["input"]
        produced = set()
        for vector in self.fixture["guardAndErrorVectors"]:
            request = copy.deepcopy(base)
            request.update(copy.deepcopy(vector["patch"]))
            produced.add(classify(request, registry, {**context, **vector.get("context", {})}, vector.get("d1Outcome"))["outcome"])
        self.assertEqual(produced & FAILURES, FAILURES)
        self.assertEqual(produced - FAILURES, {"admitted", "refuse-before-plan-execution"})

    def test_guard_and_error_vectors_follow_the_independent_oracle(self):
        vectors = self.fixture["guardAndErrorVectors"]
        self.assertEqual(len({row["id"] for row in vectors}), len(vectors))
        registry = {
            (row["planId"], row["planVersion"]): row for row in self.fixture["planRegistry"]
        }
        context = self.fixture["guardContext"]
        base = self.positive["execute-plan-typed-parameters"]["input"]
        for vector in vectors:
            with self.subTest(vector=vector["id"]):
                request = copy.deepcopy(base)
                request.update(copy.deepcopy(vector["patch"]))
                effective = {**context, **vector.get("context", {})}
                actual = classify(request, registry, effective, vector.get("d1Outcome"))
                self.assertEqual(actual, vector["expected"])
                if vector["expected"]["outcome"] in FAILURES:
                    # Typed failures are representable replies; the request still names its manifest.
                    reply = {"requestId": request["requestId"], "manifestHash": request["manifestHash"],
                             "failure": vector["expected"]["outcome"]}
                    self.assertTrue(self.check(reply, "ExecutePlanResponse"))
        ambiguous = next(row for row in vectors if row["id"] == "ambiguous-timeout-remains-unknown")
        self.assertEqual(ambiguous["expected"]["effects"], "unknown")
        self.assertIs(ambiguous["expected"]["retryWithSameRequestId"], True)

    def test_maximum_width_values_and_text_encoding_are_exact(self):
        request = self.positive["execute-plan-typed-parameters"]["input"]
        values = request["arguments"]
        self.assertEqual(values[0][1], {"kind": "uint64", "value": "18446744073709551615"})
        self.assertEqual(values[1][0], {"kind": "bytes", "value": "AQID_w"})
        self.assertEqual(json.loads(values[1][1]["value"]), {"active": True, "count": 2})
        reply = self.positive["execute-plan-tagged-result-scalars"]["input"]
        self.assertEqual(reply["rows"][0][0], {"kind": "int64", "value": "-9223372036854775808"})
        self.assertEqual(reply["rows"][0][1], {"kind": "decimal", "value": "12345678901234567890.125"})
        everything = self.positive["execute-plan-every-scalar-kind"]["input"]["arguments"][0]
        self.assertEqual({row["kind"] for row in everything},
                         {"null", "boolean", "int64", "uint64", "decimal", "text", "bytes"})


if __name__ == "__main__":
    unittest.main()
