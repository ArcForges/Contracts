# SPDX-License-Identifier: Apache-2.0
"""Deliberate compiled-descriptor breaks must fail before publication."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
from check_compatibility import compare, descriptor, fields


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


if __name__ == "__main__":
    unittest.main()
