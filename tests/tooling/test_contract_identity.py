# SPDX-License-Identifier: Apache-2.0
"""Offline package-specific contract identity and independent declaration checks."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eng"))
import build_identity
import package_catalog

ROOT = Path(__file__).resolve().parents[2]


class ContractIdentityTests(unittest.TestCase):
    def axes(self, name, root=ROOT, descriptor=b"independent-descriptor-fixture"):
        return build_identity.axes({"name": name, "version": "1.0.0-ci.1.1"}, [], descriptor, root)

    def test_every_package_reports_its_actual_schema_closure(self):
        for row in package_catalog.packages():
            value = self.axes(row["id"])
            expected = {path for package in package_catalog.closure(row["id"])
                        for path in package["proto"] + package["jsonSchemas"]}
            actual = {item["source"]["path"] for item in value["ContractSet"].get("values", [])}
            self.assertEqual(actual, expected, row["id"])
            self.assertEqual(value["ContractSet"]["status"], "present" if expected else "not-applicable")
            self.assertEqual(set(value), set(build_identity.AXES))
            has_extension = "public/proto/arcforges/extensions/v1/extensions.proto" in expected
            self.assertEqual(value["ExtensionProtocolVersion"]["status"], "present" if has_extension else "not-applicable")

    def test_maven_sbom_coordinate_normalization(self):
        self.assertEqual(self.axes("io.github.arcforges/contracts-proto"), self.axes("io.github.arcforges:contracts-proto"))

    def test_http_only_package_uses_own_schema_version_without_fake_descriptor(self):
        axes = self.axes("@arcforges/ai-internal", descriptor=b"")
        values = axes["ContractSet"]["values"]
        self.assertEqual([(v["subject"], v["version"]) for v in values], [("json:CommitReceipt", "1")])
        self.assertNotIn("descriptorSha256", values[0])

    def test_schema_mutation_does_not_change_unrelated_package_or_other_axes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for path in ["eng/version-sources.json", "eng/contract-packages.json"]:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, root / path)
            for base in ["public/proto", "internal/proto", "public/http", "internal/ai-http"]:
                shutil.copytree(ROOT / base, root / base)
            before = self.axes("ArcForges.Contracts.PublicApi", root)
            unrelated = self.axes("ArcForges.Contracts.LocalRpc.Sandbox", root)
            schema = root / "public/http/v1/schema.json"
            data = json.loads(schema.read_text(encoding="utf-8"))
            data["x-arcforges-schema-version"] = "2"
            schema.write_text(json.dumps(data), encoding="utf-8")
            after = self.axes("ArcForges.Contracts.PublicApi", root)
            self.assertEqual([axis for axis in build_identity.AXES if before[axis] != after[axis]], ["ContractSet"])
            self.assertEqual(unrelated, self.axes("ArcForges.Contracts.LocalRpc.Sandbox", root))
            del data["x-arcforges-schema-version"]
            schema.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "own declared schema version"):
                self.axes("ArcForges.Contracts.PublicApi", root)

    def test_extension_axis_is_authored_protocol_not_release_alias(self):
        before = self.axes("ArcForges.Sdk.Contracts")
        after = build_identity.axes({"name": "ArcForges.Sdk.Contracts", "version": "9.9.9"}, [], b"independent-descriptor-fixture")
        self.assertEqual(before, after)
        self.assertEqual(before["ExtensionProtocolVersion"]["values"][0]["subject"], "arcforges.extensions")
        self.assertEqual(before["ExtensionProtocolVersion"]["values"][0]["version"], "1")
        with self.assertRaisesRegex(ValueError, "Unregistered contract package"):
            self.axes("ArcForges.Contracts.Unknown")


if __name__ == "__main__":
    unittest.main()
