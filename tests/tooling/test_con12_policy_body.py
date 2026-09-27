# SPDX-License-Identifier: Apache-2.0
"""Independent policy.body.v1 shape/static vectors, never signature or activation evidence."""
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]

def shape(value, node, schema):
    if "$ref" in node:
        return shape(value, schema["$defs"][node["$ref"].split("/")[-1]], schema)
    if "oneOf" in node:
        return sum(shape(value, branch, schema) for branch in node["oneOf"]) == 1
    kind = node.get("type")
    if kind == "object":
        if not isinstance(value, dict) or not set(node["required"]).issubset(value) or set(value) - set(node["properties"]): return False
        if not all(shape(v, node["properties"][k], schema) for k, v in value.items()): return False
    elif kind == "array":
        if not isinstance(value, list) or not node.get("minItems", 0) <= len(value) <= node["maxItems"]: return False
        if not all(shape(item, node["items"], schema) for item in value): return False
    elif kind == "string":
        if not isinstance(value, str) or not node.get("minLength", 0) <= len(value) <= node.get("maxLength", 1000000): return False
        if "pattern" in node and re.fullmatch(node["pattern"], value) is None: return False
        if "nonzeroUuid" in node.get("x-arcforges-rules", []) and value == "00000000-0000-0000-0000-000000000000": return False
        if "uint64String" in node.get("x-arcforges-rules", []) and int(value) > 2**64-1: return False
    elif kind == "integer":
        if type(value) is not int or not node["minimum"] <= value <= node["maximum"]: return False
    elif kind == "boolean":
        if type(value) is not bool: return False
    if "const" in node and value != node["const"]: return False
    if "enum" in node and value not in node["enum"]: return False
    return True

def static_rules(body):
    """Independent normative algorithm mirrored by generated C#/TS policyBody hooks.

    Disjoint time windows or different stable-ID targets cannot overlap. Predicate
    overlap is conservative: a same-key/scope/priority ambiguity refuses admission.
    Group ranges are allocated by ordinal experiment ID and must fit one bucket.
    Salt is version-bound by the namespace supplied to the separate bucket vector.
    """
    instant = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    def predicate(node, depth=1):
        if isinstance(node, str): return 0
        if depth > 8: raise ValueError("predicate-depth")
        if node["op"] in ("all", "any"):
            return 1 + sum(predicate(child, depth+1) for child in node["terms"])
        if node["op"] == "not": return 1 + predicate(node["term"], depth+1)
        if node.get("field") in ("realmId", "workspaceId", "userId", "installationId"):
            values = node["values"] if node["op"] == "in" else [node["value"]]
            if any(not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", x) or x == "00000000-0000-0000-0000-000000000000" for x in values):
                raise ValueError("predicate-id")
        return 1
    def check_predicate(node):
        if predicate(node) > 128: raise ValueError("predicate-nodes")
    try:
        issued, expires = instant(body["issuedAt"]), instant(body["expiresAt"])
        if not 0 < (expires-issued).total_seconds() <= 86400: return "bundle-window"
        seen, priorities = set(), []
        for rule in body["rules"]:
            if rule["ruleId"] in seen: return "duplicate-rule"
            seen.add(rule["ruleId"])
            start, end = instant(rule.get("effectiveAt", body["issuedAt"])), instant(rule.get("expiresAt", body["expiresAt"]))
            if not start < end: return "rule-window"
            check_predicate(rule["target"])
            for other in priorities:
                if (rule["key"], rule["scope"], rule["priority"]) == (other["key"], other["scope"], other["priority"]):
                    other_start = instant(other.get("effectiveAt", body["issuedAt"]))
                    other_end = instant(other.get("expiresAt", body["expiresAt"]))
                    if end <= other_start or other_end <= start: continue
                    disjoint = isinstance(rule["target"], str) and isinstance(other["target"], str) and rule["target"] != other["target"]
                    if not disjoint: return "overlapping-priority"
            priorities.append(rule)
            if rule["key"].endswith(".stop"):
                stop = rule["value"]
                if not 0 < (instant(stop["until"])-instant(stop["effectiveAt"])).total_seconds() <= 86400: return "stop-window"
            if rule["key"] == "client.minimumApp":
                if any(row["platform"] == "android" and "minimumVersionCode" not in row for row in rule["value"]): return "android-version-code"
        experiments, groups = set(), {}
        for experiment in body["experiments"]:
            if experiment["experimentId"] in experiments: return "duplicate-experiment"
            experiments.add(experiment["experimentId"])
            if not instant(experiment["startsAt"]) < instant(experiment["endsAt"]): return "experiment-window"
            check_predicate(experiment["eligibility"])
            variants = experiment["variants"]
            if len({v["variantId"] for v in variants}) != len(variants): return "duplicate-variant"
            if any(not variant["values"] for variant in variants): return "empty-variant"
            if sum(variant["allocation"] for variant in variants) != experiment["allocation"]: return "variant-allocation"
            total = experiment["allocation"] + experiment["holdoutBasisPoints"]
            if total > 10000: return "holdout-allocation"
            if "exclusionGroup" in experiment:
                group = experiment["exclusionGroup"]
                groups[group] = groups.get(group, 0) + total
                if groups[group] > 10000: return "exclusion-overlap"
    except ValueError as error:
        return str(error) if str(error).startswith("predicate-") else "timestamp"
    return "accepted"

def bucket(components):
    encoded = b"".join(len(value.encode()).to_bytes(4, "big") + value.encode() for value in components)
    digest = hashlib.sha256(encoded).digest()
    return encoded.hex(), digest.hex(), int.from_bytes(digest[:8], "big") % 10000

class PolicyBodyVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "public/http/v1/policy-body.schema.json").read_text(encoding="utf-8"))
        fixture_path = ROOT / "fixtures/public/con-12-extension-policy.json"
        # The owner folds these independently authored cases into the shared fixture.
        cls.fixture = json.loads(fixture_path.read_text(encoding="utf-8"))["policyBody"]

    def test_independent_policy_vectors(self):
        for case in self.fixture["cases"]:
            body = copy.deepcopy(self.fixture["base"])
            for mutation in case.get("mutations", []):
                target = body
                for part in mutation["path"][:-1]: target = target[part]
                if mutation.get("remove"): del target[mutation["path"][-1]]
                else: target[mutation["path"][-1]] = mutation["value"]
            for recipe in case.get("recipes", []):
                if recipe["kind"] == "nested-not":
                    node = {"op": "equal", "field": "product", "value": "arcscope"}
                    for _ in range(recipe["count"]): node = {"op": "not", "term": node}
                    body["rules"][0]["target"] = node
                elif recipe["kind"] == "wide-predicate":
                    leaf = {"op": "equal", "field": "product", "value": "arcscope"}
                    body["rules"][0]["target"] = {"op": "all", "terms": [{"op":"any", "terms":[leaf]*64}]*2}
            valid = shape(body, self.schema, self.schema)
            actual = static_rules(body) if valid else "shape"
            with self.subTest(case=case["id"]): self.assertEqual(actual, case["expected"])

    def test_independent_length_prefixed_hashes(self):
        for row in self.fixture["hashVectors"]:
            encoded, digest, result = bucket(row["components"])
            self.assertEqual((encoded, digest, result), (row["encodedHex"], row["sha256"], row["bucket"]))
            self.assertFalse(result < 0)
            self.assertTrue(result < 10000)
            for allocation in (0, 10000): self.assertEqual(result < allocation, allocation == 10000)

if __name__ == "__main__": unittest.main()






