# SPDX-License-Identifier: Apache-2.0
"""Constraint source layout preserves rules and fails closed on conflicting input."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eng"))
import contracts


class ConstraintShards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(contracts, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        for visibility in ("public", "internal"):
            self.shard(visibility, "base", {"owner.v1.Base": {"fields": {}}})

    def shard(self, visibility, name, messages):
        path = self.root / visibility / "proto/constraints" / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schemaVersion": "proto-constraints.v1", "license": "Apache-2.0",
                                    "messages": messages}), encoding="utf-8")
        return path

    def test_committed_layout_preserves_both_snapshot_bytes(self):
        with patch.object(contracts, "ROOT", ROOT):
            paths = [ROOT / side / "proto/constraints.json" for side in ("public", "internal")]
            before = [path.read_bytes() for path in paths]
            contracts.merge_constraint_shards(check=True)
            contracts.merge_constraint_shards()
            self.assertEqual(before, [path.read_bytes() for path in paths])

    def test_new_shard_merges_and_stale_check_does_not_write(self):
        contracts.merge_constraint_shards()
        target = self.root / "public/proto/constraints.json"
        old = target.read_bytes()
        self.shard("public", "additional", {"owner.v1.New": {"fields": {"id": {"required": True}}}})
        with self.assertRaisesRegex(ValueError, "Stale merged"):
            contracts.merge_constraint_shards(check=True)
        self.assertEqual(old, target.read_bytes())
        contracts.merge_constraint_shards()
        self.assertEqual(["owner.v1.New", "owner.v1.Base"], list(json.loads(target.read_text())["messages"]))
        contracts.merge_constraint_shards(check=True)

    def test_duplicate_message_rejected(self):
        self.shard("public", "conflict", {"owner.v1.Base": {"fields": {}}})
        with self.assertRaisesRegex(ValueError, "Duplicate constraint message"):
            contracts.merge_constraint_shards()

    def test_duplicate_nested_field_key_rejected(self):
        path = self.shard("public", "bad", {})
        path.write_text('{"schemaVersion":"proto-constraints.v1","license":"Apache-2.0",'
                        '"messages":{"owner.v1.Bad":{"fields":{"id":{},"id":{}}}}}')
        with self.assertRaisesRegex(ValueError, "Duplicate constraint JSON key"):
            contracts.merge_constraint_shards()

    def test_bad_envelopes_rejected(self):
        path = self.shard("public", "bad", {})
        valid = json.loads(path.read_text())
        for key, value in (("license", "other"), ("schemaVersion", "v2"), ("messages", []), ("unknown", True)):
            with self.subTest(key=key):
                path.write_text(json.dumps({**valid, key: value}))
                with self.assertRaisesRegex(ValueError, "Invalid constraint shard envelope"):
                    contracts.merge_constraint_shards()

    def test_invalid_message_rejected(self):
        for name, value in (("unqualified", {}), ("owner.v1.Bad", [])):
            with self.subTest(name=name):
                self.shard("public", "bad", {name: value})
                with self.assertRaisesRegex(ValueError, "Invalid constraint message"):
                    contracts.merge_constraint_shards()

    def test_missing_shards_rejected(self):
        (self.root / "public/proto/constraints/base.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing constraint shards"):
            contracts.merge_constraint_shards()


if __name__ == "__main__":
    unittest.main()
