# SPDX-License-Identifier: Apache-2.0
"""Deliberate compiled-descriptor breaks must fail before publication."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from check_compatibility import (CURRENT_TO_MINIMUM, INJECTED_UNKNOWN, LATER_REQUIRED_TASKS, LATER_WINDOW,
                                 PREVIOUS_TO_CURRENT, UNKNOWN, check_later_services, compare, con08_frozen_errors,
                                 decode_message, descriptor, emit_later_exchange, encode_field, encode_message,
                                 exchange, fields, frozen_file_projection, later_accounting_errors,
                                 later_compare_errors, later_exchange_errors, later_schema_errors, later_window,
                                 retained, synthesize, verify_later_exchange)
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

        changed_tag = deepcopy(original)
        message = next(iter(changed_tag["files"][filename]["messages"].values()))
        tag = next(iter(message))
        field = message.pop(tag)
        message[max(message, default=tag) + 1] = field
        mutations.append(changed_tag)

        changed_type = deepcopy(original)
        message = next(iter(changed_type["files"][filename]["messages"].values()))
        field = next(iter(message.values()))
        field["type"] = 9 if field["type"] != 9 else 4
        mutations.append(changed_type)

        changed_presence = deepcopy(original)
        messages = changed_presence["files"][filename]["messages"]
        presence_field = next(
            field for fields in messages.values() for field in fields.values()
            if field["oneof"] is not None
        )
        presence_field["oneof"] = "_changed_presence"
        mutations.append(changed_presence)

        changed_optional_presence = deepcopy(original)
        messages = changed_optional_presence["files"][filename]["messages"]
        optional_field = next(
            field for fields in messages.values() for field in fields.values()
            if field["optional"] == 1
        )
        optional_field["optional"] = 0
        mutations.append(changed_optional_presence)

        added_method = deepcopy(original)
        service = next(iter(added_method["files"][filename]["services"].values()))
        service["UnreviewedMethod"] = {
            "input": ".arcforges.publicapi.v1.AttemptCharge",
            "output": ".arcforges.publicapi.v1.AttemptCharge",
            "clientStreaming": 0,
            "serverStreaming": 0,
        }
        mutations.append(added_method)

        removed_method = deepcopy(original)
        service = next(iter(removed_method["files"][filename]["services"].values()))
        del service[next(iter(service))]
        mutations.append(removed_method)

        deleted_message = deepcopy(original)
        messages = deleted_message["files"][filename]["messages"]
        del messages[next(iter(messages))]
        mutations.append(deleted_message)

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


LATER = json.loads((ROOT / LATER_WINDOW).read_text(encoding="utf-8"))
PINNED_PATH = ROOT / LATER["descriptor"]["previousAndMinimum"]
PINNED = descriptor(PINNED_PATH.read_bytes())
PUBLIC = "arcforges.publicapi.v1."
# Independent expectations taken from the reviewed ledger records of CON.07-CON.14, not from the window.
LATER_SERVICES = {
    "CON.07": {PUBLIC + "IdentityService": 32, PUBLIC + "WorkspaceService": 7, PUBLIC + "DeviceService": 10},
    "CON.08": {PUBLIC + "EntitlementService": 6, PUBLIC + "CommerceService": 14},
    "CON.09": {PUBLIC + "SyncService": 10, PUBLIC + "ResourceService": 7, PUBLIC + "TransferService": 6},
    "CON.10": {PUBLIC + "AgentService": 7, PUBLIC + "ApprovalService": 2, PUBLIC + "AutomationService": 9,
               PUBLIC + "BridgeService": 3, PUBLIC + "ChatService": 21, PUBLIC + "SearchService": 1,
               PUBLIC + "SourceService": 5, PUBLIC + "TaskService": 9},
    "CON.11": {PUBLIC + "ApplicationService": 3, PUBLIC + "HistoryService": 4, "arcforges.events.v1.EventService": 2,
               "arcforges.events.v1.ExecutionService": 5, "arcforges.cf.v1.RunStreamService": 1},
    "CON.13": {"arcforges.catalog.v1.CatalogService": 7},
    "CON.14": {"arcforges.operator.v1.OperatorService": 31},
}
LATER_SCHEMAS = {
    "CON.07": {"public/http/v1/browser.schema.json", "public/http/v1/native-auth.schema.json"},
    "CON.10": {"internal/ai-http/v1/schema.json"},
    "CON.12": {"public/http/v1/manifest.schema.json", "public/http/v1/workflow.schema.json",
               "public/http/v1/panel.schema.json", "public/http/v1/policy-body.schema.json",
               "internal/ai-http/v1/configuration.schema.json"},
    "CON.15": {"internal/cf-http/v1/schema.json", "internal/storage-http/v1/schema.json"},
    "CON.16": {"public/http/v1/signed-formats.schema.json"},
}
# Changing the declared type changes the meaning of the written sample value on the wire.
MEANING_CHANGES = {3: 18, 4: 3, 5: 17, 9: 12, 12: 9, 13: 17}
NEW_FIELD = {"name": "future", "type": 9, "typeName": "", "label": 1, "oneof": None, "optional": 0, "jsonName": "future"}


def later_rows(task):
    return [row for row in LATER["domains"] if task in row["tasks"]]


class Target:
    """One published message, field, service, method and enum of a domain, found in the pinned descriptor."""

    def __init__(self, task):
        files = [entry for row in later_rows(task) for entry in row["files"]]
        owned = {name for entry in files for name in PINNED["files"][entry["file"]]["messages"]}
        for name in sorted(owned):
            fields = PINNED["messages"][name]
            tags = [tag for tag, field in sorted(fields.items()) if field["type"] in MEANING_CHANGES]
            if tags:
                self.message, self.tag = name, tags[0]
                break
        else:
            raise AssertionError("No mutable message in " + task)
        service = next(name for entry in files for name in sorted(PINNED["files"][entry["file"]]["services"]))
        self.service, self.method = service, sorted(PINNED["services"][service])[0]
        self.enum = next(name for entry in files for name in sorted(PINNED["files"][entry["file"]]["enums"]))
        self.member = sorted(PINNED["enums"][self.enum])[0]
        self.task = task


MUTATIONS = {
    "deleted method": (lambda m, t: m["services"][t.service].pop(t.method), "deleted member"),
    "deleted service": (lambda m, t: m["services"].pop(t.service), "deleted definition"),
    "deleted message": (lambda m, t: m["messages"].pop(t.message), "deleted definition"),
    "deleted field": (lambda m, t: m["messages"][t.message].pop(t.tag), "deleted member"),
    "reused tag": (lambda m, t: m["messages"][t.message][t.tag].update(name="reused"), "changed member or reused tag"),
    "type change": (lambda m, t: m["messages"][t.message][t.tag].update(type=MEANING_CHANGES[m["messages"][t.message][t.tag]["type"]]),
                    "changed member or reused tag"),
    "presence change": (lambda m, t: m["messages"][t.message][t.tag].update(optional=1 - m["messages"][t.message][t.tag]["optional"]),
                        "changed member or reused tag"),
    "oneof change": (lambda m, t: m["messages"][t.message][t.tag].update(oneof="moved"), "changed member or reused tag"),
    "enum number change": (lambda m, t: m["enums"][t.enum].update({t.member: 12345}), "changed member or reused tag"),
    "streaming change": (lambda m, t: m["services"][t.service][t.method].update(serverStreaming=1), "changed member or reused tag"),
}
# Mutations that change what a written value means or loses it; the reference codecs must reject these too.
EXCHANGE_REJECTED = ["deleted message", "deleted field", "type change"]


def one_field_model(kind, label=1, tag=1):
    field = b"".join(member(key, value) for key, value in [(1, "value"), (3, tag), (4, label), (5, kind), (10, "value")])
    message = member(1, "M") + member(2, field)
    return descriptor(member(1, member(1, "fixture.proto") + member(2, "fixture") + member(4, message)))


class LaterServiceMatrixTests(unittest.TestCase):
    def window_in(self, directory, mutate=None):
        root = Path(directory)
        (root / "eng/compatibility").mkdir(parents=True, exist_ok=True)
        data = deepcopy(LATER)
        if mutate:
            mutate(data)
        (root / LATER_WINDOW).write_text(json.dumps(data), encoding="utf-8")
        return root, data

    def test_window_record_binds_the_published_candidate_and_the_pinned_descriptor(self):
        window = later_window(ROOT)
        self.assertEqual(window["candidate"], {
            "version": "1.0.0-ci.287.1", "sourceCommit": "ca45f36cccbdd31380f76b8f6cdecc958fdcb430",
            "publication": "https://github.com/ArcForges/Contracts/actions/runs/36966686225",
            "retainedArchive": {"artifactId": 11210775779, "name": "contracts-candidate-36966686225-1",
                                "sha256": "96fdd28556d0e753f54c4b7245398382a029bcbd58684a49954f339eaa71d425"}})
        self.assertEqual((window["previousVersion"], window["minimumVersion"]), ("1.0.0-ci.287.1", "1.0.0-ci.287.1"))
        self.assertEqual(window["descriptor"]["package"], "ArcForges.Contracts.CloudInternal")
        pinned = hashlib.sha256(PINNED_PATH.read_bytes()).hexdigest()
        self.assertEqual(pinned, window["descriptor"]["sha256"])
        self.assertEqual(pinned, "e6a295a5b14c45a158a58e5542ef9d3a34ba65281569018bcbf1dc962ddb4adc")
        self.assertEqual(PINNED_PATH.name, "cloud-internal-1.0.0-ci.287.1.binpb")

    def test_every_completion_prerequisite_is_pinned_and_independently_counted(self):
        self.assertEqual(set(LATER_SERVICES) | set(LATER_SCHEMAS), set(LATER_REQUIRED_TASKS))
        for task, services in LATER_SERVICES.items():
            with self.subTest(task=task):
                owned = {name: count for row in later_rows(task) for entry in row["files"]
                         for name, count in entry["services"].items()}
                self.assertEqual(owned, services)
                for name, count in services.items():
                    self.assertEqual(len(PINNED["services"]["." + name]), count)
        for task, paths in LATER_SCHEMAS.items():
            with self.subTest(task=task):
                self.assertEqual({row["path"] for row in LATER["schemas"] if row["task"] == task}, paths)
        self.assertEqual(sum(len(paths) for paths in LATER_SCHEMAS.values()), len(LATER["schemas"]))
        self.assertEqual(later_accounting_errors(LATER, PINNED), [])

    def test_accounting_rejects_unaccounted_files_and_wrong_counts(self):
        extra = deepcopy(PINNED)
        extra["files"]["arcforges/future/v1/future.proto"] = {"package": "arcforges.future.v1", "messages": {}, "enums": {}, "services": {}}
        self.assertIn("arcforges/future/v1/future.proto", later_accounting_errors(LATER, extra)[0])
        wrong = deepcopy(LATER)
        wrong["domains"][5]["files"][0]["messages"] += 1
        self.assertEqual(len(later_accounting_errors(wrong, PINNED)), 1)
        wrong = deepcopy(LATER)
        service = next(iter(wrong["domains"][5]["files"][0]["services"]))
        wrong["domains"][5]["files"][0]["services"][service] -= 1
        self.assertEqual(len(later_accounting_errors(wrong, PINNED)), 1)

    def test_pinned_candidate_passes_both_directions_and_the_exchange_covers_every_message(self):
        report = check_later_services(ROOT, PINNED_PATH)
        self.assertEqual((report["errorCount"], report["errors"]), (0, []))
        self.assertEqual([run["direction"] for run in report["exchange"]], [PREVIOUS_TO_CURRENT, CURRENT_TO_MINIMUM])
        self.assertEqual([run["messages"] for run in report["exchange"]], [len(PINNED["messages"])] * 2)
        self.assertEqual(len(PINNED["messages"]), 976)
        self.assertEqual(report["closedSchemas"], 11)

    def test_generated_current_descriptor_passes_when_it_was_generated(self):
        current = ROOT / LATER["descriptor"]["current"]
        if not current.is_file():
            self.skipTest("artifacts/operator.binpb is produced by eng/contracts.py generate; the window gate checks it in the build")
        self.assertEqual(check_later_services(ROOT)["errors"], [])

    def test_additive_growth_is_accepted_and_unknown_to_the_minimum_reader(self):
        target = Target("CON.07")
        current = deepcopy(PINNED)
        current["messages"][target.message][900] = deepcopy(NEW_FIELD)
        current["messages"][".arcforges.publicapi.v1.FutureAddition"] = {1: deepcopy(NEW_FIELD)}
        current["services"][target.service]["FutureMethod"] = {"input": target.message, "output": target.message,
                                                               "clientStreaming": 0, "serverStreaming": 0}
        current["enums"][target.enum]["FUTURE_VALUE"] = 777
        self.assertEqual(later_compare_errors(LATER, PINNED, PINNED, current), [])
        runs, errors = later_exchange_errors(PINNED, PINNED, current)
        self.assertEqual(errors, [])
        self.assertEqual(runs[1]["messages"], len(PINNED["messages"]))
        tree = synthesize(current, target.message)
        data = encode_message(current, target.message, tree)
        seen = decode_message(PINNED, target.message, data)
        self.assertNotIn(900, seen)
        self.assertIn(encode_field(current, NEW_FIELD, 900, tree[900]), seen[UNKNOWN])

    def test_every_domain_rejects_every_deliberate_break_in_both_directions(self):
        for task in LATER_SERVICES:
            target = Target(task)
            for label, (mutate, phrase) in MUTATIONS.items():
                with self.subTest(task=task, mutation=label):
                    current = deepcopy(PINNED)
                    mutate(current, target)
                    errors = later_compare_errors(LATER, PINNED, PINNED, current)
                    for direction in (PREVIOUS_TO_CURRENT, CURRENT_TO_MINIMUM):
                        self.assertTrue(any(direction in error and task in error and phrase in error for error in errors), errors[:3])

    def test_reference_codecs_reject_breaks_that_change_what_a_value_means(self):
        for task in LATER_SERVICES:
            target = Target(task)
            for label in EXCHANGE_REJECTED:
                with self.subTest(task=task, mutation=label):
                    current = deepcopy(PINNED)
                    MUTATIONS[label][0](current, target)
                    _, errors = later_exchange_errors(PINNED, PINNED, current, only={target.message})
                    self.assertTrue(errors)
                    self.assertTrue(any(PREVIOUS_TO_CURRENT in error for error in errors), errors)

    def test_a_type_change_is_also_seen_when_the_current_client_writes(self):
        target = Target("CON.10")
        current = deepcopy(PINNED)
        MUTATIONS["type change"][0](current, target)
        summary, errors = exchange(current, PINNED, CURRENT_TO_MINIMUM)
        self.assertGreaterEqual(len(errors), 1)
        self.assertTrue(any(target.message in error for error in errors))
        self.assertEqual(summary["errors"], len(errors))

    def test_reference_codec_matches_the_published_wire_examples(self):
        # Examples from the Protocol Buffers encoding guide plus exact integer boundaries.
        cases = [
            (5, 1, {1: 150}, "089601"), (9, 1, {1: "testing"}, "0a0774657374696e67"),
            (5, 1, {1: -1}, "08ffffffffffffffffff01"), (17, 1, {1: -1}, "0801"), (17, 1, {1: 1}, "0802"),
            (18, 1, {1: -2}, "0803"), (3, 1, {1: 9007199254740993}, "088180808080808010"),
            (7, 1, {1: 1}, "0d01000000"), (6, 1, {1: 1}, "090100000000000000"), (1, 1, {1: 1.0}, "09000000000000f03f"),
            (8, 1, {1: True}, "0801"), (12, 1, {1: b"\x00\xff"}, "0a0200ff"),
            (5, 3, {1: [3, 270, 86942]}, "0a06038e029ea705"),
        ]
        for kind, label, value, expected in cases:
            with self.subTest(kind=kind, value=value):
                model = one_field_model(kind, label)
                data = encode_message(model, ".fixture.M", value)
                self.assertEqual(data.hex(), expected)
                self.assertEqual(decode_message(model, ".fixture.M", data), value)
        model = one_field_model(5, 3)
        unpacked = bytes.fromhex("0803" "088e02" "089ea705")
        self.assertEqual(decode_message(model, ".fixture.M", unpacked), {1: [3, 270, 86942]})

    def test_reference_reader_refuses_malformed_and_mistyped_input(self):
        text = one_field_model(9)
        number = one_field_model(5)
        cases = [(text, bytes.fromhex("0801")), (number, bytes.fromhex("0a0161")), (text, bytes.fromhex("0a02ff")),
                 (text, bytes.fromhex("0a02c328")), (number, bytes.fromhex("08")), (number, bytes.fromhex("0980")),
                 (number, bytes.fromhex("0b")), (number, b"\x08" + b"\xff" * 10), (number, bytes.fromhex("00"))]
        for model, data in cases:
            with self.subTest(data=data.hex()):
                with self.assertRaises(ValueError):
                    decode_message(model, ".fixture.M", data)
        with self.assertRaisesRegex(ValueError, "unresolved message"):
            decode_message(number, ".fixture.Missing", b"")

    def test_unknown_members_survive_at_every_level_as_raw_bytes(self):
        reader = one_field_model(5)
        data = bytes.fromhex("0801") + bytes.fromhex("a0060a") + bytes.fromhex("aa0603666f6f")
        seen = decode_message(reader, ".fixture.M", data)
        self.assertEqual(seen, {1: 1, UNKNOWN: [bytes.fromhex("a0060a"), bytes.fromhex("aa0603666f6f")]})

    def test_synthesis_is_deterministic_bounded_and_populates_one_arm_per_oneof(self):
        for name in sorted(PINNED["messages"])[:80]:
            self.assertEqual(synthesize(PINNED, name), synthesize(PINNED, name))
        def real_arms(fields):
            return [field for field in fields.values() if field["oneof"] and not field["oneof"].startswith("_")]
        message = next(name for name, fields in PINNED["messages"].items() if len(real_arms(fields)) >= 2)
        tree = synthesize(PINNED, message)
        arms = {}
        for tag in tree:
            if tag != UNKNOWN and PINNED["messages"][message][tag]["oneof"]:
                arms.setdefault(PINNED["messages"][message][tag]["oneof"], []).append(tag)
        self.assertTrue(arms and all(len(tags) == 1 for tags in arms.values()), arms)
        self.assertEqual(tree[UNKNOWN], [INJECTED_UNKNOWN])

    def test_closed_schema_pins_match_and_reject_changes_but_not_formatting(self):
        self.assertEqual(later_schema_errors(ROOT, LATER), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for row in LATER["schemas"]:
                (root / row["path"]).parent.mkdir(parents=True, exist_ok=True)
                (root / row["path"]).write_bytes((ROOT / row["path"]).read_bytes())
            self.assertEqual(later_schema_errors(root, LATER), [])
            first = root / LATER["schemas"][0]["path"]
            original = first.read_text(encoding="utf-8")
            first.write_text(re.sub(r"(?m)^( +)", lambda found: found.group(1) * 2, original).replace("\n", "\r\n") + "\n  \n", encoding="utf-8", newline="")
            self.assertEqual(later_schema_errors(root, LATER), [])
            changes = {
                "added property": lambda text: text.replace('"$defs": {', '"$defs": {"AddedRoot": {"type": "object"}, ', 1),
                "changed bound": lambda text: re.sub(r'"maxLength": (\d+)', lambda found: '"maxLength": ' + str(int(found.group(1)) + 1), text, count=1),
                "changed version": lambda text: re.sub(r'"x-arcforges-schema-version": "1"', '"x-arcforges-schema-version": "2"', text, count=1),
                "duplicate property": lambda text: text.replace('"$defs": {', '"$defs": {}, "$defs": {', 1),
                "invalid document": lambda text: text + "{",
            }
            for label, change in changes.items():
                with self.subTest(change=label):
                    first.write_text(change(original), encoding="utf-8", newline="")
                    errors = later_schema_errors(root, LATER)
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn(LATER["schemas"][0]["path"], errors[0])
            first.unlink()
            self.assertEqual(len(later_schema_errors(root, LATER)), 1)

    def test_window_record_rejects_invalid_identity_dates_and_missing_prerequisites(self):
        def dropping(task):
            return lambda data: data.update(schemas=[row for row in data["schemas"] if row["task"] != task])
        cases = {
            "distinct minimum": lambda d: d.update(minimumVersion="1.0.0-ci.113.1"),
            "short window": lambda d: d.update(minimumReadSupportDays=89),
            "retirement too early": lambda d: d.update(earliestRetirement="2026-12-30"),
            "missing CON.15": dropping("CON.15"), "missing CON.16": dropping("CON.16"), "missing CON.12": dropping("CON.12"),
            "missing CON.14": lambda d: d.update(domains=[r for r in d["domains"] if "CON.14" not in r["tasks"]]),
            "CON.09 services unpinned": lambda d: d.update(domains=[r for r in d["domains"] if r["name"] != "Sync, resource and transfer operations"]),
            "bad task identifier": lambda d: d["domains"][0].update(tasks=["CON-09"]),
            "blank domain name": lambda d: d["domains"][0].update(name=" "),
            "duplicate file": lambda d: d["domains"][1]["files"].append(deepcopy(d["domains"][0]["files"][0])),
            "unknown key": lambda d: d.update(extra=1),
            "short commit": lambda d: d["candidate"].update(sourceCommit="ca45f36"),
            "foreign run": lambda d: d["candidate"].update(publication="https://github.com/ArcForges/Cloud/actions/runs/1"),
            "stable version": lambda d: d["candidate"].update(version="1.0.0"),
            "upper-case digest": lambda d: d["descriptor"].update(sha256=d["descriptor"]["sha256"].upper()),
            "traversal": lambda d: d["descriptor"].update(previousAndMinimum="../escape.binpb"),
            "duplicate schema": lambda d: d["schemas"].append(deepcopy(d["schemas"][0])),
            "bad archive digest": lambda d: d["candidate"]["retainedArchive"].update(sha256="abc"),
        }
        for label, mutate in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root, _ = self.window_in(directory, mutate)
                with self.assertRaises(ValueError):
                    later_window(root)
        with tempfile.TemporaryDirectory() as directory:
            self.window_in(directory)
            self.assertEqual(later_window(Path(directory))["candidate"]["version"], "1.0.0-ci.287.1")

    def test_tampered_pinned_descriptor_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root, data = self.window_in(directory)
            target = root / data["descriptor"]["previousAndMinimum"]
            target.write_bytes(PINNED_PATH.read_bytes() + b"\x00")
            with self.assertRaisesRegex(ValueError, "fixture changed"):
                check_later_services(root, PINNED_PATH)

    def test_generated_codec_exchange_round_trips_and_detects_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            exchange_directory = Path(directory)
            self.assertEqual(emit_later_exchange(ROOT, exchange_directory), len(PINNED["messages"]))
            names = (exchange_directory / "messages.txt").read_text(encoding="utf-8").split()
            self.assertEqual(len(names), 976)
            (exchange_directory / "current").mkdir()
            for name in names:
                (exchange_directory / "current" / (name + ".bin")).write_bytes((exchange_directory / "previous" / (name + ".bin")).read_bytes())
            report = verify_later_exchange(ROOT, exchange_directory)
            self.assertEqual((report["errorCount"], report["messages"], report["byteIdentical"]), (0, 976, 976))
            victim = exchange_directory / "current" / (names[10] + ".bin")
            original = victim.read_bytes()
            for label, data in {"emptied": b"", "unknown member dropped": original[:-len(INJECTED_UNKNOWN)],
                                "truncated": original + b"\xff", "wire type": b"\x0b"}.items():
                with self.subTest(change=label):
                    victim.write_bytes(data)
                    result = verify_later_exchange(ROOT, exchange_directory)
                    self.assertEqual(result["errorCount"], 1, result["errors"])
                    self.assertIn(names[10], result["errors"][0])
            victim.write_bytes(original)
            victim.unlink()
            self.assertEqual(verify_later_exchange(ROOT, exchange_directory)["errorCount"], 1)
            victim.write_bytes(original)
            (exchange_directory / "messages.txt").write_text("\n".join(names[1:]) + "\n", encoding="utf-8")
            self.assertIn("message list differs", verify_later_exchange(ROOT, exchange_directory)["errors"][0])

    def test_command_line_emits_and_verifies_the_exchange(self):
        script = str(ROOT / "eng/check_compatibility.py")
        with tempfile.TemporaryDirectory() as directory:
            emitted = subprocess.run([sys.executable, script, "--emit-later-exchange", directory], capture_output=True, text=True)
            self.assertEqual(emitted.returncode, 0, emitted.stderr)
            self.assertEqual(len(list((Path(directory) / "previous").glob("*.bin"))), 976)
            missing = subprocess.run([sys.executable, script, "--verify-later-exchange", directory], capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            shutil.copytree(Path(directory) / "previous", Path(directory) / "current")
            verified = subprocess.run([sys.executable, script, "--verify-later-exchange", directory], capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stdout[-400:])

    def test_the_window_gate_reports_later_service_errors_and_the_build_runs_the_exchange(self):
        failing = {"errors": ["later-services: injected"], "errorCount": 1}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = json.loads((ROOT / "eng/compatibility/window.json").read_text(encoding="utf-8"))
            (root / "eng/compatibility").mkdir(parents=True)
            (root / "artifacts").mkdir()
            (root / "eng/compatibility/window.json").write_text(json.dumps(window), encoding="utf-8")
            (root / "eng/foundation-inventory.json").write_text(json.dumps({"retirement": {}}), encoding="utf-8")
            for row in window["descriptors"]:
                data = (ROOT / row["previousAndMinimum"]).read_bytes()
                (root / row["previousAndMinimum"]).write_bytes(data)
                (root / row["current"]).write_bytes(data)
            import check_compatibility
            import check_foundation
            with mock.patch.object(check_foundation, "check", lambda _root: None), \
                    mock.patch.object(check_compatibility, "con08_frozen_errors", lambda _root, _current: []), \
                    mock.patch.object(check_compatibility, "check_later_services", lambda _root: failing):
                report = check_compatibility.check_window(root)
        self.assertEqual(report["errors"], failing["errors"])
        self.assertIs(report["laterServices"], failing)
        contracts = (ROOT / "eng/contracts.py").read_text(encoding="utf-8")
        self.assertIn("compatibility_exchange(structure_tests)\n    later_services_exchange(structure_tests)", contracts)
        self.assertIn('"--compatibility-later-services"', contracts)
        self.assertIn('args[1] == "--compatibility-later-services"', (ROOT / "tests/StructureTests/Program.cs").read_text(encoding="utf-8"))

    def test_generated_codec_leg_lists_exactly_the_pinned_files(self):
        source = (ROOT / "tests/StructureTests/LaterServiceCases.cs").read_text(encoding="utf-8")
        listed = re.findall(r"\.(\w+Reflection)\.Descriptor", source)
        expected = ["".join(part.capitalize() for part in re.split("[-_]", Path(name).stem)) + "Reflection"
                    for name in PINNED["files"]]
        self.assertEqual(sorted(listed), sorted(expected))
        self.assertEqual(len(set(listed)), len(listed))


if __name__ == "__main__":
    unittest.main()
