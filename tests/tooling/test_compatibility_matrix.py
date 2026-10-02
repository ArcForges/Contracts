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
                                 oneof_arms, pin_key, pin_samples, retained, sample_ids, synthesize,
                                 synthesize_sample, verify_later_exchange)
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
PINS = {pin_key(pin): pin for pin in LATER["pins"]}
MODELS = {key: descriptor((ROOT / pin["previousAndMinimum"]).read_bytes()) for key, pin in PINS.items()}
LATEST_VERSION = "1.0.0-ci.287.1"
LATEST_KEY = "cloud-internal-" + LATEST_VERSION
LATEST = MODELS[LATEST_KEY]
LATEST_PATH = ROOT / PINS[LATEST_KEY]["previousAndMinimum"]
# The newest CloudInternal pin is the whole public closure, so it stands in for the current descriptor of
# PublicApi and CloudInternal; each local pin stands in for itself (it equals the current descriptor today).
STAND_IN = {"artifacts/public-api.binpb": LATEST_PATH, "artifacts/operator.binpb": LATEST_PATH,
            **{pin["current"]: ROOT / pin["previousAndMinimum"] for pin in LATER["pins"]
               if pin["package"].startswith("ArcForges.Contracts.LocalRpc.")}}
DESCRIPTOR_PACKAGES = ("ArcForges.Contracts.PublicApi", "ArcForges.Contracts.CloudInternal")
PUBLISHED_ON = {"168": "2026-09-27", "201": "2026-09-27", "224": "2026-09-28", "244": "2026-09-28", "250": "2026-09-29",
                "258": "2026-09-29", "270": "2026-10-01", "279": "2026-10-01", "284": "2026-10-01", "287": "2026-10-02"}


def stand_in(pin):
    return descriptor(Path(STAND_IN[pin["current"]]).read_bytes())


def introducing(task):
    return next(pin for pin in LATER["pins"] if task in pin["introduces"])
PUBLIC = "arcforges.publicapi.v1."
# Independent expectations taken from the reviewed ledger records and the GitHub run and artifact metadata of each
# published candidate, not from the window.
CANDIDATES = {
    "1.0.0-ci.168.1": ("7eeaa3b407ca1d99f1320ecf9d1fb752c9c9ba21", 36345239115, 10941045051,
                       "d339c85d371fa260c684a35d849970c94cf28e92d780030a6a53ac94aa32d984"),
    "1.0.0-ci.201.1": ("665f0e887dbb1fca61dd3cda1b27d1d8f6c56e71", 36355148074, 10943607531,
                       "df43e8ff32fea11f1473009c3c67396b20e397d7b9c2fd5f623b86f7db824b3d"),
    "1.0.0-ci.224.1": ("dfbb0217198cf1d6ae71484dd30193a699b525eb", 36361959334, 10945234331,
                       "f3f6cb62f94cb13b6e7663babd970dc7c90c084fe7c002b6296ac1114f3086d1"),
    "1.0.0-ci.244.1": ("063762f32c551449fb01936d9ec30fedb77260de", 36461962570, 10987453891,
                       "9742fd78c5685aa294b13fcb015fbf8523f4eabbb5424282496f208c108e393f"),
    "1.0.0-ci.250.1": ("bf42fef5e4fd28792004c8a16623465784e2bfb7", 36523643235, 11013652456,
                       "7a2d3960bb39e56f5b9dea374d540343025f6f7151aa836a3b3038dcd5993206"),
    "1.0.0-ci.258.1": ("67f1f08e35b7f46bc4292aba3f0f7be4a5044875", 36612589134, 11054248041,
                       "ba4e472d73807af0b1c41cd1b8b7af63c988f03e72886e9f648197116202d129"),
    "1.0.0-ci.270.1": ("4047930ef2207e8a4c6de9e7ef679f0d9359a8e4", 36809684358, 11139622574,
                       "b5b8613ef30c47503acd9bb345fb5425735305da7babd88e1868b48c2bd67bbd"),
    "1.0.0-ci.279.1": ("e816db7da9a3de120511ba2058309f0c7bfac96d", 36914480340, 11188639785,
                       "275b92a8ad7212748614008fca6381af53b64e5786361a430324cfbfbe59f4e2"),
    "1.0.0-ci.284.1": ("bcd592a75c0b540923a77a499a8f82e18bbff743", 36922469148, 11192683906,
                       "d6f3c30a4da3af73490c053ea526e9bc68056910275e16b797272e8cf5d72c51"),
    "1.0.0-ci.287.1": ("ca45f36cccbdd31380f76b8f6cdecc958fdcb430", 36966686225, 11210775779,
                       "96fdd28556d0e753f54c4b7245398382a029bcbd58684a49954f339eaa71d425"),
}
INTRODUCED = {"CON.13": "1.0.0-ci.224.1", "CON.08": "1.0.0-ci.244.1", "CON.09": "1.0.0-ci.250.1", "CON.10": "1.0.0-ci.258.1",
              "CON.11": "1.0.0-ci.270.1", "CON.14": "1.0.0-ci.284.1", "CON.07": "1.0.0-ci.287.1"}
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
    "CON.07": ({"public/http/v1/browser.schema.json", "public/http/v1/native-auth.schema.json"}, "1.0.0-ci.287.1"),
    "CON.10": ({"internal/ai-http/v1/schema.json"}, "1.0.0-ci.258.1"),
    "CON.12": ({"public/http/v1/manifest.schema.json", "public/http/v1/workflow.schema.json",
                "public/http/v1/panel.schema.json", "public/http/v1/policy-body.schema.json",
                "internal/ai-http/v1/configuration.schema.json"}, "1.0.0-ci.201.1"),
    "CON.15": ({"internal/cf-http/v1/schema.json", "internal/storage-http/v1/schema.json"}, "1.0.0-ci.279.1"),
    "CON.16": ({"public/http/v1/signed-formats.schema.json"}, "1.0.0-ci.168.1"),
    "CON.92": ({"public/http/v1/schema.json", "public/http/v1/inventory.schema.json"}, "1.0.0-ci.168.1"),
}
# Changing the declared type changes the meaning of the written sample value on the wire.
MEANING_CHANGES = {3: 18, 4: 3, 5: 17, 9: 12, 12: 9, 13: 17}
NEW_FIELD = {"name": "future", "type": 9, "typeName": "", "label": 1, "oneof": None, "optional": 0, "jsonName": "future"}


