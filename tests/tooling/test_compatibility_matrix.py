# SPDX-License-Identifier: Apache-2.0
"""Deliberate compiled-descriptor breaks must fail before publication."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from check_compatibility import (compare, con08_frozen_errors, descriptor, fields,
                                 frozen_file_projection, retained)
ROOT = Path(__file__).resolve().parents[2]


CON08_METHODS = {
    "entitlement.getSnapshot": ("EntitlementService", "GetSnapshot"),
    "entitlement.getServiceTerm": ("EntitlementService", "GetServiceTerm"),
    "entitlement.getCapacity": ("EntitlementService", "GetCapacity"),
    "entitlement.listGrants": ("EntitlementService", "ListGrants"),
    "entitlement.getUsage": ("EntitlementService", "GetUsage"),
    "entitlement.check": ("EntitlementService", "Check"),
    "commerce.authoriseExtraUsage": ("CommerceService", "AuthoriseExtraUsage"),
    "commerce.revokeExtraUsage": ("CommerceService", "RevokeExtraUsage"),
    "commerce.explainCharge": ("CommerceService", "ExplainCharge"),
    "commerce.getCatalogue": ("CommerceService", "GetCatalogue"),
    "commerce.createPurchaseIntent": ("CommerceService", "CreatePurchaseIntent"),
    "commerce.createCheckoutAttempt": ("CommerceService", "CreateCheckoutAttempt"),
    "commerce.getPurchaseState": ("CommerceService", "GetPurchaseState"),
    "commerce.getSubscription": ("CommerceService", "GetSubscription"),
    "commerce.cancelSubscription": ("CommerceService", "CancelSubscription"),
    "commerce.reactivateSubscription": ("CommerceService", "ReactivateSubscription"),
    "commerce.getCredits": ("CommerceService", "GetCredits"),
    "commerce.listBillingHistory": ("CommerceService", "ListBillingHistory"),
    "commerce.requestRefund": ("CommerceService", "RequestRefund"),
    "commerce.exportEvidence": ("CommerceService", "ExportEvidence"),
}
CON08_ERROR_ROWS = {
    "entitlement.no_service_term", "entitlement.not_entitled", "entitlement.quota_exceeded",
    "entitlement.capacity_exhausted", "entitlement.extra_credits_required", "entitlement.credits_exhausted",
    "entitlement.request_too_large", "commerce.supplier_budget_exhausted",
}


def consume_exactly_once(vectors, expected_ids):
    seen = set()
    for vector in vectors:
        vector_id = vector.get("id")
        if vector_id not in expected_ids:
            raise ValueError(f"unknown vector: {vector_id}")
        if vector_id in seen:
            raise ValueError(f"duplicate vector: {vector_id}")
        seen.add(vector_id)
    missing = expected_ids - seen
    if missing:
        raise ValueError(f"unconsumed vectors: {', '.join(sorted(missing))}")
    return seen


def file_model_from_projection(projection):
    return {
        "package": projection["package"],
        "messages": {
            name: {field["tag"]: {key: value for key, value in field.items() if key != "tag"}
                   for field in fields}
            for name, fields in projection["messages"].items()
        },
        "enums": {
            name: {member["name"]: member["number"] for member in members}
            for name, members in projection["enums"].items()
        },
        "services": projection["services"],
    }


def integer(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def member(tag, value):
    if isinstance(value, int):
        return integer(tag << 3) + integer(value)
    if isinstance(value, str):
        value = value.encode("utf-8")
    return integer((tag << 3) | 2) + integer(len(value)) + value


def compiled():
    # Exact FileDescriptorSet / FileDescriptorProto field numbers, independent
    # of the production reader. One message, enum and unary method suffice to
    # exercise each immutable element, including int64 versus uint64.
    field = b"".join(member(k, v) for k, v in [(1, "revision"), (3, 1), (4, 1), (5, 3), (10, "revision")])
    message = member(1, "Request") + member(2, field)
    enum = member(1, "State") + member(2, member(1, "UNKNOWN") + member(2, 0))
    method = member(1, "Read") + member(2, ".fixture.Request") + member(3, ".fixture.Request")
    service = member(1, "Api") + member(2, method)
    file = member(1, "fixture.proto") + member(2, "fixture") + member(4, message) + member(5, enum) + member(6, service)
    return member(1, file)


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.old = descriptor(compiled())
        self.new = deepcopy(self.old)

    def test_identical_descriptors(self):
        self.assertEqual(compare(self.old, self.new), [])

    def test_additive_response_field_and_method(self):
        self.new["messages"][".fixture.Request"][2] = {"name": "added"}
        self.new["services"][".fixture.Api"]["NewMethod"] = {"input": ".fixture.Request"}
        self.assertEqual(compare(self.old, self.new), [])

    def test_deletion_refused(self):
        del self.new["messages"][".fixture.Request"][1]
        self.assertIn("deleted member", compare(self.old, self.new)[0])

    def test_reuse_and_exact_type_presence_changes_refused(self):
        for key, replacement in [("name", "other"), ("type", 4), ("label", 3),
                                 ("oneof", "new_group"), ("optional", 1),
                                 ("typeName", ".different.Message"), ("jsonName", "other")]:
            with self.subTest(key=key):
                current = deepcopy(self.old)
                current["messages"][".fixture.Request"][1][key] = replacement
                self.assertTrue(compare(self.old, current))

    def test_enum_number_and_rpc_streaming_changes_refused(self):
        self.new["enums"][".fixture.State"]["UNKNOWN"] = 1
        self.new["services"][".fixture.Api"]["Read"]["serverStreaming"] = 1
        self.assertEqual(len(compare(self.old, self.new)), 2)

    def test_removed_message_enum_service_refused(self):
        for kind in self.new:
            self.new[kind].clear()
        self.assertEqual(len(compare(self.old, self.new)), 3)

    def test_unknown_descriptor_metadata_is_ignored(self):
        self.assertEqual(descriptor(compiled() + member(100, b"future")), self.old)

    def test_malformed_descriptor_refused(self):
        for raw in [b"", b"\x00", b"\x0a\x7fshort", b"\x08" + b"\xff" * 10,
                    compiled()[:-1], compiled() + compiled()]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    descriptor(raw)

    def test_fixed_width_truncation(self):
        for raw in [b"\x09abc", b"\x0dabc"]:
            with self.assertRaises(ValueError):
                fields(raw)

    def test_con08_fixture_vectors_are_direct_and_exactly_once(self):
        fixture_path = ROOT / "fixtures/public/con-08-entitlement-commerce.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schemaVersion"], "con-08-entitlement-commerce.v1")
        projection = fixture["frozenDescriptor"]["projection"]
        positive = fixture["positiveVectors"]
        self.assertEqual(consume_exactly_once(positive, set(CON08_METHODS)), set(CON08_METHODS))
        errors = fixture["errorRowVectors"]
        self.assertEqual(consume_exactly_once(errors, CON08_ERROR_ROWS), CON08_ERROR_ROWS)

        for vector in positive:
            expected_service, expected_method = CON08_METHODS[vector["operationId"]]
            self.assertEqual((vector["service"], vector["method"]),
                             (f".arcforges.publicapi.v1.{expected_service}", expected_method))
            method = projection["services"][vector["service"]][vector["method"]]
            self.assertEqual(method["input"], vector["requestType"])
            self.assertEqual(method["output"], vector["responseType"])
            self.assertIn(vector["requestType"], projection["messages"])
            self.assertIn(vector["responseType"], projection["messages"])
            response = projection["messages"][vector["responseType"]]
            value = next(field for field in response if field["name"] == vector["successVariant"])
            self.assertEqual(value["typeName"], vector["valueType"])
            self.assertEqual(value["oneof"], "outcome")

        for vector in errors:
            self.assertEqual(vector["code"], vector["id"])
            self.assertEqual(vector["category"], "entitlement")
            self.assertEqual(vector["effectCertainty"], "Did not happen")
            self.assertTrue(vector["retryDisposition"])

    def test_con08_fixture_missing_duplicate_and_unknown_vectors_fail_closed(self):
        expected = set(CON08_METHODS)
        sample = {"id": "entitlement.getSnapshot"}
        with self.assertRaisesRegex(ValueError, "unconsumed"):
            consume_exactly_once([sample], expected)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            consume_exactly_once([sample, sample], expected)
        with self.assertRaisesRegex(ValueError, "unknown"):
            consume_exactly_once([{"id": "invented.operation"}], expected)

    def test_con08_frozen_projection_gate_rejects_any_declaration_change(self):
        fixture = json.loads((ROOT / "fixtures/public/con-08-entitlement-commerce.json").read_text(encoding="utf-8"))
        lock = fixture["frozenDescriptor"]
        filename = lock["file"]
        original = {"files": {filename: file_model_from_projection(lock["projection"])}}
        self.assertEqual(frozen_file_projection(original["files"][filename]), lock["projection"])
        self.assertEqual(con08_frozen_errors(ROOT, original), [])

        mutations = []
        added_field = deepcopy(original)
        message = next(iter(added_field["files"][filename]["messages"].values()))
        message[999] = {"name": "future", "type": 9, "typeName": "", "label": 1,
                        "oneof": None, "optional": 0, "jsonName": "future"}
        mutations.append(added_field)
        removed_method = deepcopy(original)
        service = next(iter(removed_method["files"][filename]["services"].values()))
        del service[next(iter(service))]
        mutations.append(removed_method)
        added_message = deepcopy(original)
        added_message["files"][filename]["messages"][".arcforges.publicapi.v1.Future"] = {}
        mutations.append(added_message)
        for current in mutations:
            with self.subTest(current=current):
                self.assertEqual(len(con08_frozen_errors(ROOT, current)), 1)

    def test_retirement_is_exact_and_does_not_waive_other_namespaces(self):
        model = deepcopy(self.old)
        model["messages"][".arcforges.foundation.v1.Request"] = deepcopy(model["messages"][".fixture.Request"])
        result = retained(model, {"messages": ["Request"]})
        self.assertNotIn(".arcforges.foundation.v1.Request", result["messages"])
        self.assertIn(".fixture.Request", result["messages"])
        self.assertIn(".arcforges.foundation.v1.Request", model["messages"])
        result = retained(model, {"fields": {"Request": [{"name": "other", "tag": 1}]}})
        self.assertIn(1, result["messages"][".arcforges.foundation.v1.Request"])
        result = retained(model, {"fields": {"Request": [{"name": "revision", "tag": 1}]}})
        self.assertNotIn(1, result["messages"][".arcforges.foundation.v1.Request"])
        self.assertIn(1, result["messages"][".fixture.Request"])


if __name__ == "__main__":
    unittest.main()