def owned_files(task):
    return {filename for owner in LATER["owners"] if task in owner["tasks"] for filename in owner["files"]}


class Target:
    """One published message, field, service, method and enum of a domain, found in the pin that introduced it."""

    def __init__(self, task):
        self.task, self.pin = task, introducing(task)
        self.model = MODELS[pin_key(self.pin)]
        files = [self.model["files"][name] for name in sorted(owned_files(task)) if name in self.model["files"]]
        for name in sorted(name for content in files for name in content["messages"]):
            tags = [tag for tag, field in sorted(self.model["messages"][name].items()) if field["type"] in MEANING_CHANGES]
            if tags:
                self.message, self.tag = name, tags[0]
                break
        else:
            raise AssertionError("No mutable message in " + task)
        self.service = next(name for content in files for name in sorted(content["services"]))
        self.method = sorted(self.model["services"][self.service])[0]
        self.enum = next(name for content in files for name in sorted(content["enums"]))
        self.member = sorted(self.model["enums"][self.enum])[0]


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
    "streaming change": (lambda m, t: m["services"][t.service][t.method].update(serverStreaming=1 - m["services"][t.service][t.method]["serverStreaming"]),
                         "changed member or reused tag"),
}
# Mutations that change what a written value means or lose it; the reference codecs must reject these too.
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

    def test_window_record_binds_every_published_candidate_and_pinned_descriptor(self):
        window = later_window(ROOT)
        self.assertEqual(set(window["candidates"]), set(CANDIDATES))
        for version, (commit, run, artifact, digest) in CANDIDATES.items():
            self.assertEqual(window["candidates"][version], {
                "publishedOn": PUBLISHED_ON[version.split(".")[3]], "sourceCommit": commit, "publication": f"https://github.com/ArcForges/Contracts/actions/runs/{run}",
                "retainedArchive": {"artifactId": artifact, "name": f"contracts-candidate-{run}-1", "sha256": digest}})
        self.assertEqual((window["minimumVersion"], window["previousVersion"]), ("1.0.0-ci.168.1", LATEST_VERSION))
        self.assertEqual([pin["candidate"] for pin in window["pins"]],
                         sorted(INTRODUCED.values(), key=lambda v: int(v.split(".")[3])) + [LATEST_VERSION] * 3)
        stems = {"ArcForges.Contracts.PublicApi": "public-api-", "ArcForges.Contracts.CloudInternal": "cloud-internal-",
                 "ArcForges.Contracts.LocalRpc.Chat": "local-chat-", "ArcForges.Contracts.LocalRpc.Scope": "local-scope-",
                 "ArcForges.Contracts.LocalRpc.Sandbox": "local-sandbox-"}
        for pin in window["pins"]:
            data = (ROOT / pin["previousAndMinimum"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin["sha256"])
            self.assertEqual(Path(pin["previousAndMinimum"]).name, stems[pin["package"]] + pin["candidate"] + ".binpb")
        self.assertEqual(PINS[LATEST_KEY]["sha256"], "e6a295a5b14c45a158a58e5542ef9d3a34ba65281569018bcbf1dc962ddb4adc")
        # The read window opens when the newest pinned candidate was published and runs the 90-day minimum.
        self.assertEqual((window["openedOn"], window["earliestRetirement"]), ("2026-10-02", "2026-12-31"))

    def test_every_protobuf_prerequisite_is_introduced_by_one_pin_with_independent_counts(self):
        self.assertEqual({task: pin["candidate"] for pin in LATER["pins"] for task in pin["introduces"]}, INTRODUCED)
        for task, services in LATER_SERVICES.items():
            with self.subTest(task=task):
                for key in (pin_key(introducing(task)), LATEST_KEY):
                    counted = {name: count for entry in PINS[key]["files"]
                               if entry["file"] in owned_files(task) for name, count in entry["services"].items()}
                    self.assertEqual(counted, services)
                    for name, count in services.items():
                        self.assertEqual(len(MODELS[key]["services"]["." + name]), count)
                for key, pin in PINS.items():
                    if pin["package"] in DESCRIPTOR_PACKAGES and int(pin["candidate"].split(".")[3]) < int(INTRODUCED[task].split(".")[3]):
                        self.assertFalse(set("." + name for name in services) & set(MODELS[key]["services"]))

    def test_closed_schemas_are_pinned_with_their_first_publication(self):
        for task, (paths, first) in LATER_SCHEMAS.items():
            with self.subTest(task=task):
                rows = [row for row in LATER["schemas"] if row["task"] == task]
                self.assertEqual({row["path"] for row in rows}, paths)
                self.assertEqual({row["identicalSince"] for row in rows}, {first})
        self.assertEqual(sum(len(paths) for paths, _ in LATER_SCHEMAS.values()), len(LATER["schemas"]))

    def test_accounting_rejects_unaccounted_files_and_wrong_counts(self):
        pin = PINS[LATEST_KEY]
        self.assertEqual(later_accounting_errors(pin, LATEST), [])
        extra = deepcopy(LATEST)
        extra["files"]["arcforges/future/v1/future.proto"] = {"package": "arcforges.future.v1", "messages": {}, "enums": {}, "services": {}}
        self.assertIn("arcforges/future/v1/future.proto", later_accounting_errors(pin, extra)[0])
        wrong = deepcopy(pin)
        wrong["files"][5]["messages"] += 1
        self.assertEqual(len(later_accounting_errors(wrong, LATEST)), 1)
        wrong = deepcopy(pin)
        service = next(entry for entry in wrong["files"] if entry["services"])
        service["services"][next(iter(service["services"]))] -= 1
        self.assertEqual(len(later_accounting_errors(wrong, LATEST)), 1)
        wrong = deepcopy(pin)
        next(entry for entry in wrong["files"] if entry["enums"])["enums"] += 1
        self.assertEqual(len(later_accounting_errors(wrong, LATEST)), 1)

    def test_every_pin_passes_and_the_exchange_covers_every_pinned_message_and_oneof_arm(self):
        report = check_later_services(ROOT, STAND_IN)
        self.assertEqual((report["errorCount"], report["errors"]), (0, []))
        self.assertEqual(len(report["pins"]), 10)
        self.assertEqual(len(report["exchange"]), 20)
        for run in report["exchange"]:
            model = MODELS[run["pin"]]
            self.assertEqual(run["messages"], len(model["messages"]), run)
            self.assertGreaterEqual(run["samples"], run["messages"])
        self.assertEqual(len(LATEST["messages"]), 976)
        self.assertEqual(report["closedSchemas"], 13)

    def test_the_only_real_additive_member_is_written_by_the_current_client_and_retained_by_old_readers(self):
        arm = LATEST["messages"][".arcforges.publicapi.v1.AggregateBody"][17]
        self.assertEqual(arm["name"], "scope_project_metadata")
        report = check_later_services(ROOT, STAND_IN)
        name = ".arcforges.publicapi.v1.AggregateBody"
        lacking = [key for key, model in MODELS.items() if name in model["messages"] and 17 not in model["messages"][name]]
        self.assertIn("public-api-1.0.0-ci.224.1", lacking)
        self.assertNotIn(LATEST_KEY, lacking)
        for key in lacking:
            previous, current = [run for run in report["exchange"] if run["pin"] == key]
            self.assertEqual(current["samples"], previous["samples"] + 1, key)
            tree = next(sample for sample in (synthesize_sample(LATEST, sid) for sid in sample_ids(LATEST, name)) if 17 in sample)
            seen = decode_message(MODELS[key], name, encode_message(LATEST, name, tree))
            self.assertNotIn(17, seen)
            self.assertIn(encode_field(LATEST, arm, 17, tree[17]), seen[UNKNOWN])

    def test_every_declared_field_is_written_by_some_sample(self):
        for key, model in MODELS.items():
            with self.subTest(pin=key):
                uncovered = []
                for name, declared_fields in model["messages"].items():
                    written = set()
                    for sample in sample_ids(model, name):
                        written |= {tag for tag in synthesize_sample(model, sample) if tag != UNKNOWN}
                    uncovered.extend((name, tag) for tag in declared_fields if tag not in written)
                # Only a member of a message that contains itself (recursion bound) may stay unwritten.
                self.assertEqual([item for item in uncovered if model["messages"][item[0]][item[1]]["typeName"] != item[0]
                                  or model["messages"][item[0]][item[1]]["type"] != 11], [], uncovered[:5])
        self.assertEqual(sample_ids(LATEST, ".arcforges.publicapi.v1.AggregateBody")[0], ".arcforges.publicapi.v1.AggregateBody")
        for name in list(LATEST["messages"])[:200]:
            extra = sum(len(tags) - 1 for tags in oneof_arms(LATEST["messages"][name]).values())
            self.assertEqual(len(sample_ids(LATEST, name)), 1 + extra)

    def test_published_history_is_additive_growth_not_identity(self):
        for key, model in MODELS.items():
            with self.subTest(pin=key):
                pin = PINS[key]
                current = stand_in(pin)
                self.assertEqual(later_compare_errors(LATER, pin, model, current), [])
                _, errors = later_exchange_errors(pin, model, current)
                self.assertEqual(errors, [])
                if pin["package"] in DESCRIPTOR_PACKAGES and pin["candidate"] != LATEST_VERSION:
                    self.assertTrue(set(current["messages"]) - set(model["messages"]))
                    self.assertTrue(set(current["services"]) - set(model["services"]))
        sizes = [len(MODELS[pin_key(pin)]["messages"]) for pin in LATER["pins"] if pin["package"] == "ArcForges.Contracts.PublicApi"]
        self.assertEqual(sizes, sorted(sizes))
        self.assertEqual(len(set(sizes)), len(sizes))

    def test_generated_current_descriptors_pass_when_they_were_generated(self):
        missing = [pin["current"] for pin in LATER["pins"] if not (ROOT / pin["current"]).is_file()]
        if missing:
            self.skipTest("artifacts are produced by eng/contracts.py generate; the window gate checks them in the build")
        self.assertEqual(check_later_services(ROOT)["errors"], [])

    def test_additive_growth_is_accepted_and_unknown_to_every_pinned_reader(self):
        target = Target("CON.07")
        current = deepcopy(LATEST)
        current["messages"][target.message][900] = deepcopy(NEW_FIELD)
        current["messages"][".arcforges.publicapi.v1.FutureAddition"] = {1: deepcopy(NEW_FIELD)}
        current["services"][target.service]["FutureMethod"] = {"input": target.message, "output": target.message,
                                                               "clientStreaming": 0, "serverStreaming": 0}
        current["enums"][target.enum]["FUTURE_VALUE"] = 777
        for key, pin in PINS.items():
            if pin["package"] not in DESCRIPTOR_PACKAGES:
                continue
            model = MODELS[key]
            with self.subTest(pin=key):
                self.assertEqual(later_compare_errors(LATER, pin, model, current), [])
                runs, errors = later_exchange_errors(pin, model, current)
                self.assertEqual(errors, [])
                self.assertEqual(runs[1]["messages"], len(model["messages"]))
        tree = synthesize(current, target.message)
        data = encode_message(current, target.message, tree)
        seen = decode_message(LATEST, target.message, data)
        self.assertNotIn(900, seen)
        self.assertIn(encode_field(current, NEW_FIELD, 900, tree[900]), seen[UNKNOWN])

    def test_every_domain_rejects_every_deliberate_break_in_both_directions(self):
        for task in LATER_SERVICES:
            target = Target(task)
            for label, (mutate, phrase) in MUTATIONS.items():
                with self.subTest(task=task, mutation=label):
                    current = deepcopy(LATEST)
                    mutate(current, target)
                    errors = later_compare_errors(LATER, target.pin, target.model, current)
                    self.assertTrue(any(target.pin["candidate"] in error and task in error and phrase in error
                                        for error in errors), errors[:3])
                    # A pin published before the contract existed has nothing to protect and raises nothing.
                    for pin in LATER["pins"]:
                        model = MODELS[pin_key(pin)]
                        if pin["package"] in DESCRIPTOR_PACKAGES and not (target.service in model["services"] or target.message in model["messages"] or target.enum in model["enums"]):
                            self.assertEqual(later_compare_errors(LATER, pin, model, current), [], pin["candidate"])

    def test_reference_codecs_reject_breaks_that_change_what_a_value_means(self):
        for task in LATER_SERVICES:
            target = Target(task)
            for label in EXCHANGE_REJECTED:
                with self.subTest(task=task, mutation=label):
                    current = deepcopy(LATEST)
                    MUTATIONS[label][0](current, target)
                    _, errors = later_exchange_errors(target.pin, target.model, current, only={target.message})
                    self.assertTrue(errors)
                    self.assertTrue(any(PREVIOUS_TO_CURRENT in error for error in errors), errors)

    def test_a_type_change_is_also_seen_when_the_current_client_writes(self):
        target = Target("CON.10")
        current = deepcopy(LATEST)
        MUTATIONS["type change"][0](current, target)
        summary, errors = exchange(current, target.model, CURRENT_TO_MINIMUM)
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

    def test_unknown_members_survive_as_raw_bytes(self):
        reader = one_field_model(5)
        data = bytes.fromhex("0801") + bytes.fromhex("a0060a") + bytes.fromhex("aa0603666f6f")
        seen = decode_message(reader, ".fixture.M", data)
        self.assertEqual(seen, {1: 1, UNKNOWN: [bytes.fromhex("a0060a"), bytes.fromhex("aa0603666f6f")]})

    def test_synthesis_is_deterministic_bounded_and_populates_one_arm_per_oneof(self):
        for name in sorted(LATEST["messages"])[:80]:
            self.assertEqual(synthesize(LATEST, name), synthesize(LATEST, name))

        def real_arms(fields):
            return [field for field in fields.values() if field["oneof"] and not field["oneof"].startswith("_")]
        message = next(name for name, fields in LATEST["messages"].items() if len(real_arms(fields)) >= 2)
        tree = synthesize(LATEST, message)
        arms = {}
        for tag in tree:
            if tag != UNKNOWN and LATEST["messages"][message][tag]["oneof"]:
                arms.setdefault(LATEST["messages"][message][tag]["oneof"], []).append(tag)
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

    def test_window_record_rejects_invalid_identity_order_introductions_and_ownership(self):
        def dropping(task):
            return lambda data: data.update(schemas=[row for row in data["schemas"] if row["task"] != task])

        def reintroduce(data):
            data["pins"][2]["introduces"] = ["CON.09", "CON.13"]

        cases = {
            "newest candidate not previous": lambda d: d.update(previousVersion="1.0.0-ci.284.1"),
            "oldest candidate not minimum": lambda d: d.update(minimumVersion="1.0.0-ci.224.1"),
            "short window": lambda d: d.update(minimumReadSupportDays=89),
            "retirement too early": lambda d: d.update(earliestRetirement="2026-12-30"),
            "window opened before the newest candidate": lambda d: d.update(openedOn="2026-09-27"),
            "unparseable publication date": lambda d: d["candidates"][LATEST_VERSION].update(publishedOn="2026-13-01"),
            "a protobuf pin removed": lambda d: d["pins"].pop(5),
            "all pins of a candidate removed": lambda d: d.update(pins=[p for p in d["pins"] if p["candidate"] != "1.0.0-ci.250.1"]),
            "pin of an unrecorded candidate": lambda d: d["pins"][0].update(candidate="1.0.0-ci.1.1"),
            "pins out of order": lambda d: d["pins"].reverse(),
            "missing CON.14": lambda d: d["pins"][5].update(introduces=["CON.99"]),
            "CON.13 introduced twice": reintroduce,
            "CON.08 not first with services": lambda d: d["pins"][2].update(introduces=["CON.09", "CON.08"]),
            "task without services": lambda d: d["pins"][0].update(introduces=["CON.13", "CON.12"]),
            "missing CON.12 schemas": dropping("CON.12"), "missing CON.15 schemas": dropping("CON.15"),
            "missing CON.16 schemas": dropping("CON.16"),
            "unknown key": lambda d: d.update(extra=1),
            "short commit": lambda d: d["candidates"][LATEST_VERSION].update(sourceCommit="ca45f36"),
            "foreign run": lambda d: d["candidates"][LATEST_VERSION].update(publication="https://github.com/ArcForges/Cloud/actions/runs/1"),
            "malformed version": lambda d: d["candidates"].update({"1.0.0": d["candidates"][LATEST_VERSION]}),
            "upper-case pin digest": lambda d: d["pins"][0].update(sha256=d["pins"][0]["sha256"].upper()),
            "traversal": lambda d: d["pins"][0].update(previousAndMinimum="../escape.binpb"),
            "bad archive digest": lambda d: d["candidates"][LATEST_VERSION]["retainedArchive"].update(sha256="abc"),
            "duplicate schema": lambda d: d["schemas"].append(deepcopy(d["schemas"][0])),
            "schema of an unrecorded candidate": lambda d: d["schemas"][0].update(identicalSince="1.0.0-ci.1.1"),
            "file without owner": lambda d: d["pins"][0]["files"].append({"file": "arcforges/none/v1/none.proto", "services": {}, "messages": 0, "enums": 0}),
            "file owned twice": lambda d: d["owners"][1]["files"].append(d["owners"][0]["files"][0]),
            "file accounted twice": lambda d: d["pins"][0]["files"].append(deepcopy(d["pins"][0]["files"][0])),
            "bad task identifier": lambda d: d["owners"][0].update(tasks=["CON-09"]),
            "blank owner name": lambda d: d["owners"][0].update(name=" "),
            "no pins": lambda d: d.update(pins=[]),
        }
        for label, mutate in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                root, _ = self.window_in(directory, mutate)
                with self.assertRaises(ValueError):
                    later_window(root)
        with tempfile.TemporaryDirectory() as directory:
            self.window_in(directory)
            self.assertEqual(later_window(Path(directory))["previousVersion"], LATEST_VERSION)

    def test_tampered_pinned_descriptor_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root, data = self.window_in(directory)
            target = root / data["pins"][0]["previousAndMinimum"]
            target.write_bytes((ROOT / data["pins"][0]["previousAndMinimum"]).read_bytes() + b"\x00")
            with self.assertRaisesRegex(ValueError, "fixture changed"):
                check_later_services(root, STAND_IN)

    def test_generated_codec_exchange_round_trips_and_detects_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            exchange_directory = Path(directory)
            total = sum(len(pin_samples(model)) for model in MODELS.values())
            self.assertEqual(emit_later_exchange(ROOT, exchange_directory), total)
            for key, model in MODELS.items():
                names = (exchange_directory / key / "messages.txt").read_text(encoding="utf-8").split()
                self.assertEqual(names, pin_samples(model))
                (exchange_directory / key / "current").mkdir()
                for name in names:
                    (exchange_directory / key / "current" / (name + ".bin")).write_bytes(
                        (exchange_directory / key / "previous" / (name + ".bin")).read_bytes())
            report = verify_later_exchange(ROOT, exchange_directory)
            self.assertEqual((report["errorCount"], report["samples"], report["byteIdentical"]), (0, total, total))
            self.assertEqual([entry["samples"] for entry in report["pins"]], [len(pin_samples(MODELS[pin_key(pin)])) for pin in LATER["pins"]])
            key = LATEST_KEY
            names = (exchange_directory / key / "messages.txt").read_text(encoding="utf-8").split()
            self.assertTrue(any("@" in name for name in names))
            victim = exchange_directory / key / "current" / (names[10] + ".bin")
            original = victim.read_bytes()
            for label, data in {"emptied": b"", "unknown member dropped": original[:-len(INJECTED_UNKNOWN)],
                                "truncated": original + b"\xff", "wire type": b"\x0b"}.items():
                with self.subTest(change=label):
                    victim.write_bytes(data)
                    result = verify_later_exchange(ROOT, exchange_directory)
                    self.assertEqual(result["errorCount"], 1, result["errors"])
                    self.assertIn(names[10], result["errors"][0])
                    self.assertIn(key, result["errors"][0])
            victim.write_bytes(original)
            # An extra oneof-arm sample is checked like any other.
            arm = next(name for name in names if "@" in name)
            (exchange_directory / key / "current" / (arm + ".bin")).write_bytes(b"")
            self.assertEqual(verify_later_exchange(ROOT, exchange_directory)["errorCount"], 1)
            (exchange_directory / key / "current" / (arm + ".bin")).write_bytes((exchange_directory / key / "previous" / (arm + ".bin")).read_bytes())
            victim.unlink()
            self.assertEqual(verify_later_exchange(ROOT, exchange_directory)["errorCount"], 1)
            victim.write_bytes(original)
            (exchange_directory / key / "messages.txt").write_text("\n".join(names[1:]) + "\n", encoding="utf-8")
            self.assertIn("sample list differs", verify_later_exchange(ROOT, exchange_directory)["errors"][0])
            shutil.rmtree(exchange_directory / "public-api-1.0.0-ci.224.1")
            self.assertTrue(any("public-api-1.0.0-ci.224.1" in error for error in verify_later_exchange(ROOT, exchange_directory)["errors"]))

    def test_command_line_emits_and_verifies_the_exchange(self):
        script = str(ROOT / "eng/check_compatibility.py")
        with tempfile.TemporaryDirectory() as directory:
            emitted = subprocess.run([sys.executable, script, "--emit-later-exchange", directory], capture_output=True, text=True)
            self.assertEqual(emitted.returncode, 0, emitted.stderr)
            self.assertEqual(len(list((Path(directory) / LATEST_KEY / "previous").glob("*.bin"))), len(pin_samples(LATEST)))
            missing = subprocess.run([sys.executable, script, "--verify-later-exchange", directory], capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            for key in MODELS:
                shutil.copytree(Path(directory) / key / "previous", Path(directory) / key / "current")
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

    def test_each_pin_current_descriptor_is_its_package_descriptor_in_the_catalog(self):
        from package_catalog import closure
        packages = json.loads((ROOT / "eng/contract-packages.json").read_text(encoding="utf-8"))["packages"]
        for pin in LATER["pins"]:
            with self.subTest(candidate=pin["candidate"]):
                row = next(package for package in packages if package["id"] == pin["package"])
                self.assertEqual(pin["current"], "artifacts/" + row["descriptor"])
                current = {source.split("/proto/", 1)[1] for owner in closure(row["id"]) for source in owner["proto"]}
                self.assertEqual({entry["file"] for entry in pin["files"]} - current, set(),
                                 "every pinned file must remain in the package closure")

    def test_generated_codec_leg_lists_exactly_the_files_of_all_pins(self):
        source = (ROOT / "tests/StructureTests/LaterServiceCases.cs").read_text(encoding="utf-8")
        qualified = re.findall(r"([\w.]+)\.(\w+Reflection)\.Descriptor", source)
        listed = [name for _, name in qualified]

        def reflection(name):
            return "".join(part.capitalize() for part in re.split("[-_]", Path(name).stem)) + "Reflection"
        pinned = {name for model in MODELS.values() for name in model["files"]}
        self.assertEqual(sorted(listed), sorted(reflection(name) for name in pinned))
        self.assertEqual(len(set(qualified)), len(qualified))
        self.assertEqual(len(listed), 25)
